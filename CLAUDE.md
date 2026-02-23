# Nick Matau AI Content Clipper

## Overview

- **Type**: Python CLI Application
- **Stack**: Python 3.11+, Deepgram Nova-3, Gemini 2.5, Claude Sonnet 4.5, Pyannote, FFmpeg
- **Architecture**: V3 Pipeline with Full LLM Engineering
- **GitHub**: https://github.com/gavishap/AI-Content-Clipping-System.git
- **Status**: V3 Phase 2.5 Complete (~55%), Enhanced Transcript Working, Phase 3 Next

This project extracts viral-worthy clips from Nick Matau's livestreams using AI analysis with multi-signal guest detection and full LLM engineering for maximum accuracy.

## Current State (Feb 8, 2026)

### What's Working End-to-End
```
YouTube URL → Download → Transcribe (Deepgram) → Create Voiceprint (Pyannote)
    → Enhance Transcript (Pyannote identify + Deepgram merge + utterance collapse)
    → Find Clips (V2 quote-based) → Extract Clips (FFmpeg)
```

### Key Achievement: Enhanced Transcript Pipeline
The system now produces named-speaker utterance transcripts by merging Deepgram's
word-level transcription with Pyannote's voiceprint-based speaker identification:

```
[2:51:53] nick: What version is it?
[2:51:56] SPEAKER_10: New American Standard.
[2:51:57] SPEAKER_06: Ask him if it has a mass.
```

This is the format that all future LLM clip-finding will use.

### Module Status

| Module | Lines | Status | Description |
|--------|-------|--------|-------------|
| `src/downloader.py` | ~100 | ✅ Working | YouTube download (yt-dlp) |
| `src/ingester.py` | ~150 | ✅ Working | Audio extraction (FFmpeg) |
| `src/transcriber.py` | ~250 | ✅ Working | Deepgram Nova-3 transcription |
| `src/visual_mapper.py` | ~300 | ✅ Working | Frame extraction + Gemini |
| `src/speaker_mapper.py` | ~200 | ✅ Working | V2 Deepgram speaker mapping |
| `src/extractor.py` | ~150 | ✅ Working | FFmpeg clip cutting |
| `src/timestamp_utils.py` | ~50 | ✅ Working | Timestamp formatting |
| `src/anthropic_client.py` | ~380 | ✅ Working | Claude API wrapper (retry, JSON, costs) |
| `src/llm_engineering.py` | ~940 | ✅ Working | Self-consistency, debate, ensemble |
| `src/visual_change_detector.py` | ~500 | ✅ Working | CoT + consistency + 3-pass verify |
| `src/voice_fingerprinter.py` | ~1500 | ✅ Working | Pyannote API + merge + utterances |
| `src/transcript_cue_detector.py` | ~550 | ✅ Working | Pattern matching + LLM validation |
| `src/quote_clip_finder.py` | ~400 | ⚠️ V2 Legacy | Quote-based clips (still usable) |
| `src/conversation_segmenter.py` | - | ❌ Deprecated | V2 only |
| `src/clip_analyzer.py` | - | ❌ Deprecated | V2 only |
| `src/smart_clip_finder.py` | - | ❌ Delete | Not used |
| `src/guest_classifier.py` | - | 🔴 Next | Multi-agent classification |
| `src/conversation_mapper.py` | - | 🔴 Pending | Hierarchical summaries |
| `src/contextual_clip_finder.py` | - | 🔴 Pending | 5-stage clip detection |

## Quick Commands

```powershell
# Setup (Windows)
$env:PATH = "C:\ffmpeg\bin;$env:PATH"
$env:PYTHONIOENCODING = "utf-8"

# Download and transcribe
python main.py download "<youtube_url>" --output ./outputs
python main.py transcribe video.mp4 --output transcript.json
python main.py transcribe-url "<youtube_url>" --output ./outputs

# Voiceprint (one-time per speaker)
python main.py create-voiceprint nick_sample.wav -o nick_voiceprint.json

# Voice analysis
python main.py analyze-voices stream.wav -v nick_voiceprint.json -o voice_analysis.json

# Enhanced transcript (NEW - the main V3 command)
python main.py enhance-transcript stream.wav \
    -t transcript.json \
    -v nick_voiceprint.json \
    -s 10314 \
    -o outputs/enhanced.json
# Produces: enhanced.json (structured), enhanced.txt (readable), enhanced_raw_words.json

# V2 pipeline commands (legacy, still work)
python main.py map-speakers audio.wav -v voiceprint.json -o voice_map.json
python main.py map-visual video.mp4 --interval 30 --output visual_map.json
python main.py segment --voice voice_map.json --visual visual_map.json --output conversations.json
python main.py find-clips -c conversations.json -t transcript.json -v voice_map.json -o clips.json
python main.py pipeline video.mp4 --nick-sample nick.wav --output ./outputs

# Run tests
pytest tests/ -v
```

## Environment Variables (.env)

```
DEEPGRAM_API_KEY=your_key_here      # Required - Transcription
GEMINI_API_KEY=your_key_here        # Required - Visual analysis
PYANNOTE_API_KEY=your_key_here      # Required - Voice identification
ANTHROPIC_API_KEY=your_key_here     # Required - Claude text analysis
```

## Critical Files to Read

- `docs/STATUS.md` - **Current session progress and next steps**
- `docs/TASKS.md` - Implementation checklist with V3 tasks + full file inventory
- `docs/ARCHITECTURE.md` - V3 system design, module map, data flow
- `docs/PIPELINE_SUMMARY.md` - V2 → V3 transition, what works, what's next
- `docs/PRD.md` - Product requirements

## Project Structure

```
src/
├── downloader.py              # ✅ YouTube download (yt-dlp)
├── ingester.py                # ✅ Audio extraction (FFmpeg)
├── transcriber.py             # ✅ Deepgram Nova-3 transcription
├── visual_mapper.py           # ✅ Frame extraction + Gemini
├── speaker_mapper.py          # ✅ V2 Deepgram speaker mapping
├── extractor.py               # ✅ FFmpeg clip cutting
├── timestamp_utils.py         # ✅ Timestamp helpers
│
├── anthropic_client.py        # ✅ Claude API wrapper (380 lines)
├── llm_engineering.py         # ✅ Self-consistency, debate, ensemble (940 lines)
├── visual_change_detector.py  # ✅ CoT + consistency + 3-pass (500 lines)
├── voice_fingerprinter.py     # ✅ Pyannote + merge + utterances (1500 lines)
├── transcript_cue_detector.py # ✅ Pattern matching + LLM validation (550 lines)
│
├── quote_clip_finder.py       # ⚠️ V2 Legacy (quote-based clips)
├── conversation_segmenter.py  # ❌ Deprecated (V2)
├── clip_analyzer.py           # ❌ Deprecated (V2)
├── smart_clip_finder.py       # ❌ Not used
├── analyzer.py                # ❌ Old module
└── sheets.py                  # ❌ Unused

tests/
├── test_anthropic_client.py   # ✅
├── test_llm_engineering.py    # ✅
├── test_visual_change_detector.py # ✅
├── test_voice_fingerprinter.py    # ✅
├── test_transcript_cue_detector.py # ✅
├── test_transcriber.py        # ✅
├── test_downloader.py         # ✅
├── test_ingester.py           # ✅
├── test_extractor.py          # ✅
└── test_timestamp_utils.py    # ✅

prompts/
├── base_prompt.md             # Base system prompt
├── clip_detection.md          # Clip finding prompt
├── frame_analysis.md          # Visual analysis prompt
└── nick_preferences.md        # Nick's content style

outputs/
├── *.mp4, *.wav               # Source media
├── *_transcript.json          # Deepgram transcripts
├── episode_258_transcript_v3.json  # ✅ Structured utterances (2,347 turns)
├── episode_258_transcript_v3.txt   # ✅ Readable transcript
├── episode_258_transcript_v3_raw_words.json # ✅ Word-level backup
├── episode_258_frames/        # 584 frames
├── clips_v2/                  # V2 extracted clips
└── clips_manual/              # Manual clips
```

## LLM Engineering Patterns Used

| Pattern | Where Used | Status | Purpose |
|---------|------------|--------|---------|
| Chain of Thought | Visual detection | ✅ Active | Step-by-step reasoning |
| Self-Consistency | Visual detection | ✅ Active | 3-run majority vote |
| Multi-Pass Verify | Visual detection | ✅ Active | Forward/backward/holistic |
| Multi-Agent Debate | Classification | ✅ Built, 🔴 Not yet used | Advocate vs Skeptic vs Judge |
| Temporal Consistency | Classification | ✅ Built, 🔴 Not yet used | Timeline validation |
| Adversarial Critique | Clip detection | ✅ Built, 🔴 Not yet used | Find own mistakes |
| Multi-Persona Eval | Clip detection | ✅ Built, 🔴 Not yet used | 4 viewpoints evaluate |
| Verification Chain | Clip detection | 🔴 Not built | 8-step validation |
| Ensemble Ranking | Clip detection | ✅ Built, 🔴 Not yet used | Borda count combine |
| Error Recovery | All stages | 🔴 Not built | Fix failures |

## Code Style

- **MUST** use type hints for all functions
- **MUST** use dataclasses for data structures
- **MUST** include docstrings for public functions
- **SHOULD** keep functions under 50 lines
- **SHOULD** use async/await for API calls
- **MUST NOT** hardcode API keys (use .env)
- **MUST** include confidence scores in outputs
- **SHOULD** log all LLM calls with token counts

## Module Contracts (V3)

### VoiceFingerprinter (voice_fingerprinter.py)
- `create_voiceprint(audio_path, name)` → Voiceprint dataclass
- `diarize_audio(audio_path, exclusive=True)` → segments, job_id
- `identify_speakers(audio_path, voiceprint_ids, threshold=50)` → segments, mapping, job_id
- `trim_audio(input, output, start, duration)` → trimmed path
- `merge_pyannote_speakers_with_transcript(segments, mapping, transcript, offset)` → enhanced dict
- `collapse_words_to_utterances(transcript, max_pause=2.0)` → List[Utterance]
- `build_readable_transcript(utterances)` → formatted string
- `build_structured_transcript(utterances, metadata)` → structured dict

### AnthropicClient (anthropic_client.py)
- Input: Prompt string + optional system prompt
- Output: Response text + usage stats
- Features: Retry logic, JSON extraction, cost tracking

### LLMEngineering (llm_engineering.py)
- `run_self_consistency(prompt, n=3)` → majority vote result
- `run_debate(topic, signals)` → advocate, skeptic, judge verdict
- `run_ensemble_ranking(items, methods)` → Borda count ranking

### VisualChangeDetector (visual_change_detector.py)
- Input: List of frame paths
- Output: visual_events.json with changes and confidence
- Method: CoT + 3x consistency + 3-pass verification

### GuestClassifier (guest_classifier.py) - TODO
- Input: Visual events + Voice fingerprints + Transcript cues
- Output: people_registry.json with nick, panel, guests
- Method: Debate + Temporal consistency + Retrospective review

### ConversationMapper (conversation_mapper.py) - TODO
- Input: People registry + Transcript
- Output: conversation_map.json with summaries and timeline
- Method: Hierarchical summarization + Topic verification

### ContextualClipFinder (contextual_clip_finder.py) - TODO
- Input: Conversation map + Enhanced utterance transcript
- Output: clips.json with contextual (5-8 min) and moment (60-90s) clips
- Method: 5-stage pipeline with verification

## Cost Estimate per Video (V3)

| Stage | Service | Cost |
|-------|---------|------|
| Transcription | Deepgram | ~$1.25 |
| Visual detection | Gemini 2.5 | ~$3.00 |
| Voice identification (2h) | Pyannote | ~$6.00 |
| Transcript cues | Claude | ~$1.00 |
| Classification | Claude | ~$2.00 |
| Conversation mapping | Claude | ~$1.50 |
| Clip detection | Claude | ~$5.50 |
| Verification | Claude | ~$0.75 |
| **Total** | | **~$22/video** |

## Testing

- Run `pytest tests/test_<module>.py` after changes
- Each module should be testable independently
- Test with Episode 258 data (existing transcript + frames)
- Compare V3 results to V2 `quote_clips.json`

## Existing Data

| File | Description |
|------|-------------|
| `nick_voiceprint.json` | Nick's Pyannote voiceprint |
| `outputs/episode_258_transcript.json` | Deepgram transcript (50,507 words) |
| `outputs/episode_258_transcript_v3.json` | Structured utterances (2,347 turns) |
| `outputs/episode_258_transcript_v3.txt` | Readable transcript with speaker names |
| `outputs/episode_258_frames/` | 584 frames (every 30s) |
| `outputs/clips_v2/` | 10 extracted V2 clips |

## Next Steps

### Immediate
1. **Update clip finder** to use enhanced utterance transcript with named speakers
2. **Test clip quality** with speaker-aware analysis

### Phase 3: Classification
3. **Implement `src/guest_classifier.py`** - Multi-agent debate
4. **Test on Episode 258** - Should identify ~8-10 guests

### Phase 4-5: Mapping & Clips
5. **Implement `src/conversation_mapper.py`** - Hierarchical summarization
6. **Implement `src/contextual_clip_finder.py`** - 5-stage clip detection

### Phase 6: Integration
7. Create prompt files (12 total)
8. Update `main.py` with remaining V3 CLI commands
9. Full pipeline test on Episode 258

**See `docs/TASKS.md` for detailed implementation checklist with file inventory.**
