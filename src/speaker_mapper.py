"""
Speaker Mapping Module - Pyannote Voiceprint Integration

Owner: Gabriel
Status: Implemented

This module identifies specific speakers (Nick vs guests) using Pyannote's
voiceprint API. It creates a voice fingerprint for Nick and then identifies
when he's speaking throughout the audio.

Pyannote API docs: https://docs.pyannote.ai/
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

import aiohttp

logger = logging.getLogger(__name__)

# Pyannote API endpoints
PYANNOTE_BASE_URL = "https://api.pyannote.ai/v1"
VOICEPRINT_ENDPOINT = f"{PYANNOTE_BASE_URL}/voiceprint"
IDENTIFY_ENDPOINT = f"{PYANNOTE_BASE_URL}/identify"
DIARIZE_ENDPOINT = f"{PYANNOTE_BASE_URL}/diarize"
JOB_ENDPOINT = f"{PYANNOTE_BASE_URL}/job"

# Timeout for long audio processing
LONG_AUDIO_TIMEOUT = 1800  # 30 minutes


@dataclass
class VoiceSegment:
    """Represents a segment of audio with speaker identification."""
    speaker: str        # "nick" | "guest" | "unknown"
    start: float        # seconds
    end: float          # seconds
    confidence: float   # 0-1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class VoiceMap:
    """Complete voice mapping for an audio file."""
    segments: List[VoiceSegment]
    total_duration: float
    nick_talk_time: float
    guest_talk_time: float
    unknown_talk_time: float
    nick_voiceprint_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'segments': [s.to_dict() for s in self.segments],
            'total_duration': self.total_duration,
            'nick_talk_time': self.nick_talk_time,
            'guest_talk_time': self.guest_talk_time,
            'unknown_talk_time': self.unknown_talk_time,
            'nick_voiceprint_id': self.nick_voiceprint_id,
        }
    
    def save(self, path: str) -> None:
        """Save voice map to JSON file."""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Voice map saved to: {path}")
    
    @classmethod
    def load(cls, path: str) -> 'VoiceMap':
        """Load voice map from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        segments = [VoiceSegment(**s) for s in data['segments']]
        return cls(
            segments=segments,
            total_duration=data['total_duration'],
            nick_talk_time=data['nick_talk_time'],
            guest_talk_time=data['guest_talk_time'],
            unknown_talk_time=data['unknown_talk_time'],
            nick_voiceprint_id=data.get('nick_voiceprint_id'),
        )


class SpeakerMapper:
    """
    Maps speakers using Pyannote voiceprint identification.
    
    This class creates a voiceprint for Nick from a clean audio sample,
    then identifies when Nick is speaking throughout the full audio.
    
    Usage:
        mapper = SpeakerMapper(api_key)
        voiceprint_id = await mapper.create_nick_voiceprint("nick_sample.wav")
        voice_map = await mapper.map_speakers("full_audio.wav", voiceprint_id)
        voice_map.save("voice_map.json")
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize with Pyannote API key.
        
        Args:
            api_key: Pyannote API key from dashboard.pyannote.ai
                     If not provided, reads from PYANNOTE_API_KEY env var
        """
        self.api_key = api_key or os.getenv('PYANNOTE_API_KEY')
        if not self.api_key:
            raise ValueError(
                "Pyannote API key required. Set PYANNOTE_API_KEY env var "
                "or pass api_key parameter."
            )
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        logger.info("SpeakerMapper initialized with Pyannote API")
    
    async def create_nick_voiceprint(self, sample_path: str) -> str:
        """
        Create a voiceprint from a clean audio sample of Nick.
        
        Args:
            sample_path: Path to 30-second audio of Nick speaking alone
                        (no overlapping voices, clean audio)
        
        Returns:
            voiceprint_id: ID to use for identification
            
        Raises:
            FileNotFoundError: If sample file doesn't exist
            RuntimeError: If voiceprint creation fails
        """
        sample_file = Path(sample_path)
        if not sample_file.exists():
            raise FileNotFoundError(f"Sample audio not found: {sample_path}")
        
        file_size_mb = sample_file.stat().st_size / (1024 * 1024)
        logger.info(f"Creating voiceprint from: {sample_file.name} ({file_size_mb:.1f} MB)")
        
        async with aiohttp.ClientSession() as session:
            # Upload audio and create voiceprint
            with open(sample_path, 'rb') as f:
                audio_data = f.read()
            
            # Pyannote expects the audio URL or base64
            # For simplicity, we'll use file upload approach
            form_data = aiohttp.FormData()
            form_data.add_field(
                'audio',
                audio_data,
                filename=sample_file.name,
                content_type='audio/wav'
            )
            
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            async with session.post(
                VOICEPRINT_ENDPOINT,
                data=form_data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=300)
            ) as response:
                if response.status != 200 and response.status != 201:
                    error_text = await response.text()
                    raise RuntimeError(f"Voiceprint creation failed: {error_text}")
                
                result = await response.json()
        
        # Get job ID and wait for completion
        job_id = result.get('jobId') or result.get('job_id') or result.get('id')
        if job_id:
            voiceprint_id = await self._wait_for_job(job_id, "voiceprint")
        else:
            voiceprint_id = result.get('voiceprintId') or result.get('voiceprint_id')
        
        logger.info(f"Voiceprint created: {voiceprint_id}")
        return voiceprint_id
    
    async def map_speakers(
        self,
        audio_path: str,
        nick_voiceprint_id: str,
        min_segment_duration: float = 0.5
    ) -> VoiceMap:
        """
        Identify Nick vs others throughout the audio.
        
        Args:
            audio_path: Path to full audio file
            nick_voiceprint_id: Voiceprint ID from create_nick_voiceprint()
            min_segment_duration: Minimum segment duration in seconds
            
        Returns:
            VoiceMap with all speaker segments
        """
        audio_file = Path(audio_path)
        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        file_size_mb = audio_file.stat().st_size / (1024 * 1024)
        logger.info(f"Mapping speakers in: {audio_file.name} ({file_size_mb:.1f} MB)")
        
        async with aiohttp.ClientSession() as session:
            # Upload audio for identification
            with open(audio_path, 'rb') as f:
                audio_data = f.read()
            
            form_data = aiohttp.FormData()
            form_data.add_field(
                'audio',
                audio_data,
                filename=audio_file.name,
                content_type='audio/wav'
            )
            form_data.add_field('voiceprints', json.dumps([{
                'id': nick_voiceprint_id,
                'label': 'nick'
            }]))
            
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            logger.info("Submitting audio for speaker identification...")
            async with session.post(
                IDENTIFY_ENDPOINT,
                data=form_data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=LONG_AUDIO_TIMEOUT)
            ) as response:
                if response.status != 200 and response.status != 201:
                    error_text = await response.text()
                    raise RuntimeError(f"Speaker identification failed: {error_text}")
                
                result = await response.json()
        
        # Get job ID and wait for completion
        job_id = result.get('jobId') or result.get('job_id') or result.get('id')
        if job_id:
            segments_data = await self._wait_for_job(job_id, "identify")
        else:
            segments_data = result.get('segments', result.get('output', {}).get('segments', []))
        
        # Process segments
        segments = self._process_segments(segments_data, min_segment_duration)
        
        # Calculate talk times
        nick_time = sum(s.end - s.start for s in segments if s.speaker == 'nick')
        guest_time = sum(s.end - s.start for s in segments if s.speaker == 'guest')
        unknown_time = sum(s.end - s.start for s in segments if s.speaker == 'unknown')
        total_duration = segments[-1].end if segments else 0.0
        
        voice_map = VoiceMap(
            segments=segments,
            total_duration=total_duration,
            nick_talk_time=nick_time,
            guest_talk_time=guest_time,
            unknown_talk_time=unknown_time,
            nick_voiceprint_id=nick_voiceprint_id,
        )
        
        logger.info(
            f"Speaker mapping complete: {len(segments)} segments, "
            f"Nick: {nick_time:.1f}s, Guest: {guest_time:.1f}s, "
            f"Unknown: {unknown_time:.1f}s"
        )
        
        return voice_map
    
    async def _wait_for_job(
        self,
        job_id: str,
        job_type: str,
        poll_interval: float = 5.0,
        max_wait: float = LONG_AUDIO_TIMEOUT
    ) -> Any:
        """
        Wait for a Pyannote job to complete.
        
        Args:
            job_id: The job ID to wait for
            job_type: Type of job (for logging)
            poll_interval: Seconds between status checks
            max_wait: Maximum time to wait
            
        Returns:
            Job result data
        """
        logger.info(f"Waiting for {job_type} job: {job_id}")
        
        elapsed = 0.0
        async with aiohttp.ClientSession() as session:
            while elapsed < max_wait:
                async with session.get(
                    f"{JOB_ENDPOINT}/{job_id}",
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise RuntimeError(f"Job status check failed: {error_text}")
                    
                    result = await response.json()
                
                status = result.get('status', '').lower()
                
                if status == 'succeeded' or status == 'completed':
                    logger.info(f"Job {job_id} completed successfully")
                    return result.get('output') or result.get('result') or result
                elif status == 'failed' or status == 'error':
                    error = result.get('error', 'Unknown error')
                    raise RuntimeError(f"Job {job_id} failed: {error}")
                
                # Still processing
                logger.debug(f"Job {job_id} status: {status}, waiting...")
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
        
        raise RuntimeError(f"Job {job_id} timed out after {max_wait}s")
    
    def _process_segments(
        self,
        segments_data: List[Dict],
        min_duration: float
    ) -> List[VoiceSegment]:
        """
        Process raw segment data into VoiceSegment objects.
        
        Args:
            segments_data: Raw segments from Pyannote API
            min_duration: Minimum segment duration to include
            
        Returns:
            List of VoiceSegment objects
        """
        segments = []
        
        for seg in segments_data:
            # Handle different response formats
            start = seg.get('start', seg.get('startTime', 0))
            end = seg.get('end', seg.get('endTime', 0))
            speaker = seg.get('speaker', seg.get('label', 'unknown'))
            confidence = seg.get('confidence', seg.get('score', 1.0))
            
            # Skip very short segments
            if (end - start) < min_duration:
                continue
            
            # Normalize speaker labels
            if speaker.lower() == 'nick':
                speaker = 'nick'
            elif speaker.lower() in ['unknown', 'unidentified', '']:
                speaker = 'unknown'
            else:
                speaker = 'guest'
            
            segments.append(VoiceSegment(
                speaker=speaker,
                start=float(start),
                end=float(end),
                confidence=float(confidence),
            ))
        
        # Sort by start time
        segments.sort(key=lambda s: s.start)
        
        return segments
    
    def map_speakers_sync(
        self,
        audio_path: str,
        nick_voiceprint_id: str,
        min_segment_duration: float = 0.5
    ) -> VoiceMap:
        """Synchronous wrapper for map_speakers."""
        return asyncio.run(
            self.map_speakers(audio_path, nick_voiceprint_id, min_segment_duration)
        )
    
    def create_nick_voiceprint_sync(self, sample_path: str) -> str:
        """Synchronous wrapper for create_nick_voiceprint."""
        return asyncio.run(self.create_nick_voiceprint(sample_path))


def get_speaker_at_timestamp(
    voice_map: VoiceMap,
    timestamp: float
) -> Optional[VoiceSegment]:
    """
    Find the speaker at a given timestamp.
    
    Args:
        voice_map: VoiceMap with all segments
        timestamp: Time in seconds
        
    Returns:
        VoiceSegment at that time, or None if not found
    """
    for segment in voice_map.segments:
        if segment.start <= timestamp <= segment.end:
            return segment
    return None


def get_segments_in_range(
    voice_map: VoiceMap,
    start: float,
    end: float
) -> List[VoiceSegment]:
    """
    Get all segments within a time range.
    
    Args:
        voice_map: VoiceMap with all segments
        start: Start time in seconds
        end: End time in seconds
        
    Returns:
        List of VoiceSegments that overlap with the range
    """
    return [
        s for s in voice_map.segments
        if s.end > start and s.start < end
    ]
