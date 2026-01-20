# Nick Matau AI Content Clipper

AI-powered content clipping system that automatically identifies viral-worthy moments from livestreams.

## Features

- 🎤 **Transcription**: Deepgram Nova-3 with word-level timestamps
- 🧠 **AI Analysis**: Gemini 2.5 Pro identifies clip-worthy moments
- ✂️ **Precise Extraction**: FFmpeg keyframe-accurate cutting
- 📊 **Review Queue**: Google Sheets integration for approval workflow

## Quick Start

```bash
# Clone the repo
git clone https://github.com/seqora/nick-matau-clipper.git
cd nick-matau-clipper

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Copy environment variables
cp .env.example .env
# Edit .env with your API keys

# Run the pipeline
python main.py process video.mp4 --output ./clips
```

## Project Structure

```
nick-matau-clipper/
├── src/
│   ├── ingester.py      # Video input + audio extraction
│   ├── transcriber.py   # Deepgram Nova-3 integration
│   ├── analyzer.py      # Gemini 2.5 Pro clip detection
│   ├── extractor.py     # FFmpeg precise clip cutting
│   ├── sheets.py        # Google Sheets review queue
│   └── timestamp_utils.py
├── prompts/
│   ├── base_prompt.md   # Master clip detection prompt
│   └── nick_preferences.md
├── docs/
│   ├── PRD.md           # Product requirements
│   ├── ARCHITECTURE.md  # System design
│   └── TASKS.md         # Implementation tasks
├── main.py              # CLI entry point
└── CLAUDE.md            # AI assistant instructions
```

## CLI Commands

```bash
# Full pipeline
python main.py process video.mp4 --output ./clips

# Just transcribe
python main.py transcribe video.mp4 --output transcript.json

# Just analyze (from existing transcript)
python main.py analyze transcript.json --output clips.json

# Just extract clips
python main.py extract video.mp4 --clips clips.json --output ./clips
```

## Configuration

Create a `config/config.yaml`:

```yaml
deepgram:
  model: nova-3

gemini:
  model: gemini-2.5-pro
  temperature: 0.3

extraction:
  quality: medium  # fast, medium, high
  padding_start: 0.3
  padding_end: 0.5
```

## Development

```bash
# Run tests
pytest tests/ -v

# Type check
mypy src/

# Format code
black src/ tests/

# Lint
ruff check src/ tests/
```

## Team

- **Gabriel** (AI Engineer): Transcription, AI analysis, prompts, orchestration
- **Jake** (Integration Engineer): FFmpeg modules, Google Sheets

## Cost

| Video Length | Deepgram | Gemini | Total |
|--------------|----------|--------|-------|
| 2 hours | $0.52 | $0.25 | $0.77 |
| 4 hours | $1.03 | $0.40 | $1.43 |

## License

Proprietary - Seqora AI
