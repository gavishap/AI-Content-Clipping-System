"""
Tests for LLM Engineering Utilities

Run with: pytest tests/test_llm_engineering.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.llm_engineering import (
    ConsistencyResult,
    VerificationResult,
    DebateVerdict,
    DebateArgument,
    DebateResult,
    RankedItem,
    EnsembleResult,
    SelfConsistencyRunner,
    TwoPassVerifier,
    MultiAgentDebate,
    EnsembleRanker,
    UncertaintyQuantifier,
    ConfidenceCalibrator,
    majority_vote,
)
from src.anthropic_client import ClaudeClient, ClaudeResponse, TokenUsage


# =============================================================================
# Test Data Classes
# =============================================================================

class TestConsistencyResult:
    """Test ConsistencyResult dataclass."""
    
    def test_is_confident_high_agreement(self):
        """Test confident with high agreement."""
        result = ConsistencyResult(
            winner="yes",
            agreement_ratio=0.8,
            all_results=["yes", "yes", "no"],
            confidence=0.85,
        )
        assert result.is_confident is True
    
    def test_is_confident_low_agreement(self):
        """Test not confident with low agreement."""
        result = ConsistencyResult(
            winner="yes",
            agreement_ratio=0.5,
            all_results=["yes", "no"],
            confidence=0.5,
        )
        assert result.is_confident is False


class TestDebateVerdict:
    """Test DebateVerdict enum."""
    
    def test_verdict_values(self):
        """Test verdict enum values."""
        assert DebateVerdict.AFFIRM.value == "affirm"
        assert DebateVerdict.DENY.value == "deny"
        assert DebateVerdict.UNCERTAIN.value == "uncertain"


class TestRankedItem:
    """Test RankedItem dataclass."""
    
    def test_ranked_item_creation(self):
        """Test creating a ranked item."""
        item = RankedItem(
            item="clip_1",
            final_rank=1,
            borda_score=15.0,
            method_ranks={"score": 1, "votes": 2},
            confidence=0.9,
        )
        assert item.item == "clip_1"
        assert item.final_rank == 1


# =============================================================================
# Test Ensemble Ranker
# =============================================================================

class TestEnsembleRanker:
    """Test EnsembleRanker class."""
    
    def test_single_ranking(self):
        """Test with single ranking method."""
        ranker = EnsembleRanker()
        items = ["a", "b", "c"]
        ranker.add_ranking("method1", items)
        
        result = ranker.compute()
        
        assert len(result.rankings) == 3
        assert result.rankings[0].item == "a"
        assert result.rankings[0].final_rank == 1
    
    def test_multiple_rankings_agreement(self):
        """Test with multiple methods that agree."""
        ranker = EnsembleRanker()
        ranker.add_ranking("method1", ["a", "b", "c"])
        ranker.add_ranking("method2", ["a", "b", "c"])
        
        result = ranker.compute()
        
        # Methods agree, "a" should be first
        assert result.top_items[0] == "a"
        assert result.agreement_score > 0.8
    
    def test_multiple_rankings_disagreement(self):
        """Test with methods that disagree."""
        ranker = EnsembleRanker()
        ranker.add_ranking("method1", ["a", "b", "c"])
        ranker.add_ranking("method2", ["c", "b", "a"])
        
        result = ranker.compute()
        
        # "b" is in the middle for both, should rank high
        assert "b" in [result.rankings[0].item, result.rankings[1].item]
    
    def test_weighted_rankings(self):
        """Test with weighted rankings."""
        ranker = EnsembleRanker()
        ranker.add_ranking("important", ["a", "c", "b"], weight=2.0)
        ranker.add_ranking("less_important", ["b", "a", "c"], weight=1.0)
        
        result = ranker.compute()
        
        # "a" should win due to higher weight
        assert result.top_items[0] == "a"
        assert result.method_weights["important"] == 2.0
    
    def test_empty_ranker_raises(self):
        """Test that empty ranker raises error."""
        ranker = EnsembleRanker()
        with pytest.raises(ValueError):
            ranker.compute()


# =============================================================================
# Test Confidence Calibrator
# =============================================================================

class TestConfidenceCalibrator:
    """Test ConfidenceCalibrator class."""
    
    def test_calibrate_reduces_overconfidence(self):
        """Test that high confidence is reduced."""
        raw = 0.95
        calibrated = ConfidenceCalibrator.calibrate(raw)
        assert calibrated < raw
    
    def test_calibrate_with_agreement(self):
        """Test calibration with agreement ratio."""
        raw = 0.7
        
        # High agreement should boost
        high_agree = ConfidenceCalibrator.calibrate(raw, agreement_ratio=0.9)
        
        # Low agreement should reduce
        low_agree = ConfidenceCalibrator.calibrate(raw, agreement_ratio=0.3)
        
        assert high_agree > low_agree
    
    def test_calibrate_with_multiple_signals(self):
        """Test calibration with multiple signals."""
        raw = 0.7
        
        single = ConfidenceCalibrator.calibrate(raw, n_signals=1)
        multi = ConfidenceCalibrator.calibrate(raw, n_signals=3)
        
        assert multi > single
    
    def test_calibrate_batch(self):
        """Test batch calibration."""
        items = [
            {"id": 1, "confidence": 0.9},
            {"id": 2, "confidence": 0.5},
            {"id": 3, "confidence": 0.7},
        ]
        
        calibrated = ConfidenceCalibrator.calibrate_batch(items)
        
        assert len(calibrated) == 3
        # Original ranking should be preserved
        confidences = [item["confidence"] for item in calibrated]
        assert confidences[0] > confidences[2] > confidences[1]
        # Raw confidence should be saved
        assert all("raw_confidence" in item for item in calibrated)
    
    def test_calibrate_bounds(self):
        """Test that calibrated values stay in bounds."""
        assert 0 <= ConfidenceCalibrator.calibrate(0.0) <= 1
        assert 0 <= ConfidenceCalibrator.calibrate(1.0) <= 1
        assert 0 <= ConfidenceCalibrator.calibrate(0.5, agreement_ratio=0.0) <= 1
        assert 0 <= ConfidenceCalibrator.calibrate(0.5, agreement_ratio=1.0) <= 1


# =============================================================================
# Test Utility Functions
# =============================================================================

class TestMajorityVote:
    """Test majority_vote function."""
    
    def test_simple_majority(self):
        """Test simple majority vote."""
        items = ["yes", "yes", "no"]
        result = majority_vote(items)
        assert result == "yes"
    
    def test_unanimous(self):
        """Test unanimous vote."""
        items = ["agree", "agree", "agree"]
        result = majority_vote(items)
        assert result == "agree"
    
    def test_with_key_function(self):
        """Test majority vote with key function."""
        items = [
            {"value": "a", "score": 1},
            {"value": "a", "score": 2},
            {"value": "b", "score": 3},
        ]
        result = majority_vote(items, key=lambda x: x["value"])
        assert result["value"] == "a"
    
    def test_empty_list_raises(self):
        """Test that empty list raises error."""
        with pytest.raises(ValueError):
            majority_vote([])


# =============================================================================
# Integration Tests (require mocking)
# =============================================================================

class TestSelfConsistencyRunner:
    """Test SelfConsistencyRunner with mocked client."""
    
    @pytest.mark.asyncio
    async def test_consistency_unanimous(self):
        """Test self-consistency with unanimous results."""
        # Create mock client
        mock_client = MagicMock(spec=ClaudeClient)
        
        # Mock response
        mock_response = MagicMock(spec=ClaudeResponse)
        mock_response.extract_json.return_value = {"answer": "yes"}
        
        mock_client.complete = AsyncMock(return_value=mock_response)
        
        runner = SelfConsistencyRunner(mock_client, n_runs=3)
        result = await runner.run(
            prompt="Test prompt",
            parse_fn=lambda r: r.extract_json()["answer"],
        )
        
        assert result.winner == "yes"
        assert result.agreement_ratio == 1.0
        assert result.is_confident is True
    
    @pytest.mark.asyncio
    async def test_consistency_split_vote(self):
        """Test self-consistency with split vote."""
        mock_client = MagicMock(spec=ClaudeClient)
        
        # Different responses
        responses = []
        for answer in ["yes", "yes", "no"]:
            resp = MagicMock(spec=ClaudeResponse)
            resp.extract_json.return_value = {"answer": answer}
            responses.append(resp)
        
        mock_client.complete = AsyncMock(side_effect=responses)
        
        runner = SelfConsistencyRunner(mock_client, n_runs=3)
        result = await runner.run(
            prompt="Test prompt",
            parse_fn=lambda r: r.extract_json()["answer"],
        )
        
        assert result.winner == "yes"
        assert result.agreement_ratio == pytest.approx(2/3, rel=0.01)


class TestMultiAgentDebate:
    """Test MultiAgentDebate with mocked client."""
    
    @pytest.mark.asyncio
    async def test_debate_affirm(self):
        """Test debate with affirm verdict."""
        mock_client = MagicMock(spec=ClaudeClient)
        
        # Mock advocate response
        advocate_resp = MagicMock(spec=ClaudeResponse)
        advocate_resp.extract_json.return_value = {
            "claim": "The evidence supports this",
            "evidence": ["Point 1", "Point 2"],
            "confidence": 0.8,
            "weaknesses": ["Minor issue"],
        }
        
        # Mock skeptic response
        skeptic_resp = MagicMock(spec=ClaudeResponse)
        skeptic_resp.extract_json.return_value = {
            "claim": "The evidence is weak",
            "evidence": ["Counter 1"],
            "confidence": 0.4,
            "weaknesses": ["Strong opposing evidence"],
        }
        
        # Mock judge response
        judge_resp = MagicMock(spec=ClaudeResponse)
        judge_resp.extract_json.return_value = {
            "verdict": "affirm",
            "reasoning": "Advocate's case is stronger",
            "confidence": 0.75,
        }
        
        mock_client.complete_json = AsyncMock(
            side_effect=[advocate_resp, skeptic_resp, judge_resp]
        )
        
        debate = MultiAgentDebate(mock_client)
        result = await debate.run(
            proposition="This is true",
            evidence={"fact1": "data"},
        )
        
        assert result.verdict == DebateVerdict.AFFIRM
        assert result.confidence == 0.75
        assert result.advocate_argument.claim == "The evidence supports this"
        assert result.skeptic_argument.claim == "The evidence is weak"


class TestTwoPassVerifier:
    """Test TwoPassVerifier with mocked client."""
    
    @pytest.mark.asyncio
    async def test_verify_agreement(self):
        """Test verification with agreement."""
        mock_client = MagicMock(spec=ClaudeClient)
        
        resp1 = MagicMock(spec=ClaudeResponse)
        resp1.extract_json.return_value = {"answer": True}
        
        resp2 = MagicMock(spec=ClaudeResponse)
        resp2.extract_json.return_value = {"answer": True}
        
        mock_client.complete_json = AsyncMock(side_effect=[resp1, resp2])
        
        verifier = TwoPassVerifier(mock_client)
        result = await verifier.verify(
            pass1_prompt="Check A",
            pass2_prompt="Check B",
            compare_fn=lambda a, b: a["answer"] == b["answer"],
        )
        
        assert result.verified is True
        assert result.agreement is True
        assert result.confidence == 0.9
    
    @pytest.mark.asyncio
    async def test_verify_disagreement(self):
        """Test verification with disagreement."""
        mock_client = MagicMock(spec=ClaudeClient)
        
        resp1 = MagicMock(spec=ClaudeResponse)
        resp1.extract_json.return_value = {"answer": True}
        
        resp2 = MagicMock(spec=ClaudeResponse)
        resp2.extract_json.return_value = {"answer": False}
        
        mock_client.complete_json = AsyncMock(side_effect=[resp1, resp2])
        
        verifier = TwoPassVerifier(mock_client)
        result = await verifier.verify(
            pass1_prompt="Check A",
            pass2_prompt="Check B",
            compare_fn=lambda a, b: a["answer"] == b["answer"],
        )
        
        assert result.verified is False
        assert result.agreement is False
        assert result.confidence == 0.4
