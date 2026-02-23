"""
Tests for Visual Change Detector

Run with: pytest tests/test_visual_change_detector.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from src.visual_change_detector import (
    ChangeType,
    PersonDescription,
    FrameComparison,
    VisualEvent,
    VisualEventsResult,
    VisualChangeDetector,
    merge_nearby_events,
    filter_by_confidence,
    _descriptions_similar,
)


# =============================================================================
# Test Data Classes
# =============================================================================

class TestChangeType:
    """Test ChangeType enum."""
    
    def test_enum_values(self):
        """Test enum values."""
        assert ChangeType.NEW_PERSON.value == "new_person"
        assert ChangeType.PERSON_LEFT.value == "person_left"
        assert ChangeType.LAYOUT_CHANGE.value == "layout_change"
        assert ChangeType.NO_CHANGE.value == "no_change"
        assert ChangeType.UNCERTAIN.value == "uncertain"


class TestPersonDescription:
    """Test PersonDescription dataclass."""
    
    def test_to_dict(self):
        """Test serialization."""
        person = PersonDescription(
            description="man with beard",
            position="left",
            visual_features=["beard", "glasses"],
        )
        d = person.to_dict()
        assert d["description"] == "man with beard"
        assert d["position"] == "left"
        assert d["visual_features"] == ["beard", "glasses"]


class TestFrameComparison:
    """Test FrameComparison dataclass."""
    
    def test_to_dict(self):
        """Test serialization."""
        person = PersonDescription("new person", "right", [])
        comparison = FrameComparison(
            frame_a_path="frame_001.jpg",
            frame_b_path="frame_002.jpg",
            timestamp_a=0.0,
            timestamp_b=30.0,
            change_detected=True,
            change_type=ChangeType.NEW_PERSON,
            person_description=person,
            confidence=0.85,
            reasoning="New face detected",
        )
        d = comparison.to_dict()
        assert d["change_detected"] is True
        assert d["change_type"] == "new_person"
        assert d["confidence"] == 0.85


class TestVisualEvent:
    """Test VisualEvent dataclass."""
    
    def test_to_dict(self):
        """Test serialization."""
        event = VisualEvent(
            timestamp=120.0,
            event_type=ChangeType.NEW_PERSON,
            description="Man with keffiyeh appeared",
            position="bottom-right",
            confidence=0.92,
            verification={"verified": True},
        )
        d = event.to_dict()
        assert d["timestamp"] == 120.0
        assert d["event_type"] == "new_person"
        assert d["confidence"] == 0.92


class TestVisualEventsResult:
    """Test VisualEventsResult dataclass."""
    
    def test_to_dict(self):
        """Test serialization."""
        event = VisualEvent(
            timestamp=60.0,
            event_type=ChangeType.NEW_PERSON,
            description="Test",
            position="left",
            confidence=0.8,
        )
        result = VisualEventsResult(
            events=[event],
            total_frames_analyzed=10,
            total_comparisons=9,
            total_changes=1,
            uncertain_events=0,
        )
        d = result.to_dict()
        assert len(d["events"]) == 1
        assert d["total_changes"] == 1
    
    def test_save_and_load(self, tmp_path):
        """Test save and load."""
        event = VisualEvent(
            timestamp=60.0,
            event_type=ChangeType.PERSON_LEFT,
            description="Someone left",
            position="right",
            confidence=0.75,
            verification={"verified": True},
        )
        result = VisualEventsResult(
            events=[event],
            total_frames_analyzed=5,
            total_comparisons=4,
            total_changes=1,
            uncertain_events=0,
        )
        
        # Save
        path = tmp_path / "events.json"
        result.save(str(path))
        
        # Load
        loaded = VisualEventsResult.load(str(path))
        assert len(loaded.events) == 1
        assert loaded.events[0].event_type == ChangeType.PERSON_LEFT
        assert loaded.events[0].confidence == 0.75


# =============================================================================
# Test Utility Functions
# =============================================================================

class TestDescriptionsSimilar:
    """Test _descriptions_similar function."""
    
    def test_identical(self):
        """Test identical descriptions."""
        assert _descriptions_similar("man with beard", "man with beard") is True
    
    def test_similar(self):
        """Test similar descriptions."""
        assert _descriptions_similar(
            "man with dark beard",
            "man with beard wearing glasses"
        ) is True
    
    def test_different(self):
        """Test different descriptions."""
        assert _descriptions_similar(
            "woman with glasses",
            "man with beard"
        ) is False
    
    def test_empty(self):
        """Test empty descriptions."""
        assert _descriptions_similar("", "") is False


class TestMergeNearbyEvents:
    """Test merge_nearby_events function."""
    
    def test_empty_list(self):
        """Test with empty list."""
        result = merge_nearby_events([])
        assert result == []
    
    def test_single_event(self):
        """Test with single event."""
        event = VisualEvent(
            timestamp=60.0,
            event_type=ChangeType.NEW_PERSON,
            description="Test",
            position="left",
            confidence=0.8,
        )
        result = merge_nearby_events([event])
        assert len(result) == 1
    
    def test_merge_similar(self):
        """Test merging similar nearby events."""
        events = [
            VisualEvent(
                timestamp=60.0,
                event_type=ChangeType.NEW_PERSON,
                description="man with beard",
                position="left",
                confidence=0.8,
            ),
            VisualEvent(
                timestamp=90.0,  # 30 seconds later
                event_type=ChangeType.NEW_PERSON,
                description="man with dark beard",
                position="left",
                confidence=0.85,
            ),
        ]
        result = merge_nearby_events(events, time_threshold=60)
        assert len(result) == 1
        assert result[0].confidence == 0.85  # Takes max
    
    def test_no_merge_different(self):
        """Test no merge for different events."""
        events = [
            VisualEvent(
                timestamp=60.0,
                event_type=ChangeType.NEW_PERSON,
                description="man with beard",
                position="left",
                confidence=0.8,
            ),
            VisualEvent(
                timestamp=90.0,
                event_type=ChangeType.PERSON_LEFT,  # Different type
                description="man with beard",
                position="left",
                confidence=0.85,
            ),
        ]
        result = merge_nearby_events(events, time_threshold=60)
        assert len(result) == 2
    
    def test_no_merge_far_apart(self):
        """Test no merge for events far apart."""
        events = [
            VisualEvent(
                timestamp=60.0,
                event_type=ChangeType.NEW_PERSON,
                description="man with beard",
                position="left",
                confidence=0.8,
            ),
            VisualEvent(
                timestamp=200.0,  # 140 seconds later
                event_type=ChangeType.NEW_PERSON,
                description="man with beard",
                position="left",
                confidence=0.85,
            ),
        ]
        result = merge_nearby_events(events, time_threshold=60)
        assert len(result) == 2


class TestFilterByConfidence:
    """Test filter_by_confidence function."""
    
    def test_filter(self):
        """Test filtering by confidence."""
        events = [
            VisualEvent(
                timestamp=60.0,
                event_type=ChangeType.NEW_PERSON,
                description="Test 1",
                position="left",
                confidence=0.5,
            ),
            VisualEvent(
                timestamp=120.0,
                event_type=ChangeType.NEW_PERSON,
                description="Test 2",
                position="right",
                confidence=0.8,
            ),
            VisualEvent(
                timestamp=180.0,
                event_type=ChangeType.NEW_PERSON,
                description="Test 3",
                position="center",
                confidence=0.9,
            ),
        ]
        
        result = filter_by_confidence(events, min_confidence=0.6)
        assert len(result) == 2
        assert all(e.confidence >= 0.6 for e in result)


# =============================================================================
# Test VisualChangeDetector
# =============================================================================

class TestVisualChangeDetector:
    """Test VisualChangeDetector class."""
    
    def test_init_without_key_raises(self):
        """Test that missing API key raises error."""
        with patch.dict("os.environ", {}, clear=True):
            import os
            if "GEMINI_API_KEY" in os.environ:
                del os.environ["GEMINI_API_KEY"]
            
            with pytest.raises(ValueError, match="Gemini API key required"):
                VisualChangeDetector(api_key=None)
    
    def test_parse_json_response_clean(self):
        """Test parsing clean JSON."""
        detector = VisualChangeDetector(api_key="test-key")
        
        result = detector._parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}
    
    def test_parse_json_response_code_block(self):
        """Test parsing JSON in code block."""
        detector = VisualChangeDetector(api_key="test-key")
        
        result = detector._parse_json_response('Here is the result:\n```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}
    
    def test_parse_json_response_embedded(self):
        """Test parsing embedded JSON."""
        detector = VisualChangeDetector(api_key="test-key")
        
        result = detector._parse_json_response('Analysis: {"found": true} was detected.')
        assert result == {"found": True}
    
    def test_calibrate_confidence_verified(self):
        """Test confidence calibration with verification."""
        detector = VisualChangeDetector(api_key="test-key")
        
        verification = {
            "verified": True,
            "change_agreement": 1.0,
            "type_agreement": 1.0,
        }
        
        calibrated = detector._calibrate_confidence(0.8, verification)
        assert calibrated > 0.7  # Should be boosted
    
    def test_calibrate_confidence_failed(self):
        """Test confidence calibration with failed verification."""
        detector = VisualChangeDetector(api_key="test-key")
        
        verification = {
            "verified": False,
        }
        
        calibrated = detector._calibrate_confidence(0.8, verification)
        assert calibrated < 0.7  # Should be reduced
    
    def test_build_event_description(self):
        """Test event description building."""
        detector = VisualChangeDetector(api_key="test-key")
        
        comparison = FrameComparison(
            frame_a_path="a.jpg",
            frame_b_path="b.jpg",
            timestamp_a=0,
            timestamp_b=30,
            change_detected=True,
            change_type=ChangeType.NEW_PERSON,
            person_description=PersonDescription("man with beard", "left", []),
            confidence=0.9,
            reasoning="test",
        )
        
        desc = detector._build_event_description(comparison)
        assert "man with beard" in desc
        assert "appeared" in desc


# Integration tests (require actual API key)
@pytest.mark.skip(reason="Requires actual GEMINI_API_KEY and test images")
class TestVisualChangeDetectorIntegration:
    """Integration tests requiring actual API access."""
    
    @pytest.mark.asyncio
    async def test_detect_changes(self):
        """Test actual change detection."""
        detector = VisualChangeDetector()
        # Would need actual frame paths
        # result = await detector.detect_changes(frame_paths)
        pass
