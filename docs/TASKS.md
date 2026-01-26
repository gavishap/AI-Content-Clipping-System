# Implementation Tasks - Pipeline V3

> **Current Sprint**: V3 Pipeline Redesign
> **Last Updated**: Jan 25, 2026
> **Goal**: Maximum accuracy guest detection with full LLM engineering

---

## Task Overview

| Phase | Tasks | Status |
|-------|-------|--------|
| Phase 1: Core Infrastructure | 3 tasks | 🔴 Not Started |
| Phase 2: Identity Detection | 3 tasks | 🔴 Not Started |
| Phase 3: Classification | 2 tasks | 🔴 Not Started |
| Phase 4: Conversation Mapping | 1 task | 🔴 Not Started |
| Phase 5: Clip Detection | 2 tasks | 🔴 Not Started |
| Phase 6: Integration | 2 tasks | 🔴 Not Started |
| **Total** | **13 tasks** | **0% Complete** |

---

## Phase 1: Core Infrastructure

### 1.1 Claude API Client [PRIORITY: CRITICAL]
- [ ] Create `src/anthropic_client.py`
- [ ] Implement `ClaudeClient` class with async support
- [ ] Add retry logic with exponential backoff
- [ ] Add structured output parsing (JSON extraction)
- [ ] Add token counting and cost tracking
- [ ] Add rate limiting support
- [ ] Create `tests/test_anthropic_client.py`

**File**: `src/anthropic_client.py`

### 1.2 LLM Engineering Utilities [PRIORITY: CRITICAL]
- [ ] Create `src/llm_engineering.py`
- [ ] Implement `SelfConsistencyRunner` - run N times, majority vote
- [ ] Implement `TwoPassVerifier` - different prompts must agree
- [ ] Implement `MultiAgentDebate` - advocate, skeptic, judge pattern
- [ ] Implement `EnsembleRanker` - Borda count combination
- [ ] Implement `UncertaintyQuantifier` - explicit uncertainty estimates
- [ ] Implement `ConfidenceCalibrator` - calibrate raw confidence scores
- [ ] Create `tests/test_llm_engineering.py`

**File**: `src/llm_engineering.py`

### 1.3 Error Recovery Module [PRIORITY: HIGH]
- [ ] Create `src/error_recovery.py`
- [ ] Implement `QuoteRecovery` - fuzzy, semantic, keyword, LLM strategies
- [ ] Implement `ClassificationFixer` - repair inconsistent classifications
- [ ] Implement `BoundaryAdjuster` - fix clip boundaries
- [ ] Add logging for all recovery attempts
- [ ] Create `tests/test_error_recovery.py`

**File**: `src/error_recovery.py`

---

## Phase 2: Identity Detection

### 2.1 Visual Change Detector [PRIORITY: CRITICAL]
- [ ] Create `src/visual_change_detector.py`
- [ ] Implement Chain of Thought prompting (6-step analysis)
- [ ] Implement 3-run self-consistency with temperature variation
- [ ] Implement 3-pass verification (forward, backward, holistic)
- [ ] Add `VisualEvent` and `FrameComparison` dataclasses
- [ ] Use existing frames from `visual_mapper.py` frame extraction
- [ ] Create `tests/test_visual_change_detector.py`

**File**: `src/visual_change_detector.py`  
**Depends on**: `src/llm_engineering.py`

### 2.2 Voice Fingerprinter [PRIORITY: HIGH]
- [ ] Create `src/voice_fingerprinter.py`
- [ ] Implement multi-speaker fingerprint creation from Deepgram speaker IDs
- [ ] Implement cross-modal validation (voice + visual correlation)
- [ ] Implement speaker clustering validation with LLM
- [ ] Add `VoiceFingerprint` and `ValidatedSpeakerChange` dataclasses
- [ ] Create `tests/test_voice_fingerprinter.py`

**File**: `src/voice_fingerprinter.py`  
**Depends on**: `src/speaker_mapper.py`, `src/anthropic_client.py`

### 2.3 Transcript Cue Detector [PRIORITY: HIGH]
- [ ] Create `src/transcript_cue_detector.py`
- [ ] Implement regex pattern matching for greetings/exits
- [ ] Implement LLM context validation (false positive filtering)
- [ ] Implement semantic similarity for greeting variations
- [ ] Add `TranscriptCue` and `ValidatedCue` dataclasses
- [ ] Create `tests/test_transcript_cue_detector.py`

**File**: `src/transcript_cue_detector.py`  
**Depends on**: `src/anthropic_client.py`

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

### 6.2 CLI & Pipeline Integration [PRIORITY: HIGH]
- [ ] Update `main.py` with V3 pipeline commands
- [ ] Add `pipeline-v3` command for full pipeline
- [ ] Add `detect-visual-changes` command
- [ ] Add `fingerprint-voices` command
- [ ] Add `detect-transcript-cues` command
- [ ] Add `classify-people` command
- [ ] Add `map-conversations` command
- [ ] Add `find-contextual-clips` command
- [ ] Add `--full-engineering` flag for max accuracy mode
- [ ] Add progress logging and intermediate saves

---

## Files to Keep (Working)

| File | Status | Notes |
|------|--------|-------|
| `src/downloader.py` | ✅ Keep | Works fine |
| `src/ingester.py` | ✅ Keep | Works fine |
| `src/transcriber.py` | ✅ Keep | Deepgram integration works |
| `src/extractor.py` | ✅ Keep | Minor updates for longer clips |
| `src/visual_mapper.py` | ✅ Keep | Use for frame extraction only |
| `src/speaker_mapper.py` | ✅ Keep | Use for Nick voiceprint |

## Files to Deprecate

| File | Reason |
|------|--------|
| `src/conversation_segmenter.py` | Replaced by `guest_classifier.py` + `conversation_mapper.py` |
| `src/clip_analyzer.py` | Replaced by `contextual_clip_finder.py` |
| `src/quote_clip_finder.py` | Keep for now, will be superseded |
| `src/smart_clip_finder.py` | Not used, delete |

---

## Dependencies to Add

```
anthropic>=0.18.0      # Claude API
numpy>=1.24.0          # For ensemble methods
scipy>=1.10.0          # For statistical functions (optional)
```

---

## API Keys Required

| Service | Variable | Status |
|---------|----------|--------|
| Claude | `ANTHROPIC_API_KEY` | 🔴 Needed |
| Gemini | `GEMINI_API_KEY` | ✅ Have |
| Pyannote | `PYANNOTE_API_KEY` | ✅ Have |
| Deepgram | `DEEPGRAM_API_KEY` | ✅ Have |

---

## Estimated Costs (Per Video)

| Stage | Service | Calls | Cost |
|-------|---------|-------|------|
| Transcription | Deepgram | 1 | $1.25 |
| Visual (CoT + consistency + passes) | Gemini 2.5 | ~1800 | $3.00 |
| Voice correlation | Claude | ~20 | $0.50 |
| Transcript cues | Claude | ~50 | $1.00 |
| Guest classification (debate) | Claude | ~60 | $2.00 |
| Retrospective review | Claude | 1 | $0.50 |
| Conversation summaries | Claude | ~30 | $1.50 |
| Clip detection (5-stage) | Claude | ~100 | $4.00 |
| Multi-persona evaluation | Claude | ~40 | $1.50 |
| Verification chains | Claude | ~30 | $0.75 |
| **Total** | | | **~$16/video** |

---

## Testing Strategy

1. **Unit Tests**: Each module has its own test file
2. **Integration Tests**: Test full pipeline on existing Episode 258 data
3. **Comparison Tests**: Compare V3 results to existing `quote_clips.json`
4. **Cost Monitoring**: Track actual API costs vs estimates

---

## Quick Start for New Session

```
Read these files to understand the project:
- CLAUDE.md - Project overview
- docs/TASKS.md - This file (implementation tasks)
- docs/ARCHITECTURE.md - System design
- docs/PIPELINE_SUMMARY.md - Current state and V3 plan

The V3 pipeline uses full LLM engineering for maximum accuracy:
- Multi-agent debate for guest classification
- Self-consistency and multi-pass verification for visual detection
- Hierarchical summarization for conversations
- 5-stage clip detection with self-critique and verification
```
