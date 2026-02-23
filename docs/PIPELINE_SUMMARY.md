# Nick Matau Clipper - Pipeline Summary

**Last Updated:** February 8, 2026
**Status:** V2 working with issues → V3 partially implemented (enhanced transcript pipeline complete)

---

## CURRENT STATE: V3 Pipeline (Partially Implemented)

### What's Working End-to-End

The following pipeline runs from start to finish:

```
YouTube URL
    │
    ▼
[1] Download (yt-dlp)
    → video.mp4
    │
    ▼
[2] Extract audio (FFmpeg, via ingester.py)
    → audio.wav
    │
    ▼
[3] Transcribe (Deepgram Nova-3)
    → transcript.json (word-level timestamps, 18 generic speaker IDs)
    │
    ▼
[4] Create voiceprint (Pyannote API, one-time)
    → nick_voiceprint.json (base64 encoded voiceprint)
    │
    ▼
[5] Enhance transcript (Pyannote identify + Deepgram merge + utterance collapse)
    ├── Trim audio to time window (optional, saves cost)
    ├── Upload to Pyannote → speaker identification with Nick's voiceprint
    ├── Merge Pyannote speaker labels with Deepgram word-level data
    └── Collapse words into speaker utterances
    → transcript_v3.json  (structured utterances for LLM analysis)
    → transcript_v3.txt   (readable: [HH:MM:SS] Speaker: text)
    → transcript_v3_raw_words.json (word-level backup)
    │
    ▼
[6] Find clips ← NEXT STEP: Update to use enhanced transcript
    → clips.json
    │
    ▼
[7] Extract clips (FFmpeg)
    → clips/*.mp4
```

### CLI Commands for Each Step

```powershell
# Setup
$env:PATH = "C:\ffmpeg\bin;$env:PATH"

# Step 1-3: Download and transcribe
python main.py transcribe-url "<youtube_url>" --output ./outputs

# Step 4: Create voiceprint (one-time per speaker)
python main.py create-voiceprint nick_sample.wav -o nick_voiceprint.json

# Step 5: Enhance transcript with speaker identity
python main.py enhance-transcript audio.wav \
    -t transcript.json \
    -v nick_voiceprint.json \
    -s 10314 \
    -o outputs/episode_258_transcript_v3.json

# Step 6: Find clips (V2 quote-based, needs updating for V3)
# Currently: python run_quote_finder.py (uses raw Deepgram transcript)
# TODO: Update to use enhanced utterance transcript
```

---

## V2 PIPELINE (Legacy - Still Available)

### V2 Problems That V3 Solves
1. **Same person = multiple descriptions** - Gemini describes each frame independently
2. **No panel vs guest distinction** - Can't tell regular panelists from actual guests
3. **No speaker names** - Deepgram gives numeric IDs (speaker 0, 1, 2...) not names
4. **No cross-validation** - Visual, voice, transcript data not combined
5. **Conversation data unreliable** - 28 "guests" instead of ~8-10

### V3 Solutions Already Implemented
- **Speaker Identity**: Pyannote voiceprint matches Nick by voice → `nick` label
- **Named Speakers**: 16 unique speakers detected, Nick's 13,240 words properly tagged
- **Utterance Transcript**: 50,507 words collapsed into 2,347 readable speaker turns
- **Cost-Efficient**: Audio trimming lets you process just the relevant portion

### V3 Solutions Still Needed
- **Guest Classification**: Multi-agent debate to classify speakers (nick vs panel vs guest)
- **Conversation Mapping**: Map which guest is talking when
- **Contextual Clip Finding**: 5-stage LLM clip detection using the enhanced transcript

---

## Quote-Based Clip Finding (V2 - Still the Best Working Clip Finder)

**Script:** `src/quote_clip_finder.py`

1. Splits transcript into 10-minute overlapping windows
2. Sends each window to Gemini asking for "money quotes"
3. Gemini returns exact memorable lines
4. Script searches full transcript for those exact quotes → precise timestamps
5. Expands clip boundaries: 40s before quote, 50s after
6. Deduplicates overlapping clips

**Results on Episode 258:** 47 clips found, 10 extracted to `clips_v2/`

**Limitations:**
- Uses raw Deepgram transcript (no speaker names)
- Doesn't know which guest each clip features
- No variety enforcement (multiple clips from same guest possible)
- Fixed expansion (40s/50s) doesn't adapt to conversation flow

---

## Enhanced Transcript Pipeline (V3 - NEW)

### How It Works

1. **Audio Trim** (optional): FFmpeg cuts audio to a time window (e.g., last 2 hours)
   - Saves Pyannote cost (~$0.10/min of audio)
   - Episode 258: full = $29, last 2h = $12

2. **Pyannote Upload**: Local file → `POST /v1/media/input` → presigned PUT URL → `media://` URL

3. **Pyannote Identify**: `POST /v1/identify` with:
   - `url`: the uploaded media URL
   - `model`: "precision-2"
   - `voiceprints`: `[{label: "nick", voiceprint: "<base64>"}]`
   - `matching`: `{threshold: 50, exclusive: true}`
   - Returns async job → poll `/v1/jobs/{id}` every 10s

4. **Merge with Deepgram**: For each of the 50,507 Deepgram words:
   - Find the Pyannote identification segment with maximum time overlap
   - Replace numeric speaker ID with Pyannote label (e.g., `nick`, `SPEAKER_04`)
   - Apply time offset if audio was trimmed

5. **Collapse to Utterances**: Group consecutive same-speaker words:
   - Split on speaker change or >2s pause between words
   - Result: 2,347 utterances from 50,507 words (21x reduction)

### Output Formats

**Structured JSON** (`transcript_v3.json`) - For LLM consumption:
```json
{"utterances": [
    {"speaker": "nick", "start": 10314.0, "end": 10314.7, "text": "What version is it?"},
    {"speaker": "SPEAKER_10", "start": 10316.2, "end": 10316.8, "text": "New American Standard."}
]}
```

**Readable Text** (`transcript_v3.txt`) - For human review and LLM context:
```
[2:51:53] nick: What version is it?
[2:51:56] SPEAKER_10: New American Standard.
```

**Raw Words** (`transcript_v3_raw_words.json`) - For precise timestamp lookups when cutting clips.

### Results on Episode 258 (Last 2 Hours)
- **Nick identified** as SPEAKER_03 → `nick` (13,240 words, 545 turns)
- **16 unique Pyannote speakers** detected
- **21,388 words** matched to Pyannote labels
- **29,119 words** in first ~2h52m remain as `deepgram_X` (not sent to Pyannote)
- Processing time: ~3 minutes (upload + Pyannote job + merge + collapse)

---

## Output Files Inventory

### Main Output Directory: `outputs/`

| File | Size | Description | Status |
|------|------|-------------|--------|
| `Israel vs Palestine Debate Episode 258.mp4` | 783 MB | Source video | ✅ |
| `Israel vs Palestine Debate Episode 258.wav` | 535 MB | Source audio | ✅ |
| `episode_258_transcript.json` | 4.8 MB | Deepgram transcript (50K words) | ✅ |
| `episode_258_transcript_v3.json` | ~200 KB | Structured utterances (2,347 turns) | ✅ NEW |
| `episode_258_transcript_v3.txt` | ~150 KB | Readable transcript w/ speakers | ✅ NEW |
| `episode_258_transcript_v3_raw_words.json` | 9.2 MB | Word-level w/ speaker_name | ✅ NEW |
| `quote_clips.json` | ~40 KB | V2 clips (47 found) | ✅ |
| `clips_v2/` | 52.7 MB | 10 extracted V2 clips | ✅ |
| `clips_manual/` | varies | Manually cut clips | ✅ |
| `episode_258_frames/` | varies | 584 frames (every 30s) | ✅ |
| `episode_258_visual_map.json` | ~2 MB | Frame analysis | ⚠️ Unreliable |
| `episode_258_conversations.json` | ~15 KB | V2 conversations | ⚠️ Unreliable |

### Root Directory

| File | Description |
|------|-------------|
| `nick_voiceprint.json` | Nick's Pyannote voiceprint (base64) |

---

## What Needs To Be Done

### Priority 1: Update Clip Finding for V3

Use the enhanced utterance transcript (`episode_258_transcript_v3.json`) instead of raw Deepgram data:
- Clips can now reference speakers by name
- LLM gets structured `[HH:MM:SS] Speaker: text` format
- Utterance start/end timestamps provide exact cut points

### Priority 2: Guest Classification (Phase 3)

Build `guest_classifier.py` using multi-agent debate:
- Input: Pyannote speaker labels + visual events + transcript cues
- Output: people_registry.json (nick, panel members, guests with arrival/departure)
- Method: Advocate argues FOR guest, Skeptic argues AGAINST, Judge decides

### Priority 3: Conversation Mapping (Phase 4)

Build `conversation_mapper.py` with hierarchical summarization:
- For each identified guest: extract their conversation transcript
- Chunk into 3-minute segments → summarize → meta-summarize
- Extract and verify discussion topics

### Priority 4: Contextual Clip Finder (Phase 5)

Build `contextual_clip_finder.py` with 5-stage pipeline:
1. 5-criteria scoring (hook, conflict, resolution, shareability, standalone)
2. Adversarial self-critique
3. Multi-persona evaluation
4. 8-step verification chain
5. Ensemble ranking (Borda count)

---

## Technical Notes

### API Keys Required
```
DEEPGRAM_API_KEY=xxx    # Transcription
GEMINI_API_KEY=xxx      # Visual analysis + V2 clips
PYANNOTE_API_KEY=xxx    # Voice identification
ANTHROPIC_API_KEY=xxx   # Claude text analysis
```

### Key Dependencies
```
yt-dlp              # Video download
ffmpeg              # Audio/video processing
deepgram-sdk        # Transcription API
google-generativeai # Gemini API
anthropic           # Claude API
aiohttp             # Async HTTP (Pyannote)
python-dotenv       # Environment variables
click               # CLI framework
```

### Processing Times (Episode 258, 4:52:00)
- Download: ~5 minutes
- Transcription: ~3.5 minutes
- Voiceprint creation: ~30 seconds
- Enhanced transcript (last 2h): ~3 minutes
- Quote clip finding (V2): ~2.5 minutes
- Clip extraction (10 clips): ~1 minute

### Pyannote API Notes
- Files must be uploaded via `POST /v1/media/input` → presigned PUT URL
- Cannot send local file data directly (must be a URL)
- Voiceprint creation: max 30 seconds of audio
- Diarization/identification: up to 24 hours, 1 GiB
- Cannot combine identification with transcription in one call
- Use `exclusive: true` for non-overlapping speaker segments
- Long jobs need fresh HTTP connections per poll (avoid session disconnect)
