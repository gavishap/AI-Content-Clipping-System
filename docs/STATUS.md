# Project Status

> **Last Updated**: Jan 25, 2026
> **Current Phase**: V3 Pipeline Design Complete, Ready for Implementation
> **Next Step**: Add Claude API key, start implementing Phase 1

---

## Current State Summary

### What's Working (V2)
- Download videos from YouTube
- Transcribe with Deepgram (word-level timestamps, speaker IDs)
- Extract frames every 30 seconds
- Find clips using quote-based method
- Extract clips with FFmpeg

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
| | `anthropic_client.py` | 🔴 Not Started | Critical |
| | `llm_engineering.py` | 🔴 Not Started | Critical |
| | `error_recovery.py` | 🔴 Not Started | High |
| | `verification.py` | 🔴 Not Started | High |
| **Identity Detection** | | | |
| | `visual_change_detector.py` | 🔴 Not Started | Critical |
| | `voice_fingerprinter.py` | 🔴 Not Started | High |
| | `transcript_cue_detector.py` | 🔴 Not Started | High |
| **Classification** | | | |
| | `guest_classifier.py` | 🔴 Not Started | Critical |
| **Mapping** | | | |
| | `conversation_mapper.py` | 🔴 Not Started | High |
| **Clip Detection** | | | |
| | `contextual_clip_finder.py` | 🔴 Not Started | Critical |
| **Prompts** | | | |
| | 12 prompt files | 🔴 Not Started | High |
| **Integration** | | | |
| | `main.py` updates | 🔴 Not Started | High |

**Overall Progress**: 0% (Design complete, implementation not started)

---

## API Keys Status

| Service | Variable | Status | Notes |
|---------|----------|--------|-------|
| Deepgram | `DEEPGRAM_API_KEY` | ✅ Configured | Working |
| Gemini | `GEMINI_API_KEY` | ✅ Configured | Working |
| Pyannote | `PYANNOTE_API_KEY` | ✅ Configured | Working |
| Claude | `ANTHROPIC_API_KEY` | 🔴 **NEEDED** | Required for V3 |

---

## Existing Data (Episode 258)

| File | Status | Notes |
|------|--------|-------|
| `Israel vs Palestine Debate Episode 258.mp4` | ✅ Have | 783 MB, 4:52:00 |
| `episode_258_transcript.json` | ✅ Have | 4.8 MB, 50K words |
| `episode_258_frames/` | ✅ Have | 584 frames |
| `episode_258_visual_map.json` | ⚠️ Unreliable | Same person = different descriptions |
| `episode_258_conversations.json` | ⚠️ Unreliable | 28 "guests" (should be ~8-10) |
| `quote_clips.json` | ✅ Good | 47 clips, verified timestamps |
| `clips_v2/*.mp4` | ✅ Good | 10 extracted clips |

**V3 will reprocess using existing transcript and frames with new detection methods.**

---

## Session History

### Session 5 - Jan 25, 2026 (Current)
**Major milestone: V3 Pipeline Design Complete**

- Analyzed V2 pipeline issues
- Identified core problem: same person = different Gemini descriptions
- Designed V3 pipeline with multi-signal detection
- Added full LLM engineering:
  - Chain of Thought prompting
  - Self-consistency (3-run majority vote)
  - Multi-pass verification
  - Multi-agent debate (advocate vs skeptic)
  - Temporal consistency checking
  - Retrospective review
  - Adversarial self-critique
  - Multi-persona evaluation
  - 8-step verification chain
  - Ensemble ranking
  - Error recovery strategies
- Updated all documentation

**Outputs**:
- `docs/TASKS.md` - New V3 task list
- `docs/ARCHITECTURE.md` - V3 architecture design
- `docs/STATUS.md` - This file
- Plan file with full implementation details

### Session 4 - Jan 22, 2026 (Evening)
- Implemented V2 pipeline (conversation segmentation + clip analyzer)
- Created visual_mapper, speaker_mapper, conversation_segmenter, clip_analyzer
- Created prompts for frame analysis and clip detection

### Session 3 - Jan 22, 2026 (Morning)
- Full YouTube → Transcription pipeline working
- Tested on 3.5-hour video: 32,234 words, 16 speakers

### Session 2 - Jan 14-21, 2026
- Initial module stubs and documentation

### Session 1 - Jan 14, 2026
- Project setup, CLAUDE.md, PRD, TASKS, ARCHITECTURE

---

## Blockers

| Blocker | Impact | Resolution |
|---------|--------|------------|
| Missing `ANTHROPIC_API_KEY` | Cannot run Claude-based modules | User needs to add key to `.env` |

---

## Next Steps (In Order)

### Immediate
1. **Add Claude API key** to `.env` file
2. **Implement `src/anthropic_client.py`** - Claude wrapper with retry logic
3. **Implement `src/llm_engineering.py`** - Core engineering utilities

### Phase 1 Complete
4. **Implement `src/visual_change_detector.py`** - Frame comparison
5. **Test on Episode 258 frames** - Verify visual changes detected correctly

### Phase 2 Complete
6. **Implement `src/guest_classifier.py`** - Multi-agent classification
7. **Test classification** - Should get ~8-10 guests, not 28

### Full Pipeline
8. Implement remaining modules
9. Test full pipeline on Episode 258
10. Compare results to V2 clips

---

## Quick Start for Next Session

```
# Read these files:
- CLAUDE.md (project overview)
- docs/TASKS.md (implementation tasks)
- docs/ARCHITECTURE.md (system design)
- Plan file at ~/.cursor/plans/guest_detection_pipeline_v3_*.plan.md

# Current status:
- V3 design complete with full LLM engineering
- Need ANTHROPIC_API_KEY to proceed
- Start with src/anthropic_client.py

# Environment setup:
$env:PATH = "C:\ffmpeg\bin;$env:PATH"
$env:PYTHONIOENCODING = "utf-8"
cd C:\Projects\nick-matau-clipper

# First file to implement:
src/anthropic_client.py
```

---

## Cost Tracking

| Video | V2 Cost | V3 Est. Cost |
|-------|---------|--------------|
| Episode 258 | ~$3 | ~$16 |

V3 is ~5x more expensive but should give significantly better accuracy.

---

## Success Criteria for V3

1. **Guest Count**: ~8-10 actual guests identified (not 28)
2. **Panel Detection**: Dani and other regulars classified as panel
3. **Timeline Accuracy**: Guest arrival/departure times within ±30 seconds
4. **Clip Quality**: Clips tell complete stories with verified quotes
5. **Variety**: Max 3 clips per guest for diversity
6. **Confidence**: All outputs include confidence scores
