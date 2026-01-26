"""
Quote-Based Clip Finder - Finds clips by searching for exact quotes.

This approach:
1. Has Gemini identify SPECIFIC MEMORABLE QUOTES from the transcript
2. Searches for those exact quotes to get precise timestamps
3. Expands around the quote to capture full context
"""

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Tuple

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


@dataclass
class QuoteClip:
    """A clip anchored by a specific quote."""
    clip_id: str
    title: str
    
    # The anchor quote and its timestamp
    anchor_quote: str
    anchor_time: float
    
    # Full clip boundaries
    start_time: float
    end_time: float
    duration: float
    
    # Story summary
    setup: str
    payoff: str
    
    clip_type: str
    virality_score: int
    why_viral: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class QuoteClipFinder:
    """Finds viral clips by anchoring on specific quotes."""
    
    QUOTE_PROMPT = '''Analyze this debate transcript and find 3-5 VIRAL MOMENTS.

For each moment, identify:
1. The EXACT "money quote" - the memorable line that makes this clip viral (10-20 words, MUST be exact text from transcript)
2. Who said it (NICK or GUEST)
3. What type of moment (debunk, gotcha, hot_take, educational, funny)
4. Why it's viral

CRITICAL: The "money_quote" MUST be the EXACT words from the transcript - I will search for this exact text.

Viral moments include:
- Nick destroying an argument with facts/logic
- Guest contradicting themselves or getting caught
- Nick delivering a mic-drop line
- A shocking claim or revelation
- A funny exchange

TRANSCRIPT:
{transcript}

Return JSON array (no other text):
[
  {{
    "money_quote": "You literally just proved me right because you never asked about",
    "speaker": "NICK",
    "moment_type": "gotcha",
    "title": "Guest Proves Nick Right!",
    "setup": "What question/claim leads to this",
    "payoff": "How the moment lands",
    "virality_score": 9,
    "why_viral": "Clear winner moment"
  }}
]

Find the 3-5 BEST moments. Return [] if none found.'''

    def __init__(self, model_name: str = "gemini-2.0-flash"):
        """Initialize with Gemini model."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        logger.info(f"QuoteClipFinder initialized with {model_name}")
    
    def _build_searchable_transcript(self, words: List[Dict]) -> Tuple[str, Dict[str, float]]:
        """Build transcript text and word-to-timestamp mapping."""
        # Build full text with markers
        text_parts = []
        word_positions = {}  # Maps character position to timestamp
        
        current_pos = 0
        for word in words:
            text = word['text']
            word_positions[current_pos] = word['start']
            text_parts.append(text)
            current_pos += len(text) + 1  # +1 for space
        
        full_text = ' '.join(text_parts)
        return full_text, word_positions
    
    def _find_quote_timestamp(
        self,
        quote: str,
        full_text: str,
        word_positions: Dict[int, float],
        words: List[Dict]
    ) -> Optional[float]:
        """Find the timestamp where a quote appears."""
        # Normalize quote for search
        quote_normalized = ' '.join(quote.lower().split())
        text_normalized = ' '.join(full_text.lower().split())
        
        # Try exact match first
        idx = text_normalized.find(quote_normalized)
        if idx != -1:
            # Find closest word position
            for pos, timestamp in sorted(word_positions.items()):
                if pos >= idx:
                    return timestamp
        
        # Try fuzzy match - find longest matching subsequence
        quote_words = quote_normalized.split()
        if len(quote_words) >= 3:
            # Search for 3-word windows
            for i in range(len(words) - 2):
                window = ' '.join(words[i+j]['text'].lower() for j in range(min(5, len(words)-i)))
                if quote_words[0] in window and quote_words[-1] in window:
                    return words[i]['start']
        
        return None
    
    def _format_transcript_segment(self, words: List[Dict], start: float, end: float) -> str:
        """Format transcript segment with speaker labels."""
        segment_words = [w for w in words if start <= w['start'] <= end]
        
        lines = []
        current_speaker = None
        current_text = []
        
        for word in segment_words:
            speaker = "NICK" if word.get('speaker', 0) == 0 else "GUEST"
            if speaker != current_speaker:
                if current_text:
                    lines.append(f"{current_speaker}: {' '.join(current_text)}")
                current_speaker = speaker
                current_text = [word['text']]
            else:
                current_text.append(word['text'])
        
        if current_text:
            lines.append(f"{current_speaker}: {' '.join(current_text)}")
        
        return '\n'.join(lines)
    
    async def find_clips(
        self,
        transcript_path: str,
        min_virality: int = 7,
        window_size: int = 600,
        context_before: float = 30,
        context_after: float = 45
    ) -> List[QuoteClip]:
        """
        Find viral clips anchored by specific quotes.
        
        Args:
            transcript_path: Path to transcript JSON
            min_virality: Minimum virality score
            window_size: Analysis window in seconds
            context_before: Seconds to include before quote
            context_after: Seconds to include after quote
        """
        with open(transcript_path, 'r', encoding='utf-8') as f:
            transcript_data = json.load(f)
        
        words = transcript_data['words']
        total_duration = transcript_data['duration']
        
        # Build searchable transcript
        full_text, word_positions = self._build_searchable_transcript(words)
        
        logger.info(f"Analyzing {total_duration/60:.0f} min transcript")
        
        all_clips = []
        clip_id = 1
        
        # Process in windows
        current_time = 0
        window_num = 0
        
        while current_time < total_duration:
            window_num += 1
            window_end = min(current_time + window_size, total_duration)
            
            # Get transcript segment for this window
            segment = self._format_transcript_segment(words, current_time, window_end)
            
            if len(segment) < 500:
                current_time += window_size - 60
                continue
            
            logger.info(f"Window {window_num}: {current_time/60:.1f}-{window_end/60:.1f} min")
            
            try:
                # Find quotes in this window
                quotes = await self._find_quotes(segment)
                
                for q in quotes:
                    if q.get('virality_score', 0) < min_virality:
                        continue
                    
                    # Find exact timestamp of quote
                    quote_text = q.get('money_quote', '')
                    timestamp = self._find_quote_timestamp(quote_text, full_text, word_positions, words)
                    
                    if timestamp is None:
                        logger.warning(f"  Could not find quote: {quote_text[:50]}...")
                        continue
                    
                    # Build clip around quote
                    start_time = max(0, timestamp - context_before)
                    end_time = min(total_duration, timestamp + context_after)
                    
                    # Expand to natural boundaries (look for speaker changes or pauses)
                    start_time, end_time = self._expand_to_natural_boundaries(
                        words, start_time, end_time, timestamp
                    )
                    
                    clip = QuoteClip(
                        clip_id=f"quote_{clip_id}",
                        title=q.get('title', 'Untitled'),
                        anchor_quote=quote_text,
                        anchor_time=timestamp,
                        start_time=start_time,
                        end_time=end_time,
                        duration=end_time - start_time,
                        setup=q.get('setup', ''),
                        payoff=q.get('payoff', ''),
                        clip_type=q.get('moment_type', 'unknown'),
                        virality_score=q.get('virality_score', 0),
                        why_viral=q.get('why_viral', '')
                    )
                    
                    if clip.duration >= 30:
                        all_clips.append(clip)
                        clip_id += 1
                        logger.info(f"  Found: {clip.title} @ {timestamp/60:.1f}min ({clip.duration:.0f}s)")
                
            except Exception as e:
                logger.warning(f"Error in window {window_num}: {e}")
            
            current_time += window_size - 60
            await asyncio.sleep(0.3)
        
        # Deduplicate
        clips = self._deduplicate(all_clips)
        clips.sort(key=lambda c: -c.virality_score)
        
        logger.info(f"Found {len(clips)} unique clips")
        return clips
    
    def _expand_to_natural_boundaries(
        self,
        words: List[Dict],
        start: float,
        end: float,
        anchor: float
    ) -> Tuple[float, float]:
        """Expand clip to natural speaker change boundaries."""
        # Find words in range
        range_words = [w for w in words if start - 30 <= w['start'] <= end + 30]
        
        if not range_words:
            return start, end
        
        # Look for speaker change before start
        new_start = start
        for i, w in enumerate(range_words):
            if w['start'] >= start:
                break
            # Look for speaker change
            if i > 0 and range_words[i-1].get('speaker') != w.get('speaker'):
                new_start = w['start']
        
        # Look for natural end (speaker change or pause after anchor)
        new_end = end
        in_end_zone = False
        for i, w in enumerate(range_words):
            if w['start'] >= anchor + 20:  # Past the anchor moment
                in_end_zone = True
            if in_end_zone and w['start'] >= end - 10:
                # Look for speaker change or pause
                if i < len(range_words) - 1:
                    gap = range_words[i+1]['start'] - w['end']
                    if gap > 1.0:  # Pause
                        new_end = w['end'] + 0.5
                        break
                    if range_words[i+1].get('speaker') != w.get('speaker'):
                        new_end = w['end'] + 0.5
                        break
        
        # Ensure minimum duration
        if new_end - new_start < 45:
            new_end = new_start + 60
        
        return new_start, min(new_end, words[-1]['end'])
    
    async def _find_quotes(self, segment: str) -> List[Dict]:
        """Find viral quotes in segment."""
        prompt = self.QUOTE_PROMPT.format(transcript=segment)
        
        response = await asyncio.to_thread(
            self.model.generate_content,
            prompt
        )
        
        text = response.text.strip()
        
        # Parse JSON
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        
        if not text.startswith('['):
            start = text.find('[')
            end = text.rfind(']') + 1
            if start != -1 and end > start:
                text = text[start:end]
        
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return []
    
    def _deduplicate(self, clips: List[QuoteClip]) -> List[QuoteClip]:
        """Remove overlapping clips."""
        clips.sort(key=lambda c: -c.virality_score)
        
        unique = []
        for clip in clips:
            overlaps = False
            for kept in unique:
                overlap_start = max(clip.start_time, kept.start_time)
                overlap_end = min(clip.end_time, kept.end_time)
                if overlap_end - overlap_start > clip.duration * 0.3:
                    overlaps = True
                    break
            if not overlaps:
                unique.append(clip)
        
        return unique
    
    def save_clips(self, clips: List[QuoteClip], output_path: str):
        """Save clips to JSON."""
        data = {
            'total_clips': len(clips),
            'clips': [c.to_dict() for c in clips]
        }
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(clips)} clips to {output_path}")


async def main():
    import sys
    logging.basicConfig(level=logging.INFO)
    
    finder = QuoteClipFinder()
    clips = await finder.find_clips(
        'outputs/episode_258_transcript.json',
        min_virality=7,
        context_before=40,
        context_after=50
    )
    finder.save_clips(clips, 'outputs/quote_clips.json')
    
    print(f"\nFound {len(clips)} clips:")
    for clip in clips[:15]:
        print(f"\n{clip.clip_id}: {clip.title}")
        print(f"  Quote: \"{clip.anchor_quote[:60]}...\"")
        print(f"  Time: {clip.start_time/60:.1f}-{clip.end_time/60:.1f} min ({clip.duration:.0f}s)")
        print(f"  Score: {clip.virality_score}/10")


if __name__ == "__main__":
    asyncio.run(main())
