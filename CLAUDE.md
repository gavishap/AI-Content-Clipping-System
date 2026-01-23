# Nick Matau AI Content Clipper

## Overview

- **Type**: Python CLI Application
- **Stack**: Python 3.11+, Deepgram Nova-3, Gemini 2.5 Pro, FFmpeg, Google Sheets API
- **Architecture**: Modular pipeline with independent components
- **GitHub**: https://github.com/gavishap/AI-Content-Clipping-System.git
- **Status**: YouTube → Transcription pipeline WORKING ✅

This project extracts viral-worthy clips from Nick Matau's livestreams using AI analysis.

## Current State (Jan 22, 2026)

### Working Pipeline
```
YouTube URL → yt-dlp → MP4 → FFmpeg → WAV → Deepgram → JSON
                                              ↓
                                         32,234 words
                                         16 speakers
                                         ~1 min processing
```

### Implemented Modules
- ✅ `src/downloader.py` - YouTube video download with yt-dlp
- ✅ `src/ingester.py` - Video metadata + audio extraction (FFmpeg)
- ✅ `src/transcriber.py` - Deepgram Nova-3 with word-level timestamps
- ✅ `main.py` - CLI with download, transcribe, transcribe-url commands

### Not Yet Implemented
- 🔴 `src/analyzer.py` - Gemini AI clip detection
- 🔴 `src/extractor.py` - FFmpeg clip cutting
- 🔴 `src/sheets.py` - Google Sheets integration
- 🔴 `src/timestamp_utils.py` - Timestamp refinement

## Quick Commands

```powershell
# Setup FFmpeg in PATH (Windows)
$env:PATH = "C:\ffmpeg\bin;$env:PATH"
$env:PYTHONIOENCODING = "utf-8"

# Full YouTube → Transcript pipeline
python main.py transcribe-url "https://www.youtube.com/watch?v=VIDEO_ID" --output ./outputs

# Download only
python main.py download "https://www.youtube.com/watch?v=VIDEO_ID" --output ./outputs

# Transcribe existing audio/video
python main.py transcribe path/to/file.wav --output ./outputs/transcript.json

# Run tests
pytest tests/ -v

# Type check
mypy src/
```

## Project Structure

```
src/
├── downloader.py     # ✅ YouTube download (yt-dlp)
├── ingester.py       # ✅ Audio extraction (FFmpeg)
├── transcriber.py    # ✅ Deepgram Nova-3 transcription
├── analyzer.py       # 🔴 Gemini clip detection
├── extractor.py      # 🔴 FFmpeg clip cutting
├── sheets.py         # 🔴 Google Sheets integration
├── timestamp_utils.py # 🔴 Timestamp refinement
└── main.py           # ✅ CLI orchestrator
```

## Environment Variables (.env)

```
DEEPGRAM_API_KEY=your_key_here   # Required ✅
GEMINI_API_KEY=your_key_here     # Not yet needed
```

## Critical Files to Read

- `docs/STATUS.md` - **Current session progress and next steps**
- `docs/TASKS.md` - Implementation checklist with progress
- `docs/ARCHITECTURE.md` - System design and data flow
- `docs/PRD.md` - Full product requirements
- `prompts/base_prompt.md` - Master AI clip detection prompt

## Code Style

- **MUST** use type hints for all functions
- **MUST** use dataclasses for data structures
- **MUST** include docstrings for public functions
- **SHOULD** keep functions under 50 lines
- **SHOULD** use async/await for API calls
- **MUST NOT** hardcode API keys (use .env)

## Module Contracts

### Downloader ✅

- Input: YouTube URL string
- Output: `DownloadResult` with video path, title, duration

### Ingester ✅

- Input: Video file path (MP4/MKV/MOV)
- Output: WAV audio path + `VideoMetadata`

### Transcriber ✅

- Input: WAV/MP3 audio file path
- Output: `TranscriptData` with timestamped transcript + word-level data
- Note: 30-minute timeout for long files (3+ hours)

### Analyzer 🔴

- Input: Timestamped transcript string
- Output: List of `ClipCandidate` dicts with start/end times

### Extractor 🔴

- Input: Video path + List of clip timestamps
- Output: List of `ClipResult` with extracted MP4 paths

## Testing

- Run `pytest tests/test_<module>.py` after changes
- Each module should be testable independently
- Use mock data for API calls in tests

## Tested Results (3.5-hour video)

- **Total Words**: 32,234
- **Duration**: 3.57 hours
- **Speakers**: 16 detected
- **Processing**: ~1 minute
- **Output**: `outputs/Israel_vs_Palestine_transcript.json` (4.8MB)
