# Nick Matau AI Content Clipper

## Overview

- **Type**: Python CLI Application
- **Stack**: Python 3.11+, Deepgram Nova-3, Gemini 2.5, Claude Sonnet 4.5, Pyannote, FFmpeg
- **Architecture**: V3 Pipeline with Full LLM Engineering
- **GitHub**: https://github.com/gavishap/AI-Content-Clipping-System.git
- **Status**: V3 Design Complete, Implementation Starting

This project extracts viral-worthy clips from Nick Matau's livestreams using AI analysis with multi-signal guest detection and full LLM engineering for maximum accuracy.

## Current State (Jan 25, 2026)

### V3 Pipeline (In Development)
```
YouTube URL → Download → Transcribe → Extract Frames
                                          ↓
         ┌────────────────────────────────┴────────────────────────────────┐
         ↓                                ↓                                ↓
  Visual Change Detector          Voice Fingerprinter          Transcript Cue Detector
  (Gemini 2.5 + CoT +             (Pyannote + Cross-           (Pattern + LLM
   Self-Consistency)               Modal Validation)            Validation)
         ↓                                ↓                                ↓
         └────────────────────────────────┬────────────────────────────────┘
                                          ↓
                              Guest Classifier
                              (Multi-Agent Debate +
                               Temporal Consistency +
                               Retrospective Review)
                                          ↓
                              Conversation Mapper
                              (Hierarchical Summarization +
                               Topic Verification)
                                          ↓
                              Contextual Clip Finder
                              (5-Criteria Scoring +
                               Self-Critique +
                               Multi-Persona +
                               8-Step Verification +
                               Ensemble Ranking)
                                          ↓
                                     clips.json
```

### Module Status

| Module | Status | Description |
|--------|--------|-------------|
| `src/downloader.py` | ✅ Working | YouTube video download |
| `src/ingester.py` | ✅ Working | Audio extraction |
| `src/transcriber.py` | ✅ Working | Deepgram transcription |
| `src/visual_mapper.py` | ✅ Working | Frame extraction |
| `src/speaker_mapper.py` | ✅ Working | Nick voiceprint |
| `src/extractor.py` | ✅ Working | FFmpeg clip cutting |
| `src/anthropic_client.py` | 🔴 Needed | Claude API wrapper |
| `src/llm_engineering.py` | 🔴 Needed | Engineering utilities |
| `src/visual_change_detector.py` | 🔴 Needed | Frame comparison |
| `src/voice_fingerprinter.py` | 🔴 Needed | Multi-speaker tracking |
| `src/transcript_cue_detector.py` | 🔴 Needed | Greeting detection |
| `src/guest_classifier.py` | 🔴 Needed | Multi-agent classification |
| `src/conversation_mapper.py` | 🔴 Needed | Hierarchical summaries |
| `src/contextual_clip_finder.py` | 🔴 Needed | 5-stage clip detection |

## Quick Commands

```powershell
# Setup (Windows)
$env:PATH = "C:\ffmpeg\bin;$env:PATH"
$env:PYTHONIOENCODING = "utf-8"

# Existing V2 commands (still work)
python main.py download "<youtube_url>" --output ./outputs
python main.py transcribe-url "<youtube_url>" --output ./outputs

# V3 commands (coming soon)
python main.py pipeline-v3 video.mp4 --nick-sample nick.wav --output ./outputs
python main.py detect-visual-changes video.mp4 --output visual_events.json
python main.py classify-people --visual ... --voice ... --cues ... --output people.json
python main.py map-conversations --people people.json --output conversations.json
python main.py find-contextual-clips --conversations ... --output clips.json

# Run tests
pytest tests/ -v
```

## Environment Variables (.env)

```
DEEPGRAM_API_KEY=your_key_here      # Required - Transcription
GEMINI_API_KEY=your_key_here        # Required - Visual analysis
PYANNOTE_API_KEY=your_key_here      # Required - Voice identification
ANTHROPIC_API_KEY=your_key_here     # Required - Claude text analysis (NEW)
```

## Critical Files to Read

- `docs/STATUS.md` - **Current session progress and next steps**
- `docs/TASKS.md` - Implementation checklist with V3 tasks
- `docs/ARCHITECTURE.md` - V3 system design and data flow
- `docs/PIPELINE_SUMMARY.md` - V2 → V3 transition details
- `docs/PRD.md` - Product requirements

## Project Structure

```
src/
├── downloader.py              # ✅ YouTube download (yt-dlp)
├── ingester.py                # ✅ Audio extraction (FFmpeg)
├── transcriber.py             # ✅ Deepgram Nova-3 transcription
├── visual_mapper.py           # ✅ Frame extraction
├── speaker_mapper.py          # ✅ Pyannote voiceprint
├── extractor.py               # ✅ FFmpeg clip cutting
│
├── anthropic_client.py        # 🔴 Claude API wrapper (NEW)
├── llm_engineering.py         # 🔴 Self-consistency, debate, etc. (NEW)
├── error_recovery.py          # 🔴 Recovery strategies (NEW)
├── verification.py            # 🔴 Verification chains (NEW)
│
├── visual_change_detector.py  # 🔴 Frame comparison (NEW)
├── voice_fingerprinter.py     # 🔴 Multi-speaker tracking (NEW)
├── transcript_cue_detector.py # 🔴 Greeting detection (NEW)
├── guest_classifier.py        # 🔴 Multi-agent classification (NEW)
├── conversation_mapper.py     # 🔴 Hierarchical summaries (NEW)
├── contextual_clip_finder.py  # 🔴 5-stage clip detection (NEW)
│
├── conversation_segmenter.py  # ❌ Deprecated (V2)
├── clip_analyzer.py           # ❌ Deprecated (V2)
├── quote_clip_finder.py       # ⚠️ Keep temporarily
└── smart_clip_finder.py       # ❌ Delete

prompts/
├── visual_cot.md              # 🔴 Chain of Thought visual
├── debate_advocate.md         # 🔴 Argue FOR new guest
├── debate_skeptic.md          # 🔴 Argue AGAINST new guest
├── debate_judge.md            # 🔴 Judge the debate
├── clip_detection.md          # ✅ Update for 5-criteria
├── clip_critique.md           # 🔴 Adversarial self-critique
├── clip_personas.md           # 🔴 Multi-persona evaluation
└── ... (12 total prompts)
```

## LLM Engineering Patterns Used

| Pattern | Where Used | Purpose |
|---------|------------|---------|
| Chain of Thought | Visual detection | Step-by-step reasoning |
| Self-Consistency | Visual detection | 3-run majority vote |
| Multi-Pass Verify | Visual, Classification | Different perspectives agree |
| Multi-Agent Debate | Classification | Advocate vs Skeptic vs Judge |
| Temporal Consistency | Classification | Timeline makes sense |
| Retrospective Review | Classification | Review all together |
| Adversarial Critique | Clip detection | Find own mistakes |
| Multi-Persona Eval | Clip detection | Multiple viewpoints |
| Verification Chain | Clip detection | 8-step validation |
| Ensemble Ranking | Clip detection | Combine methods |
| Error Recovery | All stages | Attempt to fix failures |

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

### AnthropicClient
- Input: Prompt string + optional system prompt
- Output: Response text + usage stats
- Features: Retry logic, JSON extraction, cost tracking

### LLMEngineering
- `run_self_consistency(prompt, n=3)` → majority vote result
- `run_debate(topic, signals)` → advocate, skeptic, judge verdict
- `run_ensemble_ranking(items, methods)` → Borda count ranking

### VisualChangeDetector
- Input: List of frame paths
- Output: `visual_events.json` with changes and confidence
- Method: CoT + 3x consistency + 3-pass verification

### GuestClassifier
- Input: Visual events + Voice fingerprints + Transcript cues
- Output: `people_registry.json` with nick, panel, guests
- Method: Debate + Temporal consistency + Retrospective review

### ConversationMapper
- Input: People registry + Transcript
- Output: `conversation_map.json` with summaries and timeline
- Method: Hierarchical summarization + Topic verification

### ContextualClipFinder
- Input: Conversation map + Transcript
- Output: `clips.json` with contextual (5-8 min) and moment (60-90s) clips
- Method: 5-stage pipeline with verification

## Cost Estimate per Video (V3)

| Stage | Service | Cost |
|-------|---------|------|
| Transcription | Deepgram | ~$1.25 |
| Visual detection | Gemini 2.5 | ~$3.00 |
| Voice/Cues | Claude/Pyannote | ~$1.50 |
| Classification | Claude | ~$2.50 |
| Conversation mapping | Claude | ~$1.50 |
| Clip detection | Claude | ~$5.50 |
| Verification | Claude | ~$0.75 |
| **Total** | | **~$16/video** |

## Testing

- Run `pytest tests/test_<module>.py` after changes
- Each module should be testable independently
- Test with Episode 258 data (existing transcript + frames)
- Compare V3 results to V2 `quote_clips.json`

## Next Steps

1. Add `ANTHROPIC_API_KEY` to `.env`
2. Implement `src/anthropic_client.py`
3. Implement `src/llm_engineering.py`
4. Implement `src/visual_change_detector.py`
5. Test on Episode 258 frames
6. Continue with remaining modules

See `docs/TASKS.md` for full implementation checklist.
