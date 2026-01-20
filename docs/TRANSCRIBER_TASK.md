# Transcription Module Implementation Guide

> **Module**: `src/transcriber.py`
> **Owner**: Gabriel
> **Priority**: HIGH
> **Dependencies**: Deepgram API key

---

## Objective

Build a transcription module using Deepgram Nova-3 that produces:
1. Full transcript text
2. **Word-level timestamps** (CRITICAL for accurate clip extraction)
3. Speaker diarization (identify Nick vs guests)
4. Timestamped transcript formatted for AI analysis

---

## Why Word-Level Timestamps Matter

The entire clip extraction accuracy depends on word-level timestamps:
- AI might say "clip starts at 00:15:32"
- But we need to know the EXACT millisecond when that sentence starts
- Word-level data lets us snap to sentence boundaries
- Without this, clips start/end mid-word

---

## Implementation Checklist

### Data Structures
```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class Word:
    text: str
    start: float      # Seconds
    end: float        # Seconds
    confidence: float # 0-1
    speaker: Optional[int] = None

@dataclass
class TranscriptData:
    full_transcript: str
    timestamped_transcript: str  # For AI prompt
    words: List[Word]
    word_count: int
    duration: float
    speakers: dict
```

### Transcriber Class
```python
class Transcriber:
    def __init__(self, api_key: str):
        """Initialize with Deepgram API key"""
        
    async def transcribe(self, audio_path: str) -> TranscriptData:
        """Main method - transcribe audio file"""
        
    def _process_response(self, response: dict) -> TranscriptData:
        """Convert Deepgram response to our format"""
        
    def _build_timestamped_transcript(self, result: dict) -> str:
        """Build [HH:MM:SS] Speaker X: text format"""
        
    def _format_timestamp(self, seconds: float) -> str:
        """Convert seconds to HH:MM:SS"""
        
    def _get_speaker_stats(self, words: List[Word]) -> dict:
        """Calculate speaking time per speaker"""
```

---

## Deepgram Configuration

```python
options = {
    'model': 'nova-3',          # Latest, most accurate
    'language': 'en',           # English
    'punctuate': True,          # Add punctuation
    'diarize': True,            # Speaker identification
    'smart_format': True,       # Format numbers, dates
    'filler_words': True,       # Keep "um", "uh" for natural feel
    'utterances': True,         # Sentence boundaries
    'paragraphs': True,         # Paragraph breaks
}
```

---

## Expected Output Format

### timestamped_transcript (for AI)
```
[00:00:05] Speaker 0: So I was thinking about this whole situation.
[00:00:12] Speaker 1: Yeah, what's your take?
[00:00:15] Speaker 0: Bro, that's actually insane if you think about it.
```

### words (for timestamp refinement)
```python
[
    Word(text="So", start=5.2, end=5.4, confidence=0.99, speaker=0),
    Word(text="I", start=5.45, end=5.55, confidence=0.98, speaker=0),
    Word(text="was", start=5.6, end=5.75, confidence=0.99, speaker=0),
    Word(text="thinking", start=5.8, end=6.1, confidence=0.97, speaker=0),
    ...
]
```

---

## Utility Functions

```python
def find_word_at_timestamp(words: List[Word], target_seconds: float) -> Optional[Word]:
    """Find the word closest to a given timestamp"""
    if not words:
        return None
    return min(words, key=lambda w: abs(w.start - target_seconds))

def find_sentence_boundary(words: List[Word], timestamp: float, direction: str = 'before') -> float:
    """
    Find nearest sentence boundary (period, question mark, etc.)
    direction: 'before' or 'after' the timestamp
    """
    sentence_enders = {'.', '?', '!'}
    
    if direction == 'before':
        for word in reversed(words):
            if word.end <= timestamp and word.text[-1] in sentence_enders:
                return word.end
        return words[0].start if words else 0
    else:
        for word in words:
            if word.start >= timestamp and word.text[-1] in sentence_enders:
                return word.end
        return words[-1].end if words else 0
```

---

## Testing Strategy

### Unit Tests
```python
# tests/test_transcriber.py

def test_process_response_extracts_words():
    """Verify word extraction from mock Deepgram response"""
    
def test_build_timestamped_transcript_format():
    """Verify [HH:MM:SS] Speaker X: format"""
    
def test_format_timestamp_edge_cases():
    """Test 0 seconds, hours > 99, etc."""
    
def test_find_word_at_timestamp():
    """Verify closest word is found"""
    
def test_find_sentence_boundary_before():
    """Verify sentence boundary detection"""
```

### Integration Test
```python
async def test_transcribe_real_audio():
    """Test with real 5-min audio file"""
    transcriber = Transcriber(os.getenv('DEEPGRAM_API_KEY'))
    result = await transcriber.transcribe('test_audio.wav')
    
    assert result.word_count > 0
    assert len(result.words) > 0
    assert '[00:' in result.timestamped_transcript
```

---

## Cost & Performance

| Video Length | Processing Time | Cost |
|--------------|-----------------|------|
| 5 min | ~10 sec | $0.02 |
| 1 hour | ~1 min | $0.26 |
| 4 hours | ~5 min | $1.03 |

---

## Implementation Steps

1. [ ] Create `src/transcriber.py` with class skeleton
2. [ ] Implement `Word` and `TranscriptData` dataclasses
3. [ ] Implement `__init__` with Deepgram client setup
4. [ ] Implement `transcribe()` async method
5. [ ] Implement `_process_response()` to extract words
6. [ ] Implement `_build_timestamped_transcript()`
7. [ ] Implement `_format_timestamp()` helper
8. [ ] Implement `_get_speaker_stats()`
9. [ ] Add utility functions
10. [ ] Create unit tests with mock data
11. [ ] Test with real Deepgram API

---

## Reference: Deepgram Response Structure

```json
{
  "results": {
    "channels": [{
      "alternatives": [{
        "transcript": "full text here",
        "words": [
          {
            "word": "So",
            "punctuated_word": "So",
            "start": 5.2,
            "end": 5.4,
            "confidence": 0.99,
            "speaker": 0
          }
        ],
        "paragraphs": {
          "paragraphs": [
            {
              "speaker": 0,
              "sentences": [
                {
                  "text": "So I was thinking about this.",
                  "start": 5.2,
                  "end": 8.5
                }
              ]
            }
          ]
        }
      }]
    }]
  }
}
```

---

## Common Pitfalls

1. **Forgetting async/await**: Deepgram SDK is async
2. **Not handling empty audio**: Check for empty words array
3. **Speaker ID not always present**: Use `word.get('speaker')` with default
4. **Timestamp precision**: Keep floats, don't round prematurely
5. **Memory with large files**: Stream if needed for very long videos
