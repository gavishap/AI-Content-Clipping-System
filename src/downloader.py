"""
YouTube Downloader Module - yt-dlp Integration

Owner: Gabriel
Status: Implemented

This module handles downloading videos from YouTube URLs.
"""

import logging
import base64
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yt_dlp

logger = logging.getLogger(__name__)

# Cached path so we only write cookies once per process
_cookies_file_path: Optional[str] = None


def _get_cookies_file() -> Optional[str]:
    """
    Write YouTube cookies to a temp file if YOUTUBE_COOKIES_B64 env var is set.
    Returns the path to the cookies file, or None if not configured.
    """
    global _cookies_file_path
    if _cookies_file_path and Path(_cookies_file_path).exists():
        return _cookies_file_path

    cookies_b64 = os.environ.get("YOUTUBE_COOKIES_B64")
    if not cookies_b64:
        # Also check for a direct file path
        cookies_path = os.environ.get("YOUTUBE_COOKIES_PATH")
        if cookies_path and Path(cookies_path).exists():
            return cookies_path
        return None

    try:
        cookies_data = base64.b64decode(cookies_b64).decode("utf-8")
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix="_youtube_cookies.txt",
            delete=False, encoding="utf-8"
        )
        tmp.write(cookies_data)
        tmp.close()
        _cookies_file_path = tmp.name
        logger.info(f"YouTube cookies written to: {_cookies_file_path}")
        return _cookies_file_path
    except Exception as e:
        logger.warning(f"Failed to write YouTube cookies: {e}")
        return None


@dataclass
class DownloadResult:
    """Result of a YouTube download operation."""
    video_path: str
    title: str
    duration_seconds: float
    channel: str
    video_id: str
    thumbnail_url: Optional[str] = None
    description: Optional[str] = None


class YouTubeDownloader:
    """
    Downloads videos from YouTube using yt-dlp.
    
    Usage:
        downloader = YouTubeDownloader(output_dir="./data")
        result = downloader.download("https://youtube.com/watch?v=...")
    """
    
    # Default format: best video + best audio, falls back to best combined
    # For livestream replays, this will merge video+audio streams using FFmpeg
    DEFAULT_FORMAT = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best"
    
    def __init__(self, output_dir: str = "./data"):
        """
        Initialize downloader with output directory.
        
        Args:
            output_dir: Directory to save downloaded videos
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"YouTubeDownloader initialized with output_dir: {self.output_dir}")
    
    def download(
        self, 
        url: str, 
        format_str: Optional[str] = None,
        filename_template: Optional[str] = None
    ) -> DownloadResult:
        """
        Download a YouTube video.
        
        Args:
            url: YouTube video URL
            format_str: yt-dlp format string (default: best up to 1080p)
            filename_template: Output filename template (default: %(title)s.%(ext)s)
            
        Returns:
            DownloadResult with video path and metadata
            
        Raises:
            ValueError: If URL is invalid
            RuntimeError: If download fails
        """
        if not self._is_valid_youtube_url(url):
            raise ValueError(f"Invalid YouTube URL: {url}")
        
        format_str = format_str or self.DEFAULT_FORMAT
        filename_template = filename_template or "%(title)s.%(ext)s"
        
        output_template = str(self.output_dir / filename_template)
        
        ydl_opts = {
            'format': format_str,
            'outtmpl': output_template,
            'quiet': False,
            'no_warnings': False,
            'extract_flat': False,
            'logger': _YtDlpLogger(),
            'progress_hooks': [self._progress_hook],
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'geo_bypass': True,
            # bgutil PO token provider - connects to local server at port 4416
            # Automatically used by yt-dlp when bgutil-ytdlp-pot-provider is installed
        }

        # Inject YouTube cookies if provided (optional, bgutil handles auth)
        cookies_file = _get_cookies_file()
        if cookies_file:
            ydl_opts['cookiefile'] = cookies_file
            logger.info(f"Using YouTube cookies from: {cookies_file}")
        
        # Only add merge format if FFmpeg is available
        if self._is_ffmpeg_available():
            ydl_opts['merge_output_format'] = 'mp4'
        
        logger.info(f"Starting download: {url}")
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info first to get metadata
                info = ydl.extract_info(url, download=True)
                
                if info is None:
                    raise RuntimeError("Failed to extract video info")
                
                # Get the actual downloaded file path
                video_path = self._get_downloaded_path(info, output_template)
                
                result = DownloadResult(
                    video_path=str(video_path),
                    title=info.get('title', 'Unknown'),
                    duration_seconds=float(info.get('duration', 0)),
                    channel=info.get('channel', info.get('uploader', 'Unknown')),
                    video_id=info.get('id', ''),
                    thumbnail_url=info.get('thumbnail'),
                    description=info.get('description'),
                )
                
                logger.info(f"Download complete: {result.title} ({result.duration_seconds:.0f}s)")
                return result
                
        except yt_dlp.utils.DownloadError as e:
            logger.error(f"Download failed: {e}")
            raise RuntimeError(f"Failed to download video: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error during download: {e}")
            raise RuntimeError(f"Download failed: {e}") from e
    
    def get_video_info(self, url: str) -> dict:
        """
        Get video metadata without downloading.
        
        Args:
            url: YouTube video URL
            
        Returns:
            Dictionary with video metadata
        """
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info or {}
    
    def _get_downloaded_path(self, info: dict, template: str) -> Path:
        """Determine the actual downloaded file path."""
        # yt-dlp may add .mp4 extension after merging
        title = info.get('title', 'video')
        # Sanitize title for filename
        safe_title = yt_dlp.utils.sanitize_filename(title)
        
        # Try common extensions
        for ext in ['mp4', 'mkv', 'webm']:
            potential_path = self.output_dir / f"{safe_title}.{ext}"
            if potential_path.exists():
                return potential_path
        
        # Fallback: look for any video file with the title
        for file in self.output_dir.glob(f"{safe_title}.*"):
            if file.suffix.lower() in ['.mp4', '.mkv', '.webm', '.mov']:
                return file
        
        # Last resort: use the template
        return Path(template % info)
    
    @staticmethod
    def _is_valid_youtube_url(url: str) -> bool:
        """Check if URL is a valid YouTube URL."""
        youtube_patterns = [
            r'(https?://)?(www\.)?youtube\.com/watch\?v=[\w-]+',
            r'(https?://)?(www\.)?youtube\.com/v/[\w-]+',
            r'(https?://)?(www\.)?youtu\.be/[\w-]+',
            r'(https?://)?(www\.)?youtube\.com/shorts/[\w-]+',
            r'(https?://)?(www\.)?youtube\.com/live/[\w-]+',
        ]
        return any(re.match(pattern, url) for pattern in youtube_patterns)
    
    @staticmethod
    def _is_ffmpeg_available() -> bool:
        """Check if FFmpeg is available in PATH."""
        import subprocess
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    
    def _progress_hook(self, d: dict) -> None:
        """Hook called during download progress."""
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                percent = (downloaded / total) * 100
                logger.debug(f"Download progress: {percent:.1f}%")
        elif d['status'] == 'finished':
            logger.info(f"Download finished, processing...")


class _YtDlpLogger:
    """Custom logger for yt-dlp to integrate with Python logging."""
    
    def debug(self, msg: str) -> None:
        if msg.startswith('[debug]'):
            logger.debug(msg)
        else:
            logger.info(msg)
    
    def info(self, msg: str) -> None:
        logger.info(msg)
    
    def warning(self, msg: str) -> None:
        logger.warning(msg)
    
    def error(self, msg: str) -> None:
        logger.error(msg)


def extract_video_id(url: str) -> Optional[str]:
    """
    Extract video ID from a YouTube URL.
    
    Args:
        url: YouTube video URL
        
    Returns:
        Video ID string or None if not found
    """
    patterns = [
        r'(?:v=|/v/|youtu\.be/|/embed/|/shorts/|/live/)([a-zA-Z0-9_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None
