# Implementation Tasks

> **Current Sprint**: Sprint 1 - MVP (Jan 13 - Jan 27)
> **Last Updated**: Jan 22, 2026

---

## Completed Tasks
- [x] Project structure created
- [x] CLAUDE.md initialized
- [x] PRD documented
- [x] Architecture designed
- [x] Task distribution planned (Gabriel 65%, Jake 35%)
- [x] Pushed to GitHub: https://github.com/gavishap/AI-Content-Clipping-System.git
- [x] FFmpeg installed (C:\ffmpeg\bin)
- [x] Deepgram API configured

---

## In Progress Tasks

### Gabriel's Tasks (65% - First Phase)

#### 🎯 Client Onboarding [PRIORITY: URGENT]
- [ ] Contact Nick for sample video (3-4 hour stream)
- [ ] Get Nick's Google account email for Sheets access
- [ ] Collect 5-10 example "good" clips from Nick
- [ ] Collect 5-10 examples of moments Nick would skip
- [ ] Document Nick's preferences in `prompts/nick_preferences.md`

#### 🔑 API Setup [PRIORITY: HIGH]
- [x] Create Deepgram account at console.deepgram.com
- [x] Generate Deepgram API key and test with sample audio
- [ ] Create/configure GCP project for Gemini API
- [ ] Generate Gemini API key and test with simple prompt
- [ ] Enable Google Sheets API in GCP project
- [ ] Enable Google Drive API in GCP project
- [x] Create `.env` with Deepgram API key
- [ ] Create `config/config.yaml.example`

#### 📥 YouTube Downloader [COMPLETE ✅]
- [x] Create `src/downloader.py`
- [x] Implement `YouTubeDownloader` class
- [x] Implement `download()` method with yt-dlp
- [x] Implement `DownloadResult` dataclass
- [x] Handle livestream replays (HLS streams)
- [x] FFmpeg detection for format merging
- [x] Progress logging
- [x] Create `tests/test_downloader.py`

#### 🎤 Transcription Module [COMPLETE ✅]
- [x] Create `src/transcriber.py`
- [x] Implement `Transcriber` class with `transcribe_sync()` method
- [x] Configure Deepgram options (nova-3, diarize, punctuate, etc.)
- [x] Implement `_process_response()` to extract word-level timestamps
- [x] Implement `_build_timestamped_transcript()` for AI input
- [x] Implement `_format_timestamp()` helper
- [x] Implement `_get_speaker_stats()` for speaker duration tracking
- [x] Add `find_word_at_timestamp()` utility function
- [x] Add `find_sentence_boundary()` utility function
- [x] Create `tests/test_transcriber.py` with mock responses
- [x] Test with real 3.5-hour video (32,234 words, 16 speakers)
- [x] Extended timeout (30 min) for long files
- [x] Pydantic model_dump() for SDK v5 response parsing

#### 🧠 AI Analysis Module [PRIORITY: HIGH - NEXT]
- [ ] Create `src/analyzer.py`
- [ ] Implement `ClipAnalyzer` class
- [ ] Implement `_load_prompt()` to load from `prompts/base_prompt.md`
- [ ] Implement `analyze_for_clips()` main method
- [ ] Implement `_build_full_prompt()` with transcript + preferences
- [ ] Implement `_validate_clips()` to catch hallucinated timestamps
- [ ] Implement `_find_closest_timestamp()` for timestamp correction
- [ ] Implement `_timestamp_to_seconds()` / `_calculate_duration()`
- [ ] Implement `_format_learning_data()` for approval/rejection patterns
- [ ] Create `tests/test_analyzer.py` with sample transcripts
- [ ] Test with real transcript from Deepgram

#### 📝 Clip Detection Prompt [PRIORITY: HIGH]
- [ ] Create `prompts/base_prompt.md` with full master prompt
- [ ] Define Nick's content style section
- [ ] Define "What Makes a Good Clip" criteria
- [ ] Define "What to Avoid" section
- [ ] Define JSON output format with all required fields
- [ ] Add transcript placeholder `{{TRANSCRIPT}}`
- [ ] Add preferences placeholder `{{PREFERENCES}}`
- [ ] Create `prompts/nick_preferences.md` template
- [ ] Test prompt with sample transcript in Gemini playground

#### ⚡ Timestamp Refinement [PRIORITY: URGENT]
- [ ] Create `src/timestamp_utils.py`
- [ ] Implement `refine_clip_boundaries()` main function
- [ ] Implement `find_sentence_start()` - find sentence before timestamp
- [ ] Implement `find_sentence_end()` - find sentence after timestamp
- [ ] Implement `verify_clip_text()` - validate AI's start_text matches
- [ ] Implement `timestamp_to_seconds()` / `seconds_to_timestamp()`
- [ ] Implement `refine_all_clips()` integration function
- [ ] Create `tests/test_timestamp_utils.py`
- [ ] Test refinement improves clip quality

#### 🔄 Pipeline Orchestrator [PARTIAL ✅]
- [x] Create `main.py` with Click CLI
- [x] Implement `download` command
- [x] Implement `transcribe` command
- [x] Implement `transcribe-url` command (full YouTube → transcript pipeline)
- [ ] Implement `process` command (full pipeline with clips)
- [ ] Implement `analyze` command (just analysis)
- [ ] Implement `extract` command (just extraction)
- [x] Add progress logging (Step 1/3, 2/3, etc.)
- [ ] Add time elapsed per step
- [ ] Add API cost tracking
- [x] Add intermediate result saving (transcript.json)
- [ ] Add resume from last successful step
- [ ] Create config loader from YAML

---

### Jake's Tasks (35% - Second Phase)

#### 📁 Project Repository [COMPLETE ✅]
- [x] Create GitHub repo (gavishap/AI-Content-Clipping-System)
- [x] Set up Python 3.11+ virtual environment
- [x] Create `requirements.txt` with all dependencies
- [x] Create `.gitignore` for credentials/outputs
- [ ] Add pre-commit hooks for linting (black, ruff)
- [ ] Create `README.md` with setup instructions
- [x] Create stub files for all modules in `src/`

#### 🎬 Video Ingestion Module [COMPLETE ✅]
- [x] Create `src/ingester.py`
- [x] Implement `VideoMetadata` dataclass
- [x] Implement `VideoIngester` class
- [x] Implement `_extract_metadata()` using ffprobe
- [x] Implement `extract_audio()` - output 16kHz mono WAV
- [x] Implement `_format_duration()` helper
- [x] Handle edge cases (no audio, corrupted, long videos)
- [x] Create `tests/test_ingester.py`
- [x] Test with various video formats (MP4, MKV, MOV)

#### ✂️ Clip Extraction Module [PRIORITY: HIGH]
- [ ] Create `src/extractor.py`
- [ ] Implement `ClipResult` dataclass
- [ ] Implement `ClipExtractor` class
- [ ] Implement `extract_clip()` with keyframe-accurate seeking
- [ ] Implement `extract_all_clips()` batch processing
- [ ] Implement `_adjust_timestamp()` for padding
- [ ] Implement `_get_quality_settings()` (fast/medium/high presets)
- [ ] Implement `_get_clip_duration()` verification
- [ ] Ensure proper audio/video sync
- [ ] Create `tests/test_extractor.py`
- [ ] Test clip quality and timing accuracy

#### 📊 Google Sheets Integration [PRIORITY: NORMAL]
- [ ] Create `src/sheets.py`
- [ ] Implement `ReviewQueue` class
- [ ] Implement `_get_credentials()` OAuth flow
- [ ] Implement `add_clips_for_review()` - populate sheet
- [ ] Implement `get_feedback()` - read approval/rejection
- [ ] Create Google Sheet template structure
- [ ] Create `tests/test_sheets.py`
- [ ] Test with real Google account

---

## Future Tasks (Post-MVP)

### 🧪 End-to-End Testing [Both]
- [ ] Test 1: Short video (10-15 min sample)
- [x] Test 2: Full stream (3.5 hours) - Transcription only
- [ ] Test 3: Review with Nick
- [ ] Document test results
- [ ] Fix identified issues

### 📞 Sprint Review [Gabriel]
- [ ] Schedule meeting with Nick
- [ ] Review extracted clips together
- [ ] Document approval/rejection patterns
- [ ] Update prompts based on feedback

---

## Implementation Notes

### Module Independence
Each module should be testable WITHOUT other modules:
- **Downloader**: Test with any YouTube URL ✅ DONE
- **Ingester**: Test with any video file ✅ DONE
- **Transcriber**: Test with any WAV/MP3 file ✅ DONE
- **Analyzer**: Test with hardcoded transcript JSON
- **Extractor**: Test with hardcoded timestamp list

### Tested Pipeline (Jan 22, 2026)
```
YouTube URL → yt-dlp → MP4 → FFmpeg → WAV → MP3 → Deepgram → JSON
                              ↓
                         3.5 hours
                         32,234 words
                         16 speakers
                         ~1 min processing
```

### Data Contracts
```python
# Downloader output
DownloadResult = {
    "video_path": str,
    "title": str,
    "duration_seconds": float,
    "channel": str,
    "video_id": str,
    "thumbnail_url": Optional[str],
    "description": Optional[str]
}

# Transcriber output
TranscriptData = {
    "full_transcript": str,
    "timestamped_transcript": str,  # For AI input
    "words": List[Word],            # For refinement
    "word_count": int,
    "duration": float,
    "speakers": Dict
}

# Analyzer output
ClipCandidate = {
    "clip_id": int,
    "start_time": str,  # "HH:MM:SS"
    "end_time": str,
    "start_text": str,  # For verification
    "end_text": str,
    "hook": str,
    "title": str,
    "virality_score": int,
    "category": str,
    "platforms": List[str],
    "reasoning": str
}

# Extractor input
ClipInput = {
    "clip_id": int,
    "start_time": str,  # or "refined_start"
    "end_time": str,    # or "refined_end"
    "title": str
}
```

---

## Progress Tracking

| Module | Owner | Status | Completion |
|--------|-------|--------|------------|
| Client Onboarding | Gabriel | 🟡 In Progress | 0% |
| API Setup | Gabriel | 🟡 In Progress | 50% |
| Downloader | Gabriel | ✅ Complete | 100% |
| Transcriber | Gabriel | ✅ Complete | 100% |
| Analyzer | Gabriel | 🔴 Not Started | 0% |
| Prompts | Gabriel | 🔴 Not Started | 0% |
| Timestamp Utils | Gabriel | 🔴 Not Started | 0% |
| Orchestrator | Gabriel | 🟡 In Progress | 40% |
| Repository | Jake | ✅ Complete | 100% |
| Ingester | Jake | ✅ Complete | 100% |
| Extractor | Jake | 🔴 Not Started | 0% |
| Sheets | Jake | 🔴 Not Started | 0% |

**Overall Progress**: ~35% Complete
