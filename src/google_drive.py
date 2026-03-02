"""
Google Drive integration using OAuth 2.0 (personal account).

Handles:
- Creating subfolders in a shared parent folder
- Uploading clip MP4s and report files
- Downloading source videos from Google Drive share links
- Returning shareable web links for uploaded files/folders
"""

import io
import logging
import os
import re
from pathlib import Path
from typing import List, Optional, Tuple

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

logger = logging.getLogger(__name__)


def _get_service():
    """Build an authenticated Google Drive service using OAuth credentials."""
    from src.google_auth import get_oauth_credentials
    creds = get_oauth_credentials()
    return build("drive", "v3", credentials=creds)


def _extract_file_id(url: str) -> Optional[str]:
    """Extract file/folder ID from a Google Drive URL."""
    patterns = [
        r"/file/d/([a-zA-Z0-9_-]+)",
        r"/folders/([a-zA-Z0-9_-]+)",
        r"id=([a-zA-Z0-9_-]+)",
        r"/open\?id=([a-zA-Z0-9_-]+)",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def create_subfolder(name: str, parent_folder_id: Optional[str] = None) -> Tuple[str, str]:
    """
    Create a subfolder in the parent folder.
    Returns (folder_id, web_view_link).
    """
    service = _get_service()
    parent = parent_folder_id or os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    if not parent:
        raise RuntimeError("Set GOOGLE_DRIVE_FOLDER_ID env var")

    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent],
    }
    folder = service.files().create(
        body=metadata,
        fields="id, webViewLink",
    ).execute()

    folder_id = folder["id"]
    web_link = folder.get("webViewLink", f"https://drive.google.com/drive/folders/{folder_id}")

    # Make the folder accessible to anyone with the link
    try:
        service.permissions().create(
            fileId=folder_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()
    except Exception as e:
        logger.warning(f"Could not set folder sharing: {e}")

    logger.info(f"Created Drive folder: {name} ({folder_id})")
    return folder_id, web_link


def upload_file(
    local_path: str,
    folder_id: str,
    mime_type: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Upload a file to a Drive folder.
    Returns (file_id, web_view_link).
    """
    service = _get_service()
    path = Path(local_path)

    if mime_type is None:
        ext = path.suffix.lower()
        mime_map = {
            ".mp4": "video/mp4",
            ".json": "application/json",
            ".md": "text/markdown",
            ".txt": "text/plain",
            ".wav": "audio/wav",
        }
        mime_type = mime_map.get(ext, "application/octet-stream")

    metadata = {
        "name": path.name,
        "parents": [folder_id],
    }
    media = MediaFileUpload(str(path), mimetype=mime_type, resumable=True)
    uploaded = service.files().create(
        body=metadata,
        media_body=media,
        fields="id, webViewLink",
    ).execute()

    file_id = uploaded["id"]
    web_link = uploaded.get("webViewLink", f"https://drive.google.com/file/d/{file_id}")
    logger.info(f"Uploaded {path.name} -> {file_id}")
    return file_id, web_link


def upload_folder_contents(
    local_dir: str,
    drive_folder_id: str,
    extensions: Optional[List[str]] = None,
) -> List[Tuple[str, str, str]]:
    """
    Upload all matching files from a local directory to a Drive folder.
    Returns list of (filename, file_id, web_link).
    """
    results = []
    local = Path(local_dir)
    if not local.exists():
        return results

    for f in sorted(local.iterdir()):
        if not f.is_file():
            continue
        if extensions and f.suffix.lower() not in extensions:
            continue
        fid, link = upload_file(str(f), drive_folder_id)
        results.append((f.name, fid, link))

    return results


def download_from_drive(url: str, output_path: str) -> str:
    """
    Download a file from a Google Drive share link to a local path.
    Returns the output path.
    """
    service = _get_service()
    file_id = _extract_file_id(url)
    if not file_id:
        raise ValueError(f"Could not extract file ID from: {url}")

    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(output_path, "wb")
    downloader = MediaIoBaseDownload(fh, request)

    logger.info(f"Downloading Drive file {file_id} -> {output_path}")
    done = False
    while not done:
        status, done = downloader.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            if pct % 20 == 0:
                logger.info(f"  Download progress: {pct}%")

    fh.close()
    logger.info(f"Download complete: {output_path}")
    return output_path
