"""
Voice Fingerprinter - Real Pyannote API Integration for Speaker Detection

Owner: Gabriel
Status: Implemented
Version: 2.0

This module provides REAL audio-based speaker detection using Pyannote's API:

1. Diarization - Detect all speakers and when they speak (from actual audio)
2. Voiceprint Training - Create voice profiles for known speakers (Nick)
3. Speaker Identification - Match detected speakers to known voiceprints
4. New Speaker Detection - Track when new voices first appear
5. Cross-Modal Validation - Combine with visual events for high confidence

Pyannote API supports:
- Up to 24 hours of audio
- Max 1 GiB file size
- Async job processing for long files

API Docs: https://docs.pyannote.ai/
"""

import asyncio
import base64
import json
import logging
import os
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
from collections import defaultdict

import aiohttp

logger = logging.getLogger(__name__)

# =============================================================================
# Pyannote API Configuration
# =============================================================================

PYANNOTE_BASE_URL = "https://api.pyannote.ai/v1"
DIARIZE_ENDPOINT = f"{PYANNOTE_BASE_URL}/diarize"
VOICEPRINT_ENDPOINT = f"{PYANNOTE_BASE_URL}/voiceprint"
IDENTIFY_ENDPOINT = f"{PYANNOTE_BASE_URL}/identify"
JOB_ENDPOINT = f"{PYANNOTE_BASE_URL}/jobs"
MEDIA_INPUT_ENDPOINT = f"{PYANNOTE_BASE_URL}/media/input"

# Pyannote voiceprint creation: max 30 seconds of audio
VOICEPRINT_MAX_DURATION = 30.0

# Timeouts (in seconds)
UPLOAD_TIMEOUT = 600  # 10 min for large file upload
JOB_POLL_INTERVAL = 10  # Check job status every 10 seconds
MAX_JOB_WAIT = 7200  # 2 hours max wait for diarization


class SpeakerType(Enum):
    """Classification of speaker types."""
    NICK = "nick"           # Host (identified via voiceprint)
    PANEL = "panel"         # Regular panel members
    GUEST = "guest"         # New/temporary guests
    UNKNOWN = "unknown"     # Unidentified speaker


class SpeakerEventType(Enum):
    """Types of speaker events."""
    FIRST_APPEARANCE = "first_appearance"  # Speaker's first time in audio
    SPEAKING_START = "speaking_start"       # Speaker starts talking
    SPEAKING_END = "speaking_end"           # Speaker stops talking
    RETURN = "return"                       # Speaker returns after absence


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class Voiceprint:
    """A trained voiceprint for a known speaker."""
    voiceprint_id: str
    speaker_name: str
    created_from: str  # Path to source audio
    created_at: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def save(self, path: str) -> None:
        """Save voiceprint info to JSON."""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Voiceprint saved to: {path}")
    
    @classmethod
    def load(cls, path: str) -> 'Voiceprint':
        """Load voiceprint info from JSON."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls(**data)


@dataclass
class DiarizedSegment:
    """A segment of audio with speaker label from Pyannote diarization."""
    speaker_label: str  # SPEAKER_00, SPEAKER_01, etc.
    start: float        # Start time in seconds
    end: float          # End time in seconds
    confidence: float   # Diarization confidence
    
    @property
    def duration(self) -> float:
        return self.end - self.start
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "speaker_label": self.speaker_label,
            "start": self.start,
            "end": self.end,
            "duration": self.duration,
            "confidence": self.confidence,
        }


@dataclass
class IdentifiedSpeaker:
    """A speaker with identification info."""
    speaker_label: str        # Original Pyannote label (SPEAKER_00)
    identified_as: Optional[str]  # "nick" if matched, None otherwise
    speaker_type: SpeakerType
    first_appearance: float   # When they first speak
    last_appearance: float    # When they last speak
    total_duration: float     # Total speaking time
    segment_count: int        # Number of speaking segments
    identification_confidence: float  # How confident is the ID
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "speaker_label": self.speaker_label,
            "identified_as": self.identified_as,
            "speaker_type": self.speaker_type.value,
            "first_appearance": self.first_appearance,
            "last_appearance": self.last_appearance,
            "total_duration": self.total_duration,
            "segment_count": self.segment_count,
            "identification_confidence": self.identification_confidence,
        }


@dataclass
class SpeakerEvent:
    """An event related to speaker detection."""
    timestamp: float
    event_type: SpeakerEventType
    speaker_label: str
    identified_as: Optional[str]
    confidence: float
    context: str = ""  # Additional context
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type.value,
            "speaker_label": self.speaker_label,
            "identified_as": self.identified_as,
            "confidence": self.confidence,
            "context": self.context,
        }


@dataclass
class ValidatedSpeakerChange:
    """A speaker change validated with cross-modal signals."""
    timestamp: float
    speaker_label: str
    event_type: SpeakerEventType
    
    # Voice-based confidence
    voice_confidence: float
    
    # Cross-modal validation
    visual_event_nearby: bool
    visual_event_timestamp: Optional[float]
    visual_correlation: Optional[float]  # 0-1, how close is visual event
    
    transcript_cue_nearby: bool
    transcript_cue_phrase: Optional[str]
    transcript_correlation: Optional[float]
    
    # Final assessment
    validation_type: str  # "triple_confirmed", "double_confirmed", "voice_only"
    final_confidence: float
    is_likely_guest: bool
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "speaker_label": self.speaker_label,
            "event_type": self.event_type.value,
            "voice_confidence": self.voice_confidence,
            "visual_event_nearby": self.visual_event_nearby,
            "visual_event_timestamp": self.visual_event_timestamp,
            "visual_correlation": self.visual_correlation,
            "transcript_cue_nearby": self.transcript_cue_nearby,
            "transcript_cue_phrase": self.transcript_cue_phrase,
            "transcript_correlation": self.transcript_correlation,
            "validation_type": self.validation_type,
            "final_confidence": self.final_confidence,
            "is_likely_guest": self.is_likely_guest,
            "notes": self.notes,
        }


@dataclass
class VoiceDiarizationResult:
    """Complete result from voice diarization and analysis."""
    # Raw diarization
    segments: List[DiarizedSegment]
    total_duration: float
    
    # Identified speakers
    speakers: Dict[str, IdentifiedSpeaker]  # speaker_label -> info
    nick_speaker_label: Optional[str]  # Which label is Nick
    
    # Events
    speaker_events: List[SpeakerEvent]
    new_speaker_events: List[SpeakerEvent]  # Just first appearances
    
    # Cross-modal validation (if provided)
    validated_changes: List[ValidatedSpeakerChange]
    
    # Nick voiceprint used
    nick_voiceprint_id: Optional[str]
    
    # Processing info
    diarization_job_id: Optional[str]
    identification_job_id: Optional[str]
    processing_metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "segments": [s.to_dict() for s in self.segments],
            "total_duration": self.total_duration,
            "speakers": {k: v.to_dict() for k, v in self.speakers.items()},
            "nick_speaker_label": self.nick_speaker_label,
            "speaker_events": [e.to_dict() for e in self.speaker_events],
            "new_speaker_events": [e.to_dict() for e in self.new_speaker_events],
            "validated_changes": [v.to_dict() for v in self.validated_changes],
            "nick_voiceprint_id": self.nick_voiceprint_id,
            "diarization_job_id": self.diarization_job_id,
            "identification_job_id": self.identification_job_id,
            "processing_metadata": self.processing_metadata,
        }
    
    def save(self, path: str) -> None:
        """Save results to JSON file."""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Voice diarization saved to: {path}")
    
    @classmethod
    def load(cls, path: str) -> 'VoiceDiarizationResult':
        """Load results from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        segments = []
        for s in data.get("segments", []):
            # Remove 'duration' if present (it's a computed property)
            s_clean = {k: v for k, v in s.items() if k != 'duration'}
            segments.append(DiarizedSegment(**s_clean))
        
        speakers = {}
        for label, info in data.get("speakers", {}).items():
            info["speaker_type"] = SpeakerType(info["speaker_type"])
            speakers[label] = IdentifiedSpeaker(**info)
        
        speaker_events = []
        for e in data.get("speaker_events", []):
            e["event_type"] = SpeakerEventType(e["event_type"])
            speaker_events.append(SpeakerEvent(**e))
        
        new_speaker_events = []
        for e in data.get("new_speaker_events", []):
            e["event_type"] = SpeakerEventType(e["event_type"])
            new_speaker_events.append(SpeakerEvent(**e))
        
        validated_changes = []
        for v in data.get("validated_changes", []):
            v["event_type"] = SpeakerEventType(v["event_type"])
            validated_changes.append(ValidatedSpeakerChange(**v))
        
        return cls(
            segments=segments,
            total_duration=data.get("total_duration", 0),
            speakers=speakers,
            nick_speaker_label=data.get("nick_speaker_label"),
            speaker_events=speaker_events,
            new_speaker_events=new_speaker_events,
            validated_changes=validated_changes,
            nick_voiceprint_id=data.get("nick_voiceprint_id"),
            diarization_job_id=data.get("diarization_job_id"),
            identification_job_id=data.get("identification_job_id"),
            processing_metadata=data.get("processing_metadata", {}),
        )


# =============================================================================
# Main Voice Fingerprinter Class
# =============================================================================

class VoiceFingerprinter:
    """
    Real audio-based speaker detection using Pyannote API.
    
    This class provides:
    1. Voiceprint training - Create voice profile for Nick from sample audio
    2. Full diarization - Detect all speakers throughout the audio
    3. Speaker identification - Match speakers to known voiceprints
    4. New speaker detection - Track when new voices first appear
    5. Cross-modal validation - Combine with visual/transcript signals
    
    Usage:
        # First time: Train Nick's voice
        fingerprinter = VoiceFingerprinter(api_key)
        voiceprint = await fingerprinter.create_voiceprint(
            audio_path="nick_sample.wav",
            speaker_name="nick"
        )
        voiceprint.save("nick_voiceprint.json")
        
        # Process a video's audio
        result = await fingerprinter.analyze_audio(
            audio_path="full_stream.wav",
            nick_voiceprint_id=voiceprint.voiceprint_id,
            visual_events=visual_events,  # Optional
            transcript_cues=transcript_cues,  # Optional
        )
        result.save("voice_analysis.json")
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize with Pyannote API key.
        
        Args:
            api_key: Pyannote API key (or set PYANNOTE_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("PYANNOTE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Pyannote API key required. Set PYANNOTE_API_KEY env var "
                "or pass api_key parameter. Get one at: https://dashboard.pyannote.ai/"
            )
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
        }
        
        logger.info("VoiceFingerprinter initialized with Pyannote API")
    
    # =========================================================================
    # Voiceprint Training
    # =========================================================================
    
    def _trim_audio_for_voiceprint(self, audio_path: str) -> str:
        """
        Trim audio to VOICEPRINT_MAX_DURATION seconds (Pyannote limit).
        Returns path to trimmed file (temp file if trimming was needed).
        """
        audio_file = Path(audio_path)
        # Get duration via ffprobe
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", str(audio_file)
                ],
                capture_output=True, text=True, check=True, timeout=10
            )
            duration = float(result.stdout.strip())
        except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
            logger.warning("Could not get audio duration, using full file")
            return audio_path

        if duration <= VOICEPRINT_MAX_DURATION:
            return audio_path

        logger.info(f"Trimming {duration:.1f}s audio to {VOICEPRINT_MAX_DURATION}s for voiceprint")
        suffix = audio_file.suffix or ".wav"
        fd, temp_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(audio_file),
                    "-t", str(VOICEPRINT_MAX_DURATION),
                    "-acodec", "copy", temp_path
                ],
                capture_output=True, check=True, timeout=60
            )
            return temp_path
        except Exception as e:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise RuntimeError(f"Failed to trim audio: {e}") from e

    async def _upload_media_and_get_url(
        self, audio_path: str, session: aiohttp.ClientSession
    ) -> str:
        """
        Upload local audio file to Pyannote temporary storage.
        Returns media:// URL for use in voiceprint/diarize/identify endpoints.
        """
        audio_file = Path(audio_path)
        object_key = f"voiceprint-{uuid.uuid4().hex[:12]}"

        # Step 1: Get pre-signed PUT URL
        async with session.post(
            MEDIA_INPUT_ENDPOINT,
            json={"url": f"media://{object_key}"},
            headers={**self.headers, "Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            if response.status not in [200, 201]:
                error_text = await response.text()
                raise RuntimeError(f"Media upload URL failed ({response.status}): {error_text}")
            data = await response.json()
            presigned_url = data.get("url")
            if not presigned_url:
                raise RuntimeError(f"No presigned URL in response: {data}")

        # Step 2: PUT file to presigned URL
        with open(audio_path, "rb") as f:
            audio_data = f.read()

        async with session.put(
            presigned_url,
            data=audio_data,
            headers={"Content-Type": self._get_content_type(audio_file.suffix)},
            timeout=aiohttp.ClientTimeout(total=UPLOAD_TIMEOUT),
        ) as response:
            if response.status not in [200, 201, 204]:
                error_text = await response.text()
                raise RuntimeError(f"Media upload failed ({response.status}): {error_text}")

        logger.info(f"Uploaded media: media://{object_key}")
        return f"media://{object_key}"

    async def create_voiceprint(
        self,
        audio_path: str,
        speaker_name: str = "nick",
    ) -> Voiceprint:
        """
        Create a voiceprint from a clean audio sample.

        Pyannote requires a URL (not file upload). For local files, we use the
        media upload flow. Audio is auto-trimmed to 30s (Pyannote limit).

        For best results:
        - Use 30+ seconds of clean speech (first 30s will be used)
        - Only one speaker (no overlapping voices)
        - Clear audio quality

        Args:
            audio_path: Path to audio file (WAV, MP3, etc.)
            speaker_name: Name to identify this speaker

        Returns:
            Voiceprint object with ID for future identification
        """
        audio_file = Path(audio_path)
        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        file_size_mb = audio_file.stat().st_size / (1024 * 1024)
        logger.info(f"Creating voiceprint for '{speaker_name}' from: {audio_file.name} ({file_size_mb:.1f} MB)")

        # Trim to 30s if needed (Pyannote voiceprint max)
        trimmed_path = self._trim_audio_for_voiceprint(audio_path)
        temp_trimmed = trimmed_path != audio_path

        try:
            async with aiohttp.ClientSession() as session:
                # Upload to Pyannote temporary storage
                media_url = await self._upload_media_and_get_url(trimmed_path, session)

                # Submit voiceprint creation job (JSON body with url)
                logger.info("Submitting voiceprint creation request...")
                async with session.post(
                    VOICEPRINT_ENDPOINT,
                    json={"url": media_url, "model": "precision-2"},
                    headers={**self.headers, "Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as response:
                    if response.status not in [200, 201, 202]:
                        error_text = await response.text()
                        raise RuntimeError(f"Voiceprint creation failed ({response.status}): {error_text}")

                    result = await response.json()

            # Handle async job (voiceprint always returns job)
            job_id = result.get("jobId") or result.get("job_id") or result.get("id")
            status = result.get("status", "").lower()
            if job_id and status in ["pending", "processing", "queued", "created", "running"]:
                logger.info(f"Voiceprint job submitted: {job_id}")
                result = await self._wait_for_job(job_id)

            # Extract voiceprint (base64 string from output when job succeeds)
            output = result.get("output", result)
            voiceprint_id = (
                output.get("voiceprint") or
                output.get("voiceprintId") or
                output.get("voiceprint_id") or
                result.get("voiceprintId") or
                result.get("voiceprint_id") or
                result.get("id")
            )

            if not voiceprint_id:
                raise RuntimeError(f"Could not extract voiceprint from response: {result}")

            from datetime import datetime
            voiceprint = Voiceprint(
                voiceprint_id=voiceprint_id,
                speaker_name=speaker_name,
                created_from=str(audio_path),
                created_at=datetime.now().isoformat(),
                metadata={
                    "file_size_mb": file_size_mb,
                    "job_id": job_id,
                },
            )

            logger.info(f"Voiceprint created successfully: {voiceprint_id[:50]}...")
            return voiceprint

        finally:
            if temp_trimmed and os.path.exists(trimmed_path):
                try:
                    os.unlink(trimmed_path)
                except OSError:
                    pass
    
    async def create_voiceprint_from_multiple(
        self,
        audio_paths: List[str],
        speaker_name: str = "nick",
    ) -> Voiceprint:
        """
        Create a stronger voiceprint from multiple audio samples.
        
        This is useful when you have multiple recordings of the same speaker.
        The samples will be processed together for better accuracy.
        
        Args:
            audio_paths: List of paths to audio files
            speaker_name: Name to identify this speaker
            
        Returns:
            Voiceprint object
        """
        # For now, use the first sample
        # TODO: Pyannote API might support multi-sample voiceprints
        if not audio_paths:
            raise ValueError("At least one audio path required")
        
        logger.info(f"Creating voiceprint from {len(audio_paths)} samples")
        
        # Use the first/primary sample
        return await self.create_voiceprint(audio_paths[0], speaker_name)
    
    # =========================================================================
    # Diarization (Speaker Detection from Audio)
    # =========================================================================
    
    async def diarize_audio(
        self,
        audio_path: str,
        min_speakers: int = 1,
        max_speakers: Optional[int] = None,
        exclusive: bool = False,
    ) -> Tuple[List[DiarizedSegment], str]:
        """
        Perform speaker diarization on audio file.

        Uses the Pyannote media upload flow for local files.

        Args:
            audio_path: Path to audio file
            min_speakers: Minimum expected speakers (default: 1)
            max_speakers: Maximum expected speakers (None = auto-detect)
            exclusive: If True, return non-overlapping segments (useful for
                       merging with STT transcripts)

        Returns:
            Tuple of (list of DiarizedSegments, job_id)
        """
        audio_file = Path(audio_path)
        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        file_size_mb = audio_file.stat().st_size / (1024 * 1024)
        logger.info(f"Starting diarization: {audio_file.name} ({file_size_mb:.1f} MB)")

        if file_size_mb > 1024:
            logger.warning(f"File is {file_size_mb:.0f} MB - this may take a while")

        async with aiohttp.ClientSession() as session:
            # Upload to Pyannote temporary storage
            media_url = await self._upload_media_and_get_url(audio_path, session)

            # Build JSON request body
            body: Dict[str, Any] = {
                "url": media_url,
                "model": "precision-2",
                "exclusive": exclusive,
            }
            if max_speakers:
                body["maxSpeakers"] = max_speakers
            if min_speakers > 1:
                body["minSpeakers"] = min_speakers

            # Submit diarization job
            logger.info("Submitting diarization request to Pyannote API...")
            async with session.post(
                DIARIZE_ENDPOINT,
                json=body,
                headers={**self.headers, "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status not in [200, 201, 202]:
                    error_text = await response.text()
                    raise RuntimeError(f"Diarization request failed ({response.status}): {error_text}")

                result = await response.json()

        # Get job ID
        job_id = result.get('jobId') or result.get('job_id') or result.get('id')

        if not job_id:
            # Synchronous response (small file)
            segments_data = result.get('output', {}).get('segments', [])
        else:
            # Async job - wait for completion
            logger.info(f"Diarization job submitted: {job_id}")
            logger.info("This may take several minutes for long audio...")

            result = await self._wait_for_job(job_id)
            output = result.get('output', {})
            # Prefer exclusive diarization when requested
            if exclusive and 'exclusiveDiarization' in output:
                segments_data = output['exclusiveDiarization']
            else:
                segments_data = output.get('diarization', output.get('segments', []))

        # Parse segments
        segments = self._parse_diarization_segments(segments_data)

        logger.info(f"Diarization complete: {len(segments)} segments detected")

        return segments, job_id or "sync"
    
    # =========================================================================
    # Speaker Identification
    # =========================================================================
    
    async def identify_speakers(
        self,
        audio_path: str,
        voiceprint_ids: Dict[str, str],  # name -> base64 voiceprint string
        match_threshold: int = 50,
        exclusive: bool = True,
    ) -> Tuple[List[DiarizedSegment], Dict[str, str], str]:
        """
        Identify known speakers in audio using voiceprints.

        Uses the Pyannote /identify endpoint which runs diarization AND
        matches speakers to known voiceprints in a single job.

        Args:
            audio_path: Path to audio file
            voiceprint_ids: Dict mapping speaker names to base64 voiceprint
                           strings, e.g. {"nick": "jONxwGuo..."}
            match_threshold: Minimum confidence (0-100) for a match.
                            Higher = fewer false positives. Default 50.
            exclusive: If True, each voiceprint can only match one speaker.

        Returns:
            Tuple of (segments, speaker_mapping, job_id)
            segments: identification segments with matched labels
            speaker_mapping: maps diarization labels to names,
                            e.g. {"SPEAKER_00": "nick"}
        """
        audio_file = Path(audio_path)
        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        file_size_mb = audio_file.stat().st_size / (1024 * 1024)
        logger.info(f"Starting speaker identification: {audio_file.name} ({file_size_mb:.1f} MB)")

        async with aiohttp.ClientSession() as session:
            # Upload to Pyannote temporary storage
            media_url = await self._upload_media_and_get_url(audio_path, session)

            # Prepare voiceprints for API (label + base64 voiceprint string)
            voiceprints_list = [
                {"label": name, "voiceprint": vp_base64}
                for name, vp_base64 in voiceprint_ids.items()
            ]

            # Build JSON request body
            body: Dict[str, Any] = {
                "url": media_url,
                "model": "precision-2",
                "voiceprints": voiceprints_list,
                "matching": {
                    "threshold": match_threshold,
                    "exclusive": exclusive,
                },
            }

            # Submit identification job
            logger.info(f"Submitting identification request with {len(voiceprint_ids)} known voiceprints...")
            async with session.post(
                IDENTIFY_ENDPOINT,
                json=body,
                headers={**self.headers, "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status not in [200, 201, 202]:
                    error_text = await response.text()
                    raise RuntimeError(f"Identification request failed ({response.status}): {error_text}")

                result = await response.json()

        # Get job ID
        job_id = result.get('jobId') or result.get('job_id') or result.get('id')
        status = result.get('status', '').lower()

        if job_id and status in ['pending', 'processing', 'queued', 'created', 'running']:
            logger.info(f"Identification job submitted: {job_id}")
            result = await self._wait_for_job(job_id)

        # Parse results -- identify returns diarization + identification + voiceprints
        output = result.get('output', result)

        # Use identification segments (have match info) if available
        identification_data = output.get('identification', [])
        diarization_data = output.get('diarization', output.get('segments', []))

        segments = self._parse_diarization_segments(
            identification_data or diarization_data
        )

        # Build speaker mapping from voiceprints summary
        speaker_mapping: Dict[str, str] = {}
        vp_summary = output.get('voiceprints', [])
        for vp_info in vp_summary:
            label = vp_info.get('speaker', '')
            match = vp_info.get('match')
            if label and match:
                speaker_mapping[label] = match

        # Fallback: scan identification segments for match field
        if not speaker_mapping and identification_data:
            for seg_data in identification_data:
                diar_speaker = seg_data.get('diarizationSpeaker', seg_data.get('speaker', ''))
                match = seg_data.get('match')
                if diar_speaker and match and diar_speaker not in speaker_mapping:
                    speaker_mapping[diar_speaker] = match

        logger.info(
            f"Identification complete: {len(segments)} segments, "
            f"{len(speaker_mapping)} speakers matched ({speaker_mapping})"
        )

        return segments, speaker_mapping, job_id or "sync"
    
    # =========================================================================
    # Full Analysis Pipeline
    # =========================================================================
    
    async def analyze_audio(
        self,
        audio_path: str,
        nick_voiceprint_id: Optional[str] = None,
        visual_events: Optional[List[Dict[str, Any]]] = None,
        transcript_cues: Optional[List[Dict[str, Any]]] = None,
        visual_correlation_window: float = 60.0,
        transcript_correlation_window: float = 30.0,
    ) -> VoiceDiarizationResult:
        """
        Full audio analysis pipeline with cross-modal validation.
        
        This is the main method for processing a video's audio. It:
        1. Diarizes the audio to detect all speakers
        2. Identifies Nick using his voiceprint (if provided)
        3. Detects when new speakers first appear
        4. Cross-validates with visual events and transcript cues
        
        Args:
            audio_path: Path to audio file (WAV recommended)
            nick_voiceprint_id: Voiceprint ID for Nick (optional but recommended)
            visual_events: List of visual change events with 'timestamp' and 'event_type'
            transcript_cues: List of transcript cues with 'timestamp' and 'cue_type'
            visual_correlation_window: Seconds to look for matching visual events
            transcript_correlation_window: Seconds to look for matching transcript cues
            
        Returns:
            VoiceDiarizationResult with all analysis
        """
        logger.info(f"Starting full audio analysis: {audio_path}")
        
        # Step 1: Diarization or Identification
        speaker_mapping: Dict[str, str] = {}
        identification_job_id = None
        
        if nick_voiceprint_id:
            # Use identification endpoint to match Nick
            logger.info("Running identification with Nick's voiceprint...")
            segments, speaker_mapping, identification_job_id = await self.identify_speakers(
                audio_path,
                {"nick": nick_voiceprint_id},
            )
            diarization_job_id = identification_job_id
        else:
            # Just diarization without identification
            logger.info("Running diarization (no voiceprint provided)...")
            segments, diarization_job_id = await self.diarize_audio(audio_path)
        
        if not segments:
            logger.warning("No segments detected in audio")
            return VoiceDiarizationResult(
                segments=[],
                total_duration=0,
                speakers={},
                nick_speaker_label=None,
                speaker_events=[],
                new_speaker_events=[],
                validated_changes=[],
                nick_voiceprint_id=nick_voiceprint_id,
                diarization_job_id=diarization_job_id,
                identification_job_id=identification_job_id,
            )
        
        # Step 2: Analyze speakers
        speakers, nick_label = self._analyze_speakers(segments, speaker_mapping)
        
        # Step 3: Detect speaker events
        speaker_events = self._detect_speaker_events(segments, speakers)
        new_speaker_events = [
            e for e in speaker_events 
            if e.event_type == SpeakerEventType.FIRST_APPEARANCE
        ]
        
        # Step 4: Cross-modal validation
        validated_changes = []
        if visual_events or transcript_cues:
            validated_changes = self._cross_validate_events(
                new_speaker_events,
                speakers,
                nick_label,
                visual_events or [],
                transcript_cues or [],
                visual_correlation_window,
                transcript_correlation_window,
            )
        
        # Calculate total duration
        total_duration = max(s.end for s in segments) if segments else 0
        
        result = VoiceDiarizationResult(
            segments=segments,
            total_duration=total_duration,
            speakers=speakers,
            nick_speaker_label=nick_label,
            speaker_events=speaker_events,
            new_speaker_events=new_speaker_events,
            validated_changes=validated_changes,
            nick_voiceprint_id=nick_voiceprint_id,
            diarization_job_id=diarization_job_id,
            identification_job_id=identification_job_id,
            processing_metadata={
                "audio_path": str(audio_path),
                "visual_events_provided": visual_events is not None,
                "transcript_cues_provided": transcript_cues is not None,
                "total_speakers_detected": len(speakers),
                "total_segments": len(segments),
            },
        )
        
        # Log summary
        logger.info(
            f"Analysis complete: {len(speakers)} speakers, "
            f"{len(new_speaker_events)} new speaker events, "
            f"{len(validated_changes)} validated changes"
        )
        
        return result
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    async def _wait_for_job(
        self,
        job_id: str,
        poll_interval: float = JOB_POLL_INTERVAL,
        max_wait: float = MAX_JOB_WAIT,
    ) -> Dict[str, Any]:
        """Wait for an async job to complete.

        Uses a fresh HTTP connection for each poll to avoid long-lived
        connections being dropped by the server on multi-minute jobs.
        """
        logger.info(f"Waiting for job {job_id}...")

        elapsed = 0
        retries = 0
        while elapsed < max_wait:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{JOB_ENDPOINT}/{job_id}",
                        headers=self.headers,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            raise RuntimeError(f"Job status check failed: {error_text}")

                        result = await response.json()
                retries = 0  # Reset on success
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                retries += 1
                if retries > 5:
                    raise RuntimeError(f"Job {job_id} poll failed after {retries} retries: {e}")
                logger.warning(f"Poll attempt failed ({e}), retry {retries}/5...")
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                continue

            status = result.get('status', '').lower()

            if status in ['succeeded', 'completed', 'done']:
                logger.info(f"Job {job_id} completed successfully")
                return result
            elif status in ['failed', 'error']:
                error = result.get('error', 'Unknown error')
                raise RuntimeError(f"Job {job_id} failed: {error}")

            # Log progress
            progress = result.get('progress', 0)
            if progress:
                logger.info(f"Job {job_id}: {status} ({progress}%)")
            else:
                logger.info(f"Job {job_id}: {status} ({elapsed:.0f}s elapsed)")

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise RuntimeError(f"Job {job_id} timed out after {max_wait}s")
    
    def _get_content_type(self, suffix: str) -> str:
        """Get MIME type for audio file."""
        content_types = {
            '.wav': 'audio/wav',
            '.mp3': 'audio/mpeg',
            '.m4a': 'audio/m4a',
            '.flac': 'audio/flac',
            '.ogg': 'audio/ogg',
            '.webm': 'audio/webm',
        }
        return content_types.get(suffix.lower(), 'audio/wav')
    
    def _parse_diarization_segments(
        self,
        segments_data: List[Dict],
    ) -> List[DiarizedSegment]:
        """Parse raw segment data from Pyannote."""
        segments = []
        
        for seg in segments_data:
            # Handle various response formats
            start = seg.get('start', seg.get('startTime', seg.get('begin', 0)))
            end = seg.get('end', seg.get('endTime', seg.get('stop', 0)))
            speaker = seg.get('speaker', seg.get('label', 'UNKNOWN'))
            confidence = seg.get('confidence', seg.get('score', 1.0))
            
            segments.append(DiarizedSegment(
                speaker_label=speaker,
                start=float(start),
                end=float(end),
                confidence=float(confidence),
            ))
        
        # Sort by start time
        segments.sort(key=lambda s: s.start)
        
        return segments
    
    def _analyze_speakers(
        self,
        segments: List[DiarizedSegment],
        speaker_mapping: Dict[str, str],
    ) -> Tuple[Dict[str, IdentifiedSpeaker], Optional[str]]:
        """Analyze speakers from diarization segments."""
        speakers: Dict[str, IdentifiedSpeaker] = {}
        nick_label = None
        
        # Group segments by speaker
        speaker_segments: Dict[str, List[DiarizedSegment]] = defaultdict(list)
        for seg in segments:
            speaker_segments[seg.speaker_label].append(seg)
        
        # Analyze each speaker
        for label, segs in speaker_segments.items():
            first_appearance = min(s.start for s in segs)
            last_appearance = max(s.end for s in segs)
            total_duration = sum(s.duration for s in segs)
            
            # Check if identified
            identified_as = speaker_mapping.get(label)
            
            # Determine speaker type
            if identified_as == "nick":
                speaker_type = SpeakerType.NICK
                nick_label = label
                confidence = 0.95
            elif identified_as:
                speaker_type = SpeakerType.PANEL
                confidence = 0.85
            else:
                speaker_type = SpeakerType.UNKNOWN
                confidence = 0.7
            
            speakers[label] = IdentifiedSpeaker(
                speaker_label=label,
                identified_as=identified_as,
                speaker_type=speaker_type,
                first_appearance=first_appearance,
                last_appearance=last_appearance,
                total_duration=total_duration,
                segment_count=len(segs),
                identification_confidence=confidence,
            )
        
        return speakers, nick_label
    
    def _detect_speaker_events(
        self,
        segments: List[DiarizedSegment],
        speakers: Dict[str, IdentifiedSpeaker],
    ) -> List[SpeakerEvent]:
        """Detect all speaker events from segments."""
        events = []
        seen_speakers: Set[str] = set()
        last_speaker: Optional[str] = None
        
        for seg in segments:
            label = seg.speaker_label
            speaker_info = speakers.get(label)
            identified = speaker_info.identified_as if speaker_info else None
            confidence = speaker_info.identification_confidence if speaker_info else 0.7
            
            # First appearance
            if label not in seen_speakers:
                seen_speakers.add(label)
                events.append(SpeakerEvent(
                    timestamp=seg.start,
                    event_type=SpeakerEventType.FIRST_APPEARANCE,
                    speaker_label=label,
                    identified_as=identified,
                    confidence=confidence,
                    context=f"First time speaker {label} is heard",
                ))
            
            # Speaker change
            if last_speaker and last_speaker != label:
                events.append(SpeakerEvent(
                    timestamp=seg.start,
                    event_type=SpeakerEventType.SPEAKING_START,
                    speaker_label=label,
                    identified_as=identified,
                    confidence=confidence,
                    context=f"Speaker changed from {last_speaker} to {label}",
                ))
            
            last_speaker = label
        
        return events
    
    def _cross_validate_events(
        self,
        new_speaker_events: List[SpeakerEvent],
        speakers: Dict[str, IdentifiedSpeaker],
        nick_label: Optional[str],
        visual_events: List[Dict[str, Any]],
        transcript_cues: List[Dict[str, Any]],
        visual_window: float,
        transcript_window: float,
    ) -> List[ValidatedSpeakerChange]:
        """Cross-validate speaker events with visual and transcript signals."""
        validated = []
        
        for event in new_speaker_events:
            # Skip Nick
            if event.speaker_label == nick_label:
                continue
            
            # Find nearby visual events
            visual_nearby = False
            visual_timestamp = None
            visual_correlation = None
            
            for ve in visual_events:
                ve_time = ve.get('timestamp', 0)
                event_type = ve.get('event_type', '').lower()
                
                if event_type in ['new_person', 'person_appeared']:
                    distance = abs(ve_time - event.timestamp)
                    if distance <= visual_window:
                        visual_nearby = True
                        visual_timestamp = ve_time
                        visual_correlation = 1.0 - (distance / visual_window)
                        break
            
            # Find nearby transcript cues
            transcript_nearby = False
            transcript_phrase = None
            transcript_correlation = None
            
            for tc in transcript_cues:
                tc_time = tc.get('timestamp', 0)
                cue_type = tc.get('cue_type', '').lower()
                
                if cue_type in ['intro', 'welcome']:
                    distance = abs(tc_time - event.timestamp)
                    if distance <= transcript_window:
                        transcript_nearby = True
                        transcript_phrase = tc.get('phrase', '')
                        transcript_correlation = 1.0 - (distance / transcript_window)
                        break
            
            # Determine validation type and confidence
            signals_matched = sum([visual_nearby, transcript_nearby, True])  # Voice always counts
            
            if visual_nearby and transcript_nearby:
                validation_type = "triple_confirmed"
                final_confidence = min(1.0, event.confidence + 0.2)
            elif visual_nearby or transcript_nearby:
                validation_type = "double_confirmed"
                final_confidence = min(1.0, event.confidence + 0.1)
            else:
                validation_type = "voice_only"
                final_confidence = event.confidence * 0.8
            
            # Is this likely a guest?
            speaker_info = speakers.get(event.speaker_label)
            is_likely_guest = (
                speaker_info is not None and
                speaker_info.speaker_type in [SpeakerType.UNKNOWN, SpeakerType.GUEST]
            )
            
            validated.append(ValidatedSpeakerChange(
                timestamp=event.timestamp,
                speaker_label=event.speaker_label,
                event_type=event.event_type,
                voice_confidence=event.confidence,
                visual_event_nearby=visual_nearby,
                visual_event_timestamp=visual_timestamp,
                visual_correlation=visual_correlation,
                transcript_cue_nearby=transcript_nearby,
                transcript_cue_phrase=transcript_phrase,
                transcript_correlation=transcript_correlation,
                validation_type=validation_type,
                final_confidence=final_confidence,
                is_likely_guest=is_likely_guest,
                notes=f"Matched {signals_matched} signals",
            ))
        
        return validated
    
    # =========================================================================
    # Synchronous Wrappers
    # =========================================================================
    
    def create_voiceprint_sync(
        self,
        audio_path: str,
        speaker_name: str = "nick",
    ) -> Voiceprint:
        """Synchronous wrapper for create_voiceprint."""
        return asyncio.run(self.create_voiceprint(audio_path, speaker_name))
    
    def diarize_audio_sync(
        self,
        audio_path: str,
        min_speakers: int = 1,
        max_speakers: Optional[int] = None,
        exclusive: bool = False,
    ) -> Tuple[List[DiarizedSegment], str]:
        """Synchronous wrapper for diarize_audio."""
        return asyncio.run(self.diarize_audio(audio_path, min_speakers, max_speakers, exclusive))

    def identify_speakers_sync(
        self,
        audio_path: str,
        voiceprint_ids: Dict[str, str],
        match_threshold: int = 50,
        exclusive: bool = True,
    ) -> Tuple[List[DiarizedSegment], Dict[str, str], str]:
        """Synchronous wrapper for identify_speakers."""
        return asyncio.run(
            self.identify_speakers(audio_path, voiceprint_ids, match_threshold, exclusive)
        )
    
    def analyze_audio_sync(
        self,
        audio_path: str,
        nick_voiceprint_id: Optional[str] = None,
        visual_events: Optional[List[Dict[str, Any]]] = None,
        transcript_cues: Optional[List[Dict[str, Any]]] = None,
    ) -> VoiceDiarizationResult:
        """Synchronous wrapper for analyze_audio."""
        return asyncio.run(
            self.analyze_audio(audio_path, nick_voiceprint_id, visual_events, transcript_cues)
        )


# =============================================================================
# Utility Functions
# =============================================================================

def get_guest_arrivals(
    result: VoiceDiarizationResult,
    min_confidence: float = 0.6,
) -> List[ValidatedSpeakerChange]:
    """Get validated guest arrival events."""
    return [
        v for v in result.validated_changes
        if v.is_likely_guest and v.final_confidence >= min_confidence
    ]


def get_speaker_at_time(
    result: VoiceDiarizationResult,
    timestamp: float,
) -> Optional[DiarizedSegment]:
    """Find who is speaking at a given timestamp."""
    for seg in result.segments:
        if seg.start <= timestamp <= seg.end:
            return seg
    return None


def get_speaker_timeline(
    result: VoiceDiarizationResult,
) -> List[Dict[str, Any]]:
    """Get a simplified timeline of speaker changes."""
    timeline = []
    
    for event in result.speaker_events:
        if event.event_type in [SpeakerEventType.FIRST_APPEARANCE, SpeakerEventType.SPEAKING_START]:
            speaker_info = result.speakers.get(event.speaker_label)
            timeline.append({
                "timestamp": event.timestamp,
                "speaker": event.speaker_label,
                "identified_as": event.identified_as,
                "type": speaker_info.speaker_type.value if speaker_info else "unknown",
                "event": event.event_type.value,
            })
    
    return timeline


def format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


# =============================================================================
# Audio Trimming
# =============================================================================

def trim_audio(
    input_path: str,
    output_path: str,
    start_seconds: float = 0,
    duration_seconds: Optional[float] = None,
) -> str:
    """
    Trim an audio file using FFmpeg.

    Args:
        input_path: Path to source audio file
        output_path: Path for trimmed output
        start_seconds: Start offset in seconds
        duration_seconds: Duration to extract (None = to end)

    Returns:
        Path to the trimmed file
    """
    cmd = ["ffmpeg", "-y", "-ss", str(start_seconds), "-i", input_path]
    if duration_seconds is not None:
        cmd.extend(["-t", str(duration_seconds)])
    cmd.extend(["-acodec", "copy", output_path])

    logger.info(f"Trimming audio: start={start_seconds}s, duration={duration_seconds}s")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg trim failed: {result.stderr}")

    logger.info(f"Trimmed audio saved to: {output_path}")
    return output_path


# =============================================================================
# Transcript Merge (Pyannote speakers + Deepgram words)
# =============================================================================

def merge_pyannote_speakers_with_transcript(
    identification_segments: List[DiarizedSegment],
    speaker_mapping: Dict[str, str],
    transcript_data: Dict[str, Any],
    time_offset: float = 0.0,
) -> Dict[str, Any]:
    """
    Merge Pyannote identification results with a Deepgram word-level transcript.

    For each Deepgram word, finds the Pyannote segment with maximum time
    overlap and assigns the Pyannote speaker label (e.g. "nick", "SPEAKER_01").

    This follows the merge approach recommended by Pyannote:
    https://docs.pyannote.ai/tutorials/diarization-asr-merge

    Args:
        identification_segments: Segments from Pyannote identify or diarize.
        speaker_mapping: Maps Pyannote labels to names,
                        e.g. {"SPEAKER_00": "nick"}.
        transcript_data: Full Deepgram transcript dict with "words" list.
        time_offset: If audio was trimmed, the start offset in seconds.
                    Pyannote times will be shifted by this amount to align
                    with the original full transcript.

    Returns:
        Enhanced transcript dict with updated speaker labels
        (new field "speaker_name" on each word, plus updated stats).
    """
    import copy

    words = transcript_data.get("words", [])
    if not words:
        logger.warning("No words in transcript to merge")
        return transcript_data

    # Build sorted list of identification segments adjusted for time offset
    id_segs = sorted(
        [
            {
                "start": seg.start + time_offset,
                "end": seg.end + time_offset,
                "speaker": seg.speaker_label,
            }
            for seg in identification_segments
        ],
        key=lambda s: s["start"],
    )

    # Resolve speaker names: apply mapping
    for seg in id_segs:
        raw_label = seg["speaker"]
        seg["speaker_name"] = speaker_mapping.get(raw_label, raw_label)

    logger.info(
        f"Merging {len(id_segs)} Pyannote segments with "
        f"{len(words)} Deepgram words (offset={time_offset}s)"
    )

    # Deep copy to avoid mutating original
    enhanced = copy.deepcopy(transcript_data)
    enhanced_words = enhanced["words"]

    # For each word, find the Pyannote segment with maximum overlap
    matched = 0
    unmatched = 0
    for word in enhanced_words:
        w_start = word["start"]
        w_end = word.get("end", w_start + 0.1)

        best_speaker = None
        best_overlap = 0.0

        for seg in id_segs:
            # Early exit: if segment starts past word end, no more can match
            if seg["start"] > w_end + 1.0:
                break

            overlap_start = max(w_start, seg["start"])
            overlap_end = min(w_end, seg["end"])
            overlap = max(0.0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = seg["speaker_name"]

        if best_speaker:
            word["speaker_name"] = best_speaker
            matched += 1
        else:
            # Keep original numeric speaker as fallback
            word["speaker_name"] = f"deepgram_{word.get('speaker', 'unknown')}"
            unmatched += 1

    # Build updated speaker stats
    speaker_stats: Dict[str, Dict[str, Any]] = {}
    for word in enhanced_words:
        name = word.get("speaker_name", "unknown")
        if name not in speaker_stats:
            speaker_stats[name] = {
                "word_count": 0,
                "first_word_time": word["start"],
                "last_word_time": word["start"],
            }
        speaker_stats[name]["word_count"] += 1
        speaker_stats[name]["last_word_time"] = max(
            speaker_stats[name]["last_word_time"], word["start"]
        )

    enhanced["speakers_named"] = speaker_stats
    enhanced["merge_metadata"] = {
        "pyannote_segments": len(id_segs),
        "words_matched": matched,
        "words_unmatched": unmatched,
        "time_offset": time_offset,
        "speaker_mapping": speaker_mapping,
    }

    logger.info(
        f"Merge complete: {matched} words matched, {unmatched} unmatched, "
        f"{len(speaker_stats)} unique speakers"
    )

    return enhanced


# =============================================================================
# Utterance Collapsing (word-level -> speaker turns)
# =============================================================================

@dataclass
class Utterance:
    """A contiguous block of speech from a single speaker."""
    speaker: str
    start: float
    end: float
    text: str
    word_count: int

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "speaker": self.speaker,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "text": self.text,
            "word_count": self.word_count,
        }


def collapse_words_to_utterances(
    enhanced_transcript: Dict[str, Any],
    max_pause: float = 2.0,
) -> List[Utterance]:
    """
    Collapse word-level transcript into speaker utterances/turns.

    Groups consecutive words from the same speaker into a single utterance.
    Starts a new utterance when:
    - The speaker changes, OR
    - There's a pause longer than max_pause seconds between words

    Args:
        enhanced_transcript: Transcript dict with "words" list where each
                            word has "text", "start", "end", "speaker_name".
        max_pause: Maximum gap in seconds before splitting into a new
                  utterance from the same speaker. Default 2.0s.

    Returns:
        List of Utterance objects in chronological order.
    """
    words = enhanced_transcript.get("words", [])
    if not words:
        return []

    utterances: List[Utterance] = []
    current_speaker = words[0].get("speaker_name", "unknown")
    current_start = words[0]["start"]
    current_end = words[0].get("end", current_start + 0.1)
    current_words: List[str] = [words[0].get("text", "")]

    for word in words[1:]:
        speaker = word.get("speaker_name", "unknown")
        w_start = word["start"]
        w_end = word.get("end", w_start + 0.1)
        gap = w_start - current_end

        # New utterance if speaker changed or long pause
        if speaker != current_speaker or gap > max_pause:
            utterances.append(Utterance(
                speaker=current_speaker,
                start=current_start,
                end=current_end,
                text=" ".join(current_words),
                word_count=len(current_words),
            ))
            current_speaker = speaker
            current_start = w_start
            current_words = []

        current_end = w_end
        current_words.append(word.get("text", ""))

    # Don't forget the last utterance
    if current_words:
        utterances.append(Utterance(
            speaker=current_speaker,
            start=current_start,
            end=current_end,
            text=" ".join(current_words),
            word_count=len(current_words),
        ))

    logger.info(
        f"Collapsed {len(words)} words into {len(utterances)} utterances"
    )
    return utterances


def build_readable_transcript(
    utterances: List[Utterance],
) -> str:
    """
    Format utterances into a human/LLM-readable transcript string.

    Output format:
        [0:05:14] Nick: What version is it?
        [0:05:16] SPEAKER_10: New American Standard.
        [0:05:17] SPEAKER_06: Ask him if it has a mass.

    Args:
        utterances: List of Utterance objects.

    Returns:
        Formatted transcript string.
    """
    lines: List[str] = []
    for utt in utterances:
        ts = format_timestamp(utt.start)
        lines.append(f"[{ts}] {utt.speaker}: {utt.text}")
    return "\n".join(lines)


def build_structured_transcript(
    utterances: List[Utterance],
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a structured JSON transcript from utterances.

    This is the format optimized for LLM clip-finding analysis:
    - Each entry is a full speaker turn (not individual words)
    - Includes start/end timestamps for precise clip extraction
    - Compact enough for LLM context windows

    Args:
        utterances: List of Utterance objects.
        metadata: Optional metadata dict to include.

    Returns:
        Structured dict with utterances list and summary stats.
    """
    # Build speaker summary
    speaker_stats: Dict[str, Dict[str, Any]] = {}
    for utt in utterances:
        if utt.speaker not in speaker_stats:
            speaker_stats[utt.speaker] = {
                "total_words": 0,
                "total_utterances": 0,
                "first_seen": utt.start,
                "last_seen": utt.end,
            }
        stats = speaker_stats[utt.speaker]
        stats["total_words"] += utt.word_count
        stats["total_utterances"] += 1
        stats["last_seen"] = max(stats["last_seen"], utt.end)

    return {
        "format": "utterance_transcript_v3",
        "utterances": [u.to_dict() for u in utterances],
        "summary": {
            "total_utterances": len(utterances),
            "total_words": sum(u.word_count for u in utterances),
            "duration_seconds": round(
                utterances[-1].end - utterances[0].start, 1
            ) if utterances else 0,
            "speakers": speaker_stats,
        },
        "metadata": metadata or {},
    }
