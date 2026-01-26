# Nick Matau Clipper - Pipeline Summary

**Last Updated:** January 25, 2026  
**Status:** V2 working with issues → V3 redesign in progress

---

## V3 PIPELINE REDESIGN (In Progress)

The V2 pipeline has fundamental issues that V3 addresses with full LLM engineering.

### V2 Problems
1. **Same person = multiple descriptions** - Gemini describes each frame independently
2. **No panel vs guest distinction** - Can't tell Dani from actual guests
3. **No cross-validation** - Visual, voice, transcript not combined
4. **Conversation data unreliable** - 28 "guests" instead of ~8-10

### V3 Solution
Multi-signal detection with LLM engineering:
- **Chain of Thought** - Step-by-step visual reasoning
- **Self-Consistency** - 3-run majority vote
- **Multi-Agent Debate** - Advocate vs Skeptic vs Judge for classification
- **5-Stage Clip Detection** - Scoring → Critique → Personas → Verify → Rank

See `docs/ARCHITECTURE.md` and `docs/TASKS.md` for V3 details.

---

## V2 PIPELINE (Current - Working with Issues)

---

## Table of Contents
1. [Current Pipeline Overview](#current-pipeline-overview)
2. [Step-by-Step Pipeline Details](#step-by-step-pipeline-details)
3. [Output Files Inventory](#output-files-inventory)
4. [Known Issues](#known-issues)
5. [Methods NOT Currently Used](#methods-not-currently-used)
6. [What Needs To Be Done](#what-needs-to-be-done)
7. [Technical Notes](#technical-notes)

---

## Current Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CURRENT WORKING PIPELINE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  YouTube URL                                                                 │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────┐                                                            │
│  │ 1. DOWNLOAD │  src/downloader.py                                         │
│  │   (yt-dlp)  │  → outputs/*.mp4                                           │
│  └──────┬──────┘                                                            │
│         │                                                                    │
│         ▼                                                                    │
│  ┌─────────────────┐                                                        │
│  │ 2. TRANSCRIBE   │  src/transcriber.py (Deepgram Nova-3)                  │
│  │   + Speaker ID  │  → outputs/*_transcript.json                           │
│  └────────┬────────┘     (word-level timestamps + speaker diarization)      │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐            │
│  │              QUOTE-BASED CLIP FINDER (V2)                    │            │
│  │              src/quote_clip_finder.py                        │            │
│  │                                                              │            │
│  │  • Analyzes transcript in 10-minute sliding windows          │            │
│  │  • Gemini finds "money quotes" - exact memorable lines       │            │
│  │  • Searches transcript for exact quote → gets timestamp      │            │
│  │  • Expands 40s before + 50s after quote                      │            │
│  │  • Does NOT use conversation segmentation                    │            │
│  │                                                              │            │
│  │  → outputs/quote_clips.json (47 clips found)                 │            │
│  └────────────────────────┬────────────────────────────────────┘            │
│                           │                                                  │
│                           ▼                                                  │
│  ┌─────────────────┐                                                        │
│  │ 4. EXTRACT      │  src/extractor.py (FFmpeg)                             │
│  │    CLIPS        │  → outputs/clips_v2/*.mp4                              │
│  └─────────────────┘                                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### What We're NOT Using (But Have Implemented)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    IMPLEMENTED BUT NOT USED IN V2                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐                                                       │
│  │ VISUAL MAPPING   │  src/visual_mapper.py                                 │
│  │ (Gemini Vision)  │  → outputs/*_visual_map.json                          │
│  │                  │  • Extracts frames every 30 seconds                   │
│  │                  │  • Gemini describes people in each frame              │
│  │                  │  • PROBLEM: Same person = different descriptions      │
│  └────────┬─────────┘                                                       │
│           │                                                                  │
│           ▼                                                                  │
│  ┌──────────────────┐                                                       │
│  │ VOICE MAPPING    │  Created from Deepgram speaker IDs                    │
│  │ (Deepgram)       │  → outputs/*_voice_map.json                           │
│  │                  │  • Speaker 0 = Nick (64% of words)                    │
│  │                  │  • All others = "guest"                               │
│  └────────┬─────────┘                                                       │
│           │                                                                  │
│           ▼                                                                  │
│  ┌──────────────────┐                                                       │
│  │ CONVERSATION     │  src/conversation_segmenter.py                        │
│  │ SEGMENTATION     │  → outputs/*_conversations.json                       │
│  │                  │  • Merges visual + voice data                         │
│  │                  │  • PROBLEM: Only detects guests from 2:42:00          │
│  │                  │  • PROBLEM: Same person = multiple "conversations"    │
│  └──────────────────┘                                                       │
│                                                                              │
│  ┌──────────────────┐                                                       │
│  │ OLD CLIP FINDER  │  src/clip_analyzer.py                                 │
│  │ (Conversation-   │  → outputs/*_clips.json                               │
│  │  based)          │  • PROBLEM: Timestamps were wrong                     │
│  │                  │  • PROBLEM: Content didn't match titles               │
│  └──────────────────┘                                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Step-by-Step Pipeline Details

### Step 1: Download Video
**Script:** `src/downloader.py`  
**Command:** `python main.py download "<youtube_url>" --output ./outputs`

**Input:** YouTube URL  
**Output:** `outputs/Israel vs Palestine Debate Episode 258.mp4` (783 MB, 4:52:00)

**What it does:**
- Uses yt-dlp to download best quality MP4
- Returns video metadata (title, duration, path)

---

### Step 2: Transcribe with Speaker Diarization
**Script:** `src/transcriber.py`  
**Command:** `python main.py transcribe-url "<youtube_url>" --output ./outputs`

**Input:** Video/audio file  
**Output:** `outputs/episode_258_transcript.json` (4.8 MB)

**What it does:**
- Extracts audio to WAV using FFmpeg
- Sends to Deepgram Nova-3 API
- Returns word-level timestamps + speaker IDs
- ~50,000 words, 18 speakers detected

**Output structure:**
```json
{
  "duration": 17514.6,
  "words": [
    {"text": "hello", "start": 0.5, "end": 0.8, "speaker": 0, "confidence": 0.99},
    ...
  ]
}
```

---

### Step 3: Find Clips (Quote-Based - V2)
**Script:** `src/quote_clip_finder.py`  
**Command:** `python run_quote_finder.py`

**Input:** `outputs/episode_258_transcript.json`  
**Output:** `outputs/quote_clips.json` (47 clips)

**What it does:**
1. Splits transcript into 10-minute overlapping windows
2. Sends each window to Gemini with prompt asking for "money quotes"
3. Gemini returns exact quotes that are viral-worthy
4. Script searches transcript for those exact quotes → gets precise timestamps
5. Expands clip boundaries: 40s before quote, 50s after
6. Deduplicates overlapping clips

**Why this works better:**
- Timestamps are verified by searching for actual quote text
- Content is guaranteed to match because we anchor on specific words

**What it does NOT do:**
- Does NOT use conversation segmentation
- Does NOT limit clips per guest
- Does NOT know which guest each clip is about

---

### Step 4: Extract Video Clips
**Script:** `src/extractor.py`  
**Command:** `python -c "...extract_clips..."`

**Input:** 
- Source video: `outputs/Israel vs Palestine Debate Episode 258.mp4`
- Clip list: `outputs/top10_clips_final.json`

**Output:** `outputs/clips_v2/*.mp4` (10 clips, 52.7 MB total)

**What it does:**
- Uses FFmpeg to cut precise segments
- Adds 2s padding before, 3s padding after
- Encodes with libx264/AAC for web compatibility

---

## Output Files Inventory

### Main Output Directory: `outputs/`

| File | Size | Description |
|------|------|-------------|
| `Israel vs Palestine Debate Episode 258.mp4` | 783 MB | Source video |
| `Israel vs Palestine Debate Episode 258.wav` | ~1.5 GB | Extracted audio |
| `episode_258_transcript.json` | 4.8 MB | Full transcript with word timestamps |
| `episode_258_voice_map.json` | ~500 KB | Speaker segments (Nick vs Guest) |
| `episode_258_visual_map.json` | ~2 MB | Frame-by-frame analysis |
| `episode_258_conversations.json` | ~15 KB | Conversation segments (HAS ISSUES) |
| `episode_258_clips.json` | ~50 KB | Old clip detection (BAD TIMESTAMPS) |
| `episode_258_clips_v2.json` | ~30 KB | Second attempt clips |
| `episode_258_clips_valid.json` | ~25 KB | Filtered valid clips |
| `quote_clips.json` | ~40 KB | **CURRENT BEST** - 47 verified clips |
| `smart_clips.json` | ~35 KB | Alternative clip finder results |
| `top10_clips_final.json` | ~5 KB | Top 10 clips selected for extraction |
| `episode_258_extraction_list.json` | ~8 KB | Old extraction list (bad) |

### Extracted Clips: `outputs/clips_v2/`

| File | Duration | Score |
|------|----------|-------|
| `quote_1_Nick_Calls_Quran_'Fake_Pagan_Slop'.mp4` | 110s | 10/10 |
| `quote_50_Guest_Fails_To_Read_Own_Source!.mp4` | 94s | 10/10 |
| `quote_3_Nick_Puts_Guest_on_the_Spot_About_Child_Marriage.mp4` | 100s | 9/10 |
| `quote_5_Nick's_Reaction_to_Guest_Defending_AdultChild_Marr.mp4` | 84s | 9/10 |
| `quote_15_Finding_Peace_in_Injustice.mp4` | 109s | 9/10 |
| `quote_20_Guest's_Extreme_Statement.mp4` | 91s | 9/10 |
| `quote_30_Anti-Semitic_Hot_Take!.mp4` | 85s | 9/10 |
| `quote_37_Epstein_Island_Background_Reveal.mp4` | 86s | 9/10 |
| `quote_39_The_Guest's_Bizarre_Explanation.mp4` | 88s | 9/10 |
| `quote_44_Questioning_International_Law.mp4` | 143s | 9/10 |

### Frame Extraction: `outputs/episode_258_frames/`
- 584 JPEG frames (extracted every 30 seconds)
- Used for visual mapping

### Old Clips (Bad): `outputs/clips/`
- 10 clips with wrong timestamps - DO NOT USE

---

## Known Issues

### Issue 1: Conversation Segmentation Only Starts at 2:42:00

**Problem:** The visual mapper only detects "new guests" when Omegle guests appear on screen around 2:42:00. The first 2+ hours show Nick + main co-host which the system sees as constant.

**Why it happens:** Visual segmentation looks for changes in the video frames. Nick and the main guest are present throughout, so no "new conversation" is detected until the format changes to Omegle.

**Impact:** We have no conversation data for the first 2:42:00 of the video.

---

### Issue 2: Same Person = Multiple "Conversations"

**Problem:** Gemini gives different descriptions for the same person across frames:
```
3:11:30 - 3:39:00  |  man with headscarf
3:13:00 - 3:34:00  |  man with headdress  
3:13:30 - 3:37:30  |  man in keffiyeh
3:14:00 - 3:24:00  |  man wearing a headdress
3:15:00 - 3:27:30  |  man with beard and keffiyeh
```

All of these are THE SAME PERSON but appear as 5 different "conversations."

**Why it happens:** Gemini describes what it sees in each frame independently. It doesn't track identity across frames or compare to previous descriptions.

**Impact:** 
- Conversation count is inflated (28 instead of maybe 8-10 actual guests)
- Can't accurately track "clips per guest"
- Timeline is confusing

---

### Issue 3: Quote Clips Don't Use Conversation Data

**Problem:** The current working clip finder (`quote_clip_finder.py`) analyzes the raw transcript and does NOT use the conversation segmentation at all.

**Impact:**
- Multiple clips may come from the same guest
- No way to ensure variety across different guests
- Clips aren't tagged with which guest they feature

---

### Issue 4: Old Clip Finder Had Wrong Timestamps

**Problem:** The original `clip_analyzer.py` had clips where the title/description didn't match the actual video content at those timestamps.

**Root cause:** Gemini returned timestamps that were either:
- Relative to conversation start (not absolute)
- Or just made up based on themes, not actual moments

**Solution implemented:** Quote-based finder that searches for exact text.

---

## Methods NOT Currently Used

### 1. Pyannote Voice Fingerprinting
**File:** Not implemented yet  
**What it would do:**
- Create voice "fingerprint" for each speaker
- Identify when the same voice appears again
- Could distinguish guests even when visual description changes

**Why we don't use it:**
- Requires additional setup (Pyannote library)
- Deepgram's speaker diarization gives basic speaker IDs
- Would need to correlate voice ID with visual appearance

**Potential benefit:** Could identify same guest across different visual descriptions by voice.

---

### 2. Image Similarity/Embedding Comparison
**File:** Not implemented  
**What it would do:**
- Compare face/person embeddings between frames
- Group frames showing the same person
- Track person identity across time

**Why we don't use it:**
- Would need face detection/embedding model
- Additional complexity

**Potential benefit:** Fix the "same person, different description" problem.

---

### 3. Conversation-Aware Clip Selection
**File:** Partially implemented in `clip_analyzer.py` but not working well  
**What it would do:**
- Limit clips per conversation/guest
- Ensure variety across different guests
- Tag clips with guest identity

**Why we don't use it:**
- Conversation segmentation data is unreliable
- Quote-based finder works better without it

---

## What Needs To Be Done

### Priority 1: Fix Conversation Segmentation

**Goal:** Accurately identify each unique guest and their start/end times.

**Approach options:**

1. **Face Embedding Comparison**
   - Extract face embedding from each frame
   - Cluster similar embeddings = same person
   - Libraries: face_recognition, DeepFace, or InsightFace
   
2. **Pyannote Voice Fingerprinting**
   - Create voice embedding for each speaker segment
   - Match voice across time
   - Would work even if guest is off-screen temporarily

3. **Hybrid Approach (Recommended)**
   - Use visual similarity for on-screen detection
   - Use voice matching as backup
   - Require BOTH visual and voice match to confirm same person
   - Start new conversation only when BOTH change

**Implementation steps:**
1. Add face embedding extraction to visual_mapper.py
2. Compare each frame's face embedding to previous frame
3. Only create new "conversation" if embedding distance exceeds threshold
4. Store face embedding as guest identifier (not text description)

---

### Priority 2: Use Conversations in Clip Selection

**Goal:** Ensure clip variety by limiting clips per guest.

**After fixing segmentation:**
1. Tag each clip with `guest_id` based on timestamp
2. Add `max_clips_per_guest` parameter to clip finder
3. When selecting top clips, ensure diversity across guests
4. Include guest info in clip metadata

---

### Priority 3: Detect Conversation Starts Earlier

**Goal:** Find guests before 2:42:00 if any exist.

**Approach:**
- The first ~2:42:00 appears to be Nick + main co-host only
- Need to verify this with visual inspection
- May not actually be a problem if no Omegle guests appear before that

---

## Technical Notes

### API Keys Required
```
DEEPGRAM_API_KEY=xxx  # For transcription
GEMINI_API_KEY=xxx    # For visual analysis + clip detection
```

### Key Dependencies
```
yt-dlp          # Video download
ffmpeg          # Audio/video processing
deepgram-sdk    # Transcription API
google-generativeai  # Gemini API
```

### Processing Times (for 4:52:00 video)
- Download: ~5 minutes
- Transcription: ~3.5 minutes
- Visual mapping (584 frames): ~28 minutes
- Quote clip finding: ~2.5 minutes
- Clip extraction (10 clips): ~1 minute

### Estimated Costs
- Deepgram: ~$1.26 (4.87 hours × $0.0043/min)
- Gemini (frames): ~$0.58 (584 frames)
- Gemini (clips): ~$1.00 (37 windows analyzed)
- **Total: ~$2.85 per video**

---

## File Structure

```
nick-matau-clipper/
├── src/
│   ├── downloader.py         # YouTube download
│   ├── ingester.py           # Audio extraction
│   ├── transcriber.py        # Deepgram transcription
│   ├── visual_mapper.py      # Frame analysis (Gemini Vision)
│   ├── voice_mapper.py       # Voice segment creation
│   ├── conversation_segmenter.py  # Merge visual+voice (NEEDS FIXING)
│   ├── clip_analyzer.py      # Old clip finder (DON'T USE)
│   ├── quote_clip_finder.py  # Current clip finder (WORKING)
│   ├── smart_clip_finder.py  # Alternative clip finder
│   └── extractor.py          # FFmpeg clip extraction
├── outputs/
│   ├── *.mp4                 # Source videos
│   ├── *_transcript.json     # Transcripts
│   ├── *_visual_map.json     # Frame analysis
│   ├── *_voice_map.json      # Speaker segments
│   ├── *_conversations.json  # Conversation data (UNRELIABLE)
│   ├── quote_clips.json      # Best clips data
│   ├── clips_v2/             # Extracted clip videos
│   └── episode_258_frames/   # Extracted frames
├── prompts/
│   ├── clip_detection.md     # Prompt for clip finding
│   └── frame_analysis.md     # Prompt for visual analysis
└── docs/
    ├── PIPELINE_SUMMARY.md   # This file
    ├── ARCHITECTURE.md       # System design
    └── TASKS.md              # Task checklist
```

---

## Quick Start for New Developer

### To process a new video:
```bash
# 1. Download and transcribe
python main.py transcribe-url "https://youtube.com/watch?v=xxx" --output ./outputs

# 2. Find clips (quote-based)
python run_quote_finder.py

# 3. Extract top clips
# (modify top10_clips_final.json or run extraction script)
```

### To improve conversation segmentation:
1. Start with `src/visual_mapper.py`
2. Add face embedding comparison
3. Update `src/conversation_segmenter.py` to use embeddings
4. Test on existing video before full pipeline run

---

## Summary

**What works:**
- Video download ✓
- Transcription with speaker ID ✓
- Quote-based clip finding ✓
- Clip extraction ✓

**What needs fixing:**
- Conversation segmentation (same person = multiple entries)
- Using conversations to ensure clip variety
- Detecting guests in first 2+ hours (if any exist)

**Main problem to solve:**
Gemini describes the same person differently across frames. Need face embedding or voice fingerprinting to track actual identity, not text descriptions.
