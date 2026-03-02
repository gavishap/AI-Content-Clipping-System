"""
Worker process for the automated clip pipeline.

Polls a Google Sheet for new job submissions, runs the full
analysis pipeline (download -> transcribe -> enhance -> segment ->
topic map -> find clips -> extract), uploads results to Google Drive,
and updates the Sheet with links.

Run: python -m src.worker
"""

import asyncio
import json
import logging
import os
import re
import shutil
import time
import traceback
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "120"))  # seconds
VOICEPRINT_PATH = os.environ.get("VOICEPRINT_PATH", "nick_voiceprint.json")
WORK_DIR = Path(os.environ.get("WORK_DIR", "/tmp/clipper_work"))


def _is_youtube_url(url: str) -> bool:
    return any(x in url.lower() for x in ["youtube.com", "youtu.be"])


def _is_drive_url(url: str) -> bool:
    return "drive.google.com" in url.lower()


def _safe_filename(title: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*]', '', title)
    return re.sub(r'\s+', '_', safe)[:60]


def run_pipeline(video_url: str, query: str | None, max_clips: int) -> dict:
    """
    Run the full clip-finding pipeline on a video.

    Returns dict with keys: output_dir, clips_dir, video_title, clip_count,
    report_path, topic_map_path, conversation_map_path
    """
    from src.downloader import YouTubeDownloader
    from src.ingester import VideoIngester
    from src.transcriber import Transcriber
    from src.voice_fingerprinter import (
        VoiceFingerprinter, Voiceprint,
        merge_pyannote_speakers_with_transcript,
        collapse_words_to_utterances, build_readable_transcript,
        build_structured_transcript,
    )
    from src.conversation_segmenter_v3 import segment_conversations, save_conversation_map
    from src.topic_mapper import TopicMapper, save_topic_map
    from src.clip_finder_unified import ClipFinderUnified
    from src.story_clip_finder import StoryClipFinder
    from src.extractor import ClipExtractor
    from src.google_drive import download_from_drive

    api_key = os.environ.get("DEEPGRAM_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPGRAM_API_KEY not set")

    WORK_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # STEP 1: Download video
    # ------------------------------------------------------------------
    logger.info("STEP 1: Downloading video...")

    if _is_youtube_url(video_url):
        downloader = YouTubeDownloader(output_dir=str(WORK_DIR / "download"))
        result = downloader.download(video_url)
        video_title = result.title
        video_src = Path(result.video_path)
    elif _is_drive_url(video_url):
        dl_dir = WORK_DIR / "download"
        dl_dir.mkdir(parents=True, exist_ok=True)
        local_path = str(dl_dir / "source_video.mp4")
        download_from_drive(video_url, local_path)
        video_title = "Drive_Video"
        video_src = Path(local_path)
    else:
        raise ValueError(f"Unsupported URL type: {video_url}")

    safe_name = _safe_filename(video_title)
    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    output_dir = WORK_DIR / f"{safe_name}_{date_str}"
    output_dir.mkdir(parents=True, exist_ok=True)
    clips_dir = output_dir / "clips"
    clips_dir.mkdir(exist_ok=True)

    video_path = output_dir / video_src.name
    if not video_path.exists():
        shutil.move(str(video_src), str(video_path))

    logger.info(f"  Title: {video_title}")
    logger.info(f"  Output: {output_dir}")

    # ------------------------------------------------------------------
    # STEP 2: Extract audio
    # ------------------------------------------------------------------
    logger.info("STEP 2: Extracting audio...")
    audio_path = output_dir / (video_path.stem + ".wav")
    if not audio_path.exists():
        ingester = VideoIngester(str(video_path))
        ingester.extract_audio(str(audio_path))
    logger.info(f"  Audio: {audio_path.name}")

    # ------------------------------------------------------------------
    # STEP 3: Transcribe with Deepgram
    # ------------------------------------------------------------------
    logger.info("STEP 3: Transcribing...")
    transcript_path = output_dir / "transcript.json"
    if not transcript_path.exists():
        transcriber = Transcriber(api_key)
        transcript_obj = transcriber.transcribe_sync(str(audio_path))
        transcript_obj.save(str(transcript_path))

    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript_data = json.load(f)
    logger.info(f"  Words: {len(transcript_data.get('words', []))}")

    # ------------------------------------------------------------------
    # STEP 4: Enhance with Pyannote
    # ------------------------------------------------------------------
    logger.info("STEP 4: Enhancing transcript (Pyannote)...")
    enhanced_path = output_dir / "enhanced_transcript.json"
    if not enhanced_path.exists():
        vp = Voiceprint.load(VOICEPRINT_PATH)
        fingerprinter = VoiceFingerprinter()
        segments, speaker_mapping, job_id = fingerprinter.identify_speakers_sync(
            str(audio_path),
            {"nick": vp.voiceprint_id},
            match_threshold=50,
        )
        enhanced = merge_pyannote_speakers_with_transcript(
            segments, speaker_mapping, transcript_data, time_offset=0.0,
        )
        utterances = collapse_words_to_utterances(enhanced, max_pause=2.0)
        merge_meta = enhanced.get("merge_metadata", {})
        structured = build_structured_transcript(utterances, metadata=merge_meta)
        with open(enhanced_path, "w", encoding="utf-8") as f:
            json.dump(structured, f, indent=2, ensure_ascii=False)

        txt_path = output_dir / "enhanced_transcript.txt"
        readable = build_readable_transcript(utterances)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(readable)

    logger.info(f"  Enhanced transcript ready")

    # ------------------------------------------------------------------
    # STEP 5: Segment conversations
    # ------------------------------------------------------------------
    logger.info("STEP 5: Segmenting conversations...")
    conv_map = segment_conversations(str(enhanced_path))
    conv_map_path = output_dir / "conversation_map.json"
    save_conversation_map(conv_map, str(conv_map_path))
    logger.info(f"  Conversations: {conv_map.total_conversations}")

    # ------------------------------------------------------------------
    # STEP 6: Topic mapping
    # ------------------------------------------------------------------
    logger.info("STEP 6: Mapping topics...")

    async def _map_topics():
        mapper = TopicMapper()
        return await mapper.map_topics(str(enhanced_path), conv_map)

    topic_map = asyncio.run(_map_topics())
    topic_map_path = output_dir / "topic_map.json"
    save_topic_map(topic_map, str(topic_map_path))
    logger.info(f"  Topics: {topic_map.total_topics} blocks")

    # ------------------------------------------------------------------
    # STEP 7: Find clips (unified Scout + Trimmer)
    # ------------------------------------------------------------------
    logger.info("STEP 7: Finding clips...")

    async def _find_clips():
        finder = ClipFinderUnified()
        intent = None
        if query:
            logger.info(f"  Query: '{query}'")
            sf = StoryClipFinder(client=finder.client)
            intent = await sf.interpret_query(query, conv_map)
        clips = await finder.find_clips(
            str(enhanced_path), conv_map, topic_map, intent, max_clips,
        )
        finder.save_results(clips, str(clips_dir), intent, topic_map)
        return clips

    unified_clips = asyncio.run(_find_clips())
    logger.info(f"  Found {len(unified_clips)} clips")

    # ------------------------------------------------------------------
    # STEP 8: Extract video clips with FFmpeg
    # ------------------------------------------------------------------
    logger.info("STEP 8: Extracting video clips...")
    extracted_count = 0

    async def _extract():
        nonlocal extracted_count
        extractor = ClipExtractor(str(video_path), str(clips_dir))
        for clip in unified_clips:
            try:
                if clip.assembly == "composite" and len(clip.segments) > 1:
                    segs = [
                        {"start_time": s.start_time, "end_time": s.end_time}
                        for s in clip.segments
                    ]
                    result = await extractor.extract_composite_clip(
                        segments=segs,
                        clip_id=clip.clip_id,
                        title=clip.title,
                        quality="medium",
                    )
                else:
                    result = await extractor.extract_clip(
                        {
                            "clip_id": clip.clip_id,
                            "start_time": clip.start_time,
                            "end_time": clip.end_time,
                            "title": clip.title,
                        },
                        quality="medium",
                    )
                if result.status == "success":
                    extracted_count += 1
                    logger.info(f"  Extracted {clip.clip_id}: {result.file_path}")
            except Exception as e:
                logger.warning(f"  Failed to extract {clip.clip_id}: {e}")

    asyncio.run(_extract())
    logger.info(f"  Extracted: {extracted_count}/{len(unified_clips)}")

    report_path = clips_dir / "unified_clips_report.md"

    return {
        "output_dir": str(output_dir),
        "clips_dir": str(clips_dir),
        "video_title": video_title,
        "clip_count": len(unified_clips),
        "extracted_count": extracted_count,
        "report_path": str(report_path) if report_path.exists() else None,
        "topic_map_path": str(topic_map_path),
        "conversation_map_path": str(conv_map_path),
    }


def process_job(job) -> None:
    """Process a single job from the Google Sheet."""
    from src.google_sheets import update_status, update_results, STATUS_PROCESSING, STATUS_COMPLETE, STATUS_FAILED
    from src.google_drive import create_subfolder, upload_file, upload_folder_contents

    sn = job.sheet_name

    logger.info(f"=" * 60)
    logger.info(f"Processing job [{sn}] row {job.row_number}: {job.video_url}")
    if job.query:
        logger.info(f"  Query: {job.query}")
    logger.info(f"  Max clips: {job.max_clips}")
    logger.info(f"=" * 60)

    update_status(job.row_number, STATUS_PROCESSING, sheet_name=sn)

    result = None
    try:
        result = run_pipeline(
            video_url=job.video_url,
            query=job.query,
            max_clips=job.max_clips,
        )

        # Upload results to Google Drive
        date_str = datetime.now().strftime("%Y-%m-%d")
        folder_name = f"{_safe_filename(result['video_title'])}_clips_{date_str}"
        folder_id, folder_link = create_subfolder(folder_name)

        # Upload all clip MP4s
        uploaded = upload_folder_contents(
            result["clips_dir"],
            folder_id,
            extensions=[".mp4"],
        )
        logger.info(f"  Uploaded {len(uploaded)} clip files")

        # Upload report and maps
        report_link = ""
        if result["report_path"]:
            _, report_link = upload_file(result["report_path"], folder_id)
        if result["topic_map_path"]:
            upload_file(result["topic_map_path"], folder_id)
        if result["conversation_map_path"]:
            upload_file(result["conversation_map_path"], folder_id)
        results_json = Path(result["clips_dir"]) / "unified_clips_results.json"
        if results_json.exists():
            upload_file(str(results_json), folder_id)

        update_results(
            row=job.row_number,
            status=STATUS_COMPLETE,
            report_link=report_link,
            clips_folder_link=folder_link,
            sheet_name=sn,
        )

        logger.info(f"Job complete! Folder: {folder_link}")

        # Only clean up after successful upload
        if result:
            cleanup_dir = Path(result["output_dir"])
            if cleanup_dir.exists():
                try:
                    shutil.rmtree(str(cleanup_dir))
                    logger.info(f"  Cleaned up: {cleanup_dir}")
                except Exception:
                    pass

    except Exception as e:
        logger.exception(f"Job failed: {e}")
        update_results(
            row=job.row_number,
            status=STATUS_FAILED,
            error=str(e)[:500],
            sheet_name=sn,
        )


def main_loop() -> None:
    """Main worker loop: poll Sheet, process jobs, repeat."""
    from src.google_sheets import get_pending_jobs

    logger.info("=" * 60)
    logger.info("NICK MATAU CLIPPER WORKER")
    logger.info(f"Polling every {POLL_INTERVAL}s")
    logger.info(f"Voiceprint: {VOICEPRINT_PATH}")
    logger.info(f"Work dir: {WORK_DIR}")
    logger.info("=" * 60)

    while True:
        try:
            jobs = get_pending_jobs()
            if jobs:
                logger.info(f"Found {len(jobs)} pending job(s)")
                for job in jobs:
                    process_job(job)
            else:
                logger.debug("No pending jobs")
        except Exception as e:
            logger.error(f"Poll cycle error: {e}")
            traceback.print_exc()

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main_loop()
