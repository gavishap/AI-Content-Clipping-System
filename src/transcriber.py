"""
Transcription Module - Deepgram Nova-3 Integration

Owner: Gabriel
Status: Implemented

This module handles audio transcription with word-level timestamps.
Uses Deepgram SDK v5+ with the latest API structure.
See docs/TRANSCRIBER_TASK.md for implementation details.
"""

import json
import logging
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

from deepgram import DeepgramClient

logger = logging.getLogger(__name__)

# Timeout in seconds for large audio files (3+ hours)
# Deepgram can take 5-10 minutes to process very long files
LONG_FILE_TIMEOUT = 1800  # 30 minutes


@dataclass
class Word:
    """Represents a single word with timestamp and metadata."""
    text: str
    start: float  # Seconds
    end: float    # Seconds
    confidence: float  # 0-1
    speaker: Optional[int] = None


@dataclass
class TranscriptData:
    """Complete transcript data from Deepgram."""
    full_transcript: str
    timestamped_transcript: str  # For AI prompt input
    words: List[Word]
    word_count: int
    duration: float
    speakers: Dict[int, Dict]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'full_transcript': self.full_transcript,
            'timestamped_transcript': self.timestamped_transcript,
            'words': [asdict(w) for w in self.words],
            'word_count': self.word_count,
            'duration': self.duration,
            'speakers': self.speakers,
        }
    
    def save(self, path: str) -> None:
        """Save transcript data to JSON file."""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Transcript saved to: {path}")


class Transcriber:
    """
    Transcribes audio files using Deepgram Nova-3 API (SDK v5+).
    
    Deepgram handles long audio files (3-4+ hours) natively without chunking.
    Processing time: ~5 min for 4-hour video.
    Cost: ~$0.0043/min (~$1.03 for 4 hours)
    
    Usage:
        transcriber = Transcriber(api_key)
        result = transcriber.transcribe_sync("audio.wav")
        # Or with async:
        result = await transcriber.transcribe("audio.wav")
    """
    
    # Default Deepgram options optimized for clip detection
    DEFAULT_OPTIONS = {
        'model': 'nova-3',  # Latest & best accuracy model
        'language': 'en',
        'punctuate': True,  # Add punctuation
        'diarize': True,  # Speaker identification
        'smart_format': True,  # Format numbers, dates
        'filler_words': True,  # Keep "um", "uh" for natural feel
        'utterances': True,  # Sentence boundaries
        'paragraphs': True,  # Paragraph breaks
    }
    
    def __init__(self, api_key: Optional[str] = None, timeout: float = LONG_FILE_TIMEOUT):
        """
        Initialize with Deepgram API key.
        
        Args:
            api_key: Deepgram API key from console.deepgram.com
                     If not provided, reads from DEEPGRAM_API_KEY env var
            timeout: Request timeout in seconds (default: 30 minutes for long files)
        """
        # Get API key from parameter or environment
        key = api_key or os.getenv('DEEPGRAM_API_KEY')
        
        # Configure client with extended timeout for large files
        self.client = DeepgramClient(api_key=key, timeout=timeout)
        logger.info(f"Transcriber initialized with Deepgram SDK v5 (timeout: {timeout}s)")
    
    def transcribe_sync(self, audio_path: str, options: Optional[Dict] = None) -> TranscriptData:
        """
        Transcribe audio file with word-level timestamps (synchronous).
        
        Args:
            audio_path: Path to WAV audio file (16kHz mono recommended)
            options: Optional dict to override default Deepgram options
            
        Returns:
            TranscriptData with full transcript, timestamps, and word data
            
        Raises:
            FileNotFoundError: If audio file doesn't exist
            RuntimeError: If transcription fails
        """
        audio_file = Path(audio_path)
        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        file_size_mb = audio_file.stat().st_size / (1024 * 1024)
        logger.info(f"Starting transcription: {audio_file.name} ({file_size_mb:.1f} MB)")
        
        # Merge custom options with defaults
        transcribe_options = {**self.DEFAULT_OPTIONS, **(options or {})}
        
        try:
            # Read audio file as bytes
            with open(audio_path, 'rb') as f:
                audio_data = f.read()
            
            # Call Deepgram API using SDK v5 structure
            logger.info("Sending audio to Deepgram API...")
            response = self.client.listen.v1.media.transcribe_file(
                request=audio_data,
                **transcribe_options
            )
            
            # Process response
            result = self._process_response(response)
            
            logger.info(
                f"Transcription complete: {result.word_count} words, "
                f"{len(result.speakers)} speakers, "
                f"{result.duration:.1f}s duration"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise RuntimeError(f"Transcription failed: {e}") from e
    
    async def transcribe(self, audio_path: str, options: Optional[Dict] = None) -> TranscriptData:
        """
        Async version of transcribe (wraps sync for compatibility).
        
        Args:
            audio_path: Path to WAV audio file
            options: Optional dict to override default Deepgram options
            
        Returns:
            TranscriptData with full transcript, timestamps, and word data
        """
        # SDK v5 uses sync API, wrap for async compatibility
        return self.transcribe_sync(audio_path, options)
    
    def _process_response(self, response: Any) -> TranscriptData:
        """
        Convert Deepgram response to TranscriptData.
        
        Args:
            response: Deepgram API response object (Pydantic model or dict)
            
        Returns:
            TranscriptData with extracted information
        """
        # Convert Pydantic model to dict (SDK v5 uses Pydantic)
        if hasattr(response, 'model_dump'):
            result = response.model_dump()
        elif hasattr(response, 'to_dict'):
            result = response.to_dict()
        elif hasattr(response, 'dict'):
            result = response.dict()
        else:
            result = response
        
        # Navigate to the channel/alternatives structure
        channels = result.get('results', {}).get('channels', [])
        if not channels:
            raise RuntimeError("No audio channels in response")
        
        alternative = channels[0].get('alternatives', [{}])[0]
        
        # Extract full transcript
        full_transcript = alternative.get('transcript', '')
        
        # Extract words with timestamps
        words = self._extract_words(alternative.get('words', []))
        
        # Build timestamped transcript for AI
        paragraphs_data = alternative.get('paragraphs', {})
        timestamped_transcript = self._build_timestamped_transcript(paragraphs_data, words)
        
        # Get duration from metadata
        metadata = result.get('metadata', {})
        duration = metadata.get('duration', 0)
        if duration == 0 and words:
            duration = words[-1].end
        
        # Calculate speaker stats
        speakers = self._get_speaker_stats(words)
        
        return TranscriptData(
            full_transcript=full_transcript,
            timestamped_transcript=timestamped_transcript,
            words=words,
            word_count=len(words),
            duration=duration,
            speakers=speakers,
        )
    
    def _extract_words(self, words_data: List[Dict]) -> List[Word]:
        """
        Extract Word objects from Deepgram words array.
        
        Args:
            words_data: List of word dicts from Deepgram
            
        Returns:
            List of Word dataclass instances
        """
        words = []
        for w in words_data:
            word = Word(
                text=w.get('punctuated_word', w.get('word', '')),
                start=float(w.get('start', 0)),
                end=float(w.get('end', 0)),
                confidence=float(w.get('confidence', 0)),
                speaker=w.get('speaker'),
            )
            words.append(word)
        return words
    
    def _build_timestamped_transcript(
        self, 
        paragraphs_data: Dict, 
        words: List[Word]
    ) -> str:
        """
        Build transcript with timestamps for AI analysis.
        Format: [HH:MM:SS] Speaker X: Text
        
        Args:
            paragraphs_data: Deepgram paragraphs structure
            words: List of Word objects
            
        Returns:
            Formatted transcript string
        """
        lines = []
        
        paragraphs = paragraphs_data.get('paragraphs', [])
        
        if paragraphs:
            # Use paragraph/sentence structure from Deepgram
            for para in paragraphs:
                speaker = para.get('speaker', 0)
                sentences = para.get('sentences', [])
                
                for sentence in sentences:
                    start = sentence.get('start', 0)
                    text = sentence.get('text', '')
                    
                    timestamp = self._format_timestamp(start)
                    lines.append(f"[{timestamp}] Speaker {speaker}: {text}")
        else:
            # Fallback: group words by speaker changes
            if not words:
                return ""
            
            current_speaker = words[0].speaker
            current_start = words[0].start
            current_text = []
            
            for word in words:
                if word.speaker != current_speaker:
                    # Speaker changed, output current segment
                    if current_text:
                        timestamp = self._format_timestamp(current_start)
                        text = ' '.join(current_text)
                        speaker_id = current_speaker if current_speaker is not None else 0
                        lines.append(f"[{timestamp}] Speaker {speaker_id}: {text}")
                    
                    current_speaker = word.speaker
                    current_start = word.start
                    current_text = [word.text]
                else:
                    current_text.append(word.text)
            
            # Output final segment
            if current_text:
                timestamp = self._format_timestamp(current_start)
                text = ' '.join(current_text)
                speaker_id = current_speaker if current_speaker is not None else 0
                lines.append(f"[{timestamp}] Speaker {speaker_id}: {text}")
        
        return '\n'.join(lines)
    
    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        """Convert seconds to HH:MM:SS format."""
        hours, remainder = divmod(int(seconds), 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def _get_speaker_stats(self, words: List[Word]) -> Dict[int, Dict]:
        """
        Calculate speaking time and word count per speaker.
        
        Args:
            words: List of Word objects
            
        Returns:
            Dict mapping speaker ID to stats dict
        """
        stats: Dict[int, Dict] = {}
        
        for word in words:
            speaker_id = word.speaker if word.speaker is not None else 0
            
            if speaker_id not in stats:
                stats[speaker_id] = {
                    'word_count': 0,
                    'duration': 0.0,
                    'first_word_time': word.start,
                    'last_word_time': word.end,
                }
            
            stats[speaker_id]['word_count'] += 1
            stats[speaker_id]['duration'] += (word.end - word.start)
            stats[speaker_id]['last_word_time'] = word.end
        
        return stats


# Utility functions for timestamp refinement

def find_word_at_timestamp(words: List[Word], target_seconds: float) -> Optional[Word]:
    """Find the word closest to a given timestamp."""
    if not words:
        return None
    return min(words, key=lambda w: abs(w.start - target_seconds))


def find_sentence_boundary(
    words: List[Word], 
    timestamp: float, 
    direction: str = "before"
) -> float:
    """
    Find nearest sentence boundary (period, question mark, etc.)
    
    Args:
        words: List of Word objects with timestamps
        timestamp: Target timestamp in seconds
        direction: "before" or "after" the timestamp
        
    Returns:
        Timestamp of the sentence boundary
    """
    sentence_enders = {'.', '?', '!'}
    
    if direction == "before":
        for word in reversed(words):
            if word.end <= timestamp and word.text and word.text[-1] in sentence_enders:
                return word.end
        return words[0].start if words else 0
    else:
        for word in words:
            if word.start >= timestamp and word.text and word.text[-1] in sentence_enders:
                return word.end
        return words[-1].end if words else 0
