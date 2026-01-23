# System Architecture

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        NICK MATAU AI CLIPPER                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐      │
│  │ YOUTUBE  │───►│  VIDEO   │───►│  AUDIO   │───►│TRANSCRIPT│      │
│  │   URL    │    │ DOWNLOAD │    │EXTRACTION│    │  + AI    │      │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘      │
│       │               │               │               │              │
│       ▼               ▼               ▼               ▼              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐      │
│  │downloader│    │ ingester │    │transcriber│   │ analyzer │      │
│  │   .py    │    │   .py    │    │   .py    │    │   .py    │      │
│  │   ✅     │    │    ✅    │    │    ✅    │    │   🔴     │      │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘      │
│       │               │               │               │              │
│       ▼               ▼               ▼               ▼              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐      │
│  │  yt-dlp  │    │  FFmpeg  │    │ Deepgram │    │  Gemini  │      │
│  │          │    │          │    │ Nova-3   │    │ 2.5 Pro  │      │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘      │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                     CLIPS OUTPUT                              │   │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────┐               │   │
│  │  │ extractor│───►│  sheets  │───►│  OUTPUT  │               │   │
│  │  │   .py    │    │   .py    │    │  CLIPS   │               │   │
│  │  │   🔴     │    │   🔴     │    │   MP4    │               │   │
│  │  └──────────┘    └──────────┘    └──────────┘               │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                      ORCHESTRATOR (main.py) ✅               │    │
│  │    CLI Interface │ Progress Logging │ Error Handling         │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘

Legend: ✅ = Implemented, 🔴 = Not Started
```

---

## Module Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                           main.py (CLI) ✅                           │
│  Commands: download | transcribe | transcribe-url | process         │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
    ┌───────────────────────────┼───────────────────────────┐
    │                           │                           │
    ▼                           ▼                           ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│ downloader.py ✅│   │  ingester.py ✅ │   │transcriber.py ✅│
│                 │   │                 │   │                 │
│YouTubeDownloader│   │ VideoIngester   │   │  Transcriber    │
│DownloadResult   │   │ VideoMetadata   │   │  Word           │
│                 │   │                 │   │  TranscriptData │
│Input: YouTube   │   │ Input:  Video   │   │ Input:  WAV/MP3 │
│       URL       │   │ Output: WAV +   │   │ Output: Timestamped│
│Output: MP4      │   │         Metadata│   │         Transcript│
└────────┬────────┘   └────────┬────────┘   └────────┬────────┘
         │                     │                     │
         ▼                     ▼                     ▼
    ┌─────────┐          ┌─────────┐          ┌─────────┐
    │ yt-dlp  │          │ FFmpeg  │          │Deepgram │
    │         │          │ ffprobe │          │ Nova-3  │
    └─────────┘          └─────────┘          └─────────┘
                                                    │
                                                    ▼
                                          ┌─────────────────┐
                                          │   analyzer.py   │
                                          │                 │
                                          │  ClipAnalyzer   │
                                          │                 │
                                          │Input: Transcript│
                                          │Output: Clips[]  │
                                          └────────┬────────┘
         │                      │                      │
         │                      ▼                      │
         │            ┌─────────────────┐              │
         │            │timestamp_utils.py│             │
         │            │                 │              │
         │            │refine_clip_     │              │
         │            │  boundaries()   │              │
         │            │find_sentence_   │              │
         │            │  start/end()    │              │
         │            │verify_clip_text()│             │
         │            └────────┬────────┘              │
         │                     │                       │
         │                     ▼                       │
         │            ┌─────────────────┐              │
         │            │  extractor.py   │              │
         │            │                 │              │
         └───────────►│ ClipExtractor   │◄─────────────┘
                      │ ClipResult      │
                      │                 │
                      │ Input: Video +  │
                      │        Timestamps│
                      │ Output: MP4 clips│
                      └────────┬────────┘
                               │
                               ▼
                      ┌─────────────────┐
                      │    sheets.py    │
                      │                 │
                      │  ReviewQueue    │
                      │                 │
                      │ Input: Clips    │
                      │ Output: Sheet   │
                      └─────────────────┘
```

---

## Data Flow Detail

### Step 0: YouTube Download (NEW ✅)
```python
# Input
youtube_url: str = "https://www.youtube.com/watch?v=VIDEO_ID"

# Process
downloader = YouTubeDownloader(output_dir="./outputs")
result = downloader.download(youtube_url)

# Output
DownloadResult(
    video_path="outputs/Video Title.mp4",
    title="Video Title",
    duration_seconds=12854.38,
    channel="Channel Name",
    video_id="VIDEO_ID",
    thumbnail_url="https://...",
    description="Video description..."
)
```

### Step 1: Video Ingestion ✅
```python
# Input
video_path: str = "stream_2024_01_14.mp4"

# Process
ingester = VideoIngester(video_path)
audio_path = ingester.extract_audio()  # "stream_2024_01_14.wav"
metadata = ingester.metadata

# Output
VideoMetadata(
    duration_seconds=14423.5,
    duration_formatted="04:00:23",
    width=1920,
    height=1080,
    fps=30.0,
    codec="h264",
    bitrate=8000000,
    file_size_mb=3450.5
)
```

### Step 2: Transcription ✅
```python
# Input
audio_path: str = "outputs/Israel_Palestine_audio.mp3"  # 82MB MP3

# Process
transcriber = Transcriber()  # Uses DEEPGRAM_API_KEY from .env
transcript_data = transcriber.transcribe_sync(audio_path)

# Output (tested with 3.5-hour video)
TranscriptData(
    full_transcript="Tomorrow and got rid of the constitution...",
    timestamped_transcript="""
        [00:00:00] Speaker 0.0: Tomorrow and got rid of the constitution...
        [00:00:07] Speaker 1.0: I mean, I believe that...
        [00:00:10] Speaker 0.0: Right.
    """,
    words=[
        Word(text="Tomorrow", start=0.08, end=0.48, confidence=0.99, speaker=0),
        Word(text="and", start=0.48, end=0.56, confidence=0.99, speaker=0),
        # ... 32,234 total words
    ],
    word_count=32234,
    duration=12854.38,  # 3.57 hours
    speakers={
        0: {"word_count": 15234, "talk_time": 5400.5},
        1: {"word_count": 8234, "talk_time": 3200.2},
        # ... 16 speakers total
    }
)

# Save to JSON
transcript_data.save("outputs/Israel_vs_Palestine_transcript.json")
```

### Step 3: AI Analysis
```python
# Input
timestamped_transcript: str  # From transcriber

# Process
analyzer = ClipAnalyzer(api_key)
clips = analyzer.analyze_for_clips(timestamped_transcript)

# Output
[
    {
        "clip_id": 1,
        "start_time": "00:15:32",
        "end_time": "00:16:18",
        "start_text": "Bro that's actually insane",
        "end_text": "think about that for a second",
        "hook": "Bro that's actually insane, I can't believe he said that",
        "title": "He Actually Said That On Stream",
        "description": "Nick reacts to controversial statement",
        "virality_score": 8,
        "category": "reaction",
        "platforms": ["TikTok", "YouTube Shorts"],
        "reasoning": "Strong emotional hook, surprise element"
    },
    ...
]
```

### Step 4: Timestamp Refinement
```python
# Input
clips: List[dict]  # From analyzer
words: List[Word]  # From transcriber

# Process
refined_clips = refine_all_clips(clips, words)

# Output (same structure, refined timestamps)
[
    {
        "clip_id": 1,
        "start_time": "00:15:32",      # Original
        "end_time": "00:16:18",        # Original
        "refined_start": "00:15:31.7", # Adjusted to sentence boundary
        "refined_end": "00:16:18.5",   # Adjusted to sentence boundary
        ...
    }
]
```

### Step 5: Clip Extraction
```python
# Input
video_path: str
refined_clips: List[dict]

# Process
extractor = ClipExtractor(video_path, output_dir)
results = extractor.extract_all_clips(refined_clips, quality="medium")

# Output
[
    ClipResult(
        clip_id="1",
        file_path="outputs/clip_1.mp4",
        start_time="00:15:32",
        end_time="00:16:18",
        duration_seconds=46.0,
        file_size_mb=12.5,
        status="success"
    ),
    ...
]
```

### Step 6: Review Queue
```python
# Input
clips: List[dict]  # With file paths
video_name: str

# Process
queue = ReviewQueue(spreadsheet_id, credentials_path)
queue.add_clips_for_review(clips, video_name)

# Output: Google Sheet row for each clip
# Columns: ID | Video | Start | End | Duration | Title | Hook | Category | Score | Platforms | Reasoning | Status | Notes | File
```

---

## File Structure

```
nick-matau-clipper/
├── .cursor/
│   └── rules/
│       └── python.mdc          # Python-specific cursor rules
├── .claude/
│   └── commands/
│       ├── implement-task.md   # Command to implement a task
│       └── review-code.md      # Command to review code
├── docs/
│   ├── PRD.md                  # Product requirements
│   ├── ARCHITECTURE.md         # This file
│   ├── TASKS.md                # Implementation tasks
│   └── STATUS.md               # Progress status (updated by AI)
├── src/
│   ├── __init__.py
│   ├── downloader.py           # ✅ YouTube download with yt-dlp
│   ├── ingester.py             # ✅ Video input + audio extraction (FFmpeg)
│   ├── transcriber.py          # ✅ Deepgram Nova-3 integration
│   ├── analyzer.py             # 🔴 Gemini clip detection
│   ├── extractor.py            # 🔴 FFmpeg clip cutting
│   ├── sheets.py               # 🔴 Google Sheets integration
│   └── timestamp_utils.py      # 🔴 Timestamp refinement
├── prompts/
│   ├── base_prompt.md          # Master clip detection prompt
│   └── nick_preferences.md     # Nick's evolving style guide
├── config/
│   ├── config.yaml.example     # Config template
│   └── credentials.json        # (gitignored) OAuth credentials
├── data/
│   ├── approved_clips.json     # Learning: approved patterns
│   └── rejected_clips.json     # Learning: rejected patterns
├── outputs/                    # (gitignored) Extracted clips
├── tests/
│   ├── test_ingester.py
│   ├── test_transcriber.py
│   ├── test_analyzer.py
│   ├── test_extractor.py
│   └── test_timestamp_utils.py
├── scripts/
│   └── test_apis.py            # API connectivity tests
├── CLAUDE.md                   # AI assistant instructions
├── main.py                     # CLI entry point
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## Technology Decisions

### Why Deepgram Nova-3?
- Best-in-class accuracy for speech recognition
- Word-level timestamps (critical for our use case)
- Speaker diarization included
- Fast processing (~5 min for 4-hour video)
- Reasonable cost ($0.0043/min)

### Why Gemini 2.5 Pro?
- 1M token context window (fits entire 4-hour transcript)
- Strong instruction following for JSON output
- Native multimodal capability (future: video analysis)
- Cost effective (~$0.40 per video)

### Why FFmpeg?
- Industry standard for video processing
- Keyframe-accurate seeking
- Supports all common formats
- Free and open source

### Why Google Sheets?
- Nick already uses it
- Real-time collaboration
- Easy approval workflow
- Free API

---

## Error Handling Strategy

### Graceful Degradation
1. Save intermediate results at each step
2. Allow resuming from last successful step
3. Log errors with context for debugging

### Validation Points
1. **After Transcription**: Verify word_count > 0
2. **After Analysis**: Verify all timestamps exist in transcript
3. **After Refinement**: Verify clips don't overlap
4. **After Extraction**: Verify file exists and has audio

### Retry Logic
- API calls: 3 retries with exponential backoff
- FFmpeg: No retry (deterministic)
