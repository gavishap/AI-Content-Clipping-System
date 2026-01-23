"""
Video Ingestion Module - FFmpeg Integration

Owner: Jake
Status: Implemented

This module handles video input and audio extraction using FFmpeg.
"""

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class VideoMetadata:
    """Metadata extracted from video file."""
    duration_seconds: float
    duration_formatted: str
    width: int
    height: int
    fps: float
    codec: str
    bitrate: int
    file_size_mb: float


class VideoIngester:
    """
    Handles video ingestion and audio extraction using FFmpeg.
    
    Usage:
        ingester = VideoIngester("video.mp4")
        audio_path = ingester.extract_audio()
        metadata = ingester.metadata
    """
    
    # Audio extraction settings optimized for speech recognition
    AUDIO_SAMPLE_RATE = 16000  # 16kHz - optimal for ASR
    AUDIO_CHANNELS = 1  # Mono
    AUDIO_CODEC = "pcm_s16le"  # 16-bit PCM WAV
    
    def __init__(self, video_path: str):
        """
        Initialize with video file path.
        
        Args:
            video_path: Path to MP4/MKV/MOV video file
            
        Raises:
            FileNotFoundError: If video file doesn't exist
            RuntimeError: If FFmpeg is not available
        """
        self.video_path = Path(video_path)
        if not self.video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")
        
        # Verify FFmpeg is available
        self._verify_ffmpeg()
        
        # Extract metadata on init
        self._metadata: Optional[VideoMetadata] = None
        logger.info(f"VideoIngester initialized for: {self.video_path.name}")
    
    @property
    def metadata(self) -> VideoMetadata:
        """Get video metadata (lazy loaded)."""
        if self._metadata is None:
            self._metadata = self._extract_metadata()
        return self._metadata
    
    def extract_audio(self, output_path: Optional[str] = None) -> str:
        """
        Extract audio as 16kHz mono WAV (optimal for ASR).
        
        Args:
            output_path: Output WAV path (default: same name as video with .wav)
            
        Returns:
            Path to extracted WAV file
            
        Raises:
            RuntimeError: If audio extraction fails
        """
        if output_path is None:
            output_path = str(self.video_path.with_suffix('.wav'))
        
        output_file = Path(output_path)
        
        # Build FFmpeg command for audio extraction
        cmd = [
            'ffmpeg',
            '-i', str(self.video_path),
            '-vn',  # No video
            '-acodec', self.AUDIO_CODEC,
            '-ar', str(self.AUDIO_SAMPLE_RATE),
            '-ac', str(self.AUDIO_CHANNELS),
            '-y',  # Overwrite output
            str(output_file)
        ]
        
        logger.info(f"Extracting audio to: {output_file}")
        logger.debug(f"FFmpeg command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            if not output_file.exists():
                raise RuntimeError("Audio extraction completed but file not found")
            
            file_size_mb = output_file.stat().st_size / (1024 * 1024)
            logger.info(f"Audio extraction complete: {output_file.name} ({file_size_mb:.1f} MB)")
            
            return str(output_file)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e.stderr}")
            raise RuntimeError(f"Audio extraction failed: {e.stderr}") from e
        except Exception as e:
            logger.error(f"Unexpected error during audio extraction: {e}")
            raise RuntimeError(f"Audio extraction failed: {e}") from e
    
    def _extract_metadata(self) -> VideoMetadata:
        """
        Extract metadata using ffprobe.
        
        Returns:
            VideoMetadata dataclass with video properties
        """
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            str(self.video_path)
        ]
        
        logger.debug(f"Running ffprobe: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            data = json.loads(result.stdout)
            
            # Get video stream info
            video_stream = None
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_stream = stream
                    break
            
            format_info = data.get('format', {})
            
            # Extract values with defaults
            duration = float(format_info.get('duration', 0))
            width = int(video_stream.get('width', 0)) if video_stream else 0
            height = int(video_stream.get('height', 0)) if video_stream else 0
            
            # Parse FPS from avg_frame_rate (e.g., "30/1" or "30000/1001")
            fps = self._parse_fps(video_stream.get('avg_frame_rate', '0/1')) if video_stream else 0.0
            
            codec = video_stream.get('codec_name', 'unknown') if video_stream else 'unknown'
            bitrate = int(format_info.get('bit_rate', 0))
            file_size = self.video_path.stat().st_size / (1024 * 1024)  # MB
            
            metadata = VideoMetadata(
                duration_seconds=duration,
                duration_formatted=self._format_duration(duration),
                width=width,
                height=height,
                fps=fps,
                codec=codec,
                bitrate=bitrate,
                file_size_mb=round(file_size, 2)
            )
            
            logger.info(
                f"Video metadata: {metadata.duration_formatted}, "
                f"{metadata.width}x{metadata.height}, "
                f"{metadata.fps:.2f}fps, {metadata.file_size_mb:.1f}MB"
            )
            
            return metadata
            
        except subprocess.CalledProcessError as e:
            logger.error(f"ffprobe error: {e.stderr}")
            raise RuntimeError(f"Failed to extract metadata: {e.stderr}") from e
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse ffprobe output: {e}")
            raise RuntimeError(f"Failed to parse metadata: {e}") from e
    
    @staticmethod
    def _parse_fps(fps_str: str) -> float:
        """Parse FPS from ffprobe format (e.g., '30/1' or '30000/1001')."""
        try:
            if '/' in fps_str:
                num, den = fps_str.split('/')
                if int(den) == 0:
                    return 0.0
                return float(num) / float(den)
            return float(fps_str)
        except (ValueError, ZeroDivisionError):
            return 0.0
    
    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Convert seconds to HH:MM:SS format."""
        hours, remainder = divmod(int(seconds), 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    @staticmethod
    def _verify_ffmpeg() -> None:
        """Verify FFmpeg and ffprobe are available."""
        for tool in ['ffmpeg', 'ffprobe']:
            try:
                result = subprocess.run(
                    [tool, '-version'],
                    capture_output=True,
                    text=True,
                    check=True
                )
                logger.debug(f"{tool} version: {result.stdout.split()[2] if len(result.stdout.split()) > 2 else 'unknown'}")
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                raise RuntimeError(
                    f"{tool} not found. Please install FFmpeg:\n"
                    "  Windows: choco install ffmpeg\n"
                    "  Mac: brew install ffmpeg\n"
                    "  Linux: apt install ffmpeg"
                ) from e


def get_video_duration(video_path: str) -> float:
    """
    Quick utility to get video duration without full metadata extraction.
    
    Args:
        video_path: Path to video file
        
    Returns:
        Duration in seconds
    """
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return 0.0
