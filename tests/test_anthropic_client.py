"""
Tests for Anthropic Claude API Client

Run with: pytest tests/test_anthropic_client.py -v
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from src.anthropic_client import (
    ClaudeClient,
    ClaudeResponse,
    TokenUsage,
    CostTracker,
    RateLimiter,
    COST_PER_MILLION_INPUT,
    COST_PER_MILLION_OUTPUT,
)


class TestTokenUsage:
    """Test TokenUsage dataclass."""
    
    def test_total_tokens(self):
        """Test total token calculation."""
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        assert usage.total_tokens == 150
    
    def test_cost_calculation(self):
        """Test cost calculation."""
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=100_000)
        expected_cost = COST_PER_MILLION_INPUT + (100_000 / 1_000_000) * COST_PER_MILLION_OUTPUT
        assert abs(usage.cost - expected_cost) < 0.001


class TestCostTracker:
    """Test CostTracker class."""
    
    def test_add_usage(self):
        """Test adding usage to tracker."""
        tracker = CostTracker()
        tracker.add(TokenUsage(input_tokens=100, output_tokens=50))
        tracker.add(TokenUsage(input_tokens=200, output_tokens=100))
        
        assert tracker.total_calls == 2
        assert tracker.total_input_tokens == 300
        assert tracker.total_output_tokens == 150
    
    def test_summary(self):
        """Test summary generation."""
        tracker = CostTracker()
        tracker.add(TokenUsage(input_tokens=1000, output_tokens=500))
        
        summary = tracker.summary()
        assert summary["total_calls"] == 1
        assert summary["total_tokens"] == 1500
        assert "total_cost_usd" in summary


class TestClaudeResponse:
    """Test ClaudeResponse JSON extraction."""
    
    def test_extract_json_direct(self):
        """Test extracting direct JSON."""
        response = ClaudeResponse(
            content='{"key": "value", "number": 42}',
            usage=TokenUsage(100, 50),
            model="test",
            stop_reason="end_turn",
            latency_ms=100.0,
        )
        result = response.extract_json()
        assert result == {"key": "value", "number": 42}
    
    def test_extract_json_code_block(self):
        """Test extracting JSON from code block."""
        response = ClaudeResponse(
            content='Here is the result:\n```json\n{"key": "value"}\n```',
            usage=TokenUsage(100, 50),
            model="test",
            stop_reason="end_turn",
            latency_ms=100.0,
        )
        result = response.extract_json()
        assert result == {"key": "value"}
    
    def test_extract_json_embedded(self):
        """Test extracting embedded JSON."""
        response = ClaudeResponse(
            content='The analysis shows: {"score": 85, "valid": true} as the result.',
            usage=TokenUsage(100, 50),
            model="test",
            stop_reason="end_turn",
            latency_ms=100.0,
        )
        result = response.extract_json()
        assert result == {"score": 85, "valid": True}
    
    def test_extract_json_array(self):
        """Test extracting JSON array."""
        response = ClaudeResponse(
            content='Results: [{"id": 1}, {"id": 2}]',
            usage=TokenUsage(100, 50),
            model="test",
            stop_reason="end_turn",
            latency_ms=100.0,
        )
        result = response.extract_json()
        assert result == [{"id": 1}, {"id": 2}]
    
    def test_extract_json_fails_gracefully(self):
        """Test that invalid JSON returns None."""
        response = ClaudeResponse(
            content='This is not JSON at all.',
            usage=TokenUsage(100, 50),
            model="test",
            stop_reason="end_turn",
            latency_ms=100.0,
        )
        result = response.extract_json()
        assert result is None
    
    def test_extract_json_strict_raises(self):
        """Test that strict extraction raises on failure."""
        response = ClaudeResponse(
            content='Not JSON',
            usage=TokenUsage(100, 50),
            model="test",
            stop_reason="end_turn",
            latency_ms=100.0,
        )
        with pytest.raises(ValueError):
            response.extract_json_strict()


class TestRateLimiter:
    """Test RateLimiter class."""
    
    @pytest.mark.asyncio
    async def test_acquire_under_limit(self):
        """Test acquiring when under limit."""
        limiter = RateLimiter(rpm=10, tpm=10000)
        # Should not block
        await limiter.acquire(100)
        assert len(limiter._request_times) == 1
    
    def test_record_usage(self):
        """Test recording token usage."""
        limiter = RateLimiter()
        limiter.record_usage(500)
        assert len(limiter._token_usage) == 1


class TestClaudeClient:
    """Test ClaudeClient class."""
    
    def test_init_without_key_raises(self):
        """Test that missing API key raises error."""
        with patch.dict("os.environ", {}, clear=True):
            # Remove ANTHROPIC_API_KEY if present
            import os
            if "ANTHROPIC_API_KEY" in os.environ:
                del os.environ["ANTHROPIC_API_KEY"]
            
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not found"):
                ClaudeClient(api_key=None)
    
    def test_init_with_key(self):
        """Test initialization with API key."""
        client = ClaudeClient(api_key="test-key-123")
        assert client.model == "claude-sonnet-4-20250514"
        assert client.max_retries == 5
    
    @pytest.mark.asyncio
    async def test_complete_success(self):
        """Test successful completion."""
        client = ClaudeClient(api_key="test-key")
        
        # Mock the anthropic client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Test response")]
        mock_response.usage = MagicMock(input_tokens=50, output_tokens=25)
        mock_response.model = "claude-sonnet-4-20250514"
        mock_response.stop_reason = "end_turn"
        
        client.client.messages.create = AsyncMock(return_value=mock_response)
        
        response = await client.complete("Test prompt")
        
        assert response.content == "Test response"
        assert response.usage.input_tokens == 50
        assert response.usage.output_tokens == 25
        assert client.cost_tracker.total_calls == 1
    
    def test_calculate_backoff(self):
        """Test exponential backoff calculation."""
        client = ClaudeClient(api_key="test-key")
        
        # First attempt should be around BASE_DELAY
        delay0 = client._calculate_backoff(0)
        assert 0.5 <= delay0 <= 2.0  # 1.0 ± 25% jitter + margin
        
        # Later attempts should increase
        delay3 = client._calculate_backoff(3)
        assert delay3 > delay0
    
    def test_cost_summary(self):
        """Test cost summary retrieval."""
        client = ClaudeClient(api_key="test-key")
        client.cost_tracker.add(TokenUsage(1000, 500))
        
        summary = client.get_cost_summary()
        assert summary["total_calls"] == 1
        assert summary["total_tokens"] == 1500
    
    def test_reset_cost_tracker(self):
        """Test cost tracker reset."""
        client = ClaudeClient(api_key="test-key")
        client.cost_tracker.add(TokenUsage(1000, 500))
        client.reset_cost_tracker()
        
        assert client.cost_tracker.total_calls == 0


# Integration test (requires actual API key)
@pytest.mark.skip(reason="Requires actual ANTHROPIC_API_KEY")
class TestClaudeClientIntegration:
    """Integration tests requiring actual API access."""
    
    @pytest.mark.asyncio
    async def test_real_completion(self):
        """Test real API call."""
        client = ClaudeClient()
        response = await client.complete(
            "What is 2+2? Reply with just the number.",
            max_tokens=10,
        )
        assert "4" in response.content
    
    @pytest.mark.asyncio
    async def test_real_json_completion(self):
        """Test real API call with JSON."""
        client = ClaudeClient()
        response = await client.complete_json(
            "Return a JSON object with keys 'a' set to 1 and 'b' set to 2."
        )
        data = response.extract_json_strict()
        assert data["a"] == 1
        assert data["b"] == 2
