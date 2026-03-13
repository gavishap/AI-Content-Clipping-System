"""
Clip Extraction Module - FFmpeg Integration

Extracts video clips with precise timestamps using FFmpeg.
"""

import asyncio
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class ClipResult:
    """Result of clip extraction."""
    clip_id: str
    file_path: str
    title: str
    start_time: float
    end_time: float
    duration_seconds: float
    file_size_mb: float
    status: str  # "success" or "failed"
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ClipExtractor:
    """
    Extracts video clips using FFmpeg with precise timestamps.
    
    Usage:
        extractor = ClipExtractor("video.mp4", "./clips")
        results = await extractor.extract_clips(clips[:10])
    """
    
    # Quality presets for FFmpeg
    QUALITY_PRESETS = {
        "fast": {
            "preset": "ultrafast",
            "crf": 28,
            "audio_bitrate": "128k"
        },
        "medium": {
            "preset": "medium",
            "crf": 23,
            "audio_bitrate": "192k"
        },
        "high": {
            "preset": "slow",
            "crf": 18,
            "audio_bitrate": "256k"
        }
    }
    
    def __init__(
        self,
        input_video: str,
        output_dir: str,
        ffmpeg_path: str = "ffmpeg"
    ):
        """
        Initialize with input video and output directory.
        
        Args:
            input_video: Path to source video file
            output_dir: Directory for extracted clips
            ffmpeg_path: Path to FFmpeg executable
        """
        self.input_video = Path(input_video)
        self.output_dir = Path(output_dir)
        self.ffmpeg_path = ffmpeg_path
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        if not self.input_video.exists():
            raise FileNotFoundError(f"Video not found: {input_video}")
        
        logger.info(f"ClipExtractor initialized: {input_video} -> {output_dir}")
    
    def _sanitize_filename(self, title: str) -> str:
        """Convert title to safe filename."""
        # Remove or replace unsafe characters
        safe = re.sub(r'[<>:"/\\|?*]', '', title)
        safe = re.sub(r'\s+', '_', safe)
        safe = safe[:50]  # Limit length
        return safe
    
    def _format_timestamp(self, seconds: float) -> str:
        """Convert seconds to HH:MM:SS.mmm format for FFmpeg."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
    
    async def extract_clip(
        self,
        clip: Dict[str, Any],
        padding_start: float = 10.0,
        padding_end: float = 10.0,
        quality: str = "medium"
    ) -> ClipResult:
        """
        Extract a single clip with precise timestamps.
        
        Args:
            clip: Clip data with start_time, end_time, title, clip_id
            padding_start: Seconds to add before start
            padding_end: Seconds to add after end
            quality: "fast", "medium", or "high"
            
        Returns:
            ClipResult with extraction status
        """
        clip_id = clip['clip_id']
        title = clip.get('title', clip_id)
        start_time = float(clip['start_time']) - padding_start
        end_time = float(clip['end_time']) + padding_end
        
        # Ensure start is not negative
        start_time = max(0, start_time)
        duration = end_time - start_time
        
        # Build output filename
        safe_title = self._sanitize_filename(title)
        output_file = self.output_dir / f"{clip_id}_{safe_title}.mp4"
        
        # Get quality settings
        preset = self.QUALITY_PRESETS.get(quality, self.QUALITY_PRESETS["medium"])
        
        # Build FFmpeg command
        # Using -ss before -i for fast seeking, then -t for duration
        cmd = [
            self.ffmpeg_path,
            "-y",  # Overwrite output
            "-ss", self._format_timestamp(start_time),  # Seek to start (fast)
            "-i", str(self.input_video),
            "-t", str(duration),  # Duration
            "-c:v", "libx264",  # Video codec
            "-preset", preset["preset"],
            "-crf", str(preset["crf"]),
            "-c:a", "aac",  # Audio codec
            "-b:a", preset["audio_bitrate"],
            "-movflags", "+faststart",  # Web optimization
            "-pix_fmt", "yuv420p",  # Compatibility
            str(output_file)
        ]
        
        logger.info(f"Extracting {clip_id}: {self._format_timestamp(start_time)} -> {self._format_timestamp(end_time)} ({duration:.1f}s)")
        
        try:
            # Run FFmpeg
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore')[-500:]
                logger.error(f"FFmpeg failed for {clip_id}: {error_msg}")
                return ClipResult(
                    clip_id=clip_id,
                    file_path="",
                    title=title,
                    start_time=start_time,
                    end_time=end_time,
                    duration_seconds=duration,
                    file_size_mb=0,
                    status="failed",
                    error=error_msg
                )
            
            # Get file size
            file_size_mb = output_file.stat().st_size / (1024 * 1024)
            
            logger.info(f"  ✓ {clip_id}: {output_file.name} ({file_size_mb:.1f}MB)")
            
            return ClipResult(
                clip_id=clip_id,
                file_path=str(output_file),
                title=title,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration,
                file_size_mb=file_size_mb,
                status="success"
            )
            
        except Exception as e:
            logger.error(f"Exception extracting {clip_id}: {e}")
            return ClipResult(
                clip_id=clip_id,
                file_path="",
                title=title,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration,
                file_size_mb=0,
                status="failed",
                error=str(e)
            )
    
    async def extract_clips(
        self,
        clips: List[Dict[str, Any]],
        quality: str = "medium",
        padding_start: float = 10.0,
        padding_end: float = 10.0
    ) -> List[ClipResult]:
        """
        Extract multiple clips sequentially.
        
        Args:
            clips: List of clip data dicts
            quality: "fast", "medium", or "high"
            padding_start: Seconds to add before each clip
            padding_end: Seconds to add after each clip
            
        Returns:
            List of ClipResult objects
        """
        logger.info(f"Extracting {len(clips)} clips with quality={quality}")
        
        results = []
        for i, clip in enumerate(clips, 1):
            print(f"Extracting clip {i}/{len(clips)}: {clip.get('title', clip['clip_id'])[:40]}...")
            
            result = await self.extract_clip(
                clip,
                padding_start=padding_start,
                padding_end=padding_end,
                quality=quality
            )
            results.append(result)
        
        # Summary
        successful = sum(1 for r in results if r.status == "success")
        total_size = sum(r.file_size_mb for r in results)
        
        logger.info(f"Extraction complete: {successful}/{len(clips)} successful, {total_size:.1f}MB total")
        
        return results
    
    def save_results(
        self,
        results: List[ClipResult],
        output_path: str
    ) -> None:
        """Save extraction results to JSON."""
        data = {
            "source_video": str(self.input_video),
            "output_dir": str(self.output_dir),
            "total_clips": len(results),
            "successful": sum(1 for r in results if r.status == "success"),
            "failed": sum(1 for r in results if r.status == "failed"),
            "total_size_mb": sum(r.file_size_mb for r in results),
            "clips": [r.to_dict() for r in results]
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Results saved to: {output_path}")


    async def extract_composite_clip(
        self,
        segments: List[Dict[str, Any]],
        clip_id: str,
        title: str = "composite",
        quality: str = "medium",
    ) -> ClipResult:
        """
        Extract multiple non-contiguous segments and merge into one video.

        Uses FFmpeg's concat demuxer for fast lossless concatenation when
        segments come from the same source video.

        Args:
            segments: List of dicts with start_time, end_time (in seconds)
            clip_id: Unique ID for this composite clip
            title: Display title
            quality: "fast", "medium", or "high"

        Returns:
            ClipResult with the merged output path
        """
        import tempfile

        if not segments:
            return ClipResult(
                clip_id=clip_id, file_path="", title=title,
                start_time=0, end_time=0, duration_seconds=0,
                file_size_mb=0, status="failed", error="No segments provided",
            )

        safe_title = self._sanitize_filename(title)
        output_file = self.output_dir / f"{clip_id}_{safe_title}.mp4"
        preset = self.QUALITY_PRESETS.get(quality, self.QUALITY_PRESETS["medium"])

        temp_dir = Path(tempfile.mkdtemp(prefix="clipmerge_"))
        temp_files: List[Path] = []

        try:
            # Extract each segment to a temp file
            for i, seg in enumerate(segments):
                start = max(0, float(seg["start_time"]) - 10.0)
                end = float(seg["end_time"]) + 10.0
                duration = end - start
                temp_out = temp_dir / f"seg_{i:03d}.mp4"

                cmd = [
                    self.ffmpeg_path, "-y",
                    "-ss", self._format_timestamp(start),
                    "-i", str(self.input_video),
                    "-t", str(duration),
                    "-c:v", "libx264",
                    "-preset", preset["preset"],
                    "-crf", str(preset["crf"]),
                    "-c:a", "aac",
                    "-b:a", preset["audio_bitrate"],
                    "-pix_fmt", "yuv420p",
                    str(temp_out),
                ]

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await process.communicate()

                if process.returncode != 0:
                    error_msg = stderr.decode("utf-8", errors="ignore")[-300:]
                    logger.error(f"Segment {i} extraction failed: {error_msg}")
                    continue

                if temp_out.exists():
                    temp_files.append(temp_out)

            if not temp_files:
                return ClipResult(
                    clip_id=clip_id, file_path="", title=title,
                    start_time=segments[0].get("start_time", 0),
                    end_time=segments[-1].get("end_time", 0),
                    duration_seconds=0, file_size_mb=0,
                    status="failed", error="All segment extractions failed",
                )

            # Write concat demuxer file
            concat_file = temp_dir / "concat.txt"
            with open(concat_file, "w", encoding="utf-8") as f:
                for tf in temp_files:
                    safe_path = str(tf).replace("\\", "/")
                    f.write(f"file '{safe_path}'\n")

            # Merge with concat demuxer
            merge_cmd = [
                self.ffmpeg_path, "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_file),
                "-c", "copy",
                "-movflags", "+faststart",
                str(output_file),
            ]

            process = await asyncio.create_subprocess_exec(
                *merge_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="ignore")[-300:]
                logger.error(f"Concat merge failed: {error_msg}")
                return ClipResult(
                    clip_id=clip_id, file_path="", title=title,
                    start_time=segments[0].get("start_time", 0),
                    end_time=segments[-1].get("end_time", 0),
                    duration_seconds=0, file_size_mb=0,
                    status="failed", error=f"Merge failed: {error_msg}",
                )

            total_dur = sum(
                float(s.get("end_time", 0)) - float(s.get("start_time", 0))
                for s in segments
            )
            file_size_mb = output_file.stat().st_size / (1024 * 1024)

            logger.info(f"Composite clip merged: {output_file.name} ({file_size_mb:.1f}MB, {len(segments)} segments)")

            return ClipResult(
                clip_id=clip_id,
                file_path=str(output_file),
                title=title,
                start_time=segments[0].get("start_time", 0),
                end_time=segments[-1].get("end_time", 0),
                duration_seconds=round(total_dur, 2),
                file_size_mb=round(file_size_mb, 2),
                status="success",
            )

        except Exception as e:
            logger.error(f"Composite extraction failed: {e}")
            return ClipResult(
                clip_id=clip_id, file_path="", title=title,
                start_time=0, end_time=0, duration_seconds=0,
                file_size_mb=0, status="failed", error=str(e),
            )
        finally:
            # Clean up temp files
            for tf in temp_files:
                try:
                    tf.unlink()
                except OSError:
                    pass
            try:
                (temp_dir / "concat.txt").unlink(missing_ok=True)
                temp_dir.rmdir()
            except OSError:
                pass


async def extract_top_clips(
    video_path: str,
    clips_json: str,
    output_dir: str,
    top_n: int = 10,
    quality: str = "medium"
) -> List[ClipResult]:
    """
    Convenience function to extract top N clips.
    
    Args:
        video_path: Path to source video
        clips_json: Path to clips JSON file
        output_dir: Directory for extracted clips
        top_n: Number of clips to extract
        quality: Extraction quality preset
        
    Returns:
        List of ClipResult objects
    """
    # Load clips
    with open(clips_json, 'r', encoding='utf-8') as f:
        clips = json.load(f)
    
    # Take top N
    clips = clips[:top_n]
    
    # Extract
    extractor = ClipExtractor(video_path, output_dir)
    results = await extractor.extract_clips(clips, quality=quality)
    
    # Save results
    results_path = os.path.join(output_dir, "extraction_results.json")
    extractor.save_results(results, results_path)
    
    return results


if __name__ == "__main__":
    import sys
    
    async def main():
        if len(sys.argv) < 4:
            print("Usage: python extractor.py <video_path> <clips_json> <output_dir> [top_n]")
            sys.exit(1)
        
        video_path = sys.argv[1]
        clips_json = sys.argv[2]
        output_dir = sys.argv[3]
        top_n = int(sys.argv[4]) if len(sys.argv) > 4 else 10
        
        results = await extract_top_clips(video_path, clips_json, output_dir, top_n)
        
        print(f"\nExtracted {sum(1 for r in results if r.status == 'success')}/{len(results)} clips")
        for r in results:
            if r.status == "success":
                print(f"  ✓ {r.clip_id}: {r.title[:40]} ({r.duration_seconds:.0f}s, {r.file_size_mb:.1f}MB)")
            else:
                print(f"  ✗ {r.clip_id}: {r.error[:50]}")
    
    asyncio.run(main())
