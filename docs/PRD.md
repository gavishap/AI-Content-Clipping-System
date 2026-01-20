# Product Requirements Document: Nick Matau AI Content Clipper

## Project Overview

### Vision
Build an AI-powered content clipping system that automatically identifies viral-worthy moments from Nick Matau's 3-4 hour livestreams and extracts them as ready-to-post short-form clips.

### Problem Statement
Nick streams 3-4 hours of content regularly. Manually reviewing footage to find clip-worthy moments is time-consuming (4-8 hours per stream). We need an automated system that can:
1. Transcribe the entire stream with precise timestamps
2. Use AI to identify moments with viral potential
3. Extract clips with accurate start/end points
4. Present clips for Nick's review and approval

### Success Metrics
- **Speed**: Process 4-hour video in under 30 minutes
- **Accuracy**: 50%+ of suggested clips approved by Nick
- **Quality**: No clips start/end mid-sentence
- **Cost**: Under $2 per video processed

---

## Target Users

### Primary User: Nick Matau
- Livestream content creator and live debater
- Creates 3-4 hour streams
- Needs viral clips for TikTok, YouTube Shorts, Instagram Reels
- Values: Hot takes, reactions, debate moments, emotional moments

### Secondary Users: Seqora AI Team
- Gabriel (AI Engineer): Builds transcription, AI analysis, prompts
- Jake (Integration Engineer): Builds FFmpeg modules, Google Sheets

---

## Core Features

### 1. Video Ingestion
- Accept MP4/MKV/MOV files (any resolution)
- Extract audio as 16kHz mono WAV (optimal for ASR)
- Extract video metadata (duration, resolution, codec)
- Handle large files (2-10GB)

### 2. AI Transcription (Deepgram Nova-3)
- Word-level timestamps (critical for accuracy)
- Speaker diarization (identify Nick vs guests)
- Smart punctuation for natural sentence breaks
- Output: Timestamped transcript for AI analysis

### 3. Clip Detection (Gemini 2.5 Pro)
- Analyze full transcript (300K+ tokens)
- Identify 15-25 clip-worthy moments per video
- Score clips by virality potential (1-10)
- Categorize: hot_take, reaction, debate, story, humor, insight
- Include verification text (start_text, end_text) for validation

### 4. Timestamp Refinement
- Use word-level data to find exact sentence boundaries
- Ensure clips don't start/end mid-word
- Add natural padding (0.3s start, 0.5s end)

### 5. Clip Extraction (FFmpeg)
- Keyframe-accurate seeking
- Re-encode for precise timing
- Multiple quality presets (fast/medium/high)
- Proper audio/video sync

### 6. Review Queue (Google Sheets)
- Display all clip candidates with metadata
- Status column: Pending/Approved/Rejected
- Notes column for Nick's feedback
- Link to clip files

---

## Technical Requirements

### APIs & Services
| Service | Purpose | Cost |
|---------|---------|------|
| Deepgram Nova-3 | Transcription | $0.0043/min (~$1.03/4hr video) |
| Gemini 2.5 Pro | Clip detection | ~$0.40/video |
| Google Sheets API | Review queue | Free |
| FFmpeg | Video processing | Free |

### Tech Stack
- Python 3.11+
- deepgram-sdk >= 3.0.0
- google-generativeai >= 0.8.0
- ffmpeg-python >= 0.2.0
- click >= 8.0.0 (CLI)
- pyyaml, python-dotenv (config)

### Performance Requirements
- Transcription: ~5 min for 4-hour video
- AI Analysis: ~2 min for full transcript
- Clip Extraction: ~30 sec per clip
- Total: Under 30 min for complete pipeline

---

## Data Flow

```
[Video File]
     │
     ▼
[1. Ingester] ─────► [WAV Audio] + [Metadata]
     │
     ▼
[2. Transcriber] ──► [Timestamped Transcript] + [Word Data]
     │
     ▼
[3. Analyzer] ─────► [Clip Candidates JSON]
     │
     ▼
[4. Refiner] ──────► [Refined Timestamps]
     │
     ▼
[5. Extractor] ────► [MP4 Clip Files]
     │
     ▼
[6. Sheets] ───────► [Review Queue]
```

---

## What Makes a Good Clip

### Strong Hook (First 3 Seconds)
- Surprising statement ("Bro, that's actually insane...")
- Bold claim ("This is the worst take I've ever heard")
- Emotional reaction (shock, laughter, frustration)
- Provocative question ("Wait, did he actually say that?")

### Clear Narrative Arc
- Setup: Quick context (1-2 sentences max)
- Peak: The clip-worthy moment
- Resolution: Natural ending (reaction, punchline, conclusion)

### Standalone Value
- Makes sense WITHOUT watching the full stream
- No context-dependent moments
- No inside jokes requiring stream history

### Platform Fit
- TikTok: 30-60s, hook in first 1 second
- YouTube Shorts: Up to 90s
- Instagram Reels: 30-60s, visual appeal
- X/Twitter: Controversial takes, <60s

---

## What to Avoid

❌ Starting mid-sentence or mid-thought
❌ Ending abruptly without resolution
❌ Dead air or long pauses (>3 seconds)
❌ Technical issues (audio glitches, stream lag)
❌ Context-dependent moments
❌ Inside jokes requiring stream context

---

## Timeline

### Sprint 1: MVP (Jan 13 - Jan 27)
**Week 1 (Jan 13-19)**
- [Gabriel] Client onboarding, API setup, transcription module
- [Jake] Repository setup, video ingestion module

**Week 2 (Jan 20-24)**
- [Gabriel] AI analyzer, prompts, timestamp refinement, orchestrator
- [Jake] Clip extraction, Google Sheets integration

**Week 3 (Jan 25-27)**
- [Both] End-to-end integration testing
- [Gabriel] Sprint review with Nick

### Future Phases
- Phase 2: Auto-posting to platforms
- Phase 3: Caption generation
- Phase 4: Thumbnail generation

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Timestamp hallucination | Clips start at wrong time | Verification text + word-level refinement |
| Low approval rate | Wasted processing | Iterate prompts based on Nick's feedback |
| API rate limits | Processing delays | Batch processing, caching transcripts |
| Large file handling | Memory issues | Stream processing, chunked upload |

---

## Appendix: API Pricing Calculator

| Video Length | Deepgram | Gemini | FFmpeg | Total |
|--------------|----------|--------|--------|-------|
| 2 hours | $0.52 | $0.25 | Free | $0.77 |
| 4 hours | $1.03 | $0.40 | Free | $1.43 |
| 6 hours | $1.55 | $0.55 | Free | $2.10 |
