"""
Smart Clip Finder - Finds viral clips with proper story structure.

Instead of segmenting by conversation, this analyzes the full transcript
in overlapping windows to find complete SETUP -> CONFLICT -> RESOLUTION arcs.
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


@dataclass
class SmartClip:
    """A clip with complete story structure."""
    clip_id: str
    title: str
    hook: str
    start_time: float  # seconds
    end_time: float    # seconds
    duration: float
    
    # Story structure
    setup_summary: str      # What question/claim triggers this
    conflict_summary: str   # The debate/argument
    resolution_summary: str # How it ends (gotcha, debunk, etc)
    
    clip_type: str  # debunk, gotcha, hot_take, etc
    virality_score: int
    why_viral: str
    
    # Transcript excerpt
    transcript_excerpt: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SmartClipFinder:
    """
    Finds viral clips by analyzing transcript with story structure requirements.
    """
    
    ANALYSIS_PROMPT = '''You are an expert at finding viral debate clips for TikTok/YouTube Shorts.

I'll give you a transcript segment from a debate podcast. Find the BEST 2-3 complete viral moments.

CRITICAL REQUIREMENTS:
1. Each clip MUST have a complete story arc:
   - SETUP: A claim, question, or statement that triggers the response (5-15 seconds)
   - CONFLICT: The debate/argument/explanation (30-90 seconds) 
   - RESOLUTION: A clear ending - gotcha moment, debunk landing, or natural conclusion (10-20 seconds)

2. Duration: 60-180 seconds total (longer is OK if the moment is exceptional)

3. Start Point: The clip should start at the QUESTION or CLAIM that triggers the interesting response.
   DO NOT start mid-argument. Start where the topic begins.

4. End Point: The clip should end AFTER the payoff moment lands.
   DO NOT cut off before the "gotcha" or debunk conclusion.
   Include any laugh, reaction, or mic-drop moment.

5. Timestamps: Return the EXACT timestamps from the transcript [HH:MM:SS] format.
   Convert to total seconds in your response.

CLIP TYPES TO FIND:
- debunk: Nick uses facts/logic to destroy a bad argument
- gotcha: Opponent contradicts themselves or gets caught
- hot_take: Controversial but compelling statement
- educational: Complex topic explained simply
- funny: Genuinely humorous exchange

TRANSCRIPT SEGMENT:
{transcript}

Return a JSON array (no other text):
[
  {{
    "title": "Short viral title (max 50 chars)",
    "hook": "First 10 words that hook viewers",
    "start_time_seconds": 3245.5,
    "end_time_seconds": 3380.2,
    "setup_summary": "Guest claims X happened because Y",
    "conflict_summary": "Nick explains why this is wrong using Z evidence",
    "resolution_summary": "Guest has no response, Nick delivers final point",
    "clip_type": "debunk",
    "virality_score": 8,
    "why_viral": "Clear winner, strong facts, quotable moment",
    "transcript_excerpt": "First 100 words of the clip..."
  }}
]

If no good clips exist in this segment, return: []
Find 2-3 clips maximum. Quality over quantity.'''

    def __init__(self, model_name: str = "gemini-2.0-flash"):
        """Initialize with Gemini model."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        logger.info(f"SmartClipFinder initialized with {model_name}")
    
    async def find_clips(
        self,
        transcript_path: str,
        min_virality: int = 7,
        window_size: int = 600,  # 10 minutes
        window_overlap: int = 120  # 2 minute overlap
    ) -> List[SmartClip]:
        """
        Find viral clips in transcript using sliding window analysis.
        
        Args:
            transcript_path: Path to transcript JSON
            min_virality: Minimum virality score (1-10)
            window_size: Analysis window in seconds
            window_overlap: Overlap between windows
            
        Returns:
            List of SmartClip objects, deduplicated and sorted by virality
        """
        # Load transcript
        with open(transcript_path, 'r', encoding='utf-8') as f:
            transcript_data = json.load(f)
        
        words = transcript_data['words']
        total_duration = transcript_data['duration']
        
        logger.info(f"Analyzing {total_duration/60:.0f} min transcript in {window_size}s windows")
        
        all_clips = []
        clip_id = 1
        
        # Slide through transcript
        current_time = 0
        window_num = 0
        
        while current_time < total_duration:
            window_num += 1
            window_end = min(current_time + window_size, total_duration)
            
            # Extract transcript segment with timestamps
            segment = self._extract_segment(words, current_time, window_end)
            
            if len(segment) < 500:  # Skip very short segments
                current_time += window_size - window_overlap
                continue
            
            logger.info(f"Window {window_num}: {current_time/60:.1f}-{window_end/60:.1f} min")
            
            # Find clips in this window
            try:
                clips = await self._analyze_segment(segment)
                
                for clip_data in clips:
                    if clip_data.get('virality_score', 0) >= min_virality:
                        clip = SmartClip(
                            clip_id=f"smart_{clip_id}",
                            title=clip_data.get('title', 'Untitled'),
                            hook=clip_data.get('hook', ''),
                            start_time=float(clip_data.get('start_time_seconds', 0)),
                            end_time=float(clip_data.get('end_time_seconds', 0)),
                            duration=float(clip_data.get('end_time_seconds', 0)) - float(clip_data.get('start_time_seconds', 0)),
                            setup_summary=clip_data.get('setup_summary', ''),
                            conflict_summary=clip_data.get('conflict_summary', ''),
                            resolution_summary=clip_data.get('resolution_summary', ''),
                            clip_type=clip_data.get('clip_type', 'unknown'),
                            virality_score=int(clip_data.get('virality_score', 0)),
                            why_viral=clip_data.get('why_viral', ''),
                            transcript_excerpt=clip_data.get('transcript_excerpt', '')
                        )
                        
                        # Validate clip
                        if clip.duration >= 45 and clip.start_time > 0:
                            all_clips.append(clip)
                            clip_id += 1
                            logger.info(f"  Found: {clip.title} ({clip.duration:.0f}s, score {clip.virality_score})")
                
            except Exception as e:
                logger.warning(f"Error analyzing window {window_num}: {e}")
            
            current_time += window_size - window_overlap
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)
        
        # Deduplicate overlapping clips
        clips = self._deduplicate_clips(all_clips)
        
        # Sort by virality score
        clips.sort(key=lambda c: -c.virality_score)
        
        logger.info(f"Found {len(clips)} unique clips")
        return clips
    
    def _extract_segment(
        self,
        words: List[Dict],
        start_time: float,
        end_time: float
    ) -> str:
        """Extract transcript segment with timestamps."""
        segment_words = [w for w in words if start_time <= w['start'] <= end_time]
        
        if not segment_words:
            return ""
        
        # Build transcript with speaker labels and timestamps
        lines = []
        current_speaker = None
        current_text = []
        current_start = None
        
        for word in segment_words:
            speaker = word.get('speaker', 0)
            speaker_label = "NICK" if speaker == 0 else "GUEST"
            
            if speaker_label != current_speaker:
                if current_text and current_start is not None:
                    ts = self._format_timestamp(current_start)
                    lines.append(f"[{ts}] {current_speaker}: {' '.join(current_text)}")
                
                current_speaker = speaker_label
                current_start = word['start']
                current_text = [word['text']]
            else:
                current_text.append(word['text'])
        
        # Final segment
        if current_text and current_start is not None:
            ts = self._format_timestamp(current_start)
            lines.append(f"[{ts}] {current_speaker}: {' '.join(current_text)}")
        
        return '\n'.join(lines)
    
    def _format_timestamp(self, seconds: float) -> str:
        """Convert seconds to HH:MM:SS."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    async def _analyze_segment(self, segment: str) -> List[Dict]:
        """Analyze segment with Gemini."""
        prompt = self.ANALYSIS_PROMPT.format(transcript=segment)
        
        response = await asyncio.to_thread(
            self.model.generate_content,
            prompt
        )
        
        # Parse JSON response
        text = response.text.strip()
        
        # Handle markdown code blocks
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        
        # Find JSON array
        if not text.startswith('['):
            start = text.find('[')
            end = text.rfind(']') + 1
            if start != -1 and end > start:
                text = text[start:end]
        
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse response: {e}")
            return []
    
    def _deduplicate_clips(self, clips: List[SmartClip]) -> List[SmartClip]:
        """Remove overlapping clips, keeping higher scored ones."""
        if not clips:
            return []
        
        # Sort by virality (higher first)
        clips.sort(key=lambda c: -c.virality_score)
        
        unique = []
        for clip in clips:
            # Check if this overlaps significantly with any kept clip
            dominated = False
            for kept in unique:
                overlap_start = max(clip.start_time, kept.start_time)
                overlap_end = min(clip.end_time, kept.end_time)
                overlap = max(0, overlap_end - overlap_start)
                
                # If >50% overlap, skip this clip
                if overlap > clip.duration * 0.5:
                    dominated = True
                    break
            
            if not dominated:
                unique.append(clip)
        
        return unique
    
    def save_clips(self, clips: List[SmartClip], output_path: str):
        """Save clips to JSON file."""
        data = {
            'total_clips': len(clips),
            'clips': [c.to_dict() for c in clips]
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved {len(clips)} clips to {output_path}")


async def main():
    """Run smart clip finder."""
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python smart_clip_finder.py <transcript.json> <output.json> [min_virality]")
        sys.exit(1)
    
    transcript_path = sys.argv[1]
    output_path = sys.argv[2]
    min_virality = int(sys.argv[3]) if len(sys.argv) > 3 else 7
    
    finder = SmartClipFinder()
    clips = await finder.find_clips(transcript_path, min_virality=min_virality)
    finder.save_clips(clips, output_path)
    
    print(f"\nFound {len(clips)} clips:")
    for clip in clips[:10]:
        print(f"\n{clip.clip_id}: {clip.title}")
        print(f"  Time: {clip.start_time/60:.1f}-{clip.end_time/60:.1f} min ({clip.duration:.0f}s)")
        print(f"  Score: {clip.virality_score}/10 | Type: {clip.clip_type}")
        print(f"  Setup: {clip.setup_summary[:60]}...")
        print(f"  Resolution: {clip.resolution_summary[:60]}...")


if __name__ == "__main__":
    asyncio.run(main())
