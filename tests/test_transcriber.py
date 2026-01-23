"""Tests for transcriber module."""

import pytest
from src.transcriber import Word, find_word_at_timestamp, find_sentence_boundary


class TestWord:
    """Test Word dataclass."""
    
    def test_word_creation(self):
        word = Word(text="Hello", start=1.0, end=1.5, confidence=0.99, speaker=0)
        assert word.text == "Hello"
        assert word.start == 1.0
        assert word.end == 1.5


class TestFindWordAtTimestamp:
    """Test find_word_at_timestamp function."""
    
    def test_finds_closest_word(self):
        words = [
            Word("Hello", 1.0, 1.5, 0.99),
            Word("world", 1.6, 2.0, 0.98),
            Word("test", 2.1, 2.5, 0.97),
        ]
        result = find_word_at_timestamp(words, 1.55)
        assert result.text == "world"  # 1.55 is closer to 1.6 than 1.0
    
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
