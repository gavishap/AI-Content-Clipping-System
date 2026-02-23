"""
Tests for Transcript Cue Detector Module

Tests cover:
- Pattern matching for greetings and exits
- CueType enum and dataclass operations
- TranscriptCue and ValidatedCue creation
- Context extraction and deduplication
- Utility functions
"""

import json
import pytest
import tempfile
from pathlib import Path

from src.transcript_cue_detector import (
    CueType,
    PatternMatch,
    TranscriptCue,
    ValidatedCue,
    TranscriptCuesResult,
    TranscriptCueDetector,
    get_intro_cues,
    get_exit_cues,
    get_cues_in_range,
    find_nearest_intro,
    correlate_with_voice_events,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_transcript():
    """Sample transcript with various greeting/exit phrases."""
    return {
        "words": [
            # Opening
            {"word": "Welcome", "start": 0.0, "end": 0.5, "speaker": 0},
            {"word": "to", "start": 0.5, "end": 0.6, "speaker": 0},
            {"word": "the", "start": 0.6, "end": 0.7, "speaker": 0},
            {"word": "show", "start": 0.7, "end": 1.0, "speaker": 0},
            {"word": "everyone", "start": 1.0, "end": 1.5, "speaker": 0},
            # Guest 1 intro
            {"word": "Hey", "start": 10.0, "end": 10.2, "speaker": 1},
            {"word": "thanks", "start": 10.2, "end": 10.5, "speaker": 1},
            {"word": "for", "start": 10.5, "end": 10.6, "speaker": 1},
            {"word": "having", "start": 10.6, "end": 10.9, "speaker": 1},
            {"word": "me", "start": 10.9, "end": 11.1, "speaker": 1},
            # Conversation
            {"word": "So", "start": 12.0, "end": 12.2, "speaker": 0},
            {"word": "let's", "start": 12.2, "end": 12.4, "speaker": 0},
            {"word": "talk", "start": 12.4, "end": 12.6, "speaker": 0},
            {"word": "about", "start": 12.6, "end": 12.9, "speaker": 0},
            {"word": "the", "start": 12.9, "end": 13.0, "speaker": 0},
            {"word": "topic", "start": 13.0, "end": 13.3, "speaker": 0},
            # Guest 1 exit
            {"word": "Thanks", "start": 50.0, "end": 50.3, "speaker": 1},
            {"word": "for", "start": 50.3, "end": 50.4, "speaker": 1},
            {"word": "the", "start": 50.4, "end": 50.5, "speaker": 1},
            {"word": "conversation", "start": 50.5, "end": 51.0, "speaker": 1},
            {"word": "goodbye", "start": 51.0, "end": 51.5, "speaker": 1},
            # Guest 2 intro
            {"word": "What's", "start": 60.0, "end": 60.3, "speaker": 2},
            {"word": "up", "start": 60.3, "end": 60.5, "speaker": 2},
            {"word": "everyone", "start": 60.5, "end": 61.0, "speaker": 2},
        ]
    }


@pytest.fixture
def sample_cue():
    """Sample TranscriptCue."""
    return TranscriptCue(
        timestamp=10.0,
        end_timestamp=11.1,
        cue_type=CueType.INTRO,
        phrase="thanks for having me",
        speaker_id="1",
        context_before="Welcome to the show everyone",
        context_after="So let's talk about the topic",
        confidence=0.85,
        pattern_matched="intro_thanks_for_having",
    )


@pytest.fixture
def sample_result(sample_cue):
    """Sample TranscriptCuesResult."""
    cue2 = TranscriptCue(
        timestamp=50.0,
        end_timestamp=51.5,
        cue_type=CueType.EXIT,
        phrase="Thanks for the conversation goodbye",
        speaker_id="1",
        context_before="previous context",
        context_after="next context",
        confidence=0.8,
        pattern_matched="exit_thanks_conversation",
    )
    
    validated = [
        ValidatedCue(
            cue=sample_cue,
            is_genuine=True,
            validation_reasoning="Clear introduction",
            speaker_change_detected=True,
            new_speaker_description="Guest speaker",
            final_confidence=0.9,
        ),
    ]
    
    return TranscriptCuesResult(
        raw_matches=[],
        cues=[sample_cue, cue2],
        validated_cues=validated,
        total_intros=1,
        total_exits=1,
        processing_metadata={"total_words": 100},
    )


# =============================================================================
# Test CueType
# =============================================================================

class TestCueType:
    """Tests for CueType enum."""
    
    def test_enum_values(self):
        """Test all enum values exist."""
        assert CueType.INTRO.value == "intro"
        assert CueType.EXIT.value == "exit"
        assert CueType.WELCOME.value == "welcome"
        assert CueType.FAREWELL.value == "farewell"
        assert CueType.FALSE_POSITIVE.value == "false_positive"
    
    def test_enum_from_value(self):
        """Test creating enum from value."""
        assert CueType("intro") == CueType.INTRO
        assert CueType("exit") == CueType.EXIT


# =============================================================================
# Test PatternMatch
# =============================================================================

class TestPatternMatch:
    """Tests for PatternMatch dataclass."""
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        match = PatternMatch(
            timestamp=10.0,
            end_timestamp=11.0,
            phrase="thanks for having me",
            pattern_name="intro_thanks_for_having",
            cue_type=CueType.INTRO,
            word_indices=(5, 9),
        )
        
        d = match.to_dict()
        
        assert d["timestamp"] == 10.0
        assert d["phrase"] == "thanks for having me"
        assert d["cue_type"] == "intro"
        assert d["word_indices"] == [5, 9]


# =============================================================================
# Test TranscriptCue
# =============================================================================

class TestTranscriptCue:
    """Tests for TranscriptCue dataclass."""
    
    def test_to_dict(self, sample_cue):
        """Test conversion to dictionary."""
        d = sample_cue.to_dict()
        
        assert d["timestamp"] == 10.0
        assert d["cue_type"] == "intro"
        assert d["phrase"] == "thanks for having me"
        assert d["speaker_id"] == "1"
        assert d["confidence"] == 0.85
        assert "context_before" in d
        assert "context_after" in d
    
    def test_optional_speaker_id(self):
        """Test cue with no speaker ID."""
        cue = TranscriptCue(
            timestamp=0,
            end_timestamp=1,
            cue_type=CueType.INTRO,
            phrase="hello",
            speaker_id=None,
            context_before="",
            context_after="",
            confidence=0.7,
        )
        
        d = cue.to_dict()
        assert d["speaker_id"] is None


# =============================================================================
# Test ValidatedCue
# =============================================================================

class TestValidatedCue:
    """Tests for ValidatedCue dataclass."""
    
    def test_to_dict(self, sample_cue):
        """Test conversion to dictionary."""
        validated = ValidatedCue(
            cue=sample_cue,
            is_genuine=True,
            validation_reasoning="Clear introduction",
            speaker_change_detected=True,
            new_speaker_description="New guest",
            final_confidence=0.92,
        )
        
        d = validated.to_dict()
        
        assert d["is_genuine"] is True
        assert d["validation_reasoning"] == "Clear introduction"
        assert d["speaker_change_detected"] is True
        assert d["new_speaker_description"] == "New guest"
        assert d["final_confidence"] == 0.92
        assert "cue" in d
    
    def test_false_positive(self, sample_cue):
        """Test validated cue marked as false positive."""
        validated = ValidatedCue(
            cue=sample_cue,
            is_genuine=False,
            validation_reasoning="Just casual speech",
            speaker_change_detected=False,
            new_speaker_description=None,
            final_confidence=0.0,
        )
        
        d = validated.to_dict()
        assert d["is_genuine"] is False
        assert d["final_confidence"] == 0.0


# =============================================================================
# Test TranscriptCuesResult
# =============================================================================

class TestTranscriptCuesResult:
    """Tests for TranscriptCuesResult dataclass."""
    
    def test_to_dict(self, sample_result):
        """Test conversion to dictionary."""
        d = sample_result.to_dict()
        
        assert "cues" in d
        assert "validated_cues" in d
        assert d["total_intros"] == 1
        assert d["total_exits"] == 1
        assert len(d["cues"]) == 2
    
    def test_save_and_load(self, sample_result):
        """Test save and load functionality."""
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        ) as f:
            temp_path = f.name
        
        try:
            sample_result.save(temp_path)
            
            loaded = TranscriptCuesResult.load(temp_path)
            
            assert len(loaded.cues) == 2
            assert loaded.total_intros == 1
            assert loaded.total_exits == 1
            assert len(loaded.validated_cues) == 1
            assert loaded.cues[0].phrase == "thanks for having me"
        finally:
            Path(temp_path).unlink(missing_ok=True)


# =============================================================================
# Test TranscriptCueDetector
# =============================================================================

class TestTranscriptCueDetector:
    """Tests for TranscriptCueDetector class."""
    
    def test_init(self):
        """Test initialization."""
        detector = TranscriptCueDetector()
        
        # Should have compiled patterns
        assert len(detector._compiled_patterns) > 0
        assert len(detector.intro_patterns) > 0
        assert len(detector.exit_patterns) > 0
    
    def test_init_with_custom_patterns(self):
        """Test initialization with custom patterns."""
        custom_intro = {"custom_hello": r"\bhowdy\b"}
        custom_exit = {"custom_bye": r"\blater\s+gator\b"}
        
        detector = TranscriptCueDetector(
            custom_intro_patterns=custom_intro,
            custom_exit_patterns=custom_exit,
        )
        
        assert "custom_hello" in detector.intro_patterns
        assert "custom_bye" in detector.exit_patterns
    
    def test_extract_words_direct(self, sample_transcript):
        """Test word extraction from direct format."""
        detector = TranscriptCueDetector()
        words = detector._extract_words(sample_transcript)
        
        assert len(words) > 0
        assert words[0]["word"] == "Welcome"
    
    def test_extract_words_deepgram_format(self):
        """Test word extraction from Deepgram response format."""
        deepgram_transcript = {
            "results": {
                "channels": [{
                    "alternatives": [{
                        "words": [
                            {"word": "Hello", "start": 0, "end": 0.5, "speaker": 0}
                        ]
                    }]
                }]
            }
        }
        
        detector = TranscriptCueDetector()
        words = detector._extract_words(deepgram_transcript)
        
        assert len(words) == 1
        assert words[0]["word"] == "Hello"
    
    def test_find_pattern_matches(self, sample_transcript):
        """Test finding pattern matches in transcript."""
        detector = TranscriptCueDetector()
        words = detector._extract_words(sample_transcript)
        full_text = " ".join(w["word"] for w in words)
        
        matches = detector._find_pattern_matches(words, full_text)
        
        # Should find several matches
        assert len(matches) >= 3  # welcome, thanks for having, goodbye, what's up
        
        # Check that matches have correct types
        intro_matches = [m for m in matches if m.cue_type == CueType.INTRO]
        exit_matches = [m for m in matches if m.cue_type == CueType.EXIT]
        
        assert len(intro_matches) >= 1
        assert len(exit_matches) >= 1
    
    def test_build_cue_with_context(self, sample_transcript):
        """Test building cue with surrounding context."""
        detector = TranscriptCueDetector()
        words = detector._extract_words(sample_transcript)
        
        # Create a mock match
        match = PatternMatch(
            timestamp=10.0,
            end_timestamp=11.1,
            phrase="thanks for having me",
            pattern_name="intro_thanks_for_having",
            cue_type=CueType.INTRO,
            word_indices=(6, 9),
        )
        
        cue = detector._build_cue_with_context(match, words, context_window=10)
        
        assert cue.phrase == "thanks for having me"
        assert cue.speaker_id == "1"
        assert len(cue.context_before) > 0
        assert len(cue.context_after) > 0
    
    def test_calculate_confidence(self):
        """Test confidence calculation."""
        detector = TranscriptCueDetector()
        
        # High confidence pattern
        match_high = PatternMatch(
            timestamp=0,
            end_timestamp=1,
            phrase="thanks for having me",
            pattern_name="intro_thanks_for_having",
            cue_type=CueType.INTRO,
            word_indices=(0, 3),
        )
        
        conf_high = detector._calculate_confidence(match_high, "", "")
        assert conf_high >= 0.8
        
        # Low confidence pattern (just "hey")
        match_low = PatternMatch(
            timestamp=0,
            end_timestamp=1,
            phrase="hey",
            pattern_name="intro_hey_greeting",
            cue_type=CueType.INTRO,
            word_indices=(0, 0),
        )
        
        conf_low = detector._calculate_confidence(match_low, "", "")
        assert conf_low < conf_high
    
    def test_deduplicate_cues(self, sample_cue):
        """Test cue deduplication."""
        detector = TranscriptCueDetector()
        
        # Create duplicate cues close in time
        cue1 = sample_cue
        cue2 = TranscriptCue(
            timestamp=10.5,  # Very close to cue1
            end_timestamp=11.5,
            cue_type=CueType.INTRO,
            phrase="similar phrase",
            speaker_id="1",
            context_before="",
            context_after="",
            confidence=0.7,  # Lower confidence
        )
        cue3 = TranscriptCue(
            timestamp=50.0,  # Far from others
            end_timestamp=51.0,
            cue_type=CueType.EXIT,
            phrase="goodbye",
            speaker_id="1",
            context_before="",
            context_after="",
            confidence=0.8,
        )
        
        deduped = detector._deduplicate_cues([cue1, cue2, cue3])
        
        # Should keep cue1 (higher confidence) and cue3 (different time/type)
        assert len(deduped) == 2
        assert deduped[0].confidence == 0.85  # cue1 kept
        assert deduped[1].cue_type == CueType.EXIT


# =============================================================================
# Test Pattern Matching
# =============================================================================

class TestPatternMatching:
    """Tests for specific pattern matching."""
    
    def test_intro_patterns(self):
        """Test intro pattern detection."""
        detector = TranscriptCueDetector()
        
        test_phrases = [
            ("what's up", True),
            ("hey man", True),
            ("thanks for having me", True),
            ("good to be here", True),
            ("hello everyone", True),
            ("random words here", False),
        ]
        
        for phrase, should_match in test_phrases:
            words = [{"word": w, "start": i, "end": i+1, "speaker": 0} 
                     for i, w in enumerate(phrase.split())]
            matches = detector._find_pattern_matches(words, phrase)
            
            intro_matches = [m for m in matches if m.cue_type == CueType.INTRO]
            
            if should_match:
                assert len(intro_matches) >= 1, f"Expected match for: {phrase}"
            else:
                assert len(intro_matches) == 0, f"Unexpected match for: {phrase}"
    
    def test_exit_patterns(self):
        """Test exit pattern detection."""
        detector = TranscriptCueDetector()
        
        test_phrases = [
            ("goodbye", True),
            ("see you later", True),
            ("take care", True),
            ("thanks for the conversation", True),
            ("peace out", True),
            ("random words here", False),
        ]
        
        for phrase, should_match in test_phrases:
            words = [{"word": w, "start": i, "end": i+1, "speaker": 0} 
                     for i, w in enumerate(phrase.split())]
            matches = detector._find_pattern_matches(words, phrase)
            
            exit_matches = [m for m in matches if m.cue_type == CueType.EXIT]
            
            if should_match:
                assert len(exit_matches) >= 1, f"Expected match for: {phrase}"
            else:
                assert len(exit_matches) == 0, f"Unexpected match for: {phrase}"
    
    def test_welcome_patterns(self):
        """Test welcome pattern detection."""
        detector = TranscriptCueDetector()
        
        test_phrases = [
            ("welcome to the show", True),
            ("thanks for joining", True),
            ("glad to have you", True),
        ]
        
        for phrase, should_match in test_phrases:
            words = [{"word": w, "start": i, "end": i+1, "speaker": 0} 
                     for i, w in enumerate(phrase.split())]
            matches = detector._find_pattern_matches(words, phrase)
            
            welcome_matches = [m for m in matches if m.cue_type == CueType.WELCOME]
            
            if should_match:
                assert len(welcome_matches) >= 1, f"Expected match for: {phrase}"


# =============================================================================
# Test Utility Functions
# =============================================================================

class TestUtilityFunctions:
    """Tests for utility functions."""
    
    def test_get_intro_cues(self, sample_result):
        """Test getting intro cues."""
        intros = get_intro_cues(sample_result)
        
        assert len(intros) == 1
        assert intros[0].cue_type == CueType.INTRO
    
    def test_get_intro_cues_with_threshold(self, sample_result):
        """Test getting intro cues with confidence threshold."""
        # High threshold
        intros = get_intro_cues(sample_result, min_confidence=0.9)
        assert len(intros) == 0
        
        # Low threshold
        intros = get_intro_cues(sample_result, min_confidence=0.5)
        assert len(intros) == 1
    
    def test_get_exit_cues(self, sample_result):
        """Test getting exit cues."""
        exits = get_exit_cues(sample_result)
        
        assert len(exits) == 1
        assert exits[0].cue_type == CueType.EXIT
    
    def test_get_cues_in_range(self, sample_result):
        """Test getting cues in time range."""
        # Range that includes intro
        cues = get_cues_in_range(sample_result, 0, 20)
        assert len(cues) == 1
        assert cues[0].cue_type == CueType.INTRO
        
        # Range that includes exit
        cues = get_cues_in_range(sample_result, 40, 60)
        assert len(cues) == 1
        assert cues[0].cue_type == CueType.EXIT
        
        # Range that includes both
        cues = get_cues_in_range(sample_result, 0, 60)
        assert len(cues) == 2
    
    def test_find_nearest_intro(self, sample_result):
        """Test finding nearest intro to timestamp."""
        # Near the intro
        nearest = find_nearest_intro(sample_result, 12.0)
        assert nearest is not None
        assert nearest.timestamp == 10.0
        
        # Far from intro
        nearest = find_nearest_intro(sample_result, 100.0, max_distance=30)
        assert nearest is None
    
    def test_correlate_with_voice_events(self, sample_result):
        """Test correlating cues with voice events."""
        voice_events = [
            {"timestamp": 9.5, "speaker_id": "1", "event_type": "new_speaker"},
            {"timestamp": 49.0, "speaker_id": "0", "event_type": "speaker_return"},
        ]
        
        correlations = correlate_with_voice_events(sample_result, voice_events)
        
        # Should find correlation for intro cue
        assert len(correlations) >= 1
        assert correlations[0]["cue_timestamp"] == 10.0
        assert correlations[0]["voice_timestamp"] == 9.5
        assert correlations[0]["correlation_strength"] > 0


# =============================================================================
# Integration Tests
# =============================================================================

class TestTranscriptCueDetectorIntegration:
    """Integration tests for TranscriptCueDetector."""
    
    @pytest.mark.asyncio
    async def test_detect_cues_without_llm(self, sample_transcript):
        """Test full cue detection without LLM validation."""
        detector = TranscriptCueDetector()
        
        result = await detector.detect_cues(
            transcript_data=sample_transcript,
            validate_with_llm=False,
            min_confidence=0.3,
        )
        
        # Should detect multiple cues
        assert result.total_intros >= 1
        assert result.total_exits >= 1
        
        # Should have processing metadata
        assert result.processing_metadata["total_words"] == len(sample_transcript["words"])
        assert result.processing_metadata["llm_validation"] is False
    
    @pytest.mark.asyncio
    async def test_detect_cues_empty_transcript(self):
        """Test handling of empty transcript."""
        detector = TranscriptCueDetector()
        
        result = await detector.detect_cues(
            transcript_data={"words": []},
            validate_with_llm=False,
        )
        
        assert len(result.cues) == 0
        assert result.total_intros == 0
        assert result.total_exits == 0
    
    def test_sync_wrapper(self, sample_transcript):
        """Test synchronous wrapper."""
        detector = TranscriptCueDetector()
        
        result = detector.detect_cues_sync(
            transcript_data=sample_transcript,
            validate_with_llm=False,
            min_confidence=0.3,
        )
        
        assert result.total_intros >= 1
        assert result.total_exits >= 1
