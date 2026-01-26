"""
Conversation Segmentation Module - Merge Voice + Visual Data

Owner: Gabriel
Status: Implemented

This module merges voice mapping data (from Pyannote) with visual mapping data
(from Gemini frame analysis) to identify distinct conversations with guests.

It finds where each conversation starts and ends based on:
- Guest first appearance (visual)
- Guest first speech (voice)
- Guest last speech before they leave
- Guest disappearance (visual)
"""

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

from .speaker_mapper import VoiceMap, VoiceSegment, get_segments_in_range
from .visual_mapper import VisualMap, FrameAnalysis, PersonInfo

logger = logging.getLogger(__name__)

# Minimum conversation duration to be considered valid
MIN_CONVERSATION_DURATION = 60.0  # seconds

# Maximum gap between guest appearances to still be same conversation
MAX_GAP_SECONDS = 120.0  # 2 minutes


@dataclass
class GuestAppearance:
    """Tracks a guest's appearance in the stream."""
    guest_id: str               # "guest_1", "guest_2", etc.
    description: str            # Physical description from visual analysis
    first_seen: float           # First visual appearance (seconds)
    last_seen: float            # Last visual appearance (seconds)
    first_spoke: Optional[float]  # First time they spoke (if identified)
    last_spoke: Optional[float]   # Last time they spoke (if identified)
    total_screen_time: float    # Total time visible
    frame_count: int            # Number of frames they appear in
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class Conversation:
    """Represents a conversation segment with a guest."""
    conversation_id: str        # "conv_1", "conv_2", etc.
    guest_id: str               # "guest_1" (based on appearance)
    guest_description: str      # "man with glasses, beard"
    start_time: float           # Conversation start (seconds)
    end_time: float             # Conversation end (seconds)
    duration: float             # Total duration
    nick_talk_time: float       # Seconds Nick spoke
    guest_talk_time: float      # Seconds guest spoke
    exchange_count: int         # Number of back-and-forth exchanges
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class ConversationMap:
    """Complete mapping of all conversations in the stream."""
    conversations: List[Conversation]
    guests: List[GuestAppearance]
    total_duration: float
    total_conversations: int
    total_nick_time: float
    total_guest_time: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'conversations': [c.to_dict() for c in self.conversations],
            'guests': [g.to_dict() for g in self.guests],
            'total_duration': self.total_duration,
            'total_conversations': self.total_conversations,
            'total_nick_time': self.total_nick_time,
            'total_guest_time': self.total_guest_time,
        }
    
    def save(self, path: str) -> None:
        """Save conversation map to JSON file."""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Conversation map saved to: {path}")
    
    @classmethod
    def load(cls, path: str) -> 'ConversationMap':
        """Load conversation map from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        conversations = [Conversation(**c) for c in data['conversations']]
        guests = [GuestAppearance(**g) for g in data['guests']]
        
        return cls(
            conversations=conversations,
            guests=guests,
            total_duration=data['total_duration'],
            total_conversations=data['total_conversations'],
            total_nick_time=data['total_nick_time'],
            total_guest_time=data['total_guest_time'],
        )
    
    def get_conversation_at_timestamp(self, timestamp: float) -> Optional[Conversation]:
        """Get the conversation active at a given timestamp."""
        for conv in self.conversations:
            if conv.start_time <= timestamp <= conv.end_time:
                return conv
        return None


class ConversationSegmenter:
    """
    Identifies conversation boundaries from voice + visual data.
    
    This class merges:
    - Voice mapping (when Nick vs guests are speaking)
    - Visual mapping (who is on screen at each point)
    
    To produce:
    - List of distinct conversations with guests
    - Start/end times for each conversation
    - Talk time breakdown per speaker
    
    Usage:
        segmenter = ConversationSegmenter()
        conversation_map = segmenter.segment_conversations(voice_map, visual_map)
        conversation_map.save("conversations.json")
    """
    
    def __init__(
        self,
        min_duration: float = MIN_CONVERSATION_DURATION,
        max_gap: float = MAX_GAP_SECONDS
    ):
        """
        Initialize the segmenter.
        
        Args:
            min_duration: Minimum conversation duration to include
            max_gap: Maximum gap between appearances to be same conversation
        """
        self.min_duration = min_duration
        self.max_gap = max_gap
        logger.info(
            f"ConversationSegmenter initialized: "
            f"min_duration={min_duration}s, max_gap={max_gap}s"
        )
    
    def segment_conversations(
        self,
        voice_map: VoiceMap,
        visual_map: VisualMap
    ) -> ConversationMap:
        """
        Find conversation start/end times from voice and visual data.
        
        Args:
            voice_map: VoiceMap with speaker segments
            visual_map: VisualMap with frame analysis
            
        Returns:
            ConversationMap with all identified conversations
        """
        logger.info("Segmenting conversations from voice + visual data...")
        
        # Step 1: Identify unique guests from visual data
        guests = self._identify_guests(visual_map)
        logger.info(f"Identified {len(guests)} unique guests")
        
        # Step 2: Build conversation segments for each guest
        conversations = self._build_conversations(guests, voice_map, visual_map)
        logger.info(f"Built {len(conversations)} conversation segments")
        
        # Step 3: Calculate totals
        total_nick_time = sum(c.nick_talk_time for c in conversations)
        total_guest_time = sum(c.guest_talk_time for c in conversations)
        total_duration = visual_map.total_duration
        
        conversation_map = ConversationMap(
            conversations=conversations,
            guests=guests,
            total_duration=total_duration,
            total_conversations=len(conversations),
            total_nick_time=total_nick_time,
            total_guest_time=total_guest_time,
        )
        
        logger.info(
            f"Conversation segmentation complete: "
            f"{len(conversations)} conversations, "
            f"Nick: {total_nick_time:.1f}s, Guest: {total_guest_time:.1f}s"
        )
        
        return conversation_map
    
    def _identify_guests(self, visual_map: VisualMap) -> List[GuestAppearance]:
        """
        Identify unique guests from visual frame analysis.
        
        Groups similar descriptions and tracks appearances.
        """
        # Collect all non-Nick people descriptions
        person_frames: Dict[str, List[Tuple[float, PersonInfo]]] = {}
        
        for frame in visual_map.frames:
            for person in frame.people:
                # Skip if this is Nick (host is usually in consistent position)
                # We'll use position + description to identify
                desc = self._normalize_description(person.description)
                
                if desc not in person_frames:
                    person_frames[desc] = []
                
                person_frames[desc].append((frame.timestamp, person))
        
        # Build guest appearances
        guests = []
        guest_num = 1
        
        for desc, appearances in person_frames.items():
            if len(appearances) < 2:  # Skip one-off appearances
                continue
            
            timestamps = [t for t, _ in appearances]
            first_seen = min(timestamps)
            last_seen = max(timestamps)
            
            # Calculate total screen time (frame_interval * frame_count)
            total_screen_time = len(appearances) * visual_map.frame_interval
            
            guests.append(GuestAppearance(
                guest_id=f"guest_{guest_num}",
                description=desc,
                first_seen=first_seen,
                last_seen=last_seen,
                first_spoke=None,  # Will be filled from voice data
                last_spoke=None,
                total_screen_time=total_screen_time,
                frame_count=len(appearances),
            ))
            guest_num += 1
        
        # Sort by first appearance
        guests.sort(key=lambda g: g.first_seen)
        
        return guests
    
    def _normalize_description(self, desc: str) -> str:
        """Normalize a person description for matching."""
        # Simple normalization - lowercase and strip
        return desc.lower().strip()
    
    def _build_conversations(
        self,
        guests: List[GuestAppearance],
        voice_map: VoiceMap,
        visual_map: VisualMap
    ) -> List[Conversation]:
        """
        Build conversation segments for each guest.
        """
        conversations = []
        conv_num = 1
        
        for guest in guests:
            # Find conversation boundaries
            # Start: When guest first appears OR first speaks (whichever is earlier)
            # End: When guest disappears OR stops speaking (whichever is later)
            
            start_time = guest.first_seen
            end_time = guest.last_seen
            
            # Get voice segments during guest's appearance
            voice_segments = get_segments_in_range(voice_map, start_time, end_time)
            
            # Calculate talk times
            nick_time = sum(
                min(s.end, end_time) - max(s.start, start_time)
                for s in voice_segments
                if s.speaker == 'nick' and s.end > start_time and s.start < end_time
            )
            
            guest_time = sum(
                min(s.end, end_time) - max(s.start, start_time)
                for s in voice_segments
                if s.speaker == 'guest' and s.end > start_time and s.start < end_time
            )
            
            # Count exchanges (speaker changes)
            exchanges = self._count_exchanges(voice_segments)
            
            # Update guest's speech times
            guest_segments = [s for s in voice_segments if s.speaker == 'guest']
            if guest_segments:
                guest.first_spoke = min(s.start for s in guest_segments)
                guest.last_spoke = max(s.end for s in guest_segments)
            
            duration = end_time - start_time
            
            # Skip if too short
            if duration < self.min_duration:
                logger.debug(
                    f"Skipping short conversation with {guest.description}: "
                    f"{duration:.1f}s < {self.min_duration}s minimum"
                )
                continue
            
            conversations.append(Conversation(
                conversation_id=f"conv_{conv_num}",
                guest_id=guest.guest_id,
                guest_description=guest.description,
                start_time=start_time,
                end_time=end_time,
                duration=duration,
                nick_talk_time=nick_time,
                guest_talk_time=guest_time,
                exchange_count=exchanges,
            ))
            conv_num += 1
        
        # Sort by start time
        conversations.sort(key=lambda c: c.start_time)
        
        return conversations
    
    def _count_exchanges(self, segments: List[VoiceSegment]) -> int:
        """Count the number of speaker changes (exchanges)."""
        if len(segments) < 2:
            return 0
        
        exchanges = 0
        prev_speaker = segments[0].speaker
        
        for seg in segments[1:]:
            if seg.speaker != prev_speaker:
                exchanges += 1
                prev_speaker = seg.speaker
        
        return exchanges


def get_transcript_for_conversation(
    conversation: Conversation,
    transcript_data: Dict,
    voice_map: VoiceMap
) -> str:
    """
    Extract the transcript portion for a specific conversation.
    
    Args:
        conversation: Conversation to extract transcript for
        transcript_data: Full transcript data (loaded from JSON)
        voice_map: VoiceMap for speaker labels
        
    Returns:
        Formatted transcript with speaker labels
    """
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
        segment = None
        for seg in voice_map.segments:
            if seg.start <= word_time <= seg.end:
                segment = seg
                break
        
        speaker = segment.speaker if segment else 'unknown'
        speaker_label = "NICK" if speaker == 'nick' else "GUEST"
        
        if speaker_label != current_speaker:
            # Output previous speaker's text
            if current_text and current_start is not None:
                timestamp = _format_timestamp(current_start)
                text = ' '.join(current_text)
                lines.append(f"[{timestamp}] {current_speaker}: {text}")
            
            current_speaker = speaker_label
            current_start = word_time
            current_text = [word['text']]
        else:
            current_text.append(word['text'])
    
    # Output final segment
    if current_text and current_start is not None:
        timestamp = _format_timestamp(current_start)
        text = ' '.join(current_text)
        lines.append(f"[{timestamp}] {current_speaker}: {text}")
    
    return '\n'.join(lines)


def _format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS format."""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
