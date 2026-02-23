"""
LLM Engineering Utilities - V3 Pipeline Infrastructure

Owner: Gabriel
Status: Implemented
Version: 1.0

This module implements advanced LLM engineering patterns for maximum accuracy:
- Self-Consistency: Run N times with temperature variation, majority vote
- Two-Pass Verification: Different prompts must agree
- Multi-Agent Debate: Advocate vs Skeptic + Judge pattern
- Ensemble Ranking: Borda count combination of multiple methods
- Uncertainty Quantification: Explicit uncertainty estimates
- Confidence Calibration: Calibrate raw confidence scores

These patterns are used throughout V3 pipeline:
- Visual change detection (CoT + self-consistency)
- Guest classification (multi-agent debate)
- Clip detection (ensemble ranking + multi-persona)
"""

import asyncio
import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TypeVar, Generic, Union
from enum import Enum

from src.anthropic_client import ClaudeClient, ClaudeResponse

logger = logging.getLogger(__name__)

T = TypeVar('T')


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ConsistencyResult(Generic[T]):
    """Result from self-consistency voting."""
    winner: T
    agreement_ratio: float  # 0-1, percentage of runs that agreed
    all_results: List[T]
    confidence: float  # Calibrated confidence based on agreement
    
    @property
    def is_confident(self) -> bool:
        """Check if result meets confidence threshold."""
        return self.agreement_ratio >= 0.67  # 2/3 majority


@dataclass
class VerificationResult:
    """Result from two-pass verification."""
    verified: bool
    pass1_result: Any
    pass2_result: Any
    agreement: bool
    confidence: float
    details: Dict[str, Any] = field(default_factory=dict)


class DebateVerdict(Enum):
    """Possible verdicts from a debate."""
    AFFIRM = "affirm"  # Advocate wins
    DENY = "deny"  # Skeptic wins
    UNCERTAIN = "uncertain"  # Judge cannot decide


@dataclass
class DebateArgument:
    """An argument from one side of the debate."""
    position: str  # "advocate" or "skeptic"
    claim: str
    evidence: List[str]
    confidence: float
    weaknesses: List[str] = field(default_factory=list)


@dataclass
class DebateResult:
    """Result from multi-agent debate."""
    verdict: DebateVerdict
    advocate_argument: DebateArgument
    skeptic_argument: DebateArgument
    judge_reasoning: str
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RankedItem(Generic[T]):
    """An item with ranking information."""
    item: T
    final_rank: int
    borda_score: float
    method_ranks: Dict[str, int]  # method_name -> rank
    confidence: float


@dataclass
class EnsembleResult(Generic[T]):
    """Result from ensemble ranking."""
    rankings: List[RankedItem[T]]
    method_weights: Dict[str, float]
    agreement_score: float  # How much methods agreed
    
    @property
    def top_items(self) -> List[T]:
        """Get items in ranked order."""
        return [r.item for r in sorted(self.rankings, key=lambda x: x.final_rank)]


# =============================================================================
# Self-Consistency Runner
# =============================================================================

class SelfConsistencyRunner:
    """
    Run a prompt multiple times and take majority vote.
    
    Useful for reducing random errors in classification tasks.
    
    Usage:
        runner = SelfConsistencyRunner(client, n_runs=3)
        result = await runner.run(
            prompt="Is this a new guest?",
            parse_fn=lambda r: r.extract_json()["is_new_guest"]
        )
        if result.is_confident:
            print(f"Answer: {result.winner} (agreement: {result.agreement_ratio:.0%})")
    """
    
    def __init__(
        self,
        client: ClaudeClient,
        n_runs: int = 3,
        temperatures: Optional[List[float]] = None,
    ):
        """
        Initialize self-consistency runner.
        
        Args:
            client: ClaudeClient instance
            n_runs: Number of runs to perform
            temperatures: Temperature for each run (default: [0.0, 0.3, 0.7])
        """
        self.client = client
        self.n_runs = n_runs
        self.temperatures = temperatures or [0.0, 0.3, 0.7][:n_runs]
        
        # Extend temperatures if n_runs > len(temperatures)
        while len(self.temperatures) < n_runs:
            self.temperatures.append(self.temperatures[-1])
    
    async def run(
        self,
        prompt: str,
        parse_fn: Callable[[ClaudeResponse], T],
        system: Optional[str] = None,
        max_tokens: int = 4096,
    ) -> ConsistencyResult[T]:
        """
        Run prompt N times and return majority vote.
        
        Args:
            prompt: The prompt to run
            parse_fn: Function to extract answer from response
            system: Optional system prompt
            max_tokens: Max tokens per response
            
        Returns:
            ConsistencyResult with winner and agreement stats
        """
        results: List[T] = []
        
        # Run all prompts concurrently
        tasks = []
        for i, temp in enumerate(self.temperatures[:self.n_runs]):
            task = self._run_single(prompt, system, max_tokens, temp, parse_fn)
            tasks.append(task)
        
        completed = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in completed:
            if isinstance(result, Exception):
                logger.warning(f"Self-consistency run failed: {result}")
            else:
                results.append(result)
        
        if not results:
            raise RuntimeError("All self-consistency runs failed")
        
        # Find majority
        counter = Counter(str(r) for r in results)  # Stringify for counting
        winner_str, winner_count = counter.most_common(1)[0]
        
        # Find the actual result object (not stringified)
        winner = next(r for r in results if str(r) == winner_str)
        
        agreement_ratio = winner_count / len(results)
        
        # Calibrate confidence based on agreement
        confidence = self._calibrate_confidence(agreement_ratio, len(results))
        
        logger.debug(
            f"Self-consistency: {winner_count}/{len(results)} agree "
            f"(confidence: {confidence:.2f})"
        )
        
        return ConsistencyResult(
            winner=winner,
            agreement_ratio=agreement_ratio,
            all_results=results,
            confidence=confidence,
        )
    
    async def _run_single(
        self,
        prompt: str,
        system: Optional[str],
        max_tokens: int,
        temperature: float,
        parse_fn: Callable[[ClaudeResponse], T],
    ) -> T:
        """Run a single completion and parse result."""
        response = await self.client.complete(
            prompt=prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return parse_fn(response)
    
    def _calibrate_confidence(self, agreement_ratio: float, n_samples: int) -> float:
        """
        Calibrate confidence based on agreement and sample size.
        
        Higher agreement + more samples = higher confidence.
        """
        # Base confidence from agreement
        base_confidence = agreement_ratio
        
        # Bonus for more samples
        sample_bonus = min(0.1, (n_samples - 2) * 0.02)  # Up to 10% bonus
        
        # Penalty for low agreement
        if agreement_ratio < 0.5:
            penalty = (0.5 - agreement_ratio) * 0.5
            base_confidence -= penalty
        
        return min(1.0, max(0.0, base_confidence + sample_bonus))


# =============================================================================
# Two-Pass Verifier
# =============================================================================

class TwoPassVerifier:
    """
    Verify results using two different prompts/perspectives.
    
    Usage:
        verifier = TwoPassVerifier(client)
        result = await verifier.verify(
            pass1_prompt="Analyze A to determine if X",
            pass2_prompt="Analyze B to check if X",
            compare_fn=lambda a, b: a["answer"] == b["answer"]
        )
    """
    
    def __init__(self, client: ClaudeClient):
        """Initialize with ClaudeClient."""
        self.client = client
    
    async def verify(
        self,
        pass1_prompt: str,
        pass2_prompt: str,
        compare_fn: Callable[[Any, Any], bool],
        pass1_system: Optional[str] = None,
        pass2_system: Optional[str] = None,
        parse_fn: Optional[Callable[[ClaudeResponse], Any]] = None,
    ) -> VerificationResult:
        """
        Run two passes and verify agreement.
        
        Args:
            pass1_prompt: First pass prompt
            pass2_prompt: Second pass prompt
            compare_fn: Function to compare results (returns True if agree)
            pass1_system: System prompt for pass 1
            pass2_system: System prompt for pass 2
            parse_fn: Function to parse response (default: extract_json)
            
        Returns:
            VerificationResult with agreement status
        """
        parse = parse_fn or (lambda r: r.extract_json())
        
        # Run both passes concurrently
        task1 = self.client.complete_json(pass1_prompt, system=pass1_system)
        task2 = self.client.complete_json(pass2_prompt, system=pass2_system)
        
        response1, response2 = await asyncio.gather(task1, task2)
        
        result1 = parse(response1)
        result2 = parse(response2)
        
        agreement = compare_fn(result1, result2)
        
        # Confidence based on agreement
        confidence = 0.9 if agreement else 0.4
        
        logger.debug(f"Two-pass verification: {'AGREE' if agreement else 'DISAGREE'}")
        
        return VerificationResult(
            verified=agreement,
            pass1_result=result1,
            pass2_result=result2,
            agreement=agreement,
            confidence=confidence,
        )
    
    async def verify_forward_backward(
        self,
        item_a: str,
        item_b: str,
        question: str,
        system: Optional[str] = None,
    ) -> VerificationResult:
        """
        Verify by asking question in both directions.
        
        Example: "Is person A different from person B?" vs
                 "Is person B different from person A?"
        
        Args:
            item_a: First item description
            item_b: Second item description
            question: Question template (use {a} and {b} as placeholders)
            system: System prompt
            
        Returns:
            VerificationResult
        """
        forward_prompt = f"Given:\nA: {item_a}\nB: {item_b}\n\n{question.format(a='A', b='B')}"
        backward_prompt = f"Given:\nA: {item_b}\nB: {item_a}\n\n{question.format(a='A', b='B')}"
        
        def compare(r1: Dict, r2: Dict) -> bool:
            # Results should be the same regardless of order
            return r1.get("answer") == r2.get("answer")
        
        return await self.verify(
            pass1_prompt=forward_prompt,
            pass2_prompt=backward_prompt,
            compare_fn=compare,
            pass1_system=system,
            pass2_system=system,
        )


# =============================================================================
# Multi-Agent Debate
# =============================================================================

class MultiAgentDebate:
    """
    Implement advocate vs skeptic debate pattern.
    
    Three agents:
    1. Advocate: Argues FOR the proposition
    2. Skeptic: Argues AGAINST the proposition
    3. Judge: Evaluates arguments and decides
    
    Usage:
        debate = MultiAgentDebate(client)
        result = await debate.run(
            proposition="This is a new guest joining the stream",
            evidence={"visual": "New face detected", "audio": "New voice"}
        )
        if result.verdict == DebateVerdict.AFFIRM:
            print("Confirmed: New guest detected")
    """
    
    ADVOCATE_SYSTEM = """You are the Advocate in a debate. Your role is to argue FOR the proposition.
Present the strongest possible case that the proposition is TRUE.
Be thorough but objective - acknowledge weaknesses in your position.
Respond with JSON: {"claim": "main argument", "evidence": ["point1", "point2"], "confidence": 0.0-1.0, "weaknesses": ["weakness1"]}"""

    SKEPTIC_SYSTEM = """You are the Skeptic in a debate. Your role is to argue AGAINST the proposition.
Present the strongest possible case that the proposition is FALSE.
Be thorough but objective - acknowledge strengths of the opposing view.
Respond with JSON: {"claim": "main argument", "evidence": ["point1", "point2"], "confidence": 0.0-1.0, "weaknesses": ["weakness1"]}"""

    JUDGE_SYSTEM = """You are the Judge in a debate. Your role is to evaluate both arguments objectively.
Consider the evidence quality, logical coherence, and acknowledged weaknesses.
Respond with JSON: {"verdict": "affirm" or "deny" or "uncertain", "reasoning": "explanation", "confidence": 0.0-1.0}"""
    
    def __init__(self, client: ClaudeClient):
        """Initialize with ClaudeClient."""
        self.client = client
    
    async def run(
        self,
        proposition: str,
        evidence: Dict[str, Any],
        context: Optional[str] = None,
    ) -> DebateResult:
        """
        Run a full debate on a proposition.
        
        Args:
            proposition: The claim to debate
            evidence: Available evidence for both sides
            context: Additional context
            
        Returns:
            DebateResult with verdict and arguments
        """
        evidence_str = json.dumps(evidence, indent=2)
        
        base_prompt = f"""Proposition: {proposition}

Available Evidence:
{evidence_str}
"""
        if context:
            base_prompt += f"\nContext: {context}"
        
        # Get advocate argument
        advocate_response = await self.client.complete_json(
            prompt=base_prompt + "\n\nPresent your argument FOR this proposition.",
            system=self.ADVOCATE_SYSTEM,
        )
        advocate_data = advocate_response.extract_json() or {}
        
        advocate_arg = DebateArgument(
            position="advocate",
            claim=advocate_data.get("claim", ""),
            evidence=advocate_data.get("evidence", []),
            confidence=float(advocate_data.get("confidence", 0.5)),
            weaknesses=advocate_data.get("weaknesses", []),
        )
        
        # Get skeptic argument
        skeptic_response = await self.client.complete_json(
            prompt=base_prompt + "\n\nPresent your argument AGAINST this proposition.",
            system=self.SKEPTIC_SYSTEM,
        )
        skeptic_data = skeptic_response.extract_json() or {}
        
        skeptic_arg = DebateArgument(
            position="skeptic",
            claim=skeptic_data.get("claim", ""),
            evidence=skeptic_data.get("evidence", []),
            confidence=float(skeptic_data.get("confidence", 0.5)),
            weaknesses=skeptic_data.get("weaknesses", []),
        )
        
        # Judge evaluates
        judge_prompt = f"""{base_prompt}

ADVOCATE'S ARGUMENT:
Claim: {advocate_arg.claim}
Evidence: {json.dumps(advocate_arg.evidence)}
Acknowledged Weaknesses: {json.dumps(advocate_arg.weaknesses)}
Confidence: {advocate_arg.confidence}

SKEPTIC'S ARGUMENT:
Claim: {skeptic_arg.claim}
Evidence: {json.dumps(skeptic_arg.evidence)}
Acknowledged Weaknesses: {json.dumps(skeptic_arg.weaknesses)}
Confidence: {skeptic_arg.confidence}

Evaluate both arguments and render your verdict."""
        
        judge_response = await self.client.complete_json(
            prompt=judge_prompt,
            system=self.JUDGE_SYSTEM,
        )
        judge_data = judge_response.extract_json() or {}
        
        # Parse verdict
        verdict_str = judge_data.get("verdict", "uncertain").lower()
        if verdict_str == "affirm":
            verdict = DebateVerdict.AFFIRM
        elif verdict_str == "deny":
            verdict = DebateVerdict.DENY
        else:
            verdict = DebateVerdict.UNCERTAIN
        
        confidence = float(judge_data.get("confidence", 0.5))
        
        logger.debug(
            f"Debate verdict: {verdict.value} "
            f"(confidence: {confidence:.2f})"
        )
        
        return DebateResult(
            verdict=verdict,
            advocate_argument=advocate_arg,
            skeptic_argument=skeptic_arg,
            judge_reasoning=judge_data.get("reasoning", ""),
            confidence=confidence,
        )
    
    async def run_with_appeals(
        self,
        proposition: str,
        evidence: Dict[str, Any],
        max_rounds: int = 2,
    ) -> DebateResult:
        """
        Run debate with appeal rounds for uncertain verdicts.
        
        Args:
            proposition: The claim to debate
            evidence: Available evidence
            max_rounds: Maximum debate rounds
            
        Returns:
            Final DebateResult
        """
        result = await self.run(proposition, evidence)
        
        for round_num in range(1, max_rounds):
            if result.verdict != DebateVerdict.UNCERTAIN:
                break
            
            # Add previous round context and run again
            context = f"""Previous round was UNCERTAIN.
Judge's reasoning: {result.judge_reasoning}
Please address the judge's concerns in this round."""
            
            result = await self.run(proposition, evidence, context)
            logger.debug(f"Appeal round {round_num}: {result.verdict.value}")
        
        return result


# =============================================================================
# Ensemble Ranker
# =============================================================================

class EnsembleRanker(Generic[T]):
    """
    Combine multiple ranking methods using Borda count.
    
    Usage:
        ranker = EnsembleRanker()
        ranker.add_ranking("score", items_by_score)
        ranker.add_ranking("votes", items_by_votes)
        ranker.add_ranking("recency", items_by_recency)
        result = ranker.compute()
    """
    
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        Initialize ranker.
        
        Args:
            weights: Optional weights for each ranking method
        """
        self.rankings: Dict[str, List[T]] = {}
        self.weights = weights or {}
    
    def add_ranking(
        self,
        method_name: str,
        ranked_items: List[T],
        weight: float = 1.0,
    ) -> None:
        """
        Add a ranking from one method.
        
        Args:
            method_name: Name of the ranking method
            ranked_items: Items in ranked order (best first)
            weight: Weight for this method (default 1.0)
        """
        self.rankings[method_name] = ranked_items
        self.weights[method_name] = weight
    
    def compute(self) -> EnsembleResult[T]:
        """
        Compute final ranking using weighted Borda count.
        
        Returns:
            EnsembleResult with final rankings
        """
        if not self.rankings:
            raise ValueError("No rankings added")
        
        # Collect all unique items
        all_items: set = set()
        for items in self.rankings.values():
            all_items.update(id(item) for item in items)
            
        # Create ID -> item mapping
        id_to_item: Dict[int, T] = {}
        for items in self.rankings.values():
            for item in items:
                id_to_item[id(item)] = item
        
        # Calculate Borda scores
        borda_scores: Dict[int, float] = {item_id: 0.0 for item_id in all_items}
        method_ranks: Dict[int, Dict[str, int]] = {item_id: {} for item_id in all_items}
        
        for method_name, items in self.rankings.items():
            weight = self.weights.get(method_name, 1.0)
            n_items = len(items)
            
            for rank, item in enumerate(items):
                item_id = id(item)
                # Borda score: (n - rank) points, weighted
                borda_scores[item_id] += (n_items - rank) * weight
                method_ranks[item_id][method_name] = rank + 1  # 1-indexed rank
        
        # Sort by Borda score
        sorted_ids = sorted(borda_scores.keys(), key=lambda x: borda_scores[x], reverse=True)
        
        # Build result
        ranked_items: List[RankedItem[T]] = []
        max_score = max(borda_scores.values()) if borda_scores else 1.0
        
        for final_rank, item_id in enumerate(sorted_ids, 1):
            item = id_to_item[item_id]
            score = borda_scores[item_id]
            
            # Confidence based on normalized score and rank agreement
            confidence = self._calculate_confidence(
                score, max_score, method_ranks[item_id]
            )
            
            ranked_items.append(RankedItem(
                item=item,
                final_rank=final_rank,
                borda_score=score,
                method_ranks=method_ranks[item_id],
                confidence=confidence,
            ))
        
        # Calculate agreement score
        agreement = self._calculate_agreement(method_ranks)
        
        return EnsembleResult(
            rankings=ranked_items,
            method_weights=self.weights.copy(),
            agreement_score=agreement,
        )
    
    def _calculate_confidence(
        self,
        score: float,
        max_score: float,
        ranks: Dict[str, int],
    ) -> float:
        """Calculate confidence for an item based on score and rank consistency."""
        # Base confidence from normalized score
        base_confidence = score / max_score if max_score > 0 else 0.5
        
        # Adjust based on rank variance
        if len(ranks) > 1:
            rank_values = list(ranks.values())
            avg_rank = sum(rank_values) / len(rank_values)
            variance = sum((r - avg_rank) ** 2 for r in rank_values) / len(rank_values)
            # Lower variance = higher confidence
            variance_penalty = min(0.3, variance * 0.05)
            base_confidence -= variance_penalty
        
        return max(0.0, min(1.0, base_confidence))
    
    def _calculate_agreement(self, method_ranks: Dict[int, Dict[str, int]]) -> float:
        """Calculate how much ranking methods agree."""
        if not method_ranks or len(self.rankings) < 2:
            return 1.0
        
        # Calculate average rank correlation between methods
        method_names = list(self.rankings.keys())
        correlations = []
        
        for i, method1 in enumerate(method_names):
            for method2 in method_names[i+1:]:
                correlation = self._rank_correlation(method1, method2, method_ranks)
                correlations.append(correlation)
        
        return sum(correlations) / len(correlations) if correlations else 1.0
    
    def _rank_correlation(
        self,
        method1: str,
        method2: str,
        method_ranks: Dict[int, Dict[str, int]],
    ) -> float:
        """Calculate Spearman-like rank correlation between two methods."""
        diffs_squared = []
        
        for item_id, ranks in method_ranks.items():
            if method1 in ranks and method2 in ranks:
                diff = ranks[method1] - ranks[method2]
                diffs_squared.append(diff ** 2)
        
        if not diffs_squared:
            return 0.5
        
        n = len(diffs_squared)
        sum_d2 = sum(diffs_squared)
        
        # Spearman's rho approximation
        if n > 1:
            rho = 1 - (6 * sum_d2) / (n * (n**2 - 1))
            # Normalize to 0-1
            return (rho + 1) / 2
        
        return 0.5


# =============================================================================
# Uncertainty Quantifier
# =============================================================================

class UncertaintyQuantifier:
    """
    Get explicit uncertainty estimates from LLM responses.
    
    Forces the model to express uncertainty in structured format.
    """
    
    UNCERTAINTY_SYSTEM = """When answering, always include explicit uncertainty quantification.
Express your confidence as a number from 0.0 (completely uncertain) to 1.0 (completely certain).
Also list what would increase or decrease your confidence."""
    
    def __init__(self, client: ClaudeClient):
        """Initialize with ClaudeClient."""
        self.client = client
    
    async def query_with_uncertainty(
        self,
        prompt: str,
        system: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Query with explicit uncertainty estimate.
        
        Args:
            prompt: The query prompt
            system: Additional system context
            
        Returns:
            Dict with 'answer', 'confidence', 'would_increase_confidence',
            'would_decrease_confidence'
        """
        full_system = self.UNCERTAINTY_SYSTEM
        if system:
            full_system = system + "\n\n" + full_system
        
        enhanced_prompt = f"""{prompt}

Respond with JSON:
{{
    "answer": <your answer>,
    "confidence": <0.0-1.0>,
    "would_increase_confidence": ["what would make you more confident"],
    "would_decrease_confidence": ["what would make you less confident"],
    "reasoning": "brief explanation of your confidence level"
}}"""
        
        response = await self.client.complete_json(
            prompt=enhanced_prompt,
            system=full_system,
        )
        
        return response.extract_json() or {
            "answer": None,
            "confidence": 0.5,
            "would_increase_confidence": [],
            "would_decrease_confidence": [],
            "reasoning": "Failed to parse response",
        }


# =============================================================================
# Confidence Calibrator
# =============================================================================

class ConfidenceCalibrator:
    """
    Calibrate raw confidence scores to be more accurate.
    
    LLMs tend to be overconfident. This applies calibration based on:
    - Agreement with other methods
    - Historical accuracy
    - Task difficulty
    """
    
    # Calibration parameters (can be tuned)
    OVERCONFIDENCE_FACTOR = 0.85  # LLMs are ~15% overconfident
    
    @staticmethod
    def calibrate(
        raw_confidence: float,
        agreement_ratio: Optional[float] = None,
        n_signals: int = 1,
    ) -> float:
        """
        Calibrate a raw confidence score.
        
        Args:
            raw_confidence: Raw confidence from LLM (0-1)
            agreement_ratio: Agreement with other methods (0-1)
            n_signals: Number of independent signals supporting this
            
        Returns:
            Calibrated confidence (0-1)
        """
        # Apply overconfidence correction
        calibrated = raw_confidence * ConfidenceCalibrator.OVERCONFIDENCE_FACTOR
        
        # Boost if multiple signals agree
        if n_signals > 1:
            signal_boost = min(0.1, (n_signals - 1) * 0.03)
            calibrated += signal_boost
        
        # Adjust based on agreement
        if agreement_ratio is not None:
            # High agreement increases confidence
            if agreement_ratio >= 0.8:
                calibrated = min(1.0, calibrated + 0.1)
            # Low agreement decreases confidence
            elif agreement_ratio < 0.5:
                calibrated = max(0.0, calibrated - 0.2)
        
        return max(0.0, min(1.0, calibrated))
    
    @staticmethod
    def calibrate_batch(
        items: List[Dict[str, Any]],
        confidence_key: str = "confidence",
    ) -> List[Dict[str, Any]]:
        """
        Calibrate confidence scores for a batch of items.
        
        Also applies relative calibration (higher raw = higher calibrated).
        
        Args:
            items: List of dicts with confidence scores
            confidence_key: Key for confidence value
            
        Returns:
            Items with calibrated confidence scores
        """
        if not items:
            return items
        
        # Get raw confidences
        raw_scores = [item.get(confidence_key, 0.5) for item in items]
        
        # Apply individual calibration
        calibrated = [
            ConfidenceCalibrator.calibrate(score)
            for score in raw_scores
        ]
        
        # Apply relative calibration (preserve ranking)
        min_cal = min(calibrated)
        max_cal = max(calibrated)
        
        if max_cal > min_cal:
            # Spread out to use more of the range
            calibrated = [
                0.3 + 0.6 * ((c - min_cal) / (max_cal - min_cal))
                for c in calibrated
            ]
        
        # Update items
        result = []
        for item, cal_conf in zip(items, calibrated):
            updated = item.copy()
            updated[confidence_key] = round(cal_conf, 3)
            updated["raw_confidence"] = item.get(confidence_key, 0.5)
            result.append(updated)
        
        return result


# =============================================================================
# Utility Functions
# =============================================================================

async def run_with_fallback(
    primary_fn: Callable,
    fallback_fn: Callable,
    *args,
    **kwargs,
) -> Any:
    """
    Run primary function with fallback on failure.
    
    Args:
        primary_fn: Primary async function to run
        fallback_fn: Fallback async function if primary fails
        *args, **kwargs: Arguments for both functions
        
    Returns:
        Result from primary or fallback
    """
    try:
        return await primary_fn(*args, **kwargs)
    except Exception as e:
        logger.warning(f"Primary function failed: {e}, trying fallback")
        return await fallback_fn(*args, **kwargs)


def majority_vote(items: List[T], key: Optional[Callable[[T], Any]] = None) -> T:
    """
    Get majority vote from a list of items.
    
    Args:
        items: List of items to vote on
        key: Optional key function for comparison
        
    Returns:
        Most common item
    """
    if not items:
        raise ValueError("Cannot vote on empty list")
    
    if key:
        counter = Counter(key(item) for item in items)
        winner_key = counter.most_common(1)[0][0]
        return next(item for item in items if key(item) == winner_key)
    else:
        counter = Counter(str(item) for item in items)
        winner_str = counter.most_common(1)[0][0]
        return next(item for item in items if str(item) == winner_str)
