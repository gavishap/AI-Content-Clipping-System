# Nick Matau AI Content Clipper

## Overview

- **Type**: Python CLI Application
- **Stack**: Python 3.11+, Deepgram Nova-3, Gemini 2.5 Pro, FFmpeg, Google Sheets API
- **Architecture**: Modular pipeline with independent components
- **Team**: Gabriel (AI/Backend 65%), Jake (FFmpeg/Integration 35%)

This project extracts viral-worthy clips from Nick Matau's livestreams using AI analysis.

## Quick Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run full pipeline
python main.py process video.mp4 --output ./clips

# Run tests
pytest tests/ -v

# Type check
mypy src/
```

## Project Structure

```
src/
├── ingester.py      # Video input + audio extraction (Jake)
├── transcriber.py   # Deepgram Nova-3 integration (Gabriel)
├── analyzer.py      # Gemini 2.5 Pro clip detection (Gabriel)
├── extractor.py     # FFmpeg precise clip cutting (Jake)
├── sheets.py        # Google Sheets review queue (Jake)
├── timestamp_utils.py # Timestamp refinement (Gabriel)
└── main.py          # Pipeline orchestrator (Gabriel)
```

## Critical Files to Read

- `docs/PRD.md` - Full product requirements
- `docs/ARCHITECTURE.md` - System design and data flow
- `docs/TASKS.md` - Current implementation progress
- `prompts/base_prompt.md` - Master AI clip detection prompt

## Code Style

- **MUST** use type hints for all functions
- **MUST** use dataclasses for data structures
- **MUST** include docstrings for public functions
- **SHOULD** keep functions under 50 lines
- **SHOULD** use async/await for API calls
- **MUST NOT** hardcode API keys (use .env)

## Module Contracts

### Transcriber (Gabriel)

- Input: WAV audio file path
- Output: `TranscriptData` with timestamped transcript + word-level data

### Analyzer (Gabriel)

- Input: Timestamped transcript string
- Output: List of `ClipCandidate` dicts with start/end times

### Ingester (Jake)

- Input: Video file path (MP4/MKV/MOV)
- Output: WAV audio path + `VideoMetadata`

### Extractor (Jake)

- Input: Video path + List of clip timestamps
- Output: List of `ClipResult` with extracted MP4 paths

## Testing

- Run `pytest tests/test_<module>.py` after changes
- Each module should be testable independently
- Use mock data for API calls in tests
