# Project Status

> **Last Updated**: Feb 8, 2026
> **Current Phase**: V3 Pipeline - Phase 2.5 (Enhanced Transcript w/ Speaker Identity)
> **Next Step**: Update clip finding to use enhanced transcript; then Phase 3 (guest_classifier.py)

---

## Current State Summary

### What's Working (V2 - Legacy)
- Download videos from YouTube
- Transcribe with Deepgram (word-level timestamps, speaker IDs)
- Extract frames every 30 seconds
- Find clips using quote-based method (`quote_clip_finder.py`)
- Extract clips with FFmpeg

### What's Working (V3 - NEW)
- **anthropic_client.py** - Claude API wrapper with retry, JSON extraction, cost tracking
- **llm_engineering.py** - Self-consistency, multi-agent debate, ensemble ranking
- **visual_change_detector.py** - Frame comparison with CoT, consistency, verification
- **voice_fingerprinter.py** - **REAL Pyannote API** for diarization, identification, voiceprints, audio trimming, transcript merging, and utterance collapsing
- **transcript_cue_detector.py** - Pattern matching + LLM context validation
- **CLI Commands** - `create-voiceprint`, `analyze-voices`, `enhance-transcript`
- **Nick Voiceprint** - Created and saved to `nick_voiceprint.json`
- **Enhanced Transcript** - Episode 258 last 2h processed with Pyannote identification, merged with Deepgram, collapsed into speaker utterances

### What's Broken (V2)
- Conversation segmentation (same person = multiple "guests")
- No distinction between panel members and actual guests
- Visual mapper describes each frame independently (no tracking)
- Clips not tagged with guest identity

### V3 Solution
Complete pipeline redesign with full LLM engineering for maximum accuracy.

---

## V3 Pipeline Status

| Phase | Module | Status | Priority |
|-------|--------|--------|----------|
| **Infrastructure** | | | |
| | `anthropic_client.py` | ✅ Complete | Critical |
| | `llm_engineering.py` | ✅ Complete | Critical |
| | `error_recovery.py` | 🔴 Not Started | High |
| | `verification.py` | 🔴 Not Started | High |
| **Identity Detection** | | | |
| | `visual_change_detector.py` | ✅ Complete | Critical |
| | `voice_fingerprinter.py` | ✅ Complete (Pyannote API + merge + utterances) | Critical |
| | `transcript_cue_detector.py` | ✅ Complete | High |
| **Enhanced Transcript** | | | |
| | `enhance-transcript` CLI | ✅ Complete (Pyannote identify + Deepgram merge + utterance collapse) | Critical |
| | Nick voiceprint | ✅ Created (`nick_voiceprint.json`) | Critical |
| | Episode 258 enhanced | ✅ Processed (last 2h, 16 speakers, Nick identified) | - |
| **Classification** | | | |
| | `guest_classifier.py` | 🔴 Not Started | Critical |
| **Mapping** | | | |
| | `conversation_mapper.py` | 🔴 Not Started | High |
| **Clip Detection** | | | |
| | `contextual_clip_finder.py` | 🔴 Not Started | Critical |
| **Prompts** | | | |
| | 12 prompt files | 🔴 Not Started | High |
| **Integration** | | | |
| | `main.py` V3 CLI commands | ✅ Partial (voiceprint + enhance commands) | High |

**Overall Progress**: ~55% (Phase 1 + Phase 2 Identity Detection complete + Enhanced Transcript pipeline)

---

## CLI Commands Available

### Download & Transcribe
```bash
# Download a YouTube video
python main.py download "<youtube_url>" --output ./outputs

# Transcribe a local video
python main.py transcribe video.mp4 --output transcript.json

# Download + transcribe in one step
python main.py transcribe-url "<youtube_url>" --output ./outputs
```

### Voiceprint Training
```bash
# Create Nick's voiceprint (one-time setup, max 30s of audio used)
python main.py create-voiceprint nick_sample.wav -o nick_voiceprint.json
```

### Voice Analysis
```bash
# Basic diarization (detect all speakers)
python main.py analyze-voices stream.wav -o voice_analysis.json

# With Nick identification
python main.py analyze-voices stream.wav -v nick_voiceprint.json -o voice_analysis.json

# Full cross-modal validation (best accuracy)
python main.py analyze-voices stream.wav \
    -v nick_voiceprint.json \
    -e visual_events.json \
    -c transcript_cues.json \
    -o voice_analysis.json
```

### Enhanced Transcript (NEW - Feb 2026)
```bash
# Full stream enhancement
python main.py enhance-transcript stream.wav \
    -t transcript.json \
    -v nick_voiceprint.json \
    -o outputs/enhanced.json

# Last 2 hours only (saves Pyannote cost)
python main.py enhance-transcript stream.wav \
    -t transcript.json \
    -v nick_voiceprint.json \
    -s 10314 \
    -o outputs/enhanced.json
```

This produces 3 output files:
- `enhanced.json` - Structured utterances (for LLM analysis)
- `enhanced.txt` - Human-readable transcript with speaker labels
- `enhanced_raw_words.json` - Word-level data with speaker_name on each word

### V2 Pipeline Commands (Legacy)
```bash
python main.py map-speakers audio.wav -v nick_voiceprint.json -o voice_map.json
python main.py map-visual video.mp4 --interval 30 --output visual_map.json
python main.py segment --voice voice_map.json --visual visual_map.json --output conversations.json
python main.py find-clips --conversations conversations.json --transcript transcript.json --voice voice_map.json --output clips.json
python main.py pipeline video.mp4 --nick-sample nick.wav --output ./outputs
```

---

## API Keys Status

| Service | Variable | Status | Notes |
|---------|----------|--------|-------|
| Deepgram | `DEEPGRAM_API_KEY` | ✅ Configured | Transcription |
| Gemini | `GEMINI_API_KEY` | ✅ Configured | Visual analysis |
| Pyannote | `PYANNOTE_API_KEY` | ✅ Configured | Voice identification |
| Claude | `ANTHROPIC_API_KEY` | ✅ Configured | Text analysis |

---

## Existing Data (Episode 258)

| File | Status | Notes |
|------|--------|-------|
| `Israel vs Palestine Debate Episode 258.mp4` | ✅ Have | 783 MB, 4:52:00 |
| `Israel vs Palestine Debate Episode 258.wav` | ✅ Have | 534.5 MB |
| `episode_258_transcript.json` | ✅ Have | 4.8 MB, 50,507 words, 18 Deepgram speakers |
| `episode_258_transcript_v3.json` | ✅ NEW | Structured utterances (2,347 turns, named speakers) |
| `episode_258_transcript_v3.txt` | ✅ NEW | Readable text transcript with speaker labels |
| `episode_258_transcript_v3_raw_words.json` | ✅ NEW | Word-level with `speaker_name` field |
| `nick_voiceprint.json` | ✅ NEW | Nick's Pyannote voiceprint (base64) |
| `episode_258_frames/` | ✅ Have | 584 frames |
| `episode_258_visual_map.json` | ⚠️ Unreliable | Same person = different descriptions |
| `episode_258_conversations.json` | ⚠️ Unreliable | 28 "guests" (should be ~8-10) |
| `quote_clips.json` | ✅ Good | 47 clips, verified timestamps |
| `clips_v2/*.mp4` | ✅ Good | 10 extracted clips |

### Enhanced Transcript Results (Last 2h of Episode 258)
- **Nick identified** as SPEAKER_03 → tagged as `nick` (13,240 words, 545 turns)
- **16 unique Pyannote speakers** detected
- **21,388 words** matched to Pyannote labels
- **29,119 words** in first ~2h52m remain as `deepgram_X` fallback
- **2,347 utterances** collapsed from 50,507 individual words
- Processing time: ~3 minutes total

---

## Session History

### Session 8 - Feb 8, 2026 (Current)
**Major milestone: Enhanced Transcript Pipeline Complete**

1. **Fixed Pyannote API calls** in `voice_fingerprinter.py`:
   - `diarize_audio()` - Now uses media upload + JSON body (was broken multipart form)
   - `identify_speakers()` - Same fix + accepts base64 voiceprints inline, `exclusive` + `matching.threshold` params
   - `_wait_for_job()` - Fixed ServerDisconnectedError on long jobs by using fresh HTTP sessions per poll

2. **Added audio trimming utility** (`trim_audio()`)
   - FFmpeg-based, supports start offset + duration
   - Used to process only last 2h of Episode 258 (~$6 savings)

3. **Added transcript merge** (`merge_pyannote_speakers_with_transcript()`)
   - Merges Pyannote identification segments with Deepgram word-level transcript
   - Assigns speaker names by maximum timestamp overlap
   - Supports time offset for trimmed audio alignment

4. **Added utterance collapsing** (`collapse_words_to_utterances()`)
   - Collapses 50,507 words into 2,347 speaker turns
   - Groups consecutive words from same speaker (splits on speaker change or 2s+ pause)
   - `build_readable_transcript()` - Produces `[HH:MM:SS] Speaker: text` format
   - `build_structured_transcript()` - Produces LLM-optimized JSON with utterance start/end timestamps

5. **Added `enhance-transcript` CLI command** in `main.py`
   - End-to-end: trim → upload → identify → merge → collapse → save
   - Produces 3 outputs: structured JSON, readable text, raw word-level backup

6. **Ran on Episode 258** - Successfully identified Nick (13,240 words) and 15 other speakers

### Session 7 - Jan 25, 2026
**Major milestone: V3 Phase 2 Identity Detection Complete + CLI**
- Rebuilt `voice_fingerprinter.py` with real Pyannote API
- Added `create-voiceprint` and `analyze-voices` CLI commands
- Created Nick's voiceprint from audio sample

### Session 6 - Jan 25, 2026
**Major milestone: V3 Phase 1 Infrastructure Complete**
- Implemented `anthropic_client.py`, `llm_engineering.py`, `visual_change_detector.py`, `transcript_cue_detector.py`

### Session 5 - Jan 25, 2026
- Designed V3 pipeline with multi-signal detection

### Session 4 - Jan 22, 2026 (Evening)
- Implemented V2 pipeline (conversation segmentation + clip analyzer)

### Session 3 - Jan 22, 2026 (Morning)
- Full YouTube → Transcription pipeline working

### Session 2 - Jan 14-21, 2026
- Initial module stubs and documentation

### Session 1 - Jan 14, 2026
- Project setup, CLAUDE.md, PRD, TASKS, ARCHITECTURE

---

## Blockers

| Blocker | Impact | Resolution |
|---------|--------|------------|
| None | - | All blockers resolved |

---

## Next Steps (In Order)

### Immediate: Update Clip Finding
1. **Update clip finder** to use the new enhanced utterance transcript (`episode_258_transcript_v3.json`) with named speakers instead of raw Deepgram transcript
2. **Test clip quality** - clips should now reference speakers by name

### Phase 3: Classification
3. **Implement `src/guest_classifier.py`** - Multi-agent debate classification
4. **Test on Episode 258** - Should get ~8-10 guests, not 28

### Phase 4: Mapping
5. **Implement `src/conversation_mapper.py`** - Hierarchical summarization

### Phase 5: Clip Detection
6. **Implement `src/contextual_clip_finder.py`** - 5-stage clip detection

### Phase 6: Integration
7. **Implement prompt files** (12 total)
8. **Update main.py** with remaining V3 CLI commands
9. **Test full pipeline** on Episode 258, compare to V2 clips

---

## Quick Start for Next Session

```
# Read these files:
- CLAUDE.md (project overview)
- docs/STATUS.md (this file)
- docs/TASKS.md (implementation tasks)
- docs/ARCHITECTURE.md (system design + full module map)

# What's DONE:
✅ src/downloader.py - YouTube download
✅ src/ingester.py - Audio extraction
✅ src/transcriber.py - Deepgram transcription
✅ src/visual_mapper.py - Frame extraction
✅ src/speaker_mapper.py - Deepgram speaker mapping (V2)
✅ src/extractor.py - FFmpeg clip cutting
✅ src/anthropic_client.py - Claude API wrapper (380 lines)
✅ src/llm_engineering.py - Self-consistency, debate, ensemble (940 lines)
✅ src/visual_change_detector.py - CoT + consistency + 3-pass (500 lines)
✅ src/voice_fingerprinter.py - Pyannote API + merge + utterances (~1500 lines)
✅ src/transcript_cue_detector.py - Pattern matching + LLM validation (550 lines)
✅ main.py - CLI: create-voiceprint, analyze-voices, enhance-transcript
✅ nick_voiceprint.json - Nick's voiceprint
✅ outputs/episode_258_transcript_v3.json - Enhanced structured transcript
✅ outputs/episode_258_transcript_v3.txt - Readable transcript

# Tests:
✅ tests/test_anthropic_client.py
✅ tests/test_llm_engineering.py
✅ tests/test_visual_change_detector.py
✅ tests/test_voice_fingerprinter.py
✅ tests/test_transcript_cue_detector.py

# Environment setup (Windows):
$env:PATH = "C:\ffmpeg\bin;$env:PATH"
$env:PYTHONIOENCODING = "utf-8"
cd C:\Projects\nick-matau-clipper

# Quick run enhanced transcript on a video:
python main.py enhance-transcript audio.wav -t transcript.json -v nick_voiceprint.json -s 10314 -o outputs/enhanced.json
```

---

## Cost Tracking

| Video | V2 Cost | V3 Est. Cost |
|-------|---------|--------------|
| Episode 258 (full) | ~$3 | ~$16 |
| Episode 258 (last 2h enhance only) | - | ~$6 (Pyannote) |

---

## Success Criteria for V3

1. **Guest Count**: ~8-10 actual guests identified (not 28)
2. **Panel Detection**: Dani and other regulars classified as panel
3. **Timeline Accuracy**: Guest arrival/departure times within ±30 seconds
4. **Clip Quality**: Clips tell complete stories with verified quotes
5. **Speaker Attribution**: Each clip tagged with who is speaking (nick vs guest)
6. **Variety**: Max 3 clips per guest for diversity
7. **Confidence**: All outputs include confidence scores
