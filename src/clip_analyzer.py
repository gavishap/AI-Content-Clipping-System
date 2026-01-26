"""
Clip Analysis Module - Gemini 3 Clip Detection

Owner: Gabriel
Status: Implemented

This module analyzes conversations to find clip-worthy moments using Gemini 3.
It looks for debate "debunk" moments, reactions, hot takes, and other viral content
within the boundaries of each conversation segment.
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

import google.generativeai as genai

from .conversation_segmenter import Conversation, ConversationMap

logger = logging.getLogger(__name__)

# Gemini model for clip analysis
GEMINI_MODEL = "gemini-2.0-flash"  # Using flash for cost efficiency

# Default prompt path
DEFAULT_PROMPT_PATH = "prompts/clip_detection.md"


@dataclass
class ClipCandidate:
    """A potential clip identified by the analyzer."""
    clip_id: str                # "clip_1", "clip_2", etc.
    conversation_id: str        # Which conversation this clip is from
    start_time: float           # Clip start (seconds)
    end_time: float             # Clip end (seconds)
    duration: float             # Clip duration
    clip_type: str              # "debunk" | "reaction" | "hot_take" | "gotcha" | "humor"
    hook: str                   # Opening hook text (first few words)
    peak_moment: str            # The key moment description
    suggested_title: str        # Suggested clip title
    virality_score: int         # 1-10 rating
    transcript_excerpt: str     # Relevant transcript portion
    reasoning: str              # Why this is a good clip
    platforms: List[str]        # Suggested platforms
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class ClipAnalysisResult:
    """Results from analyzing all conversations."""
    clips: List[ClipCandidate]
    total_clips: int
    by_conversation: Dict[str, int]     # conversation_id -> clip count
    by_type: Dict[str, int]             # clip_type -> count
    average_virality: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'clips': [c.to_dict() for c in self.clips],
            'total_clips': self.total_clips,
            'by_conversation': self.by_conversation,
            'by_type': self.by_type,
            'average_virality': self.average_virality,
        }
    
    def save(self, path: str) -> None:
        """Save clip analysis to JSON file."""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Clip analysis saved to: {path}")
    
    @classmethod
    def load(cls, path: str) -> 'ClipAnalysisResult':
        """Load clip analysis from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        clips = [ClipCandidate(**c) for c in data['clips']]
        
        return cls(
            clips=clips,
            total_clips=data['total_clips'],
            by_conversation=data['by_conversation'],
            by_type=data['by_type'],
            average_virality=data['average_virality'],
        )
    
    def get_top_clips(self, n: int = 10) -> List[ClipCandidate]:
        """Get top N clips by virality score."""
        sorted_clips = sorted(self.clips, key=lambda c: c.virality_score, reverse=True)
        return sorted_clips[:n]
    
    def get_clips_for_conversation(self, conversation_id: str) -> List[ClipCandidate]:
        """Get all clips from a specific conversation."""
        return [c for c in self.clips if c.conversation_id == conversation_id]


class ClipAnalyzer:
    """
    Analyzes conversations for clip-worthy moments using Gemini 3.
    
    This class takes conversation segments and their transcripts,
    then uses Gemini to identify moments that would make good clips:
    - Debate "debunk" moments where Nick defeats an argument
    - Strong reactions
    - Hot takes
    - Gotcha moments
    - Humor
    
    Usage:
        analyzer = ClipAnalyzer(api_key)
        result = await analyzer.analyze_all_conversations(
            conversation_map, 
            transcript_data,
            voice_map
        )
        result.save("clips.json")
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        prompt_path: Optional[str] = None
    ):
        """
        Initialize with Gemini API key.
        
        Args:
            api_key: Gemini API key from Google AI Studio
                     If not provided, reads from GEMINI_API_KEY env var
            prompt_path: Path to clip detection prompt file
        """
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError(
                "Gemini API key required. Set GEMINI_API_KEY env var "
                "or pass api_key parameter."
            )
        
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(GEMINI_MODEL)
        
        # Load prompt template
        self.prompt_template = self._load_prompt(prompt_path)
        
        logger.info(f"ClipAnalyzer initialized with Gemini model: {GEMINI_MODEL}")
    
    def _load_prompt(self, prompt_path: Optional[str]) -> str:
        """Load the clip detection prompt template."""
        if prompt_path:
            path = Path(prompt_path)
        else:
            # Try default path
            path = Path(DEFAULT_PROMPT_PATH)
            if not path.exists():
                # Use embedded default prompt
                return self._get_default_prompt()
        
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            return self._get_default_prompt()
    
    def _get_default_prompt(self) -> str:
        """Get the default clip detection prompt."""
        return """# CLIP DETECTION PROMPT

You are analyzing a conversation from a debate/podcast stream to find clip-worthy moments.

## CONVERSATION CONTEXT
Guest: {{GUEST_DESCRIPTION}}
Duration: {{DURATION}}
Start Time: {{START_TIME}}
End Time: {{END_TIME}}

## TRANSCRIPT (with speaker labels)
{{TRANSCRIPT}}

## WHAT TO LOOK FOR

Find moments where:
1. **DEBUNK**: Nick makes a strong counter-argument that defeats the guest's claim
2. **GOTCHA**: Nick catches the guest in a contradiction or logical error
3. **REACTION**: Nick has a memorable reaction (shock, frustration, laughter)
4. **HOT_TAKE**: Nick makes a bold, controversial statement
5. **HUMOR**: A genuinely funny moment

## CLIP REQUIREMENTS

- **Duration**: 30-90 seconds (optimal: 45-60 seconds)
- **Start**: Must begin with context (what Nick is responding to) - don't start mid-sentence
- **End**: Must have resolution (reaction, conclusion, or decisive moment) - don't end abruptly
- **Standalone**: Clip must make sense without watching the full stream
- **Within bounds**: All timestamps must be between {{START_TIME}} and {{END_TIME}}

## OUTPUT FORMAT

Return ONLY valid JSON array:
```json
[
  {
    "start_time": 125.5,
    "end_time": 172.3,
    "clip_type": "debunk",
    "hook": "Wait, did you just say...",
    "peak_moment": "Nick points out the logical contradiction",
    "suggested_title": "Guest Gets DESTROYED by Simple Logic",
    "virality_score": 8,
    "transcript_excerpt": "First 50 words of the clip...",
    "reasoning": "Strong gotcha moment with clear winner",
    "platforms": ["TikTok", "YouTube Shorts"]
  }
]
```

Find 3-5 best clips from this conversation. If no good clips exist, return empty array [].
Return ONLY the JSON array, no other text."""
    
    async def analyze_all_conversations(
        self,
        conversation_map: ConversationMap,
        transcript_data: Dict,
        voice_map: Any,  # VoiceMap type
        min_virality: int = 5
    ) -> ClipAnalysisResult:
        """
        Analyze all conversations for clip-worthy moments.
        
        Args:
            conversation_map: ConversationMap with all conversations
            transcript_data: Full transcript data (loaded from JSON)
            voice_map: VoiceMap for speaker labels
            min_virality: Minimum virality score to include
            
        Returns:
            ClipAnalysisResult with all identified clips
        """
        logger.info(
            f"Analyzing {len(conversation_map.conversations)} conversations for clips..."
        )
        
        all_clips = []
        clip_num = 1
        by_conversation = {}
        by_type = {}
        
        for conv in conversation_map.conversations:
            logger.info(f"Analyzing conversation: {conv.conversation_id} ({conv.duration:.1f}s)")
            
            try:
                clips = await self.analyze_conversation(
                    conv, transcript_data, voice_map
                )
                
                # Filter by virality and assign IDs
                for clip in clips:
                    if clip.virality_score >= min_virality:
                        clip.clip_id = f"clip_{clip_num}"
                        all_clips.append(clip)
                        clip_num += 1
                        
                        # Update counts
                        by_conversation[conv.conversation_id] = \
                            by_conversation.get(conv.conversation_id, 0) + 1
                        by_type[clip.clip_type] = by_type.get(clip.clip_type, 0) + 1
                
                logger.info(f"  Found {len(clips)} clips (above min_virality: {min_virality})")
                
            except Exception as e:
                logger.error(f"Failed to analyze {conv.conversation_id}: {e}")
        
        # Calculate average virality
        avg_virality = (
            sum(c.virality_score for c in all_clips) / len(all_clips)
            if all_clips else 0.0
        )
        
        result = ClipAnalysisResult(
            clips=all_clips,
            total_clips=len(all_clips),
            by_conversation=by_conversation,
            by_type=by_type,
            average_virality=avg_virality,
        )
        
        logger.info(
            f"Clip analysis complete: {len(all_clips)} clips found, "
            f"avg virality: {avg_virality:.1f}"
        )
        
        return result
    
    async def analyze_conversation(
        self,
        conversation: Conversation,
        transcript_data: Dict,
        voice_map: Any
    ) -> List[ClipCandidate]:
        """
        Analyze a single conversation for clip-worthy moments.
        
        Args:
            conversation: Conversation to analyze
            transcript_data: Full transcript data
            voice_map: VoiceMap for speaker labels
            
        Returns:
            List of ClipCandidate objects
        """
        # Extract transcript for this conversation
        transcript_segment = self._extract_transcript(
            conversation, transcript_data, voice_map
        )
        
        if not transcript_segment:
            logger.warning(f"No transcript found for {conversation.conversation_id}")
            return []
        
        # Build prompt
        prompt = self._build_prompt(conversation, transcript_segment)
        
        # Call Gemini
        response = await asyncio.to_thread(
            self.model.generate_content,
            prompt
        )
        
        # Parse response
        clips = self._parse_response(response.text, conversation)
        
        return clips
    
    def _extract_transcript(
        self,
        conversation: Conversation,
        transcript_data: Dict,
        voice_map: Any
    ) -> str:
        """Extract the transcript portion for a conversation."""
        words = transcript_data.get('words', [])
        
        # Filter words within conversation time range
        conv_words = [
            w for w in words
            if conversation.start_time <= w['start'] <= conversation.end_time
        ]
        
        if not conv_words:
            return ""
        
        # Build transcript with speaker labels
        lines = []
        current_speaker = None
        current_text = []
        current_start = None
        
        for word in conv_words:
            # Determine speaker from voice map
            word_time = word['start']
            speaker = 'unknown'
            
            for seg in voice_map.segments:
                if seg.start <= word_time <= seg.end:
                    speaker = seg.speaker
                    break
            
            speaker_label = "NICK" if speaker == 'nick' else "GUEST"
            
            if speaker_label != current_speaker:
                # Output previous speaker's text
                if current_text and current_start is not None:
                    timestamp = self._format_timestamp(current_start)
                    text = ' '.join(current_text)
                    lines.append(f"[{timestamp}] {current_speaker}: {text}")
                
                current_speaker = speaker_label
                current_start = word_time
                current_text = [word['text']]
            else:
                current_text.append(word['text'])
        
        # Output final segment
        if current_text and current_start is not None:
            timestamp = self._format_timestamp(current_start)
            text = ' '.join(current_text)
            lines.append(f"[{timestamp}] {current_speaker}: {text}")
        
        return '\n'.join(lines)
    
    def _format_timestamp(self, seconds: float) -> str:
        """Convert seconds to HH:MM:SS format."""
        hours, remainder = divmod(int(seconds), 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def _build_prompt(
        self,
        conversation: Conversation,
        transcript_segment: str
    ) -> str:
        """Build the prompt for clip detection."""
        # Format times
        start_str = self._format_timestamp(conversation.start_time)
        end_str = self._format_timestamp(conversation.end_time)
        duration_str = f"{conversation.duration / 60:.1f} minutes"
        
        prompt = self.prompt_template
        prompt = prompt.replace("{{GUEST_DESCRIPTION}}", conversation.guest_description)
        prompt = prompt.replace("{{DURATION}}", duration_str)
        prompt = prompt.replace("{{START_TIME}}", start_str)
        prompt = prompt.replace("{{END_TIME}}", end_str)
        prompt = prompt.replace("{{TRANSCRIPT}}", transcript_segment)
        
        return prompt
    
    def _parse_response(
        self,
        response_text: str,
        conversation: Conversation
    ) -> List[ClipCandidate]:
        """Parse Gemini response into ClipCandidate objects."""
        try:
            # Try to extract JSON from response
            json_str = response_text.strip()
            
            # Handle markdown code blocks
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]
            
            clips_data = json.loads(json_str)
            
            if not isinstance(clips_data, list):
                logger.warning(f"Expected list, got {type(clips_data)}")
                return []
            
            clips = []
            for data in clips_data:
                # Get timestamps from Gemini
                start = float(data.get('start_time', 0))
                end = float(data.get('end_time', 0))
                
                # Check if timestamps are relative (smaller than conversation start)
                # If so, convert to absolute by adding conversation start time
                if start < conversation.start_time and end < conversation.start_time:
                    # Gemini returned relative timestamps, convert to absolute
                    start = conversation.start_time + start
                    end = conversation.start_time + end
                    logger.debug(f"Converted relative timestamps to absolute: {start}-{end}")
                
                # Validate and clamp to conversation bounds
                if start < conversation.start_time or end > conversation.end_time:
                    logger.debug(
                        f"Clamping clip timestamps to conversation bounds: "
                        f"{start}-{end} -> {conversation.start_time}-{conversation.end_time}"
                    )
                    start = max(start, conversation.start_time)
                    end = min(end, conversation.end_time)
                
                clips.append(ClipCandidate(
                    clip_id="",  # Will be assigned later
                    conversation_id=conversation.conversation_id,
                    start_time=start,
                    end_time=end,
                    duration=end - start,
                    clip_type=data.get('clip_type', 'unknown'),
                    hook=data.get('hook', ''),
                    peak_moment=data.get('peak_moment', ''),
                    suggested_title=data.get('suggested_title', ''),
                    virality_score=int(data.get('virality_score', 5)),
                    transcript_excerpt=data.get('transcript_excerpt', ''),
                    reasoning=data.get('reasoning', ''),
                    platforms=data.get('platforms', ['TikTok', 'YouTube Shorts']),
                ))
            
            return clips
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse Gemini response: {e}")
            logger.debug(f"Response was: {response_text[:500]}")
            return []
    
    def analyze_conversation_sync(
        self,
        conversation: Conversation,
        transcript_data: Dict,
        voice_map: Any
    ) -> List[ClipCandidate]:
        """Synchronous wrapper for analyze_conversation."""
        return asyncio.run(
            self.analyze_conversation(conversation, transcript_data, voice_map)
        )
    
    def analyze_all_conversations_sync(
        self,
        conversation_map: ConversationMap,
        transcript_data: Dict,
        voice_map: Any,
        min_virality: int = 5
    ) -> ClipAnalysisResult:
        """Synchronous wrapper for analyze_all_conversations."""
        return asyncio.run(
            self.analyze_all_conversations(
                conversation_map, transcript_data, voice_map, min_virality
            )
        )
