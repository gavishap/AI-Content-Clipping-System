"""
Anthropic Claude API Client - V3 Pipeline Infrastructure

Owner: Gabriel
Status: Implemented
Version: 1.0

This module provides a robust Claude API wrapper with:
- Async support for all operations
- Retry logic with exponential backoff
- Structured JSON output extraction
- Token counting and cost tracking
- Rate limiting support

Used by all V3 modules requiring text analysis:
- guest_classifier.py
- conversation_mapper.py
- contextual_clip_finder.py
- transcript_cue_detector.py
"""

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TypeVar, Callable
from functools import wraps

import anthropic
from anthropic import APIError, RateLimitError, APIConnectionError

logger = logging.getLogger(__name__)

# Cost per million tokens (as of Jan 2026)
# Claude Sonnet 4.5 pricing
COST_PER_MILLION_INPUT = 3.00  # $3 per 1M input tokens
COST_PER_MILLION_OUTPUT = 15.00  # $15 per 1M output tokens

# Default model
DEFAULT_MODEL = "claude-sonnet-4-20250514"

# Rate limiting defaults
DEFAULT_RPM = 50  # Requests per minute
DEFAULT_TPM = 40000  # Tokens per minute

# Retry configuration
MAX_RETRIES = 5
BASE_DELAY = 1.0  # Base delay in seconds
MAX_DELAY = 60.0  # Maximum delay between retries


@dataclass
class TokenUsage:
    """Tracks token usage for a single API call."""
    input_tokens: int
    output_tokens: int
    
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens
    
    @property
    def cost(self) -> float:
        """Calculate cost in USD."""
        input_cost = (self.input_tokens / 1_000_000) * COST_PER_MILLION_INPUT
        output_cost = (self.output_tokens / 1_000_000) * COST_PER_MILLION_OUTPUT
        return input_cost + output_cost


@dataclass
class ClaudeResponse:
    """Response from Claude API with metadata."""
    content: str
    usage: TokenUsage
    model: str
    stop_reason: str
    latency_ms: float
    
    def extract_json(self) -> Optional[Dict[str, Any]]:
        """
        Extract JSON from response content.
        
        Handles various formats:
        - Pure JSON
        - JSON in code blocks (```json ... ```)
        - JSON embedded in text
        
        Returns:
            Parsed JSON dict or None if extraction fails
        """
        content = self.content.strip()
        
        # Try 1: Direct JSON parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        # Try 2: Extract from code block
        json_block_pattern = r'```(?:json)?\s*\n?([\s\S]*?)\n?```'
        matches = re.findall(json_block_pattern, content)
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue
        
        # Try 3: Find JSON object/array in text
        # Look for outermost { } or [ ]
        for pattern in [r'\{[\s\S]*\}', r'\[[\s\S]*\]']:
            matches = re.findall(pattern, content)
            for match in matches:
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    continue
        
        logger.warning("Failed to extract JSON from response")
        return None
    
    def extract_json_strict(self) -> Dict[str, Any]:
        """
        Extract JSON, raising error if not found.
        
        Returns:
            Parsed JSON dict
            
        Raises:
            ValueError: If JSON cannot be extracted
        """
        result = self.extract_json()
        if result is None:
            raise ValueError(f"Could not extract JSON from response: {self.content[:200]}...")
        return result


@dataclass
class CostTracker:
    """Tracks cumulative API costs across multiple calls."""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_calls: int = 0
    calls: List[TokenUsage] = field(default_factory=list)
    
    def add(self, usage: TokenUsage) -> None:
        """Record a new API call."""
        self.total_input_tokens += usage.input_tokens
        self.total_output_tokens += usage.output_tokens
        self.total_calls += 1
        self.calls.append(usage)
    
    @property
    def total_cost(self) -> float:
        """Total cost in USD."""
        input_cost = (self.total_input_tokens / 1_000_000) * COST_PER_MILLION_INPUT
        output_cost = (self.total_output_tokens / 1_000_000) * COST_PER_MILLION_OUTPUT
        return input_cost + output_cost
    
    def summary(self) -> Dict[str, Any]:
        """Get cost summary."""
        return {
            "total_calls": self.total_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "total_cost_usd": round(self.total_cost, 4),
        }


class RateLimiter:
    """
    Token bucket rate limiter for API calls.
    
    Implements both requests-per-minute and tokens-per-minute limits.
    """
    
    def __init__(self, rpm: int = DEFAULT_RPM, tpm: int = DEFAULT_TPM):
        """
        Initialize rate limiter.
        
        Args:
            rpm: Maximum requests per minute
            tpm: Maximum tokens per minute
        """
        self.rpm = rpm
        self.tpm = tpm
        self._request_times: List[float] = []
        self._token_usage: List[tuple[float, int]] = []  # (timestamp, tokens)
        self._lock = asyncio.Lock()
    
    async def acquire(self, estimated_tokens: int = 1000) -> None:
        """
        Wait until we can make another request.
        
        Args:
            estimated_tokens: Estimated tokens for this request
        """
        async with self._lock:
            now = time.time()
            window_start = now - 60.0  # 1 minute window
            
            # Clean old entries
            self._request_times = [t for t in self._request_times if t > window_start]
            self._token_usage = [(t, tokens) for t, tokens in self._token_usage if t > window_start]
            
            # Check request limit
            while len(self._request_times) >= self.rpm:
                wait_time = self._request_times[0] - window_start + 0.1
                logger.debug(f"Rate limit: waiting {wait_time:.1f}s for RPM")
                await asyncio.sleep(wait_time)
                now = time.time()
                window_start = now - 60.0
                self._request_times = [t for t in self._request_times if t > window_start]
            
            # Check token limit
            current_tokens = sum(tokens for _, tokens in self._token_usage)
            while current_tokens + estimated_tokens > self.tpm:
                wait_time = self._token_usage[0][0] - window_start + 0.1
                logger.debug(f"Rate limit: waiting {wait_time:.1f}s for TPM")
                await asyncio.sleep(wait_time)
                now = time.time()
                window_start = now - 60.0
                self._token_usage = [(t, tokens) for t, tokens in self._token_usage if t > window_start]
                current_tokens = sum(tokens for _, tokens in self._token_usage)
            
            # Record this request
            self._request_times.append(now)
    
    def record_usage(self, tokens: int) -> None:
        """Record actual token usage after request completes."""
        self._token_usage.append((time.time(), tokens))


class ClaudeClient:
    """
    Claude API client with retry logic, rate limiting, and cost tracking.
    
    Usage:
        client = ClaudeClient()
        response = await client.complete("Analyze this text...")
        
        # For JSON responses
        response = await client.complete_json("Return JSON with fields x, y, z...")
        data = response.extract_json_strict()
        
        # Check costs
        print(client.cost_tracker.summary())
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        rpm: int = DEFAULT_RPM,
        tpm: int = DEFAULT_TPM,
        max_retries: int = MAX_RETRIES,
    ):
        """
        Initialize Claude client.
        
        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            model: Claude model to use
            rpm: Requests per minute limit
            tpm: Tokens per minute limit
            max_retries: Maximum retry attempts
        """
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError(
                "ANTHROPIC_API_KEY not found. "
                "Set it in .env file or pass api_key parameter."
            )
        
        self.client = anthropic.AsyncAnthropic(api_key=key)
        self.model = model
        self.max_retries = max_retries
        self.rate_limiter = RateLimiter(rpm=rpm, tpm=tpm)
        self.cost_tracker = CostTracker()
        
        logger.info(f"ClaudeClient initialized (model: {model}, rpm: {rpm}, tpm: {tpm})")
    
    async def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        stop_sequences: Optional[List[str]] = None,
    ) -> ClaudeResponse:
        """
        Send a completion request to Claude.
        
        Args:
            prompt: User message/prompt
            system: Optional system prompt
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0 = deterministic)
            stop_sequences: Optional stop sequences
            
        Returns:
            ClaudeResponse with content and metadata
            
        Raises:
            RuntimeError: If all retries fail
        """
        # Estimate tokens for rate limiting (rough: 4 chars per token)
        estimated_tokens = (len(prompt) + len(system or "")) // 4 + max_tokens
        
        messages = [{"role": "user", "content": prompt}]
        
        for attempt in range(self.max_retries):
            try:
                # Wait for rate limiter
                await self.rate_limiter.acquire(estimated_tokens)
                
                # Make request
                start_time = time.time()
                
                kwargs: Dict[str, Any] = {
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "messages": messages,
                    "temperature": temperature,
                }
                
                if system:
                    kwargs["system"] = system
                if stop_sequences:
                    kwargs["stop_sequences"] = stop_sequences
                
                response = await self.client.messages.create(**kwargs)
                
                latency_ms = (time.time() - start_time) * 1000
                
                # Extract content
                content = ""
                if response.content:
                    content = response.content[0].text if hasattr(response.content[0], "text") else str(response.content[0])
                
                # Track usage
                usage = TokenUsage(
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                )
                self.cost_tracker.add(usage)
                self.rate_limiter.record_usage(usage.total_tokens)
                
                logger.debug(
                    f"Claude response: {usage.total_tokens} tokens, "
                    f"${usage.cost:.4f}, {latency_ms:.0f}ms"
                )
                
                return ClaudeResponse(
                    content=content,
                    usage=usage,
                    model=response.model,
                    stop_reason=response.stop_reason or "unknown",
                    latency_ms=latency_ms,
                )
                
            except RateLimitError as e:
                delay = self._calculate_backoff(attempt)
                logger.warning(f"Rate limited (attempt {attempt + 1}/{self.max_retries}), waiting {delay:.1f}s")
                await asyncio.sleep(delay)
                
            except APIConnectionError as e:
                delay = self._calculate_backoff(attempt)
                logger.warning(f"Connection error (attempt {attempt + 1}/{self.max_retries}): {e}")
                await asyncio.sleep(delay)
                
            except APIError as e:
                if e.status_code and e.status_code >= 500:
                    # Server error, retry
                    delay = self._calculate_backoff(attempt)
                    logger.warning(f"Server error {e.status_code} (attempt {attempt + 1}/{self.max_retries})")
                    await asyncio.sleep(delay)
                else:
                    # Client error, don't retry
                    logger.error(f"API error: {e}")
                    raise RuntimeError(f"Claude API error: {e}") from e
        
        raise RuntimeError(f"All {self.max_retries} retries failed")
    
    async def complete_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> ClaudeResponse:
        """
        Send a completion request expecting JSON response.
        
        Adds JSON formatting instructions to system prompt.
        
        Args:
            prompt: User message/prompt
            system: Optional system prompt (JSON instruction will be appended)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            
        Returns:
            ClaudeResponse (use extract_json() or extract_json_strict())
        """
        json_instruction = (
            "\n\nIMPORTANT: Respond with valid JSON only. "
            "Do not include any text before or after the JSON. "
            "Do not use markdown code blocks."
        )
        
        full_system = (system or "") + json_instruction
        
        return await self.complete(
            prompt=prompt,
            system=full_system.strip(),
            max_tokens=max_tokens,
            temperature=temperature,
        )
    
    async def complete_with_schema(
        self,
        prompt: str,
        schema: Dict[str, Any],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Send request with expected JSON schema, returning parsed result.
        
        Args:
            prompt: User message/prompt
            schema: Expected JSON schema (for documentation in prompt)
            system: Optional system prompt
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            
        Returns:
            Parsed JSON dict
            
        Raises:
            ValueError: If response doesn't match expected format
        """
        schema_instruction = f"\n\nRespond with JSON matching this schema:\n{json.dumps(schema, indent=2)}"
        full_prompt = prompt + schema_instruction
        
        response = await self.complete_json(
            prompt=full_prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        
        return response.extract_json_strict()
    
    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay with jitter."""
        import random
        delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
        # Add jitter (±25%)
        jitter = delay * 0.25 * (random.random() * 2 - 1)
        return delay + jitter
    
    def get_cost_summary(self) -> Dict[str, Any]:
        """Get cost tracking summary."""
        return self.cost_tracker.summary()
    
    def reset_cost_tracker(self) -> None:
        """Reset the cost tracker (e.g., for a new video)."""
        self.cost_tracker = CostTracker()
        logger.info("Cost tracker reset")


# Synchronous wrapper for convenience
class ClaudeClientSync:
    """
    Synchronous wrapper around ClaudeClient for non-async contexts.
    
    Usage:
        client = ClaudeClientSync()
        response = client.complete("Analyze this text...")
    """
    
    def __init__(self, **kwargs):
        """Initialize with same arguments as ClaudeClient."""
        self._async_client = ClaudeClient(**kwargs)
    
    def complete(self, prompt: str, **kwargs) -> ClaudeResponse:
        """Synchronous completion."""
        return asyncio.run(self._async_client.complete(prompt, **kwargs))
    
    def complete_json(self, prompt: str, **kwargs) -> ClaudeResponse:
        """Synchronous JSON completion."""
        return asyncio.run(self._async_client.complete_json(prompt, **kwargs))
    
    def complete_with_schema(self, prompt: str, schema: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Synchronous schema-guided completion."""
        return asyncio.run(self._async_client.complete_with_schema(prompt, schema, **kwargs))
    
    def get_cost_summary(self) -> Dict[str, Any]:
        """Get cost tracking summary."""
        return self._async_client.get_cost_summary()
    
    def reset_cost_tracker(self) -> None:
        """Reset the cost tracker."""
        self._async_client.reset_cost_tracker()


# Utility function for one-off calls
async def quick_complete(
    prompt: str,
    system: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.0,
) -> str:
    """
    Quick one-off completion without managing a client.
    
    Args:
        prompt: User message
        system: Optional system prompt
        model: Model to use
        temperature: Sampling temperature
        
    Returns:
        Response content string
    """
    client = ClaudeClient(model=model)
    response = await client.complete(prompt, system=system, temperature=temperature)
    return response.content
