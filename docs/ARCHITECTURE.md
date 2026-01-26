# System Architecture - Pipeline V3

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                     NICK MATAU AI CLIPPER v3.0                                    │
│              Full LLM Engineering for Maximum Accuracy                            │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │                    PHASE 1: DATA COLLECTION (Existing)                       │ │
│  │                                                                              │ │
│  │  YouTube URL → Download → Extract Audio → Transcribe → Extract Frames       │ │
│  │      │           │            │              │              │               │ │
│  │      ▼           ▼            ▼              ▼              ▼               │ │
│  │  [yt-dlp]    [video.mp4]  [audio.wav]  [transcript]    [frames/]           │ │
│  │                                         (Deepgram)     (FFmpeg)             │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │                    PHASE 2: IDENTITY DETECTION (New)                         │ │
│  │                                                                              │ │
│  │  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐    │ │
│  │  │ Visual Change      │  │ Voice Fingerprint  │  │ Transcript Cue     │    │ │
│  │  │ Detector           │  │ er                 │  │ Detector           │    │ │
│  │  │                    │  │                    │  │                    │    │ │
│  │  │ • CoT prompting    │  │ • Multi-speaker    │  │ • Pattern match    │    │ │
│  │  │ • 3x consistency   │  │ • Cross-modal      │  │ • LLM validation   │    │ │
│  │  │ • 3-pass verify    │  │   validation       │  │ • Semantic search  │    │ │
│  │  │                    │  │ • Cluster verify   │  │                    │    │ │
│  │  └─────────┬──────────┘  └─────────┬──────────┘  └─────────┬──────────┘    │ │
│  │            │                       │                       │               │ │
│  │            ▼                       ▼                       ▼               │ │
│  │     visual_events.json    voice_fingerprints.json   transcript_cues.json  │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │                    PHASE 3: CLASSIFICATION (New)                             │ │
│  │                                                                              │ │
│  │  ┌──────────────────────────────────────────────────────────────────────┐  │ │
│  │  │                       Guest Classifier                                │  │ │
│  │  │                                                                       │  │ │
│  │  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐              │  │ │
│  │  │  │  Advocate   │ vs │   Skeptic   │ → │    Judge    │              │  │ │
│  │  │  │ "IS guest"  │    │"NOT guest"  │    │  (decides)  │              │  │ │
│  │  │  └─────────────┘    └─────────────┘    └─────────────┘              │  │ │
│  │  │                           │                                          │  │ │
│  │  │                           ▼                                          │  │ │
│  │  │              ┌─────────────────────────┐                            │  │ │
│  │  │              │ Temporal Consistency    │                            │  │ │
│  │  │              │ Check                   │                            │  │ │
│  │  │              └────────────┬────────────┘                            │  │ │
│  │  │                           ▼                                          │  │ │
│  │  │              ┌─────────────────────────┐                            │  │ │
│  │  │              │ Retrospective Review    │                            │  │ │
│  │  │              │ (all classifications)   │                            │  │ │
│  │  │              └────────────┬────────────┘                            │  │ │
│  │  └───────────────────────────┼───────────────────────────────────────────┘  │ │
│  │                              ▼                                              │ │
│  │                     people_registry.json                                    │ │
│  │                     {nick, panel[], guests[]}                               │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │                    PHASE 4: CONVERSATION MAPPING (New)                       │ │
│  │                                                                              │ │
│  │  For each guest:                                                            │ │
│  │  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐    │ │
│  │  │ Extract     │ → │ Chunk into  │ → │ Summarize   │ → │ Meta-       │    │ │
│  │  │ transcript  │   │ 3-min parts │   │ each chunk  │   │ summarize   │    │ │
│  │  └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘    │ │
│  │                                                              │              │ │
│  │                                                              ▼              │ │
│  │                                              ┌─────────────────────────┐    │ │
│  │                                              │ Extract & Verify Topics │    │ │
│  │                                              └────────────┬────────────┘    │ │
│  │                                                           ▼                 │ │
│  │                                                  conversation_map.json      │ │
│  │                                                  {summaries, topics,        │ │
│  │                                                   scrollable timeline}      │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │                    PHASE 5: CLIP DETECTION (New)                             │ │
│  │                                                                              │ │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │ │
│  │  │ Stage 1: 5-Criteria Detection                                        │   │ │
│  │  │ Hook (1-10) + Conflict (1-10) + Resolution (1-10) +                  │   │ │
│  │  │ Shareability (1-10) + Standalone (1-10) = Score/50                   │   │ │
│  │  └──────────────────────────────┬──────────────────────────────────────┘   │ │
│  │                                 ▼                                           │ │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │ │
│  │  │ Stage 2: Adversarial Self-Critique                                   │   │ │
│  │  │ 6 attack vectors: Quote, Hook, Context, Resolution, Ethics, Platform │   │ │
│  │  └──────────────────────────────┬──────────────────────────────────────┘   │ │
│  │                                 ▼                                           │ │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │ │
│  │  │ Stage 3: Multi-Persona Evaluation                                    │   │ │
│  │  │ Viral Expert + Content Creator + Casual Viewer + Critic              │   │ │
│  │  └──────────────────────────────┬──────────────────────────────────────┘   │ │
│  │                                 ▼                                           │ │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │ │
│  │  │ Stage 4: 8-Step Verification Chain                                   │   │ │
│  │  │ Quote exists → Context exists → Timeline logical → Duration valid →  │   │ │
│  │  │ Speaker correct → Within conversation → Clean hook → Final check     │   │ │
│  │  └──────────────────────────────┬──────────────────────────────────────┘   │ │
│  │                                 ▼                                           │ │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │ │
│  │  │ Stage 5: Ensemble Ranking (Borda Count)                              │   │ │
│  │  │ Raw Score + Pairwise Tournament + Persona Consensus → Final Rank     │   │ │
│  │  └──────────────────────────────┬──────────────────────────────────────┘   │ │
│  │                                 ▼                                           │ │
│  │                            clips.json                                       │ │
│  │                 {contextual_clips (5-8 min), moment_clips (60-90s)}        │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │                    PHASE 6: EXTRACTION (Existing)                            │ │
│  │                                                                              │ │
│  │  clips.json → FFmpeg extraction → clips_v3/*.mp4                            │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## Module Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              main.py (CLI)                                       │
│  Commands: pipeline-v3 | detect-visual-changes | classify-people |              │
│            map-conversations | find-contextual-clips                             │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         │                         │                         │
         ▼                         ▼                         ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ EXISTING        │    │ LLM ENGINEERING │    │ NEW MODULES     │
│ (Keep)          │    │ INFRASTRUCTURE  │    │                 │
├─────────────────┤    ├─────────────────┤    ├─────────────────┤
│ downloader.py   │    │anthropic_client │    │visual_change_   │
│ ingester.py     │    │   .py           │    │  detector.py    │
│ transcriber.py  │    │                 │    │                 │
│ visual_mapper.py│    │llm_engineering  │    │voice_finger     │
│ speaker_mapper  │    │   .py           │    │  printer.py     │
│   .py           │    │                 │    │                 │
│ extractor.py    │    │error_recovery   │    │transcript_cue_  │
│                 │    │   .py           │    │  detector.py    │
│                 │    │                 │    │                 │
│                 │    │verification.py  │    │guest_classifier │
│                 │    │                 │    │   .py           │
│                 │    │                 │    │                 │
│                 │    │                 │    │conversation_    │
│                 │    │                 │    │  mapper.py      │
│                 │    │                 │    │                 │
│                 │    │                 │    │contextual_clip_ │
│                 │    │                 │    │  finder.py      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                      │                      │
         ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                           APIS                                   │
├───────────────┬───────────────┬───────────────┬─────────────────┤
│   Deepgram    │   Gemini 2.5  │    Claude     │    Pyannote     │
│   Nova-3      │   (images)    │  Sonnet 4.5   │   (voice)       │
│               │               │   (text)      │                 │
└───────────────┴───────────────┴───────────────┴─────────────────┘
```

---

## LLM Engineering Patterns

### Pattern 1: Chain of Thought (CoT)
```
Used in: Visual Change Detection

Force step-by-step reasoning:
Step 1 → Step 2 → Step 3 → ... → Final Answer

Reduces errors by making reasoning explicit.
```

### Pattern 2: Self-Consistency
```
Used in: Visual Change Detection

Run same query N times (N=3) with temperature variation.
Take majority vote.
Only accept if agreement ratio >= 66%.
```

### Pattern 3: Multi-Pass Verification
```
Used in: Visual Change Detection, Classification

Run with different prompts/perspectives:
- Pass 1: Forward (A → B)
- Pass 2: Backward (B → A)
- Pass 3: Holistic (both together)

Require 2/3 agreement to confirm.
```

### Pattern 4: Multi-Agent Debate
```
Used in: Guest Classification

Agent 1 (Advocate): Argues FOR the conclusion
Agent 2 (Skeptic): Argues AGAINST the conclusion
Agent 3 (Judge): Weighs both arguments, decides

Forces consideration of counterarguments.
```

### Pattern 5: Adversarial Self-Critique
```
Used in: Clip Detection

After initial answer, attack own work:
- Find flaws in reasoning
- Identify potential errors
- Verify claims programmatically
- Adjust confidence accordingly
```

### Pattern 6: Multi-Persona Evaluation
```
Used in: Clip Detection

Evaluate from multiple perspectives:
- Viral Expert: Will this spread?
- Content Creator: Fits the brand?
- Casual Viewer: Would I watch this?
- Critic: What's wrong with this?

Consensus = higher confidence.
```

### Pattern 7: Verification Chains
```
Used in: Clip Detection, Classification

Programmatic verification steps:
Step 1: Check X exists → Pass/Fail
Step 2: Check Y is valid → Pass/Fail
...
All must pass or attempt recovery.
```

### Pattern 8: Ensemble Ranking
```
Used in: Final Clip Ranking

Multiple ranking methods:
1. Raw score ranking
2. Pairwise tournament
3. Persona consensus

Combine with Borda count for final order.
```

---

## Data Flow

```
video.mp4 + nick_sample.wav
         │
         ├─► [1] Transcribe (Deepgram) ──► transcript.json
         │
         ├─► [2] Extract Frames (FFmpeg) ──► frames/*.jpg
         │
         ├─► [3] Visual Changes (Gemini + CoT + Consistency)
         │         └──► visual_events.json
         │
         ├─► [4] Voice Fingerprints (Pyannote + Validation)
         │         └──► voice_fingerprints.json
         │
         ├─► [5] Transcript Cues (Pattern + LLM Validation)
         │         └──► transcript_cues.json
         │
         └─► [6] Classify (Debate + Consistency + Retrospective)
                   └──► people_registry.json
                              │
                              ▼
                   [7] Map Conversations (Hierarchical Summary)
                              └──► conversation_map.json
                                         │
                                         ▼
                   [8] Find Clips (5-Stage Pipeline)
                              └──► clips.json
                                         │
                                         ▼
                   [9] Extract (FFmpeg)
                              └──► clips_v3/*.mp4
```

---

## Data Contracts

### Visual Events (`visual_events.json`)
```json
{
    "events": [
        {
            "timestamp": 9720.0,
            "type": "NEW_PERSON",
            "description": "Man with dark beard wearing keffiyeh",
            "position": "bottom-right box",
            "confidence": 0.92,
            "verification": {
                "consistency_agreement": 1.0,
                "pass_agreement": "3/3",
                "verified": true
            }
        }
    ],
    "total_changes": 15,
    "uncertain_events": 2
}
```

### People Registry (`people_registry.json`)
```json
{
    "nick": {
        "voice_id": "speaker_0",
        "visual_position": "left",
        "total_talk_time": 8500.0
    },
    "panel": [
        {
            "name": "Dani",
            "voice_id": "speaker_1",
            "time_visible": 16500.0,
            "classification_confidence": 0.95
        }
    ],
    "guests": [
        {
            "guest_id": "guest_1",
            "voice_id": "speaker_5",
            "arrival_time": 9720.0,
            "departure_time": 11400.0,
            "duration": 1680.0,
            "intro_cue": "what's up man",
            "visual_description": "man with keffiyeh",
            "classification": {
                "method": "debate",
                "advocate_score": 8,
                "skeptic_score": 3,
                "judge_verdict": "NEW_GUEST",
                "confidence": 0.91
            }
        }
    ],
    "classification_metadata": {
        "temporal_consistency_passed": true,
        "retrospective_corrections": 2,
        "final_confidence": 0.89
    }
}
```

### Conversation Map (`conversation_map.json`)
```json
{
    "conversations": [
        {
            "guest_id": "guest_1",
            "start_time": 9720.0,
            "end_time": 11400.0,
            "summary": {
                "executive": "Heated debate about Israel-Palestine...",
                "detailed": "The conversation began with...",
                "chunk_count": 6
            },
            "topics": [
                {
                    "topic": "Gaza civilian casualties",
                    "confidence": 0.92,
                    "evidence_quotes": ["quote1", "quote2"],
                    "time_range": [9800.0, 10200.0]
                }
            ],
            "timeline": [
                {"time": 9720.0, "entry": "Guest introduces himself as Palestinian-American"},
                {"time": 9900.0, "entry": "Debate about civilian casualty numbers begins"},
                {"time": 10500.0, "entry": "Nick challenges guest's source"}
            ],
            "mood": "contentious",
            "winner": "NICK"
        }
    ]
}
```

### Clips (`clips.json`)
```json
{
    "clips": [
        {
            "clip_id": "clip_1",
            "guest_id": "guest_1",
            "type": "gotcha",
            "contextual": {
                "start_time": 9800.0,
                "end_time": 10200.0,
                "duration": 400.0,
                "title": "Nick Destroys Guest's Source",
                "story_arc": "Setup → Challenge → Revelation → Reaction"
            },
            "moment": {
                "start_time": 10050.0,
                "end_time": 10140.0,
                "duration": 90.0,
                "money_quote": "You didn't even read your own source!"
            },
            "scores": {
                "hook": 9,
                "conflict": 9,
                "resolution": 10,
                "shareability": 9,
                "standalone": 8,
                "total": 45
            },
            "verification": {
                "quote_verified": true,
                "timeline_verified": true,
                "duration_verified": true,
                "all_8_steps_passed": true
            },
            "persona_evaluation": {
                "viral_expert": {"score": 9, "approved": true},
                "content_creator": {"score": 8, "approved": true},
                "casual_viewer": {"score": 8, "approved": true},
                "critic": {"score": 7, "approved": true}
            },
            "final_rank": 1,
            "confidence": 0.94
        }
    ]
}
```

---

## File Structure (V3)

```
nick-matau-clipper/
├── src/
│   ├── __init__.py
│   │
│   │  # Existing (Keep)
│   ├── downloader.py           # YouTube download
│   ├── ingester.py             # Audio extraction
│   ├── transcriber.py          # Deepgram transcription
│   ├── visual_mapper.py        # Frame extraction (keep for frames)
│   ├── speaker_mapper.py       # Nick voiceprint
│   ├── extractor.py            # FFmpeg clip cutting
│   │
│   │  # LLM Engineering Infrastructure (New)
│   ├── anthropic_client.py     # Claude API wrapper
│   ├── llm_engineering.py      # Self-consistency, debate, ensemble
│   ├── error_recovery.py       # Recovery strategies
│   ├── verification.py         # Verification chains
│   │
│   │  # V3 Pipeline Modules (New)
│   ├── visual_change_detector.py    # Frame comparison with CoT
│   ├── voice_fingerprinter.py       # Multi-speaker tracking
│   ├── transcript_cue_detector.py   # Greeting/exit detection
│   ├── guest_classifier.py          # Multi-agent classification
│   ├── conversation_mapper.py       # Hierarchical summarization
│   ├── contextual_clip_finder.py    # 5-stage clip detection
│   │
│   │  # Deprecated (Move to archive/)
│   ├── conversation_segmenter.py    # → archived
│   ├── clip_analyzer.py             # → archived
│   ├── quote_clip_finder.py         # → archived (keep temporarily)
│   └── smart_clip_finder.py         # → delete
│
├── prompts/
│   ├── visual_cot.md               # Chain of Thought visual
│   ├── visual_passes.md            # Three-pass verification
│   ├── debate_advocate.md          # Argue FOR new guest
│   ├── debate_skeptic.md           # Argue AGAINST new guest
│   ├── debate_judge.md             # Judge the debate
│   ├── temporal_consistency.md     # Timeline consistency
│   ├── retrospective_review.md     # Review all classifications
│   ├── clip_detection.md           # 5-criteria detection
│   ├── clip_critique.md            # Adversarial self-critique
│   ├── clip_personas.md            # Multi-persona evaluation
│   ├── hierarchical_summary.md     # Conversation summarization
│   └── topic_extraction.md         # Topic extraction
│
├── outputs/
│   │  # Existing
│   ├── *.mp4                       # Source videos
│   ├── *_transcript.json           # Transcripts
│   ├── *_frames/                   # Extracted frames
│   │
│   │  # V3 Outputs
│   ├── visual_events.json          # Visual change events
│   ├── voice_fingerprints.json     # Speaker fingerprints
│   ├── transcript_cues.json        # Detected cues
│   ├── people_registry.json        # Classified people
│   ├── conversation_map.json       # Conversations + timeline
│   ├── clips.json                  # Final clips
│   └── clips_v3/                   # Extracted clip videos
│
├── docs/
│   ├── ARCHITECTURE.md             # This file
│   ├── TASKS.md                    # Implementation tasks
│   ├── STATUS.md                   # Progress status
│   ├── PIPELINE_SUMMARY.md         # V2 → V3 transition
│   └── PRD.md                      # Product requirements
│
├── tests/
│   ├── test_anthropic_client.py
│   ├── test_llm_engineering.py
│   ├── test_visual_change_detector.py
│   ├── test_guest_classifier.py
│   ├── test_conversation_mapper.py
│   └── test_contextual_clip_finder.py
│
├── CLAUDE.md                       # AI assistant instructions
├── main.py                         # CLI entry point
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## API & Cost Summary

### APIs Used

| API | Model | Purpose | Cost/Unit |
|-----|-------|---------|-----------|
| Deepgram | Nova-3 | Transcription | $0.0043/min |
| Gemini | 2.5 Flash | Visual analysis | ~$0.001/image |
| Claude | Sonnet 4.5 | Text analysis | $3/$15 per MTok |
| Pyannote | - | Voice ID | ~$0.10/min |

### Cost per 4-Hour Video

| Stage | Cost |
|-------|------|
| Transcription | $1.25 |
| Visual (with engineering) | $3.00 |
| Voice correlation | $0.50 |
| Transcript cues | $1.00 |
| Classification (debate) | $2.00 |
| Retrospective review | $0.50 |
| Conversation summaries | $1.50 |
| Clip detection (5-stage) | $4.00 |
| Persona evaluation | $1.50 |
| Verification | $0.75 |
| **Total** | **~$16** |

---

## Error Handling

### Recovery Strategies

1. **Quote Not Found**: Fuzzy → Semantic → Keyword → LLM recovery
2. **Classification Inconsistent**: Temporal check → Auto-fix → Flag for review
3. **Verification Failed**: Boundary adjustment → Duration fix → Reject
4. **Low Confidence**: Flag for human review (don't auto-reject)

### Confidence Thresholds

| Level | Range | Action |
|-------|-------|--------|
| High | ≥ 0.85 | Auto-accept |
| Medium | 0.70-0.85 | Include with flag |
| Low | < 0.70 | Attempt recovery or reject |
