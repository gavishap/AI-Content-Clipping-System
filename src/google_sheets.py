"""
Google Sheets integration for the worker pipeline.

Scans BOTH tabs in the job spreadsheet:
- "Sheet1" (manual entries): has Status/Report/Clips columns already
- "Form Responses 1" (Google Form submissions): only has Timestamp/URL/Query/Max Clips

For Form Responses, the worker adds Status/Report/Clips/Error columns on first run.
Uses OAuth 2.0 credentials (same as Drive) for personal Gmail accounts.
"""

import logging
import os
from dataclasses import dataclass
from typing import List, Optional

import gspread

logger = logging.getLogger(__name__)

# Column names we look for (case-insensitive, stripped)
COL_TIMESTAMP = "Timestamp"
COL_VIDEO_URL = "Video URL"
COL_QUERY_VARIANTS = ["Query", "Query (optional)"]
COL_MAX_CLIPS = "Max Clips"
COL_STATUS = "Status"
COL_REPORT_LINK = "Report Link"
COL_CLIPS_FOLDER = "Clips Folder"
COL_ERROR = "Error"

EXTRA_HEADERS = [COL_STATUS, COL_REPORT_LINK, COL_CLIPS_FOLDER, COL_ERROR]

STATUS_NEW = ""
STATUS_PROCESSING = "processing"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"


@dataclass
class Job:
    """A single clip-finding job from the Google Sheet."""
    row_number: int
    sheet_name: str
    video_url: str
    query: Optional[str]
    max_clips: int
    timestamp: str


def _get_client() -> gspread.Client:
    """Get gspread client using OAuth credentials."""
    from src.google_auth import get_oauth_credentials
    creds = get_oauth_credentials()
    return gspread.authorize(creds)


def _get_spreadsheet() -> gspread.Spreadsheet:
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise RuntimeError("Set GOOGLE_SHEET_ID env var")
    client = _get_client()
    return client.open_by_key(sheet_id)


def _ensure_extra_columns(ws: gspread.Worksheet) -> None:
    """Add Status/Report/Clips/Error headers if they don't exist yet."""
    headers = [h.strip() for h in ws.row_values(1)]
    missing = [h for h in EXTRA_HEADERS if h not in headers]
    if missing:
        next_col = len(headers) + 1
        for h in missing:
            ws.update_cell(1, next_col, h)
            next_col += 1
        logger.info(f"  Added columns to '{ws.title}': {missing}")


def _find_col(headers: List[str], name: str, fallback: int) -> int:
    """Find column index (1-based) by header name, with strip/case handling."""
    clean = [h.strip() for h in headers]
    if name in clean:
        return clean.index(name) + 1
    return fallback


def _get_query_value(row: dict) -> str:
    """Extract query value from a row, handling both header variants."""
    for variant in COL_QUERY_VARIANTS:
        for key in row:
            if str(key).strip().lower() == variant.lower():
                return str(row[key]).strip()
    return ""


def get_pending_jobs() -> List[Job]:
    """Scan all worksheet tabs for rows where Status is blank."""
    spreadsheet = _get_spreadsheet()
    all_jobs: List[Job] = []

    for ws in spreadsheet.worksheets():
        try:
            headers_raw = ws.row_values(1)
            if not headers_raw:
                continue

            headers_clean = [h.strip() for h in headers_raw]

            # Must have at least a Video URL column
            has_url = any(
                h.lower() in ["video url"] for h in headers_clean
            )
            if not has_url:
                continue

            # Ensure Status/Report/Clips/Error columns exist
            _ensure_extra_columns(ws)

            # Re-read headers after potential additions
            headers_raw = ws.row_values(1)
            records = ws.get_all_records()

            for i, row in enumerate(records):
                row_num = i + 2
                clean = {str(k).strip(): v for k, v in row.items()}

                status = str(clean.get(COL_STATUS, "")).strip()
                video_url = str(clean.get(COL_VIDEO_URL, "")).strip()

                if status == STATUS_NEW and video_url:
                    query_raw = _get_query_value(row)

                    max_clips_raw = clean.get(COL_MAX_CLIPS, 10)
                    try:
                        max_clips = int(max_clips_raw) if max_clips_raw else 10
                    except (ValueError, TypeError):
                        max_clips = 10

                    all_jobs.append(Job(
                        row_number=row_num,
                        sheet_name=ws.title,
                        video_url=video_url,
                        query=query_raw if query_raw else None,
                        max_clips=max_clips,
                        timestamp=str(clean.get(COL_TIMESTAMP, "")),
                    ))

        except Exception as e:
            logger.warning(f"Error scanning tab '{ws.title}': {e}")

    return all_jobs


def _get_worksheet(sheet_name: str) -> gspread.Worksheet:
    spreadsheet = _get_spreadsheet()
    return spreadsheet.worksheet(sheet_name)


def update_status(row: int, status: str, sheet_name: str = "Sheet1") -> None:
    """Set the Status column for a row."""
    ws = _get_worksheet(sheet_name)
    headers = ws.row_values(1)
    col_idx = _find_col(headers, COL_STATUS, 5)
    ws.update_cell(row, col_idx, status)
    logger.info(f"[{sheet_name}] Row {row}: status -> {status}")


def update_results(
    row: int,
    status: str,
    report_link: str = "",
    clips_folder_link: str = "",
    error: str = "",
    sheet_name: str = "Sheet1",
) -> None:
    """Update status, report link, clips folder link, and error for a row."""
    ws = _get_worksheet(sheet_name)
    headers = ws.row_values(1)

    updates = [
        (row, _find_col(headers, COL_STATUS, 5), status),
        (row, _find_col(headers, COL_REPORT_LINK, 6), report_link),
        (row, _find_col(headers, COL_CLIPS_FOLDER, 7), clips_folder_link),
        (row, _find_col(headers, COL_ERROR, 8), error),
    ]

    for r, c, val in updates:
        if val is not None:
            ws.update_cell(r, c, val)

    logger.info(f"[{sheet_name}] Row {row}: results updated (status={status})")
