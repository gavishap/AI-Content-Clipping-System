"""Tests for transcriber module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json

from src.transcriber import (
    Word, 
    TranscriptData, 
    Transcriber,
    find_word_at_timestamp, 
    find_sentence_boundary,
)


class TestWord:
    """Test Word dataclass."""
    
    def test_word_creation(self):
        word = Word(text="Hello", start=1.0, end=1.5, confidence=0.99, speaker=0)
        assert word.text == "Hello"
        assert word.start == 1.0
        assert word.end == 1.5
        assert word.confidence == 0.99
        assert word.speaker == 0
    
    def test_word_optional_speaker(self):
        word = Word(text="Test", start=0.0, end=0.5, confidence=0.95)
        assert word.speaker is None


class TestTranscriptData:
    """Test TranscriptData dataclass."""
    
    def test_creation(self):
        words = [
            Word("Hello", 0.0, 0.5, 0.99, 0),
            Word("world.", 0.6, 1.0, 0.98, 0),
        ]
        
        data = TranscriptData(
            full_transcript="Hello world.",
            timestamped_transcript="[00:00:00] Speaker 0: Hello world.",
            words=words,
            word_count=2,
            duration=1.0,
            speakers={0: {"word_count": 2, "duration": 1.0}},
        )
        
        assert data.full_transcript == "Hello world."
        assert data.word_count == 2
        assert len(data.words) == 2
    
    def test_to_dict(self):
        words = [Word("Test", 0.0, 0.5, 0.99, 0)]
        data = TranscriptData(
            full_transcript="Test",
            timestamped_transcript="[00:00:00] Speaker 0: Test",
            words=words,
            word_count=1,
            duration=0.5,
            speakers={0: {"word_count": 1}},
        )
        
        result = data.to_dict()
        assert result['full_transcript'] == "Test"
        assert result['word_count'] == 1
        assert len(result['words']) == 1
        assert result['words'][0]['text'] == "Test"
    
    def test_save(self, tmp_path):
        words = [Word("Test", 0.0, 0.5, 0.99, 0)]
        data = TranscriptData(
            full_transcript="Test",
            timestamped_transcript="[00:00:00] Speaker 0: Test",
            words=words,
            word_count=1,
            duration=0.5,
            speakers={},
        )
        
        output_file = tmp_path / "transcript.json"
        data.save(str(output_file))
        
        assert output_file.exists()
        loaded = json.loads(output_file.read_text())
        assert loaded['full_transcript'] == "Test"


class TestTranscriber:
    """Test Transcriber class."""
    
    def test_format_timestamp(self):
        """Test timestamp formatting."""
        assert Transcriber._format_timestamp(0) == "00:00:00"
        assert Transcriber._format_timestamp(59) == "00:00:59"
        assert Transcriber._format_timestamp(60) == "00:01:00"
        assert Transcriber._format_timestamp(3600) == "01:00:00"
        assert Transcriber._format_timestamp(3661) == "01:01:01"
        assert Transcriber._format_timestamp(14423.5) == "04:00:23"
    
    @patch('src.transcriber.DeepgramClient')
    def test_init(self, mock_client):
        """Test Transcriber initialization."""
        transcriber = Transcriber("test_api_key")
        mock_client.assert_called_once_with("test_api_key")
    
    def test_get_speaker_stats(self):
        """Test speaker stats calculation."""
        words = [
            Word("Hello", 0.0, 0.5, 0.99, 0),
            Word("there", 0.6, 1.0, 0.98, 0),
            Word("Hi", 1.1, 1.4, 0.97, 1),
            Word("back", 1.5, 1.9, 0.96, 1),
        ]
        
        with patch('src.transcriber.DeepgramClient'):
            transcriber = Transcriber("test_key")
            stats = transcriber._get_speaker_stats(words)
        
        assert 0 in stats
        assert 1 in stats
        assert stats[0]['word_count'] == 2
        assert stats[1]['word_count'] == 2


class TestFindWordAtTimestamp:
    """Test find_word_at_timestamp function."""
    
    def test_finds_closest_word(self):
        words = [
            Word("Hello", 1.0, 1.5, 0.99),
            Word("world", 1.6, 2.0, 0.98),
            Word("test", 2.1, 2.5, 0.97),
        ]
        result = find_word_at_timestamp(words, 1.55)
        assert result.text == "Hello"  # 1.55 is closer to 1.0 than 1.6
    
    def test_finds_exact_match(self):
        words = [
            Word("Hello", 1.0, 1.5, 0.99),
            Word("world", 1.6, 2.0, 0.98),
        ]
        result = find_word_at_timestamp(words, 1.6)
        assert result.text == "world"
    
    def test_empty_list_returns_none(self):
        result = find_word_at_timestamp([], 1.0)
        assert result is None


class TestFindSentenceBoundary:
    """Test find_sentence_boundary function."""
    
    def test_finds_boundary_before(self):
        words = [
            Word("Hello.", 1.0, 1.5, 0.99),
            Word("World", 1.6, 2.0, 0.98),
        ]
        result = find_sentence_boundary(words, 1.7, direction="before")
        assert result == 1.5  # End of "Hello."
    
    def test_finds_boundary_after(self):
        words = [
            Word("Hello", 1.0, 1.5, 0.99),
            Word("world.", 1.6, 2.0, 0.98),
        ]
        result = find_sentence_boundary(words, 1.2, direction="after")
        assert result == 2.0  # End of "world."
    
    def test_finds_question_mark(self):
        words = [
            Word("What?", 1.0, 1.5, 0.99),
            Word("Nothing", 1.6, 2.0, 0.98),
        ]
        result = find_sentence_boundary(words, 1.7, direction="before")
        assert result == 1.5  # End of "What?"
    
    def test_finds_exclamation(self):
        words = [
            Word("Wow!", 1.0, 1.5, 0.99),
            Word("Amazing", 1.6, 2.0, 0.98),
        ]
        result = find_sentence_boundary(words, 1.7, direction="before")
        assert result == 1.5  # End of "Wow!"
    
    def test_empty_list_returns_zero(self):
        result = find_sentence_boundary([], 1.0, direction="before")
        assert result == 0
