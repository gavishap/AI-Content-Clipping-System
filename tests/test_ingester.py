"""Tests for ingester module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import json

from src.ingester import VideoIngester, VideoMetadata, get_video_duration


class TestVideoMetadata:
    """Test VideoMetadata dataclass."""
    
    def test_creation(self):
        metadata = VideoMetadata(
            duration_seconds=3600.5,
            duration_formatted="01:00:00",
            width=1920,
            height=1080,
            fps=30.0,
            codec="h264",
            bitrate=8000000,
            file_size_mb=1024.5,
        )
        assert metadata.duration_seconds == 3600.5
        assert metadata.width == 1920
        assert metadata.height == 1080


class TestVideoIngester:
    """Test VideoIngester class."""
    
    def test_format_duration(self):
        """Test duration formatting."""
        assert VideoIngester._format_duration(0) == "00:00:00"
        assert VideoIngester._format_duration(59) == "00:00:59"
        assert VideoIngester._format_duration(60) == "00:01:00"
        assert VideoIngester._format_duration(3600) == "01:00:00"
        assert VideoIngester._format_duration(3661) == "01:01:01"
        assert VideoIngester._format_duration(14423) == "04:00:23"
    
    def test_parse_fps(self):
        """Test FPS parsing from ffprobe format."""
        assert VideoIngester._parse_fps("30/1") == 30.0
        assert VideoIngester._parse_fps("30000/1001") == pytest.approx(29.97, rel=0.01)
        assert VideoIngester._parse_fps("60/1") == 60.0
        assert VideoIngester._parse_fps("0/1") == 0.0
        assert VideoIngester._parse_fps("invalid") == 0.0
    
    def test_file_not_found_raises(self):
        """Test that missing video file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            VideoIngester("/nonexistent/video.mp4")
    
    @patch('src.ingester.subprocess.run')
    def test_ffmpeg_verification(self, mock_run, tmp_path):
        """Test FFmpeg verification on init."""
        # Create a dummy video file
        video_file = tmp_path / "test.mp4"
        video_file.touch()
        
        # Mock successful ffmpeg/ffprobe calls
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="ffmpeg version 5.0",
            stderr=""
        )
        
        # Should not raise
        ingester = VideoIngester(str(video_file))
        assert ingester.video_path == video_file


class TestGetVideoDuration:
    """Test get_video_duration utility function."""
    
    @patch('src.ingester.subprocess.run')
    def test_returns_duration(self, mock_run):
        """Test duration extraction."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="123.456\n",
            stderr=""
        )
        
        duration = get_video_duration("/path/to/video.mp4")
        assert duration == 123.456
    
    @patch('src.ingester.subprocess.run')
    def test_returns_zero_on_error(self, mock_run):
        """Test returns 0 on error."""
        from subprocess import CalledProcessError
        mock_run.side_effect = CalledProcessError(1, "ffprobe")
        
        duration = get_video_duration("/path/to/video.mp4")
        assert duration == 0.0
