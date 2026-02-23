"""
Tests for Voice Fingerprinter Module (Real Pyannote API)

Tests cover:
- Voiceprint dataclass operations
- DiarizedSegment and IdentifiedSpeaker dataclasses
- SpeakerEvent detection logic
- Cross-modal validation logic
- Save/load functionality

Note: Tests with @pytest.mark.integration require real API key and audio files.
"""

import json
import os
import pytest
import tempfile
from pathlib import Path

from src.voice_fingerprinter import (
    # Enums
    SpeakerType,
    SpeakerEventType,
    # Data classes
    Voiceprint,
    DiarizedSegment,
    IdentifiedSpeaker,
    SpeakerEvent,
    ValidatedSpeakerChange,
    VoiceDiarizationResult,
    # Main class
    VoiceFingerprinter,
    # Utility functions
    get_guest_arrivals,
    get_speaker_at_time,
    get_speaker_timeline,
    format_timestamp,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_voiceprint():
    """Sample Voiceprint object."""
    return Voiceprint(
        voiceprint_id="vp_abc123",
        speaker_name="nick",
        created_from="/path/to/nick_sample.wav",
        created_at="2026-01-26T12:00:00",
        metadata={"file_size_mb": 5.2},
    )


@pytest.fixture
def sample_segments():
    """Sample diarized segments."""
    return [
        DiarizedSegment("SPEAKER_00", 0.0, 10.0, 0.95),
        DiarizedSegment("SPEAKER_00", 12.0, 25.0, 0.92),
        DiarizedSegment("SPEAKER_01", 26.0, 45.0, 0.88),  # New speaker
        DiarizedSegment("SPEAKER_00", 46.0, 60.0, 0.90),
        DiarizedSegment("SPEAKER_02", 62.0, 90.0, 0.85),  # Another new speaker
        DiarizedSegment("SPEAKER_01", 92.0, 110.0, 0.87),  # First speaker returns
    ]


@pytest.fixture
def sample_speakers():
    """Sample identified speakers."""
    return {
        "SPEAKER_00": IdentifiedSpeaker(
            speaker_label="SPEAKER_00",
            identified_as="nick",
            speaker_type=SpeakerType.NICK,
            first_appearance=0.0,
            last_appearance=60.0,
            total_duration=48.0,
            segment_count=3,
            identification_confidence=0.95,
        ),
        "SPEAKER_01": IdentifiedSpeaker(
            speaker_label="SPEAKER_01",
            identified_as=None,
            speaker_type=SpeakerType.UNKNOWN,
            first_appearance=26.0,
            last_appearance=110.0,
            total_duration=37.0,
            segment_count=2,
            identification_confidence=0.7,
        ),
        "SPEAKER_02": IdentifiedSpeaker(
            speaker_label="SPEAKER_02",
            identified_as=None,
            speaker_type=SpeakerType.UNKNOWN,
            first_appearance=62.0,
            last_appearance=90.0,
            total_duration=28.0,
            segment_count=1,
            identification_confidence=0.7,
        ),
    }


@pytest.fixture
def sample_visual_events():
    """Sample visual events for cross-validation."""
    return [
        {"timestamp": 25.5, "event_type": "new_person", "description": "Guest 1 appeared"},
        {"timestamp": 61.0, "event_type": "new_person", "description": "Guest 2 appeared"},
    ]


@pytest.fixture
def sample_transcript_cues():
    """Sample transcript cues for cross-validation."""
    return [
        {"timestamp": 27.0, "cue_type": "intro", "phrase": "Hey thanks for having me"},
        {"timestamp": 63.0, "cue_type": "intro", "phrase": "What's up everyone"},
    ]


@pytest.fixture
def sample_result(sample_segments, sample_speakers):
    """Sample VoiceDiarizationResult."""
    return VoiceDiarizationResult(
        segments=sample_segments,
        total_duration=110.0,
        speakers=sample_speakers,
        nick_speaker_label="SPEAKER_00",
        speaker_events=[
            SpeakerEvent(0.0, SpeakerEventType.FIRST_APPEARANCE, "SPEAKER_00", "nick", 0.95),
            SpeakerEvent(26.0, SpeakerEventType.FIRST_APPEARANCE, "SPEAKER_01", None, 0.88),
            SpeakerEvent(62.0, SpeakerEventType.FIRST_APPEARANCE, "SPEAKER_02", None, 0.85),
        ],
        new_speaker_events=[
            SpeakerEvent(0.0, SpeakerEventType.FIRST_APPEARANCE, "SPEAKER_00", "nick", 0.95),
            SpeakerEvent(26.0, SpeakerEventType.FIRST_APPEARANCE, "SPEAKER_01", None, 0.88),
            SpeakerEvent(62.0, SpeakerEventType.FIRST_APPEARANCE, "SPEAKER_02", None, 0.85),
        ],
        validated_changes=[
            ValidatedSpeakerChange(
                timestamp=26.0,
                speaker_label="SPEAKER_01",
                event_type=SpeakerEventType.FIRST_APPEARANCE,
                voice_confidence=0.88,
                visual_event_nearby=True,
                visual_event_timestamp=25.5,
                visual_correlation=0.992,
                transcript_cue_nearby=True,
                transcript_cue_phrase="Hey thanks for having me",
                transcript_correlation=0.967,
                validation_type="triple_confirmed",
                final_confidence=0.98,
                is_likely_guest=True,
            ),
        ],
        nick_voiceprint_id="vp_abc123",
        diarization_job_id="job_123",
        identification_job_id="job_456",
    )


# =============================================================================
# Test Enums
# =============================================================================

class TestSpeakerType:
    """Tests for SpeakerType enum."""
    
    def test_enum_values(self):
        assert SpeakerType.NICK.value == "nick"
        assert SpeakerType.PANEL.value == "panel"
        assert SpeakerType.GUEST.value == "guest"
        assert SpeakerType.UNKNOWN.value == "unknown"


class TestSpeakerEventType:
    """Tests for SpeakerEventType enum."""
    
    def test_enum_values(self):
        assert SpeakerEventType.FIRST_APPEARANCE.value == "first_appearance"
        assert SpeakerEventType.SPEAKING_START.value == "speaking_start"
        assert SpeakerEventType.SPEAKING_END.value == "speaking_end"
        assert SpeakerEventType.RETURN.value == "return"


# =============================================================================
# Test Voiceprint
# =============================================================================

class TestVoiceprint:
    """Tests for Voiceprint dataclass."""
    
    def test_to_dict(self, sample_voiceprint):
        d = sample_voiceprint.to_dict()
        
        assert d["voiceprint_id"] == "vp_abc123"
        assert d["speaker_name"] == "nick"
        assert d["created_from"] == "/path/to/nick_sample.wav"
        assert d["metadata"]["file_size_mb"] == 5.2
    
    def test_save_and_load(self, sample_voiceprint):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        try:
            sample_voiceprint.save(temp_path)
            loaded = Voiceprint.load(temp_path)
            
            assert loaded.voiceprint_id == sample_voiceprint.voiceprint_id
            assert loaded.speaker_name == sample_voiceprint.speaker_name
            assert loaded.created_from == sample_voiceprint.created_from
        finally:
            Path(temp_path).unlink(missing_ok=True)


# =============================================================================
# Test DiarizedSegment
# =============================================================================

class TestDiarizedSegment:
    """Tests for DiarizedSegment dataclass."""
    
    def test_duration_property(self):
        seg = DiarizedSegment("SPEAKER_00", 10.0, 25.5, 0.95)
        assert seg.duration == 15.5
    
    def test_to_dict(self):
        seg = DiarizedSegment("SPEAKER_00", 10.0, 25.5, 0.95)
        d = seg.to_dict()
        
        assert d["speaker_label"] == "SPEAKER_00"
        assert d["start"] == 10.0
        assert d["end"] == 25.5
        assert d["duration"] == 15.5
        assert d["confidence"] == 0.95


# =============================================================================
# Test IdentifiedSpeaker
# =============================================================================

class TestIdentifiedSpeaker:
    """Tests for IdentifiedSpeaker dataclass."""
    
    def test_to_dict(self, sample_speakers):
        speaker = sample_speakers["SPEAKER_00"]
        d = speaker.to_dict()
        
        assert d["speaker_label"] == "SPEAKER_00"
        assert d["identified_as"] == "nick"
        assert d["speaker_type"] == "nick"
        assert d["total_duration"] == 48.0
        assert d["segment_count"] == 3
    
    def test_unidentified_speaker(self, sample_speakers):
        speaker = sample_speakers["SPEAKER_01"]
        d = speaker.to_dict()
        
        assert d["identified_as"] is None
        assert d["speaker_type"] == "unknown"


# =============================================================================
# Test SpeakerEvent
# =============================================================================

class TestSpeakerEvent:
    """Tests for SpeakerEvent dataclass."""
    
    def test_to_dict(self):
        event = SpeakerEvent(
            timestamp=26.0,
            event_type=SpeakerEventType.FIRST_APPEARANCE,
            speaker_label="SPEAKER_01",
            identified_as=None,
            confidence=0.88,
            context="New speaker detected",
        )
        
        d = event.to_dict()
        
        assert d["timestamp"] == 26.0
        assert d["event_type"] == "first_appearance"
        assert d["speaker_label"] == "SPEAKER_01"
        assert d["identified_as"] is None
        assert d["confidence"] == 0.88


# =============================================================================
# Test ValidatedSpeakerChange
# =============================================================================

class TestValidatedSpeakerChange:
    """Tests for ValidatedSpeakerChange dataclass."""
    
    def test_to_dict(self):
        change = ValidatedSpeakerChange(
            timestamp=26.0,
            speaker_label="SPEAKER_01",
            event_type=SpeakerEventType.FIRST_APPEARANCE,
            voice_confidence=0.88,
            visual_event_nearby=True,
            visual_event_timestamp=25.5,
            visual_correlation=0.99,
            transcript_cue_nearby=True,
            transcript_cue_phrase="Hey thanks",
            transcript_correlation=0.97,
            validation_type="triple_confirmed",
            final_confidence=0.98,
            is_likely_guest=True,
            notes="Test",
        )
        
        d = change.to_dict()
        
        assert d["timestamp"] == 26.0
        assert d["validation_type"] == "triple_confirmed"
        assert d["visual_event_nearby"] is True
        assert d["transcript_cue_nearby"] is True
        assert d["final_confidence"] == 0.98
        assert d["is_likely_guest"] is True
    
    def test_voice_only_validation(self):
        change = ValidatedSpeakerChange(
            timestamp=100.0,
            speaker_label="SPEAKER_03",
            event_type=SpeakerEventType.FIRST_APPEARANCE,
            voice_confidence=0.75,
            visual_event_nearby=False,
            visual_event_timestamp=None,
            visual_correlation=None,
            transcript_cue_nearby=False,
            transcript_cue_phrase=None,
            transcript_correlation=None,
            validation_type="voice_only",
            final_confidence=0.6,
            is_likely_guest=True,
        )
        
        assert change.validation_type == "voice_only"
        assert change.visual_correlation is None


# =============================================================================
# Test VoiceDiarizationResult
# =============================================================================

class TestVoiceDiarizationResult:
    """Tests for VoiceDiarizationResult dataclass."""
    
    def test_to_dict(self, sample_result):
        d = sample_result.to_dict()
        
        assert len(d["segments"]) == 6
        assert len(d["speakers"]) == 3
        assert d["nick_speaker_label"] == "SPEAKER_00"
        assert d["total_duration"] == 110.0
        assert len(d["speaker_events"]) == 3
        assert len(d["validated_changes"]) == 1
    
    def test_save_and_load(self, sample_result):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        try:
            sample_result.save(temp_path)
            loaded = VoiceDiarizationResult.load(temp_path)
            
            assert len(loaded.segments) == 6
            assert len(loaded.speakers) == 3
            assert loaded.nick_speaker_label == "SPEAKER_00"
            assert loaded.total_duration == 110.0
            assert len(loaded.speaker_events) == 3
            assert loaded.speakers["SPEAKER_00"].speaker_type == SpeakerType.NICK
        finally:
            Path(temp_path).unlink(missing_ok=True)


# =============================================================================
# Test VoiceFingerprinter (Unit Tests - No API)
# =============================================================================

class TestVoiceFingerprinterUnit:
    """Unit tests for VoiceFingerprinter (no API calls)."""
    
    def test_init_without_key_raises(self, monkeypatch):
        """Test that initialization fails without API key."""
        monkeypatch.delenv("PYANNOTE_API_KEY", raising=False)
        
        with pytest.raises(ValueError, match="Pyannote API key required"):
            VoiceFingerprinter()
    
    def test_init_with_key(self, monkeypatch):
        """Test initialization with API key."""
        monkeypatch.setenv("PYANNOTE_API_KEY", "test_key")
        
        fp = VoiceFingerprinter()
        assert fp.api_key == "test_key"
    
    def test_get_content_type(self, monkeypatch):
        """Test content type detection."""
        monkeypatch.setenv("PYANNOTE_API_KEY", "test_key")
        fp = VoiceFingerprinter()
        
        assert fp._get_content_type(".wav") == "audio/wav"
        assert fp._get_content_type(".mp3") == "audio/mpeg"
        assert fp._get_content_type(".m4a") == "audio/m4a"
        assert fp._get_content_type(".flac") == "audio/flac"
        assert fp._get_content_type(".unknown") == "audio/wav"  # Default
    
    def test_parse_diarization_segments(self, monkeypatch):
        """Test parsing raw segment data."""
        monkeypatch.setenv("PYANNOTE_API_KEY", "test_key")
        fp = VoiceFingerprinter()
        
        raw_data = [
            {"speaker": "SPEAKER_00", "start": 0.0, "end": 10.0, "confidence": 0.95},
            {"speaker": "SPEAKER_01", "start": 12.0, "end": 25.0, "confidence": 0.88},
        ]
        
        segments = fp._parse_diarization_segments(raw_data)
        
        assert len(segments) == 2
        assert segments[0].speaker_label == "SPEAKER_00"
        assert segments[0].start == 0.0
        assert segments[0].end == 10.0
        assert segments[1].speaker_label == "SPEAKER_01"
    
    def test_parse_diarization_alternate_format(self, monkeypatch):
        """Test parsing alternate response formats."""
        monkeypatch.setenv("PYANNOTE_API_KEY", "test_key")
        fp = VoiceFingerprinter()
        
        # Alternate format with different keys
        raw_data = [
            {"label": "SPEAKER_00", "startTime": 0.0, "endTime": 10.0, "score": 0.95},
        ]
        
        segments = fp._parse_diarization_segments(raw_data)
        
        assert len(segments) == 1
        assert segments[0].speaker_label == "SPEAKER_00"
        assert segments[0].start == 0.0
        assert segments[0].confidence == 0.95
    
    def test_analyze_speakers(self, monkeypatch, sample_segments):
        """Test speaker analysis from segments."""
        monkeypatch.setenv("PYANNOTE_API_KEY", "test_key")
        fp = VoiceFingerprinter()
        
        speaker_mapping = {"SPEAKER_00": "nick"}
        speakers, nick_label = fp._analyze_speakers(sample_segments, speaker_mapping)
        
        assert nick_label == "SPEAKER_00"
        assert len(speakers) == 3
        assert speakers["SPEAKER_00"].identified_as == "nick"
        assert speakers["SPEAKER_00"].speaker_type == SpeakerType.NICK
        assert speakers["SPEAKER_01"].identified_as is None
        assert speakers["SPEAKER_01"].speaker_type == SpeakerType.UNKNOWN
    
    def test_detect_speaker_events(self, monkeypatch, sample_segments, sample_speakers):
        """Test speaker event detection."""
        monkeypatch.setenv("PYANNOTE_API_KEY", "test_key")
        fp = VoiceFingerprinter()
        
        events = fp._detect_speaker_events(sample_segments, sample_speakers)
        
        # Should detect first appearances
        first_appearances = [e for e in events if e.event_type == SpeakerEventType.FIRST_APPEARANCE]
        assert len(first_appearances) == 3  # SPEAKER_00, 01, 02
        
        # Check order
        assert first_appearances[0].speaker_label == "SPEAKER_00"
        assert first_appearances[1].speaker_label == "SPEAKER_01"
        assert first_appearances[2].speaker_label == "SPEAKER_02"
    
    def test_cross_validate_events(
        self, monkeypatch, sample_speakers, sample_visual_events, sample_transcript_cues
    ):
        """Test cross-modal validation."""
        monkeypatch.setenv("PYANNOTE_API_KEY", "test_key")
        fp = VoiceFingerprinter()
        
        new_speaker_events = [
            SpeakerEvent(26.0, SpeakerEventType.FIRST_APPEARANCE, "SPEAKER_01", None, 0.88),
            SpeakerEvent(62.0, SpeakerEventType.FIRST_APPEARANCE, "SPEAKER_02", None, 0.85),
        ]
        
        validated = fp._cross_validate_events(
            new_speaker_events,
            sample_speakers,
            "SPEAKER_00",  # Nick
            sample_visual_events,
            sample_transcript_cues,
            visual_window=60.0,
            transcript_window=30.0,
        )
        
        assert len(validated) == 2
        
        # First speaker (26.0s) should have triple confirmation
        v1 = validated[0]
        assert v1.speaker_label == "SPEAKER_01"
        assert v1.visual_event_nearby is True
        assert v1.transcript_cue_nearby is True
        assert v1.validation_type == "triple_confirmed"
        assert v1.final_confidence > v1.voice_confidence
        
        # Second speaker (62.0s) should also have visual and transcript matches
        v2 = validated[1]
        assert v2.speaker_label == "SPEAKER_02"
        assert v2.visual_event_nearby is True


# =============================================================================
# Test Utility Functions
# =============================================================================

class TestUtilityFunctions:
    """Tests for utility functions."""
    
    def test_get_guest_arrivals(self, sample_result):
        """Test filtering guest arrivals."""
        guests = get_guest_arrivals(sample_result)
        
        assert len(guests) == 1
        assert guests[0].speaker_label == "SPEAKER_01"
        assert guests[0].is_likely_guest is True
    
    def test_get_guest_arrivals_with_threshold(self, sample_result):
        """Test filtering with confidence threshold."""
        # Very high threshold
        guests = get_guest_arrivals(sample_result, min_confidence=0.99)
        assert len(guests) == 0
        
        # Lower threshold
        guests = get_guest_arrivals(sample_result, min_confidence=0.5)
        assert len(guests) == 1
    
    def test_get_speaker_at_time(self, sample_result):
        """Test finding speaker at timestamp."""
        # At start
        seg = get_speaker_at_time(sample_result, 5.0)
        assert seg is not None
        assert seg.speaker_label == "SPEAKER_00"
        
        # During guest
        seg = get_speaker_at_time(sample_result, 30.0)
        assert seg is not None
        assert seg.speaker_label == "SPEAKER_01"
        
        # Between segments
        seg = get_speaker_at_time(sample_result, 11.0)
        assert seg is None
    
    def test_get_speaker_timeline(self, sample_result):
        """Test getting speaker timeline."""
        timeline = get_speaker_timeline(sample_result)
        
        assert len(timeline) >= 3
        assert timeline[0]["speaker"] == "SPEAKER_00"
        assert timeline[0]["identified_as"] == "nick"
        assert timeline[0]["type"] == "nick"
    
    def test_format_timestamp(self):
        """Test timestamp formatting."""
        assert format_timestamp(0) == "0:00:00"
        assert format_timestamp(65) == "0:01:05"
        assert format_timestamp(3661) == "1:01:01"
        assert format_timestamp(7325) == "2:02:05"


# =============================================================================
# Integration Tests (Require Real API)
# =============================================================================

@pytest.mark.skipif(
    not os.getenv("PYANNOTE_API_KEY"),
    reason="PYANNOTE_API_KEY not set"
)
class TestVoiceFingerprinterIntegration:
    """Integration tests requiring real Pyannote API key."""
    
    @pytest.mark.asyncio
    async def test_create_voiceprint(self, tmp_path):
        """Test creating a voiceprint (requires real audio file)."""
        # This test needs a real audio file
        # Skip if no test audio available
        test_audio = Path("outputs/test_nick_sample.wav")
        if not test_audio.exists():
            pytest.skip("No test audio file available")
        
        fp = VoiceFingerprinter()
        voiceprint = await fp.create_voiceprint(str(test_audio), "nick")
        
        assert voiceprint.voiceprint_id is not None
        assert voiceprint.speaker_name == "nick"
    
    @pytest.mark.asyncio
    async def test_diarize_audio(self):
        """Test audio diarization (requires real audio file)."""
        test_audio = Path("outputs/test_audio.wav")
        if not test_audio.exists():
            pytest.skip("No test audio file available")
        
        fp = VoiceFingerprinter()
        segments, job_id = await fp.diarize_audio(str(test_audio))
        
        assert len(segments) > 0
        assert job_id is not None
