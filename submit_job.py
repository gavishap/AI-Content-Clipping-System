"""
Local job submitter: Download YouTube video, upload to Google Drive, submit to Sheet.

Bypasses YouTube bot detection by downloading from your local IP, then uploads
the video to Google Drive so Railway can process it.

Usage:
    python submit_job.py "https://youtube.com/watch?v=..." 
    python submit_job.py "https://youtube.com/watch?v=..." -q "find the best debunk moments"
    python submit_job.py "https://youtube.com/watch?v=..." -q "gotcha clips" -n 5
"""

import argparse
import logging
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def download_video(url: str, output_dir: str) -> dict:
    """Download YouTube video locally using yt-dlp."""
    import yt_dlp

    output_template = os.path.join(output_dir, "%(title)s.%(ext)s")

    ydl_opts = {
        "format": (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo[ext=mp4]+bestaudio/"
            "bestvideo+bestaudio/"
            "best[ext=mp4]/"
            "best"
        ),
        "outtmpl": output_template,
        "quiet": False,
        "no_warnings": False,
        "nocheckcertificate": True,
        "geo_bypass": True,
        "merge_output_format": "mp4",
        "extractor_args": {
            "youtube": {
                "player_client": ["web"],
            },
        },
        "js_runtimes": {"node": {}},
    }

    logger.info(f"Downloading: {url}")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    if info is None:
        raise RuntimeError("Failed to extract video info")

    title = info.get("title", "video")
    safe_title = yt_dlp.utils.sanitize_filename(title)

    video_path = None
    for ext in ["mp4", "mkv", "webm"]:
        candidate = Path(output_dir) / f"{safe_title}.{ext}"
        if candidate.exists():
            video_path = candidate
            break
    if video_path is None:
        for f in Path(output_dir).iterdir():
            if f.suffix.lower() in [".mp4", ".mkv", ".webm"]:
                video_path = f
                break

    if video_path is None:
        raise RuntimeError(f"Downloaded file not found in {output_dir}")

    return {
        "path": str(video_path),
        "title": title,
        "duration": info.get("duration", 0),
        "video_id": info.get("id", ""),
    }


def upload_to_drive(local_path: str, title: str) -> tuple[str, str]:
    """Upload video to Google Drive and return (file_id, shareable_link)."""
    from src.google_auth import get_oauth_credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = get_oauth_credentials()
    service = build("drive", "v3", credentials=creds)

    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    if not folder_id:
        raise RuntimeError("GOOGLE_DRIVE_FOLDER_ID not set in .env")

    # Upload to a "source_videos" subfolder to keep things tidy
    subfolder_name = "source_videos"
    query = (
        f"name='{subfolder_name}' and "
        f"'{folder_id}' in parents and "
        f"mimeType='application/vnd.google-apps.folder' and trashed=false"
    )
    results = service.files().list(q=query, fields="files(id)").execute()
    existing = results.get("files", [])

    if existing:
        upload_folder_id = existing[0]["id"]
    else:
        meta = {
            "name": subfolder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [folder_id],
        }
        folder = service.files().create(body=meta, fields="id").execute()
        upload_folder_id = folder["id"]
        logger.info(f"Created source_videos subfolder: {upload_folder_id}")

    file_size_mb = Path(local_path).stat().st_size / (1024 * 1024)
    filename = Path(local_path).name
    logger.info(f"Uploading {filename} ({file_size_mb:.0f} MB) to Google Drive...")

    file_meta = {
        "name": filename,
        "parents": [upload_folder_id],
    }
    media = MediaFileUpload(local_path, mimetype="video/mp4", resumable=True)
    request = service.files().create(body=file_meta, media_body=media, fields="id,webViewLink")

    response = None
    last_progress = 0
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            if pct >= last_progress + 10:
                logger.info(f"  Upload progress: {pct}%")
                last_progress = pct

    file_id = response["id"]
    web_link = response.get("webViewLink", f"https://drive.google.com/file/d/{file_id}/view")

    # Make shareable
    try:
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()
    except Exception as e:
        logger.warning(f"Could not set sharing: {e}")

    logger.info(f"Uploaded: {web_link}")
    return file_id, web_link


def submit_to_sheet(
    drive_url: str,
    query: str | None,
    max_clips: int,
    video_title: str,
) -> int:
    """Add a new row to the Google Sheet with the Drive URL."""
    from src.google_auth import get_oauth_credentials
    import gspread

    creds = get_oauth_credentials()
    client = gspread.authorize(creds)

    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise RuntimeError("GOOGLE_SHEET_ID not set in .env")

    spreadsheet = client.open_by_key(sheet_id)
    ws = spreadsheet.worksheet("Form Responses 1")

    timestamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
    row = [
        timestamp,
        drive_url,
        query or "",
        str(max_clips),
    ]

    ws.append_row(row, value_input_option="USER_ENTERED", table_range="A1")
    row_count = len(ws.get_all_values())
    logger.info(f"Submitted to Sheet row {row_count}: {video_title}")
    return row_count


def main():
    parser = argparse.ArgumentParser(
        description="Download a YouTube video and submit it for clip processing.",
    )
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument(
        "-q", "--query", default=None,
        help='Search query (e.g. "find the best debunk moments")',
    )
    parser.add_argument(
        "-n", "--max-clips", type=int, default=10,
        help="Maximum clips to find (default: 10)",
    )
    parser.add_argument(
        "--keep", action="store_true",
        help="Keep the local downloaded file after uploading",
    )
    args = parser.parse_args()

    # Validate URL
    yt_patterns = [
        r"(https?://)?(www\.)?youtube\.com/watch\?v=",
        r"(https?://)?(www\.)?youtu\.be/",
        r"(https?://)?(www\.)?youtube\.com/live/",
        r"(https?://)?(www\.)?youtube\.com/shorts/",
    ]
    if not any(re.search(p, args.url) for p in yt_patterns):
        logger.error(f"Not a valid YouTube URL: {args.url}")
        sys.exit(1)

    start_time = time.time()
    tmp_dir = tempfile.mkdtemp(prefix="clipper_submit_")

    try:
        # Step 1: Download locally
        logger.info("=" * 50)
        logger.info("STEP 1: Downloading video (local)")
        logger.info("=" * 50)
        video_info = download_video(args.url, tmp_dir)
        logger.info(f"  Title: {video_info['title']}")
        logger.info(f"  Duration: {video_info['duration'] / 60:.1f} min")
        logger.info(f"  File: {video_info['path']}")

        # Step 2: Upload to Google Drive
        logger.info("")
        logger.info("=" * 50)
        logger.info("STEP 2: Uploading to Google Drive")
        logger.info("=" * 50)
        file_id, drive_url = upload_to_drive(video_info["path"], video_info["title"])

        # Step 3: Submit to Google Sheet
        logger.info("")
        logger.info("=" * 50)
        logger.info("STEP 3: Submitting job to Google Sheet")
        logger.info("=" * 50)
        row = submit_to_sheet(drive_url, args.query, args.max_clips, video_info["title"])

        elapsed = time.time() - start_time
        logger.info("")
        logger.info("=" * 50)
        logger.info("DONE!")
        logger.info("=" * 50)
        logger.info(f"  Video: {video_info['title']}")
        logger.info(f"  Drive: {drive_url}")
        logger.info(f"  Sheet row: {row}")
        logger.info(f"  Query: {args.query or '(none)'}")
        logger.info(f"  Max clips: {args.max_clips}")
        logger.info(f"  Time: {elapsed:.0f}s")
        logger.info("")
        logger.info("Railway worker will pick this up within ~2 minutes.")

    finally:
        if not args.keep:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        else:
            logger.info(f"Local files kept in: {tmp_dir}")


if __name__ == "__main__":
    main()
