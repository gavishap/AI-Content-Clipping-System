# Implementation Tasks - Pipeline V3

> **Current Sprint**: V3 Pipeline Redesign
> **Last Updated**: Feb 8, 2026
> **Goal**: Maximum accuracy guest detection with full LLM engineering

---

## Task Overview

| Phase | Tasks | Status |
|-------|-------|--------|
| Phase 1: Core Infrastructure | 3 tasks | ✅ 2/3 Complete |
| Phase 2: Identity Detection | 3 tasks | ✅ 3/3 Complete |
| Phase 2.5: Enhanced Transcript | 4 tasks | ✅ 4/4 Complete |
| Phase 3: Classification | 2 tasks | 🔴 Not Started |
| Phase 4: Conversation Mapping | 1 task | 🔴 Not Started |
| Phase 5: Clip Detection | 2 tasks | 🔴 Not Started |
| Phase 6: Integration | 2 tasks | 🟡 Partial |
| **Total** | **17 tasks** | **~55% Complete** |

---

## Phase 1: Core Infrastructure

### 1.1 Claude API Client [PRIORITY: CRITICAL] ✅ COMPLETE
- [x] Create `src/anthropic_client.py`
- [x] Implement `ClaudeClient` class with async support
- [x] Add retry logic with exponential backoff
- [x] Add structured output parsing (JSON extraction)
- [x] Add token counting and cost tracking
- [x] Add rate limiting support
- [x] Create `tests/test_anthropic_client.py`

**File**: `src/anthropic_client.py` (~380 lines)

### 1.2 LLM Engineering Utilities [PRIORITY: CRITICAL] ✅ COMPLETE
- [x] Create `src/llm_engineering.py`
- [x] Implement `SelfConsistencyRunner` - run N times, majority vote
- [x] Implement `TwoPassVerifier` - different prompts must agree
- [x] Implement `MultiAgentDebate` - advocate, skeptic, judge pattern
- [x] Implement `EnsembleRanker` - Borda count combination
- [x] Implement `UncertaintyQuantifier` - explicit uncertainty estimates
- [x] Implement `ConfidenceCalibrator` - calibrate raw confidence scores
- [x] Create `tests/test_llm_engineering.py`

**File**: `src/llm_engineering.py` (~940 lines)

### 1.3 Error Recovery Module [PRIORITY: HIGH]
- [ ] Create `src/error_recovery.py`
- [ ] Implement `QuoteRecovery` - fuzzy, semantic, keyword, LLM strategies
- [ ] Implement `ClassificationFixer` - repair inconsistent classifications
- [ ] Implement `BoundaryAdjuster` - fix clip boundaries
- [ ] Add logging for all recovery attempts
- [ ] Create `tests/test_error_recovery.py`

**File**: `src/error_recovery.py`

---

## Phase 2: Identity Detection ✅ COMPLETE

### 2.1 Visual Change Detector [PRIORITY: CRITICAL] ✅ COMPLETE
- [x] Create `src/visual_change_detector.py`
- [x] Implement Chain of Thought prompting (6-step analysis)
- [x] Implement 3-run self-consistency with temperature variation
- [x] Implement 3-pass verification (forward, backward, holistic)
- [x] Add `VisualEvent` and `FrameComparison` dataclasses
- [x] Use existing frames from `visual_mapper.py` frame extraction
- [x] Create `tests/test_visual_change_detector.py`

**File**: `src/visual_change_detector.py` (~500 lines)
**Depends on**: `src/llm_engineering.py`

### 2.2 Voice Fingerprinter [PRIORITY: CRITICAL] ✅ COMPLETE (REBUILT)
- [x] Create `src/voice_fingerprinter.py`
- [x] **Use REAL Pyannote API** for diarization (not Deepgram speaker IDs)
- [x] Implement `create_voiceprint()` - Train voice profile from audio sample
- [x] Implement `diarize_audio()` - Detect all speakers from actual audio
- [x] Implement `identify_speakers()` - Match speakers to known voiceprints
- [x] Implement `analyze_audio()` - Full analysis pipeline
- [x] Support up to 24 hours of audio (no chunking needed)
- [x] Implement cross-modal validation (voice + visual + transcript)
- [x] Fix Pyannote API: media upload flow, JSON body (not multipart form)
- [x] Add `exclusive` and `matching.threshold` params for clean identification
- [x] Fix `_wait_for_job()` - Fresh sessions per poll to avoid disconnect on long jobs
- [x] Add `trim_audio()` - FFmpeg audio trimming for cost savings
- [x] Add `merge_pyannote_speakers_with_transcript()` - Merge Pyannote labels with Deepgram words
- [x] Add `collapse_words_to_utterances()` - Word-level → speaker turns
- [x] Add `build_readable_transcript()` - `[HH:MM:SS] Speaker: text` format
- [x] Add `build_structured_transcript()` - LLM-optimized JSON with utterances
- [x] Add `Utterance` dataclass
- [x] Add `identify_speakers_sync()` sync wrapper
- [x] Add CLI commands: `create-voiceprint`, `analyze-voices`, `enhance-transcript`
- [x] Create `tests/test_voice_fingerprinter.py`
- [x] Create Nick's voiceprint from audio sample → `nick_voiceprint.json`
- [x] Run on Episode 258 last 2h → `episode_258_transcript_v3.json`

**File**: `src/voice_fingerprinter.py` (~1500 lines)
**Depends on**: Pyannote API (`PYANNOTE_API_KEY`), FFmpeg
**CLI**: `create-voiceprint` | `analyze-voices` | `enhance-transcript`

### 2.3 Transcript Cue Detector [PRIORITY: HIGH] ✅ COMPLETE
- [x] Create `src/transcript_cue_detector.py`
- [x] Implement regex pattern matching for greetings/exits
- [x] Implement LLM context validation (false positive filtering)
- [x] Implement semantic similarity for greeting variations
- [x] Add `TranscriptCue` and `ValidatedCue` dataclasses
- [x] Create `tests/test_transcript_cue_detector.py`

**File**: `src/transcript_cue_detector.py` (~550 lines)
**Depends on**: `src/anthropic_client.py`

---

## Phase 2.5: Enhanced Transcript Pipeline ✅ COMPLETE

### 2.5.1 Fix Pyannote API Methods ✅ COMPLETE
- [x] Fix `diarize_audio()` - media upload + JSON body (was broken multipart form)
- [x] Fix `identify_speakers()` - same fix + base64 voiceprints inline
- [x] Fix `_wait_for_job()` - fresh HTTP sessions per poll for long jobs
- [x] Add `identify_speakers_sync()` wrapper

### 2.5.2 Audio Trimming ✅ COMPLETE
- [x] Add `trim_audio()` utility function (FFmpeg-based)
- [x] Supports start offset + optional duration
- [x] Integrated into `enhance-transcript` CLI command

### 2.5.3 Transcript Merge ✅ COMPLETE
- [x] Add `merge_pyannote_speakers_with_transcript()` 
- [x] Assigns Pyannote speaker labels to Deepgram words by timestamp overlap
- [x] Supports time offset for trimmed audio alignment
- [x] Fallback to `deepgram_X` for unmatched words

### 2.5.4 Utterance Collapsing ✅ COMPLETE
- [x] Add `collapse_words_to_utterances()` - Groups words into speaker turns
- [x] Add `build_readable_transcript()` - `[HH:MM:SS] Speaker: text` format
- [x] Add `build_structured_transcript()` - JSON with utterances + speaker stats
- [x] Add `Utterance` dataclass with `to_dict()` serialization
- [x] Add `enhance-transcript` CLI command producing 3 output files

---

## Phase 3: Classification

### 3.1 Guest Classifier [PRIORITY: CRITICAL]
- [ ] Create `src/guest_classifier.py`
- [ ] Implement multi-agent debate (advocate vs skeptic + judge)
- [ ] Implement temporal consistency checking
- [ ] Implement retrospective review (review all classifications together)
- [ ] Implement cross-signal validation (require 2+ signals)
- [ ] Add `PeopleRegistry`, `GuestClassification` dataclasses
- [ ] Output: `people_registry.json`
- [ ] Create `tests/test_guest_classifier.py`

**File**: `src/guest_classifier.py`
**Depends on**: `src/llm_engineering.py`, `src/visual_change_detector.py`, `src/voice_fingerprinter.py`, `src/transcript_cue_detector.py`

### 3.2 Verification Chain [PRIORITY: HIGH]
- [ ] Create `src/verification.py`
- [ ] Implement 8-step verification chain
- [ ] Implement quote existence verification
- [ ] Implement timeline logic verification
- [ ] Implement duration validation and adjustment
- [ ] Implement speaker attribution verification
- [ ] Implement confidence calibration
- [ ] Create `tests/test_verification.py`

**File**: `src/verification.py`
**Depends on**: `src/error_recovery.py`

---

## Phase 4: Conversation Mapping

### 4.1 Conversation Mapper [PRIORITY: HIGH]
- [ ] Create `src/conversation_mapper.py`
- [ ] Implement hierarchical summarization (chunk → summarize → meta)
- [ ] Implement topic extraction with verification
- [ ] Implement timeline entry generation
- [ ] Add `ConversationMap`, `HierarchicalSummary`, `VerifiedTopic` dataclasses
- [ ] Output: `conversation_map.json` with scrollable timeline
- [ ] Create `tests/test_conversation_mapper.py`

**File**: `src/conversation_mapper.py`
**Depends on**: `src/guest_classifier.py`, `src/anthropic_client.py`

---

## Phase 5: Clip Detection

### 5.1 Contextual Clip Finder [PRIORITY: CRITICAL]
- [ ] Create `src/contextual_clip_finder.py`
- [ ] Implement 5-criteria scoring with explicit justification
- [ ] Implement adversarial self-critique (6 attack vectors)
- [ ] Implement multi-persona evaluation (4 personas)
- [ ] Implement ensemble ranking (Borda count)
- [ ] Generate contextual clips (5-8 min) and moment clips (60-90s)
- [ ] **Use enhanced utterance transcript** (not raw Deepgram words)
- [ ] Add `ClipCandidate`, `PersonaEvaluation`, `FinalRanking` dataclasses
- [ ] Output: `clips.json` with full metadata
- [ ] Create `tests/test_contextual_clip_finder.py`

**File**: `src/contextual_clip_finder.py`
**Depends on**: `src/conversation_mapper.py`, `src/verification.py`, `src/llm_engineering.py`

### 5.2 Clip Verification [PRIORITY: HIGH]
- [ ] Integrate 8-step verification chain into clip finder
- [ ] Implement quote recovery for failed verifications
- [ ] Implement boundary adjustment for duration issues
- [ ] Add confidence scoring to all clips
- [ ] Flag low-confidence clips for human review

**Integrated into**: `src/contextual_clip_finder.py`

---

## Phase 6: Integration

### 6.1 Prompt Files [PRIORITY: HIGH]
Create 12 engineered prompt files in `prompts/`:
- [ ] `visual_cot.md` - Chain of Thought visual comparison
- [ ] `visual_passes.md` - Three-pass verification prompts
- [ ] `debate_advocate.md` - Argue FOR new guest
- [ ] `debate_skeptic.md` - Argue AGAINST new guest
- [ ] `debate_judge.md` - Judge the debate
- [ ] `temporal_consistency.md` - Check timeline consistency
- [ ] `retrospective_review.md` - Review all classifications
- [ ] `clip_detection.md` - 5-criteria clip detection (UPDATE existing)
- [ ] `clip_critique.md` - Adversarial self-critique
- [ ] `clip_personas.md` - Multi-persona evaluation
- [ ] `hierarchical_summary.md` - Conversation summarization
- [ ] `topic_extraction.md` - Topic extraction with verification

### 6.2 CLI & Pipeline Integration [PRIORITY: HIGH] 🟡 PARTIAL
- [x] Add `create-voiceprint` command - Train Nick's voice
- [x] Add `analyze-voices` command - Full diarization + identification
- [x] Add `enhance-transcript` command - Pyannote identify + merge + utterances
- [ ] Add `pipeline-v3` command for full pipeline
- [ ] Add `detect-visual-changes` command
- [ ] Add `detect-transcript-cues` command
- [ ] Add `classify-people` command
- [ ] Add `map-conversations` command
- [ ] Add `find-contextual-clips` command
- [ ] Add `--full-engineering` flag for max accuracy mode
- [ ] Add progress logging and intermediate saves

---

## Complete Source File Inventory

### Active Pipeline Scripts

| File | Lines | Status | Purpose | APIs Used |
|------|-------|--------|---------|-----------|
| `src/downloader.py` | ~100 | ✅ Working | YouTube download via yt-dlp | - |
| `src/ingester.py` | ~150 | ✅ Working | Audio extraction via FFmpeg | - |
| `src/transcriber.py` | ~250 | ✅ Working | Deepgram Nova-3 transcription | Deepgram |
| `src/visual_mapper.py` | ~300 | ✅ Working | Frame extraction + Gemini analysis | Gemini |
| `src/speaker_mapper.py` | ~200 | ✅ Working | Deepgram speaker mapping (V2) | - |
| `src/extractor.py` | ~150 | ✅ Working | FFmpeg clip cutting | - |
| `src/anthropic_client.py` | ~380 | ✅ Working | Claude API wrapper | Claude |
| `src/llm_engineering.py` | ~940 | ✅ Working | LLM engineering patterns | Claude |
| `src/visual_change_detector.py` | ~500 | ✅ Working | CoT + consistency visual detection | Gemini |
| `src/voice_fingerprinter.py` | ~1500 | ✅ Working | Pyannote voice ID + merge + utterances | Pyannote |
| `src/transcript_cue_detector.py` | ~550 | ✅ Working | Pattern matching + LLM validation | Claude |
| `src/quote_clip_finder.py` | ~400 | ⚠️ V2 Legacy | Quote-based clip finding | Gemini |
| `src/timestamp_utils.py` | ~50 | ✅ Utility | Timestamp formatting helpers | - |

### Deprecated / Not Used

| File | Status | Reason |
|------|--------|--------|
| `src/conversation_segmenter.py` | ❌ Deprecated | Replaced by guest_classifier + conversation_mapper |
| `src/clip_analyzer.py` | ❌ Deprecated | Replaced by contextual_clip_finder |
| `src/smart_clip_finder.py` | ❌ Delete | Never used |
| `src/analyzer.py` | ❌ Deprecated | Old analysis module |
| `src/sheets.py` | ❌ Unused | Google Sheets integration (not needed) |

### Not Yet Created

| File | Phase | Purpose |
|------|-------|---------|
| `src/error_recovery.py` | 1 | Recovery strategies |
| `src/verification.py` | 3 | 8-step verification chain |
| `src/guest_classifier.py` | 3 | Multi-agent debate classification |
| `src/conversation_mapper.py` | 4 | Hierarchical summarization |
| `src/contextual_clip_finder.py` | 5 | 5-stage clip detection |

### Test Files

| File | Status | Covers |
|------|--------|--------|
| `tests/test_anthropic_client.py` | ✅ | anthropic_client.py |
| `tests/test_llm_engineering.py` | ✅ | llm_engineering.py |
| `tests/test_visual_change_detector.py` | ✅ | visual_change_detector.py |
| `tests/test_voice_fingerprinter.py` | ✅ | voice_fingerprinter.py |
| `tests/test_transcript_cue_detector.py` | ✅ | transcript_cue_detector.py |
| `tests/test_transcriber.py` | ✅ | transcriber.py |
| `tests/test_downloader.py` | ✅ | downloader.py |
| `tests/test_ingester.py` | ✅ | ingester.py |
| `tests/test_extractor.py` | ✅ | extractor.py |
| `tests/test_analyzer.py` | ⚠️ | Old analyzer (deprecated) |
| `tests/test_timestamp_utils.py` | ✅ | timestamp_utils.py |

### Prompt Files

| File | Status | Purpose |
|------|--------|---------|
| `prompts/base_prompt.md` | ✅ Exists | Base system prompt |
| `prompts/clip_detection.md` | ✅ Exists | Clip finding prompt |
| `prompts/frame_analysis.md` | ✅ Exists | Visual analysis prompt |
| `prompts/nick_preferences.md` | ✅ Exists | Nick's content preferences |

---

## API Keys Required

| Service | Variable | Status |
|---------|----------|--------|
| Claude | `ANTHROPIC_API_KEY` | ✅ Have |
| Gemini | `GEMINI_API_KEY` | ✅ Have |
| Pyannote | `PYANNOTE_API_KEY` | ✅ Have |
| Deepgram | `DEEPGRAM_API_KEY` | ✅ Have |

---

## Estimated Costs (Per Video)

| Stage | Service | Cost |
|-------|---------|------|
| Transcription | Deepgram | $1.25 |
| Visual (CoT + consistency + passes) | Gemini 2.5 | $3.00 |
| Voice identification (full stream) | Pyannote | $12.00 |
| Voice identification (last 2h) | Pyannote | $6.00 |
| Transcript cues | Claude | $1.00 |
| Guest classification (debate) | Claude | $2.00 |
| Conversation summaries | Claude | $1.50 |
| Clip detection (5-stage) | Claude | $4.00 |
| Multi-persona evaluation | Claude | $1.50 |
| Verification chains | Claude | $0.75 |
| **Total (full stream)** | | **~$28/video** |
| **Total (last 2h only)** | | **~$22/video** |
