"""Tests for downloader module."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.downloader import (
    YouTubeDownloader, 
    DownloadResult, 
    extract_video_id,
)


class TestExtractVideoId:
    """Test extract_video_id function."""
    
    def test_standard_url(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"
    
    def test_short_url(self):
        url = "https://youtu.be/dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"
    
    def test_shorts_url(self):
        url = "https://www.youtube.com/shorts/dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"
    
    def test_live_url(self):
        url = "https://www.youtube.com/live/dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"
    
    def test_invalid_url(self):
        url = "https://example.com/video"
        assert extract_video_id(url) is None


class TestYouTubeDownloader:
    """Test YouTubeDownloader class."""
    
    def test_is_valid_youtube_url(self):
        """Test URL validation."""
        valid_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
            "https://www.youtube.com/live/dQw4w9WgXcQ",
        ]
        
        invalid_urls = [
            "https://example.com/video",
            "https://vimeo.com/123456",
            "not a url",
        ]
        
        for url in valid_urls:
            assert YouTubeDownloader._is_valid_youtube_url(url), f"Expected valid: {url}"
        
        for url in invalid_urls:
            assert not YouTubeDownloader._is_valid_youtube_url(url), f"Expected invalid: {url}"
    
    def test_init_creates_output_dir(self, tmp_path):
        """Test that init creates output directory."""
        output_dir = tmp_path / "downloads"
        downloader = YouTubeDownloader(output_dir=str(output_dir))
        assert output_dir.exists()
    
    def test_download_invalid_url_raises(self, tmp_path):
        """Test that invalid URL raises ValueError."""
        downloader = YouTubeDownloader(output_dir=str(tmp_path))
        with pytest.raises(ValueError, match="Invalid YouTube URL"):
            downloader.download("https://example.com/not-youtube")


class TestDownloadResult:
    """Test DownloadResult dataclass."""
    
    def test_creation(self):
        result = DownloadResult(
            video_path="/path/to/video.mp4",
            title="Test Video",
            duration_seconds=120.5,
            channel="Test Channel",
            video_id="abc123",
        )
        assert result.video_path == "/path/to/video.mp4"
        assert result.title == "Test Video"
        assert result.duration_seconds == 120.5
        assert result.channel == "Test Channel"
        assert result.video_id == "abc123"
