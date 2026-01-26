"""
Visual Mapping Module - Frame Extraction + Gemini 3 Analysis

Owner: Gabriel
Status: Implemented

This module extracts frames from video at regular intervals and analyzes
them with Gemini 3 to identify who is on screen (panel layout, people visible,
who appears to be speaking).

Used to build a visual timeline of the stream.
"""

import asyncio
import base64
import json
import logging
import os
import subprocess
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Optional, Dict, Any

import google.generativeai as genai

logger = logging.getLogger(__name__)

# Default frame extraction interval
DEFAULT_INTERVAL_SECONDS = 30

# Gemini model to use
GEMINI_MODEL = "gemini-2.0-flash"  # Use flash for cost efficiency on batch images

# Batch size for Gemini API calls
BATCH_SIZE = 10  # Process 10 frames at a time


@dataclass
class PersonInfo:
    """Information about a person visible in a frame."""
    description: str            # "man with beard, glasses"
    position: str               # "left", "right", "center", "top-left", etc.
    appears_speaking: bool      # Based on mouth open, highlighted box, etc.
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class FrameAnalysis:
    """Analysis result for a single video frame."""
    timestamp: float            # seconds into video
    frame_path: str             # path to extracted frame image
    people_count: int
    people: List[PersonInfo]
    nick_visible: bool          # Based on known position/appearance
    layout_type: str            # "solo" | "two_panel" | "multi_panel" | "other"
    on_screen_text: List[str]   # Any visible names or text
    raw_analysis: str           # Full Gemini response for debugging
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'timestamp': self.timestamp,
            'frame_path': self.frame_path,
            'people_count': self.people_count,
            'people': [p.to_dict() for p in self.people],
            'nick_visible': self.nick_visible,
            'layout_type': self.layout_type,
            'on_screen_text': self.on_screen_text,
            'raw_analysis': self.raw_analysis,
        }


@dataclass
class VisualMap:
    """Complete visual mapping for a video."""
    frames: List[FrameAnalysis]
    total_duration: float
    frame_interval: int         # seconds between frames
    total_frames: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'frames': [f.to_dict() for f in self.frames],
            'total_duration': self.total_duration,
            'frame_interval': self.frame_interval,
            'total_frames': self.total_frames,
        }
    
    def save(self, path: str) -> None:
        """Save visual map to JSON file."""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Visual map saved to: {path}")
    
    @classmethod
    def load(cls, path: str) -> 'VisualMap':
        """Load visual map from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        frames = []
        for f_data in data['frames']:
            people = [PersonInfo(**p) for p in f_data['people']]
            frames.append(FrameAnalysis(
                timestamp=f_data['timestamp'],
                frame_path=f_data['frame_path'],
                people_count=f_data['people_count'],
                people=people,
                nick_visible=f_data['nick_visible'],
                layout_type=f_data['layout_type'],
                on_screen_text=f_data['on_screen_text'],
                raw_analysis=f_data.get('raw_analysis', ''),
            ))
        
        return cls(
            frames=frames,
            total_duration=data['total_duration'],
            frame_interval=data['frame_interval'],
            total_frames=data['total_frames'],
        )
    
    def get_frame_at_timestamp(self, timestamp: float) -> Optional[FrameAnalysis]:
        """Get the frame analysis closest to a timestamp."""
        if not self.frames:
            return None
        
        closest = min(self.frames, key=lambda f: abs(f.timestamp - timestamp))
        return closest
    
    def get_frames_in_range(self, start: float, end: float) -> List[FrameAnalysis]:
        """Get all frames within a time range."""
        return [f for f in self.frames if start <= f.timestamp <= end]


class VisualMapper:
    """
    Extracts and analyzes video frames to map who is on screen.
    
    This class extracts frames at regular intervals using FFmpeg,
    then analyzes each frame with Gemini 3 to identify:
    - Number of people visible
    - Physical descriptions of each person
    - Who appears to be speaking
    - Panel layout type
    - Any on-screen text/names
    
    Usage:
        mapper = VisualMapper(api_key)
        frame_paths = mapper.extract_frames("video.mp4", interval=30)
        visual_map = await mapper.analyze_frames(frame_paths)
        visual_map.save("visual_map.json")
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize with Gemini API key.
        
        Args:
            api_key: Gemini API key from Google AI Studio
                     If not provided, reads from GEMINI_API_KEY env var
        """
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError(
                "Gemini API key required. Set GEMINI_API_KEY env var "
                "or pass api_key parameter."
            )
        
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(GEMINI_MODEL)
        logger.info(f"VisualMapper initialized with Gemini model: {GEMINI_MODEL}")
    
    def extract_frames(
        self,
        video_path: str,
        output_dir: Optional[str] = None,
        interval: int = DEFAULT_INTERVAL_SECONDS
    ) -> List[str]:
        """
        Extract frames from video at regular intervals using FFmpeg.
        
        Args:
            video_path: Path to video file
            output_dir: Directory to save frames (defaults to video dir)
            interval: Seconds between frames
            
        Returns:
            List of paths to extracted frame images
        """
        video_file = Path(video_path)
        if not video_file.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        # Create output directory
        if output_dir:
            frames_dir = Path(output_dir)
        else:
            frames_dir = video_file.parent / f"{video_file.stem}_frames"
        
        frames_dir.mkdir(parents=True, exist_ok=True)
        
        # Get video duration
        duration = self._get_video_duration(video_path)
        expected_frames = int(duration / interval) + 1
        
        logger.info(
            f"Extracting frames from {video_file.name}: "
            f"{duration:.1f}s duration, {interval}s interval, "
            f"~{expected_frames} frames expected"
        )
        
        # FFmpeg command to extract frames
        # fps=1/interval extracts one frame every N seconds
        output_pattern = str(frames_dir / "frame_%05d.jpg")
        
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vf", f"fps=1/{interval}",
            "-q:v", "2",  # High quality JPEG
            "-y",  # Overwrite existing
            output_pattern
        ]
        
        logger.info(f"Running FFmpeg: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            logger.error(f"FFmpeg stderr: {result.stderr}")
            raise RuntimeError(f"FFmpeg frame extraction failed: {result.stderr}")
        
        # Get list of extracted frames
        frame_paths = sorted(frames_dir.glob("frame_*.jpg"))
        
        logger.info(f"Extracted {len(frame_paths)} frames to {frames_dir}")
        
        return [str(p) for p in frame_paths]
    
    def _get_video_duration(self, video_path: str) -> float:
        """Get video duration in seconds using ffprobe."""
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            str(video_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr}")
        
        return float(result.stdout.strip())
    
    async def analyze_frames(
        self,
        frame_paths: List[str],
        interval: int = DEFAULT_INTERVAL_SECONDS,
        nick_description: Optional[str] = None
    ) -> VisualMap:
        """
        Analyze frames with Gemini 3 to identify people and layout.
        
        Args:
            frame_paths: List of paths to frame images
            interval: Seconds between frames (for timestamp calculation)
            nick_description: Optional description of Nick to help identify him
            
        Returns:
            VisualMap with analysis for each frame
        """
        logger.info(f"Analyzing {len(frame_paths)} frames with Gemini...")
        
        # Process in batches
        frames = []
        total_frames = len(frame_paths)
        
        for i in range(0, total_frames, BATCH_SIZE):
            batch = frame_paths[i:i + BATCH_SIZE]
            batch_results = await self._analyze_batch(
                batch, 
                start_index=i,
                interval=interval,
                nick_description=nick_description
            )
            frames.extend(batch_results)
            
            logger.info(f"Analyzed {min(i + BATCH_SIZE, total_frames)}/{total_frames} frames")
        
        # Calculate total duration
        total_duration = (len(frames) - 1) * interval if frames else 0
        
        visual_map = VisualMap(
            frames=frames,
            total_duration=total_duration,
            frame_interval=interval,
            total_frames=len(frames),
        )
        
        logger.info(
            f"Visual mapping complete: {len(frames)} frames analyzed, "
            f"{total_duration:.1f}s total duration"
        )
        
        return visual_map
    
    async def _analyze_batch(
        self,
        frame_paths: List[str],
        start_index: int,
        interval: int,
        nick_description: Optional[str] = None
    ) -> List[FrameAnalysis]:
        """Analyze a batch of frames."""
        results = []
        
        for i, frame_path in enumerate(frame_paths):
            timestamp = (start_index + i) * interval
            
            try:
                analysis = await self._analyze_single_frame(
                    frame_path,
                    timestamp,
                    nick_description
                )
                results.append(analysis)
            except Exception as e:
                logger.warning(f"Failed to analyze frame {frame_path}: {e}")
                # Add placeholder for failed frame
                results.append(FrameAnalysis(
                    timestamp=timestamp,
                    frame_path=frame_path,
                    people_count=0,
                    people=[],
                    nick_visible=False,
                    layout_type="unknown",
                    on_screen_text=[],
                    raw_analysis=f"Error: {e}",
                ))
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.1)
        
        return results
    
    async def _analyze_single_frame(
        self,
        frame_path: str,
        timestamp: float,
        nick_description: Optional[str] = None
    ) -> FrameAnalysis:
        """Analyze a single frame with Gemini."""
        # Read and encode image
        with open(frame_path, 'rb') as f:
            image_data = f.read()
        
        # Build prompt
        prompt = self._build_analysis_prompt(nick_description)
        
        # Upload image to Gemini
        image_part = {
            "mime_type": "image/jpeg",
            "data": base64.b64encode(image_data).decode('utf-8')
        }
        
        # Call Gemini
        response = await asyncio.to_thread(
            self.model.generate_content,
            [prompt, image_part]
        )
        
        # Parse response
        return self._parse_response(response.text, frame_path, timestamp)
    
    def _build_analysis_prompt(self, nick_description: Optional[str] = None) -> str:
        """Build the prompt for frame analysis."""
        nick_hint = ""
        if nick_description:
            nick_hint = f"\nNote: Nick (the host) typically appears as: {nick_description}"
        
        return f"""Analyze this video frame from a debate/podcast stream.
{nick_hint}

Count people visible, describe each briefly, identify panel layout, and note who appears to be speaking.

RESPOND WITH ONLY THIS JSON FORMAT, NO OTHER TEXT:
{{"people_count": 2, "people": [{{"description": "man with beard", "position": "left", "appears_speaking": true}}, {{"description": "woman with glasses", "position": "right", "appears_speaking": false}}], "layout": "two_panel", "on_screen_text": [], "nick_visible": true, "nick_position": "left"}}"""
    
    def _parse_response(
        self,
        response_text: str,
        frame_path: str,
        timestamp: float
    ) -> FrameAnalysis:
        """Parse Gemini response into FrameAnalysis."""
        try:
            # Try to extract JSON from response
            json_str = response_text.strip()
            
            # Handle markdown code blocks
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                parts = json_str.split("```")
                if len(parts) >= 2:
                    json_str = parts[1].strip()
                    # Remove language identifier if present (e.g., "json\n{")
                    if json_str.startswith(('json', 'JSON')):
                        json_str = json_str[4:].strip()
            
            # Try to find JSON object in the response
            if not json_str.startswith('{'):
                # Look for the first { and last }
                start_idx = json_str.find('{')
                end_idx = json_str.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    json_str = json_str[start_idx:end_idx + 1]
            
            # Clean up common issues
            json_str = json_str.replace('\n', ' ').replace('\r', '')
            
            data = json.loads(json_str)
            
            # Parse people
            people = []
            for p in data.get('people', []):
                people.append(PersonInfo(
                    description=p.get('description', 'unknown'),
                    position=p.get('position', 'unknown'),
                    appears_speaking=p.get('appears_speaking', False),
                ))
            
            return FrameAnalysis(
                timestamp=timestamp,
                frame_path=frame_path,
                people_count=data.get('people_count', len(people)),
                people=people,
                nick_visible=data.get('nick_visible', False),
                layout_type=data.get('layout', 'unknown'),
                on_screen_text=data.get('on_screen_text', []),
                raw_analysis=response_text,
            )
            
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse Gemini response: {e}")
            # Try to extract basic info from the raw text
            people_count = 0
            layout = "unknown"
            raw = response_text.lower()
            
            # Try to guess people count from text
            for i in range(10, 0, -1):
                if str(i) in raw or f"{i} people" in raw or f"{i} person" in raw:
                    people_count = i
                    break
            
            # Try to guess layout
            if "multi" in raw or "grid" in raw or "3" in raw or "4" in raw:
                layout = "multi_panel"
            elif "two" in raw or "2" in raw or "split" in raw:
                layout = "two_panel"
            elif "solo" in raw or "one" in raw or "1 person" in raw:
                layout = "solo"
            
            return FrameAnalysis(
                timestamp=timestamp,
                frame_path=frame_path,
                people_count=people_count,
                people=[],
                nick_visible=False,
                layout_type=layout,
                on_screen_text=[],
                raw_analysis=response_text[:500],  # Truncate for storage
            )
    
    def analyze_frames_sync(
        self,
        frame_paths: List[str],
        interval: int = DEFAULT_INTERVAL_SECONDS,
        nick_description: Optional[str] = None
    ) -> VisualMap:
        """Synchronous wrapper for analyze_frames."""
        return asyncio.run(
            self.analyze_frames(frame_paths, interval, nick_description)
        )


def get_unique_people(visual_map: VisualMap) -> List[str]:
    """
    Get unique person descriptions from the visual map.
    
    Useful for identifying distinct guests.
    """
    descriptions = set()
    for frame in visual_map.frames:
        for person in frame.people:
            descriptions.add(person.description)
    return sorted(descriptions)


def get_person_timeline(
    visual_map: VisualMap,
    description_contains: str
) -> List[tuple]:
    """
    Get timeline of when a person (by description) appears.
    
    Args:
        visual_map: VisualMap with all frames
        description_contains: Partial description to match
        
    Returns:
        List of (start_time, end_time) tuples
    """
    appearances = []
    current_start = None
    last_seen = None
    
    for frame in visual_map.frames:
        person_visible = any(
            description_contains.lower() in p.description.lower()
            for p in frame.people
        )
        
        if person_visible:
            if current_start is None:
                current_start = frame.timestamp
            last_seen = frame.timestamp
        else:
            if current_start is not None:
                appearances.append((current_start, last_seen))
                current_start = None
                last_seen = None
    
    # Don't forget the last appearance
    if current_start is not None:
        appearances.append((current_start, last_seen))
    
    return appearances
