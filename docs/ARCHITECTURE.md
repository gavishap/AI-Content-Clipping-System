# System Architecture - Pipeline V3

> **Last Updated**: Feb 8, 2026

## High-Level Pipeline

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                     NICK MATAU AI CLIPPER v3.0                                    │
│              Full LLM Engineering for Maximum Accuracy                            │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  PHASE 1: DATA COLLECTION ✅ Working                                             │
│  ────────────────────────────────────────────────────                             │
│  YouTube URL → Download → Extract Audio → Transcribe → Extract Frames            │
│      │           │            │              │              │                     │
│      ▼           ▼            ▼              ▼              ▼                     │
│  [yt-dlp]    [video.mp4]  [audio.wav]  [transcript]    [frames/]                │
│                                         (Deepgram)     (FFmpeg)                  │
│                                                                                   │
│  PHASE 2: IDENTITY DETECTION ✅ Working                                          │
│  ────────────────────────────────────────────────────                             │
│                                                                                   │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐         │
│  │ Visual Change      │  │ Voice Fingerprint  │  │ Transcript Cue     │         │
│  │ Detector           │  │ er (Pyannote)      │  │ Detector           │         │
│  │                    │  │                    │  │                    │         │
│  │ • CoT prompting    │  │ • Voiceprint train │  │ • 20+ regex intro  │         │
│  │ • 3x consistency   │  │ • Speaker identify │  │ • 15+ regex exit   │         │
│  │ • 3-pass verify    │  │ • Audio trim       │  │ • LLM validation   │         │
│  │                    │  │ • Deepgram merge   │  │                    │         │
│  │ Gemini 2.5         │  │ • Utterance collapse│  │ Claude             │         │
│  └─────────┬──────────┘  └─────────┬──────────┘  └─────────┬──────────┘         │
│            │                       │                       │                     │
│            ▼                       ▼                       ▼                     │
│     visual_events.json    episode_258_         transcript_cues.json              │
│                           transcript_v3.json                                     │
│                           transcript_v3.txt                                      │
│                                                                                   │
│  PHASE 2.5: ENHANCED TRANSCRIPT ✅ Working                                       │
│  ────────────────────────────────────────────────────                             │
│                                                                                   │
│  Deepgram transcript + Pyannote identification → Merged utterance transcript     │
│                                                                                   │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐     │
│  │ Trim audio   │ → │ Upload to    │ → │ Pyannote     │ → │ Merge with   │     │
│  │ (FFmpeg)     │   │ Pyannote     │   │ identify     │   │ Deepgram     │     │
│  │              │   │ (media/input)│   │ w/ voiceprint│   │ by overlap   │     │
│  └──────────────┘   └──────────────┘   └──────────────┘   └──────┬───────┘     │
│                                                                    │             │
│                                           ┌────────────────────────┘             │
│                                           ▼                                      │
│                                    ┌──────────────┐                              │
│                                    │ Collapse to  │                              │
│                                    │ utterances   │                              │
│                                    └──────┬───────┘                              │
│                                           │                                      │
│                              ┌────────────┼────────────┐                         │
│                              ▼            ▼            ▼                         │
│                        .json         .txt         _raw_words.json               │
│                     (structured)  (readable)   (word-level backup)               │
│                                                                                   │
│  PHASE 3: CLASSIFICATION 🔴 TODO                                                │
│  ────────────────────────────────────────────────────                             │
│                                                                                   │
│  ┌──────────────────────────────────────────────────────────────────────┐        │
│  │                       Guest Classifier                                │        │
│  │                                                                       │        │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐              │        │
│  │  │  Advocate   │ vs │   Skeptic   │ → │    Judge    │              │        │
│  │  │ "IS guest"  │    │"NOT guest"  │    │  (decides)  │              │        │
│  │  └─────────────┘    └─────────────┘    └─────────────┘              │        │
│  │                           │                                          │        │
│  │                           ▼                                          │        │
│  │              Temporal Consistency → Retrospective Review             │        │
│  └──────────────────────────────────────────────────────────────────────┘        │
│                              ▼                                                    │
│                     people_registry.json                                          │
│                                                                                   │
│  PHASE 4: CONVERSATION MAPPING 🔴 TODO                                           │
│  ────────────────────────────────────────────────────                             │
│                                                                                   │
│  For each guest:                                                                 │
│  Extract transcript → Chunk 3-min → Summarize → Meta-summarize → Topics         │
│                              ▼                                                    │
│                     conversation_map.json                                         │
│                                                                                   │
│  PHASE 5: CLIP DETECTION 🔴 TODO                                                 │
│  ────────────────────────────────────────────────────                             │
│                                                                                   │
│  Stage 1: 5-Criteria Detection (Hook + Conflict + Resolution +                   │
│           Shareability + Standalone = Score/50)                                   │
│  Stage 2: Adversarial Self-Critique (6 attack vectors)                           │
│  Stage 3: Multi-Persona Evaluation (4 personas)                                  │
│  Stage 4: 8-Step Verification Chain                                              │
│  Stage 5: Ensemble Ranking (Borda Count)                                         │
│                              ▼                                                    │
│                         clips.json                                                │
│                                                                                   │
│  PHASE 6: EXTRACTION ✅ Working                                                   │
│  ────────────────────────────────────────────────────                             │
│                                                                                   │
│  clips.json → FFmpeg extraction → clips_v3/*.mp4                                 │
│                                                                                   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## Complete Module Map

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              main.py (CLI Entry Point)                           │
│                                                                                  │
│  Working commands:                                                                │
│    download | transcribe | transcribe-url | create-voiceprint |                  │
│    map-speakers | analyze-voices | enhance-transcript |                          │
│    map-visual | segment | find-clips | pipeline                                  │
│                                                                                  │
│  Legacy commands: process | analyze | extract                                    │
└──────────────────────────────────┬───────────────────────────────────────────────┘
                                   │
    ┌──────────────────────────────┼──────────────────────────────┐
    │                              │                              │
    ▼                              ▼                              ▼
┌───────────────────┐  ┌────────────────────┐  ┌────────────────────────────────┐
│ DATA COLLECTION   │  │ LLM ENGINEERING    │  │ V3 DETECTION & ANALYSIS        │
│ (Phase 1)         │  │ INFRASTRUCTURE     │  │ (Phase 2+)                     │
├───────────────────┤  ├────────────────────┤  ├────────────────────────────────┤
│                   │  │                    │  │                                │
│ downloader.py     │  │ anthropic_client   │  │ visual_change_detector.py  ✅ │
│  └ yt-dlp         │  │   .py          ✅ │  │  └ Gemini 2.5                 │
│                   │  │  └ Claude API      │  │  └ CoT + consistency + verify │
│ ingester.py       │  │  └ Retry, JSON     │  │                                │
│  └ FFmpeg audio   │  │  └ Cost tracking   │  │ voice_fingerprinter.py     ✅ │
│                   │  │                    │  │  └ Pyannote API               │
│ transcriber.py    │  │ llm_engineering    │  │  └ Voiceprint create          │
│  └ Deepgram Nova-3│  │   .py          ✅ │  │  └ Diarize + Identify         │
│  └ Word timestamps│  │  └ SelfConsistency │  │  └ Audio trim (FFmpeg)        │
│  └ Speaker IDs    │  │  └ MultiAgentDebate│  │  └ Deepgram merge             │
│                   │  │  └ EnsembleRanker  │  │  └ Utterance collapse         │
│ visual_mapper.py  │  │  └ TwoPassVerifier │  │  └ Readable transcript        │
│  └ Frame extract  │  │  └ Confidence cal. │  │                                │
│  └ Gemini analysis│  │                    │  │ transcript_cue_detector.py ✅ │
│                   │  │ error_recovery     │  │  └ 20+ intro regex patterns   │
│ speaker_mapper.py │  │   .py          🔴 │  │  └ 15+ exit regex patterns    │
│  └ V2 Deepgram    │  │                    │  │  └ LLM context validation     │
│    speaker map    │  │ verification       │  │                                │
│                   │  │   .py          🔴 │  │ guest_classifier.py        🔴 │
│ extractor.py      │  │                    │  │  └ Multi-agent debate         │
│  └ FFmpeg clip cut│  │                    │  │                                │
│                   │  │                    │  │ conversation_mapper.py     🔴 │
│ timestamp_utils.py│  │                    │  │  └ Hierarchical summaries     │
│  └ Format helpers │  │                    │  │                                │
│                   │  │                    │  │ contextual_clip_finder.py  🔴 │
│                   │  │                    │  │  └ 5-stage clip detection     │
└───────────────────┘  └────────────────────┘  └────────────────────────────────┘
         │                      │                           │
         ▼                      ▼                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                           EXTERNAL APIs                          │
├───────────────┬───────────────┬───────────────┬─────────────────┤
│   Deepgram    │   Gemini 2.5  │    Claude     │    Pyannote     │
│   Nova-3      │   Flash       │  Sonnet 4.5   │   AI            │
│               │               │               │                 │
│ Transcription │ Visual frames │ Text analysis  │ Voice ID        │
│ Word timestamps│ Image analysis│ LLM patterns  │ Diarization     │
│ Speaker IDs   │              │ Cue validation │ Identification  │
│               │              │               │ Voiceprints     │
│ ~$0.004/min   │ ~$0.001/img  │ $3/$15 per MTok│ ~$0.10/min     │
└───────────────┴───────────────┴───────────────┴─────────────────┘
```

---

## V2 Legacy Pipeline (Still Available)

```
┌──────────────────────────────────────────────────────────────────────┐
│                      V2 LEGACY PIPELINE                               │
│               (Works but has known issues)                            │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  speaker_mapper.py → conversation_segmenter.py → clip_analyzer.py    │
│  (Deepgram IDs)       (visual + voice merge)      (Gemini clips)     │
│                       ⚠️ Same person = many        ⚠️ Bad timestamps │
│                          "conversations"                              │
│                                                                       │
│  quote_clip_finder.py (V2 - Best working clip finder)                │
│  ├ 10-min sliding windows over transcript                             │
│  ├ Gemini finds "money quotes"                                        │
│  ├ Search transcript for exact text → precise timestamp               │
│  ├ Expand 40s before + 50s after                                      │
│  └ Dedup overlapping clips                                            │
│  → 47 clips found, 10 extracted to clips_v2/                         │
│                                                                       │
│  CLI: map-speakers | map-visual | segment | find-clips | pipeline    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Enhanced Transcript Data Flow (New)

```
audio.wav + nick_voiceprint.json + episode_258_transcript.json
         │
         ├─► [1] Trim audio (FFmpeg, optional -s start -d duration)
         │         └──► trimmed_for_pyannote.wav (e.g., last 2 hours)
         │
         ├─► [2] Upload to Pyannote (POST /v1/media/input → PUT presigned URL)
         │         └──► media://voiceprint-xxxx (temporary Pyannote URL)
         │
         ├─► [3] Pyannote Identify (POST /v1/identify)
         │         ├── model: precision-2
         │         ├── voiceprints: [{label: "nick", voiceprint: "<base64>"}]
         │         ├── matching: {threshold: 50, exclusive: true}
         │         └──► Job ID → Poll /v1/jobs/{id} → identification segments
         │              └── 2,302 segments, SPEAKER_03 = nick
         │
         ├─► [4] Merge with Deepgram (by timestamp overlap)
         │         ├── For each Deepgram word: find Pyannote segment with max overlap
         │         ├── Replace speaker number with name (nick, SPEAKER_XX)
         │         ├── Time offset adjustment for trimmed audio
         │         └──► 50,507 words with speaker_name field
         │
         └─► [5] Collapse to utterances (group by speaker + 2s pause threshold)
                   ├──► episode_258_transcript_v3.json  (structured, 2,347 utterances)
                   ├──► episode_258_transcript_v3.txt   (readable text)
                   └──► episode_258_transcript_v3_raw_words.json (word-level backup)
```

---

## Output Data Formats

### Structured Utterance Transcript (`*_v3.json`)
```json
{
    "format": "utterance_transcript_v3",
    "utterances": [
        {
            "speaker": "nick",
            "start": 10314.0,
            "end": 10314.7,
            "text": "What version is it?",
            "word_count": 4
        },
        {
            "speaker": "SPEAKER_10",
            "start": 10316.2,
            "end": 10316.8,
            "text": "New American Standard.",
            "word_count": 3
        }
    ],
    "summary": {
        "total_utterances": 2347,
        "total_words": 50507,
        "duration_seconds": 17498.2,
        "speakers": {
            "nick": {"total_words": 13240, "total_utterances": 545, ...},
            "SPEAKER_04": {"total_words": 5250, "total_utterances": 316, ...}
        }
    },
    "metadata": {
        "pyannote_segments": 2302,
        "words_matched": 21388,
        "words_unmatched": 29119,
        "time_offset": 10314.0,
        "speaker_mapping": {"SPEAKER_03": "nick"}
    }
}
```

### Readable Transcript (`*_v3.txt`)
```
[2:51:53] nick: What version is it?
[2:51:56] SPEAKER_10: New American Standard.
[2:51:57] SPEAKER_06: Ask him if it has a mass.
[2:52:19] nick: I haven't... I read the King James Version mostly.
```

### Visual Events (`visual_events.json`) - Future
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
    ]
}
```

### People Registry (`people_registry.json`) - Future
```json
{
    "nick": {"voice_id": "speaker_0", "total_talk_time": 8500.0},
    "panel": [{"name": "Dani", "voice_id": "speaker_1", "confidence": 0.95}],
    "guests": [
        {
            "guest_id": "guest_1",
            "voice_id": "SPEAKER_04",
            "arrival_time": 9720.0,
            "departure_time": 11400.0,
            "classification": {"method": "debate", "confidence": 0.91}
        }
    ]
}
```

### Clips (`clips.json`) - Future
```json
{
    "clips": [
        {
            "clip_id": "clip_1",
            "guest_id": "guest_1",
            "type": "gotcha",
            "contextual": {"start_time": 9800.0, "end_time": 10200.0, "duration": 400.0},
            "moment": {"start_time": 10050.0, "end_time": 10140.0, "money_quote": "..."},
            "scores": {"hook": 9, "conflict": 9, "total": 45},
            "verification": {"all_8_steps_passed": true},
            "final_rank": 1,
            "confidence": 0.94
        }
    ]
}
```

---

## LLM Engineering Patterns

| Pattern | Status | Where Used | How It Works |
|---------|--------|------------|--------------|
| Chain of Thought | ✅ | Visual detection | 6-step reasoning forced in prompt |
| Self-Consistency | ✅ | Visual detection | 3 runs w/ temp variation, majority vote |
| Multi-Pass Verify | ✅ | Visual detection | Forward, backward, holistic passes |
| Multi-Agent Debate | ✅ Implemented | Classification (TODO) | Advocate vs Skeptic → Judge decides |
| Temporal Consistency | ✅ Implemented | Classification (TODO) | Verify timeline makes sense |
| Adversarial Critique | ✅ Implemented | Clip detection (TODO) | 6 attack vectors on own work |
| Multi-Persona Eval | ✅ Implemented | Clip detection (TODO) | 4 personas evaluate each clip |
| Verification Chain | 🔴 | Clip detection | 8-step programmatic validation |
| Ensemble Ranking | ✅ Implemented | Clip detection (TODO) | Borda count across ranking methods |
| Error Recovery | 🔴 | All stages | Fuzzy/semantic/keyword/LLM recovery |

---

## File Structure

```
nick-matau-clipper/
├── main.py                            # CLI entry point (1067 lines)
├── CLAUDE.md                          # AI assistant instructions
├── README.md                          # Project readme
├── requirements.txt                   # Python dependencies
├── .env                               # API keys (not committed)
├── .env.example                       # API key template
├── nick_voiceprint.json               # Nick's Pyannote voiceprint
│
├── src/
│   ├── __init__.py
│   │
│   │  # DATA COLLECTION (Phase 1) - All ✅ Working
│   ├── downloader.py                  # YouTube download (yt-dlp)
│   ├── ingester.py                    # Audio extraction (FFmpeg)
│   ├── transcriber.py                 # Deepgram Nova-3 transcription
│   ├── visual_mapper.py               # Frame extraction + Gemini
│   ├── speaker_mapper.py              # Deepgram speaker mapping (V2)
│   ├── extractor.py                   # FFmpeg clip cutting
│   ├── timestamp_utils.py             # Timestamp helpers
│   │
│   │  # LLM ENGINEERING (Phase 1) - ✅ Working
│   ├── anthropic_client.py            # Claude API wrapper (380 lines)
│   ├── llm_engineering.py             # LLM patterns (940 lines)
│   │
│   │  # IDENTITY DETECTION (Phase 2) - All ✅ Working
│   ├── visual_change_detector.py      # CoT + consistency (500 lines)
│   ├── voice_fingerprinter.py         # Pyannote + merge + utterances (1500 lines)
│   ├── transcript_cue_detector.py     # Pattern + LLM validation (550 lines)
│   │
│   │  # V2 CLIP FINDING (Legacy)
│   ├── quote_clip_finder.py           # ⚠️ Quote-based clips (V2, still usable)
│   │
│   │  # DEPRECATED
│   ├── conversation_segmenter.py      # ❌ Replaced by V3
│   ├── clip_analyzer.py               # ❌ Replaced by V3
│   ├── smart_clip_finder.py           # ❌ Not used
│   ├── analyzer.py                    # ❌ Old module
│   └── sheets.py                      # ❌ Google Sheets (unused)
│
├── prompts/
│   ├── base_prompt.md                 # Base system prompt
│   ├── clip_detection.md              # Clip finding prompt
│   ├── frame_analysis.md              # Visual analysis prompt
│   └── nick_preferences.md            # Nick's content style
│
├── outputs/
│   ├── *.mp4, *.wav                   # Source media
│   ├── *_transcript.json              # Deepgram transcripts
│   ├── episode_258_transcript_v3.json # ✅ Structured utterances (NEW)
│   ├── episode_258_transcript_v3.txt  # ✅ Readable transcript (NEW)
│   ├── episode_258_transcript_v3_raw_words.json # ✅ Word-level (NEW)
│   ├── episode_258_frames/            # Extracted frames
│   ├── clips_v2/                      # V2 extracted clips
│   └── clips_manual/                  # Manually cut clips
│
├── tests/
│   ├── test_anthropic_client.py       # ✅
│   ├── test_llm_engineering.py        # ✅
│   ├── test_visual_change_detector.py # ✅
│   ├── test_voice_fingerprinter.py    # ✅
│   ├── test_transcript_cue_detector.py# ✅
│   ├── test_transcriber.py            # ✅
│   ├── test_downloader.py             # ✅
│   ├── test_ingester.py               # ✅
│   ├── test_extractor.py              # ✅
│   └── test_timestamp_utils.py        # ✅
│
└── docs/
    ├── ARCHITECTURE.md                # This file
    ├── TASKS.md                       # Implementation checklist
    ├── STATUS.md                      # Session progress
    ├── PIPELINE_SUMMARY.md            # V2→V3 transition
    ├── PRD.md                         # Product requirements
    └── TRANSCRIBER_TASK.md            # Transcriber design doc
```

---

## API & Cost Summary

### APIs Used

| API | Model | Purpose | Cost/Unit |
|-----|-------|---------|-----------|
| Deepgram | Nova-3 | Transcription (word-level) | $0.0043/min |
| Gemini | 2.5 Flash | Visual analysis + V2 clips | ~$0.001/image |
| Claude | Sonnet 4.5 | Text analysis, LLM patterns | $3/$15 per MTok |
| Pyannote | precision-2 | Voice ID, diarization | ~$0.10/min |

### Cost per 4-Hour Video

| Stage | Cost |
|-------|------|
| Transcription (Deepgram) | $1.25 |
| Visual detection (Gemini, with engineering) | $3.00 |
| Voice identification (Pyannote, last 2h) | $6.00 |
| Transcript cues (Claude) | $1.00 |
| Classification (Claude, debate) | $2.00 |
| Conversation summaries (Claude) | $1.50 |
| Clip detection (Claude, 5-stage) | $4.00 |
| Persona evaluation + verification | $2.25 |
| **Total** | **~$22** |
