"""
Nick Matau AI Content Clipper - CLI Entry Point

Owner: Gabriel
Status: Implemented (YouTube -> Transcribe pipeline)

Usage:
    python main.py download "https://youtube.com/watch?v=..." --output ./data
    python main.py transcribe video.mp4 --output transcript.json
    python main.py transcribe-url "https://youtube.com/watch?v=..." --output ./outputs
    python main.py process video.mp4 --output ./clips
"""

import logging
import os
import sys
import time
from pathlib import Path

import click
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


def get_deepgram_api_key() -> str:
    """Get Deepgram API key from environment."""
    api_key = os.getenv('DEEPGRAM_API_KEY') or os.getenv('deepgram_api_key')
    if not api_key:
        raise click.ClickException(
            "DEEPGRAM_API_KEY not found in environment.\n"
            "Please add it to your .env file:\n"
            "  DEEPGRAM_API_KEY=your_key_here\n"
            "Get a key at: https://console.deepgram.com"
        )
    return api_key


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Nick Matau AI Content Clipper - Extract viral clips from livestreams."""
    pass


@cli.command()
@click.argument("url")
@click.option("--output", "-o", default="./data", help="Output directory")
def download(url: str, output: str):
    """
    Download a YouTube video.
    
    URL: YouTube video URL (e.g., https://youtube.com/watch?v=...)
    """
    from src.downloader import YouTubeDownloader
    
    click.echo(f"📥 Downloading: {url}")
    start_time = time.time()
    
    try:
        downloader = YouTubeDownloader(output_dir=output)
        result = downloader.download(url)
        
        elapsed = time.time() - start_time
        click.echo(f"✅ Download complete!")
        click.echo(f"   Title: {result.title}")
        click.echo(f"   Duration: {result.duration_seconds / 60:.1f} minutes")
        click.echo(f"   File: {result.video_path}")
        click.echo(f"   Time: {elapsed:.1f}s")
        
    except Exception as e:
        raise click.ClickException(f"Download failed: {e}")


@cli.command()
@click.argument("video_path", type=click.Path(exists=True))
@click.option("--output", "-o", default=None, help="Output JSON file (default: video_name_transcript.json)")
def transcribe(video_path: str, output: str):
    """
    Transcribe a video file to timestamped transcript.
    
    VIDEO_PATH: Path to MP4/MKV/MOV video file
    """
    from src.ingester import VideoIngester
    from src.transcriber import Transcriber
    
    api_key = get_deepgram_api_key()
    video_file = Path(video_path)
    
    # Determine output path
    if output is None:
        output = str(video_file.with_suffix('')) + "_transcript.json"
    
    click.echo(f"🎤 Transcribing: {video_file.name}")
    total_start = time.time()
    
    try:
        # Step 1: Ingest video and extract audio
        click.echo("\n📁 Step 1/2: Extracting audio...")
        step_start = time.time()
        
        ingester = VideoIngester(video_path)
        metadata = ingester.metadata
        click.echo(f"   Video: {metadata.duration_formatted}, {metadata.width}x{metadata.height}")
        
        audio_path = ingester.extract_audio()
        click.echo(f"   Audio extracted: {Path(audio_path).name}")
        click.echo(f"   Time: {time.time() - step_start:.1f}s")
        
        # Step 2: Transcribe with Deepgram
        click.echo("\n🎙️ Step 2/2: Transcribing with Deepgram...")
        step_start = time.time()
        
        transcriber = Transcriber(api_key)
        transcript = transcriber.transcribe_sync(audio_path)
        
        click.echo(f"   Words: {transcript.word_count}")
        click.echo(f"   Speakers: {len(transcript.speakers)}")
        click.echo(f"   Duration: {transcript.duration / 60:.1f} minutes")
        click.echo(f"   Time: {time.time() - step_start:.1f}s")
        
        # Save transcript
        transcript.save(output)
        
        total_elapsed = time.time() - total_start
        click.echo(f"\n✅ Transcription complete!")
        click.echo(f"   Output: {output}")
        click.echo(f"   Total time: {total_elapsed:.1f}s")
        
        # Estimate cost
        cost = (transcript.duration / 60) * 0.0043
        click.echo(f"   Estimated cost: ${cost:.2f}")
        
    except Exception as e:
        logger.exception("Transcription failed")
        raise click.ClickException(f"Transcription failed: {e}")


@cli.command("transcribe-url")
@click.argument("url")
@click.option("--output", "-o", default="./outputs", help="Output directory")
def transcribe_url(url: str, output: str):
    """
    Download and transcribe a YouTube video (full pipeline).
    
    URL: YouTube video URL
    """
    from src.downloader import YouTubeDownloader
    from src.ingester import VideoIngester
    from src.transcriber import Transcriber
    
    api_key = get_deepgram_api_key()
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    click.echo(f"🚀 Full pipeline: {url}")
    total_start = time.time()
    
    try:
        # Step 1: Download video
        click.echo("\n📥 Step 1/3: Downloading video...")
        step_start = time.time()
        
        downloader = YouTubeDownloader(output_dir=str(output_dir))
        download_result = downloader.download(url)
        
        click.echo(f"   Title: {download_result.title}")
        click.echo(f"   Duration: {download_result.duration_seconds / 60:.1f} minutes")
        click.echo(f"   Time: {time.time() - step_start:.1f}s")
        
        # Step 2: Extract audio
        click.echo("\n📁 Step 2/3: Extracting audio...")
        step_start = time.time()
        
        ingester = VideoIngester(download_result.video_path)
        metadata = ingester.metadata
        audio_path = ingester.extract_audio()
        
        click.echo(f"   Audio: {Path(audio_path).name}")
        click.echo(f"   Time: {time.time() - step_start:.1f}s")
        
        # Step 3: Transcribe
        click.echo("\n🎙️ Step 3/3: Transcribing with Deepgram...")
        step_start = time.time()
        
        transcriber = Transcriber(api_key)
        transcript = transcriber.transcribe_sync(audio_path)
        
        click.echo(f"   Words: {transcript.word_count}")
        click.echo(f"   Speakers: {len(transcript.speakers)}")
        click.echo(f"   Time: {time.time() - step_start:.1f}s")
        
        # Save transcript
        transcript_path = output_dir / f"{Path(download_result.video_path).stem}_transcript.json"
        transcript.save(str(transcript_path))
        
        total_elapsed = time.time() - total_start
        click.echo(f"\n✅ Pipeline complete!")
        click.echo(f"   Video: {download_result.video_path}")
        click.echo(f"   Transcript: {transcript_path}")
        click.echo(f"   Total time: {total_elapsed / 60:.1f} minutes")
        
        # Estimate cost
        cost = (transcript.duration / 60) * 0.0043
        click.echo(f"   Estimated cost: ${cost:.2f}")
        
    except Exception as e:
        logger.exception("Pipeline failed")
        raise click.ClickException(f"Pipeline failed: {e}")


@cli.command()
@click.argument("video_path", type=click.Path(exists=True))
@click.option("--output", "-o", default="./outputs", help="Output directory")
@click.option("--config", "-c", default="./config/config.yaml", help="Config file")
@click.option("--skip-sheets", is_flag=True, help="Skip Google Sheets upload")
@click.option("--quality", default="medium", type=click.Choice(["fast", "medium", "high"]))
def process(video_path: str, output: str, config: str, skip_sheets: bool, quality: str):
    """
    Process a video through the full pipeline (including AI analysis).
    
    Steps:
    1. Ingest video and extract audio
    2. Transcribe with Deepgram
    3. Analyze with Gemini for clips
    4. Refine timestamps
    5. Extract clips with FFmpeg
    6. (Optional) Upload to Google Sheets
    """
    click.echo(f"🎬 Processing: {video_path}")
    click.echo("⚠️ Full pipeline (with AI analysis) not yet implemented")
    click.echo("💡 Use 'transcribe' or 'transcribe-url' for transcription only")
    raise click.ClickException("Full process command requires analyzer implementation")


@cli.command()
@click.argument("transcript_path", type=click.Path(exists=True))
@click.option("--output", "-o", default="clips.json", help="Output JSON file")
def analyze(transcript_path: str, output: str):
    """Analyze a transcript for clip candidates (requires Gemini API)."""
    click.echo(f"🧠 Analyzing: {transcript_path}")
    click.echo("⚠️ Analysis not yet implemented - requires Gemini API setup")
    raise click.ClickException("Analyze command requires analyzer implementation")


@cli.command()
@click.argument("video_path", type=click.Path(exists=True))
@click.option("--clips", "-c", required=True, type=click.Path(exists=True), help="Clips JSON")
@click.option("--output", "-o", default="./outputs", help="Output directory")
@click.option("--quality", default="medium", type=click.Choice(["fast", "medium", "high"]))
def extract(video_path: str, clips: str, output: str, quality: str):
    """Extract clips from a video using clip definitions."""
    click.echo(f"✂️ Extracting clips from: {video_path}")
    click.echo("⚠️ Extraction not yet implemented - requires extractor implementation")
    raise click.ClickException("Extract command requires extractor implementation")


if __name__ == "__main__":
    cli()
