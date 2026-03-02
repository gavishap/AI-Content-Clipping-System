"""
Nick Matau AI Content Clipper - CLI Entry Point

Owner: Gabriel
Status: Implemented (Full V3 pipeline)

Usage:
    # ONE-COMMAND full pipeline (recommended)
    python main.py pipeline-v3 "https://youtube.com/watch?v=..." --max-clips 10
    python main.py pipeline-v3 "https://youtube.com/watch?v=..." -n 5 -o my_folder

    # Individual commands
    python main.py download "https://youtube.com/watch?v=..." --output ./data
    python main.py transcribe video.mp4 --output transcript.json
    python main.py transcribe-url "https://youtube.com/watch?v=..." --output ./outputs
    python main.py create-voiceprint nick_sample.wav --output nick_voiceprint.json
    python main.py enhance-transcript stream.wav -t transcript.json -v nick_voiceprint.json
    python main.py find-clips-v3 enhanced_transcript.json -o outputs/clips_v3
"""

import asyncio
import json
import logging
import os
import re
import shutil
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


def get_gemini_api_key() -> str:
    """Get Gemini API key from environment."""
    api_key = os.getenv('GEMINI_API_KEY') or os.getenv('gemini_api_key')
    if not api_key:
        raise click.ClickException(
            "GEMINI_API_KEY not found in environment.\n"
            "Please add it to your .env file:\n"
            "  GEMINI_API_KEY=your_key_here\n"
            "Get a key at: https://aistudio.google.com/apikey"
        )
    return api_key


def get_pyannote_api_key() -> str:
    """Get Pyannote API key from environment."""
    api_key = os.getenv('PYANNOTE_API_KEY') or os.getenv('pyannote_api_key')
    if not api_key:
        raise click.ClickException(
            "PYANNOTE_API_KEY not found in environment.\n"
            "Please add it to your .env file:\n"
            "  PYANNOTE_API_KEY=your_key_here\n"
            "Get a key at: https://dashboard.pyannote.ai"
        )
    return api_key


@click.group()
@click.version_option(version="0.3.0")
def cli():
    """Nick Matau AI Content Clipper - Extract viral clips from livestreams."""
    pass


# =============================================================================
# EXISTING COMMANDS (Download, Transcribe)
# =============================================================================

@cli.command()
@click.argument("url")
@click.option("--output", "-o", default="./data", help="Output directory")
def download(url: str, output: str):
    """
    Download a YouTube video.
    
    URL: YouTube video URL (e.g., https://youtube.com/watch?v=...)
    """
    from src.downloader import YouTubeDownloader
    
    click.echo(f"Downloading: {url}")
    start_time = time.time()
    
    try:
        downloader = YouTubeDownloader(output_dir=output)
        result = downloader.download(url)
        
        elapsed = time.time() - start_time
        click.echo(f"Download complete!")
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
    
    click.echo(f"Transcribing: {video_file.name}")
    total_start = time.time()
    
    try:
        # Step 1: Ingest video and extract audio
        click.echo("\nStep 1/2: Extracting audio...")
        step_start = time.time()
        
        ingester = VideoIngester(video_path)
        metadata = ingester.metadata
        click.echo(f"   Video: {metadata.duration_formatted}, {metadata.width}x{metadata.height}")
        
        audio_path = ingester.extract_audio()
        click.echo(f"   Audio extracted: {Path(audio_path).name}")
        click.echo(f"   Time: {time.time() - step_start:.1f}s")
        
        # Step 2: Transcribe with Deepgram
        click.echo("\nStep 2/2: Transcribing with Deepgram...")
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
        click.echo(f"\nTranscription complete!")
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
    
    click.echo(f"Full pipeline: {url}")
    total_start = time.time()
    
    try:
        # Step 1: Download video
        click.echo("\nStep 1/3: Downloading video...")
        step_start = time.time()
        
        downloader = YouTubeDownloader(output_dir=str(output_dir))
        download_result = downloader.download(url)
        
        click.echo(f"   Title: {download_result.title}")
        click.echo(f"   Duration: {download_result.duration_seconds / 60:.1f} minutes")
        click.echo(f"   Time: {time.time() - step_start:.1f}s")
        
        # Step 2: Extract audio
        click.echo("\nStep 2/3: Extracting audio...")
        step_start = time.time()
        
        ingester = VideoIngester(download_result.video_path)
        metadata = ingester.metadata
        audio_path = ingester.extract_audio()
        
        click.echo(f"   Audio: {Path(audio_path).name}")
        click.echo(f"   Time: {time.time() - step_start:.1f}s")
        
        # Step 3: Transcribe
        click.echo("\nStep 3/3: Transcribing with Deepgram...")
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
        click.echo(f"\nPipeline complete!")
        click.echo(f"   Video: {download_result.video_path}")
        click.echo(f"   Transcript: {transcript_path}")
        click.echo(f"   Total time: {total_elapsed / 60:.1f} minutes")
        
        # Estimate cost
        cost = (transcript.duration / 60) * 0.0043
        click.echo(f"   Estimated cost: ${cost:.2f}")
        
    except Exception as e:
        logger.exception("Pipeline failed")
        raise click.ClickException(f"Pipeline failed: {e}")


# =============================================================================
# NEW PIPELINE COMMANDS (Speaker Mapping, Visual Mapping, etc.)
# =============================================================================

@cli.command("create-voiceprint")
@click.argument("sample_path", type=click.Path(exists=True))
@click.option("--output", "-o", default="nick_voiceprint.json", help="Output JSON file")
@click.option("--name", "-n", default="nick", help="Speaker name (default: nick)")
def create_voiceprint(sample_path: str, output: str, name: str):
    """
    Create a voiceprint from a clean audio sample using Pyannote API.
    
    SAMPLE_PATH: Path to 30-60 second audio of the speaker (no overlapping voices)
    
    For best results:
    - Use clear audio with minimal background noise
    - Only one person speaking
    - 30-60 seconds is ideal
    - WAV or MP3 format
    
    Example:
        python main.py create-voiceprint nick_sample.wav -o nick_voiceprint.json
    """
    from src.voice_fingerprinter import VoiceFingerprinter
    
    click.echo(f"Creating voiceprint for '{name}' from: {sample_path}")
    click.echo("   Using Pyannote API for voice fingerprinting...")
    start_time = time.time()
    
    try:
        fingerprinter = VoiceFingerprinter()
        voiceprint = fingerprinter.create_voiceprint_sync(sample_path, name)
        
        # Save voiceprint to file
        voiceprint.save(output)
        
        elapsed = time.time() - start_time
        click.echo(f"\nVoiceprint created successfully!")
        click.echo(f"   Speaker: {voiceprint.speaker_name}")
        click.echo(f"   ID: {voiceprint.voiceprint_id}")
        click.echo(f"   Saved to: {output}")
        click.echo(f"   Time: {elapsed:.1f}s")
        click.echo(f"\nUse this voiceprint to identify {name} in videos:")
        click.echo(f"   python main.py analyze-voices audio.wav --voiceprint {output}")
        
    except Exception as e:
        logger.exception("Voiceprint creation failed")
        raise click.ClickException(f"Failed: {e}")


@cli.command("map-speakers")
@click.argument("audio_path", type=click.Path(exists=True))
@click.option("--voiceprint", "-v", required=True, type=click.Path(exists=True), 
              help="Path to voiceprint JSON file")
@click.option("--output", "-o", default="voice_map.json", help="Output JSON file")
def map_speakers(audio_path: str, voiceprint: str, output: str):
    """
    Map speakers (Nick vs guests) throughout the audio.
    
    AUDIO_PATH: Path to audio file (WAV/MP3)
    """
    from src.speaker_mapper import SpeakerMapper
    
    click.echo(f"Mapping speakers in: {audio_path}")
    start_time = time.time()
    
    try:
        # Load voiceprint ID
        with open(voiceprint, 'r') as f:
            vp_data = json.load(f)
        voiceprint_id = vp_data['voiceprint_id']
        
        mapper = SpeakerMapper()
        voice_map = mapper.map_speakers_sync(audio_path, voiceprint_id)
        voice_map.save(output)
        
        elapsed = time.time() - start_time
        click.echo(f"Speaker mapping complete!")
        click.echo(f"   Segments: {len(voice_map.segments)}")
        click.echo(f"   Nick talk time: {voice_map.nick_talk_time / 60:.1f} minutes")
        click.echo(f"   Guest talk time: {voice_map.guest_talk_time / 60:.1f} minutes")
        click.echo(f"   Saved to: {output}")
        click.echo(f"   Time: {elapsed:.1f}s")
        
    except Exception as e:
        logger.exception("Speaker mapping failed")
        raise click.ClickException(f"Failed: {e}")


@cli.command("analyze-voices")
@click.argument("audio_path", type=click.Path(exists=True))
@click.option("--voiceprint", "-v", default=None, type=click.Path(exists=True),
              help="Path to Nick's voiceprint JSON file (optional but recommended)")
@click.option("--visual-events", "-e", default=None, type=click.Path(exists=True),
              help="Path to visual events JSON for cross-validation (optional)")
@click.option("--transcript-cues", "-c", default=None, type=click.Path(exists=True),
              help="Path to transcript cues JSON for cross-validation (optional)")
@click.option("--output", "-o", default="voice_analysis.json", help="Output JSON file")
def analyze_voices(
    audio_path: str, 
    voiceprint: str, 
    visual_events: str,
    transcript_cues: str,
    output: str
):
    """
    Analyze audio to detect all speakers using Pyannote API (V3).
    
    AUDIO_PATH: Path to audio file (WAV/MP3) - supports files up to 24 hours!
    
    This command uses the Pyannote API to:
    - Detect all unique speakers (diarization)
    - Identify Nick using his voiceprint (if provided)
    - Track when new speakers first appear
    - Cross-validate with visual events and transcript cues
    
    Examples:
        # Basic diarization (no Nick identification)
        python main.py analyze-voices stream.wav
        
        # With Nick identification
        python main.py analyze-voices stream.wav -v nick_voiceprint.json
        
        # Full cross-modal validation
        python main.py analyze-voices stream.wav \\
            -v nick_voiceprint.json \\
            -e visual_events.json \\
            -c transcript_cues.json
    """
    from src.voice_fingerprinter import (
        VoiceFingerprinter, Voiceprint, get_guest_arrivals, format_timestamp
    )
    
    click.echo(f"Analyzing voices in: {audio_path}")
    click.echo("   Using Pyannote API for speaker diarization...")
    
    # Check file size
    file_size_mb = Path(audio_path).stat().st_size / (1024 * 1024)
    click.echo(f"   File size: {file_size_mb:.1f} MB")
    
    if file_size_mb > 500:
        click.echo("   Note: Large file - diarization may take 10-30 minutes...")
    
    start_time = time.time()
    
    try:
        fingerprinter = VoiceFingerprinter()
        
        # Load voiceprint if provided
        nick_voiceprint_id = None
        if voiceprint:
            vp = Voiceprint.load(voiceprint)
            nick_voiceprint_id = vp.voiceprint_id
            click.echo(f"   Nick voiceprint: {nick_voiceprint_id[:20]}...")
        
        # Load visual events if provided
        visual_data = None
        if visual_events:
            with open(visual_events, 'r', encoding='utf-8') as f:
                visual_data = json.load(f)
            if isinstance(visual_data, dict):
                visual_data = visual_data.get('events', [])
            click.echo(f"   Visual events: {len(visual_data)} events")
        
        # Load transcript cues if provided
        cue_data = None
        if transcript_cues:
            with open(transcript_cues, 'r', encoding='utf-8') as f:
                cue_data = json.load(f)
            if isinstance(cue_data, dict):
                cue_data = cue_data.get('cues', [])
            click.echo(f"   Transcript cues: {len(cue_data)} cues")
        
        # Run analysis
        click.echo("\n   Running diarization (this may take a while)...")
        result = fingerprinter.analyze_audio_sync(
            audio_path,
            nick_voiceprint_id=nick_voiceprint_id,
            visual_events=visual_data,
            transcript_cues=cue_data,
        )
        
        # Save results
        result.save(output)
        
        elapsed = time.time() - start_time
        
        # Summary
        click.echo(f"\nVoice analysis complete!")
        click.echo(f"   Total duration: {result.total_duration / 60:.1f} minutes")
        click.echo(f"   Speakers detected: {len(result.speakers)}")
        click.echo(f"   New speaker events: {len(result.new_speaker_events)}")
        
        if result.nick_speaker_label:
            nick_info = result.speakers.get(result.nick_speaker_label)
            if nick_info:
                click.echo(f"   Nick identified: {result.nick_speaker_label}")
                click.echo(f"   Nick talk time: {nick_info.total_duration / 60:.1f} minutes")
        
        if result.validated_changes:
            click.echo(f"   Cross-validated changes: {len(result.validated_changes)}")
            guests = get_guest_arrivals(result, min_confidence=0.6)
            if guests:
                click.echo(f"\n   Likely guest arrivals:")
                for g in guests[:10]:  # Show top 10
                    click.echo(
                        f"      {format_timestamp(g.timestamp)}: "
                        f"{g.speaker_label} ({g.validation_type}, conf={g.final_confidence:.2f})"
                    )
        
        click.echo(f"\n   Saved to: {output}")
        click.echo(f"   Time: {elapsed / 60:.1f} minutes")
        
    except Exception as e:
        logger.exception("Voice analysis failed")
        raise click.ClickException(f"Failed: {e}")


@cli.command("enhance-transcript")
@click.argument("audio_path", type=click.Path(exists=True))
@click.option("--transcript", "-t", required=True, type=click.Path(exists=True),
              help="Path to existing Deepgram transcript JSON")
@click.option("--voiceprint", "-v", required=True, type=click.Path(exists=True),
              help="Path to Nick's voiceprint JSON file")
@click.option("--start-time", "-s", default=0.0, type=float,
              help="Start offset in seconds (to trim audio for cost savings)")
@click.option("--duration", "-d", default=None, type=float,
              help="Duration in seconds to process (default: to end of file)")
@click.option("--output", "-o", default="enhanced_transcript.json",
              help="Output JSON file for enhanced transcript")
@click.option("--match-threshold", default=50, type=int,
              help="Pyannote voiceprint match confidence threshold 0-100 (default: 50)")
def enhance_transcript(
    audio_path: str,
    transcript: str,
    voiceprint: str,
    start_time: float,
    duration: float,
    output: str,
    match_threshold: int,
):
    """
    Re-analyze audio with Pyannote identification and merge with Deepgram transcript.

    Uses Nick's voiceprint to identify his voice via Pyannote, then merges
    the speaker labels back into the existing Deepgram word-level transcript.
    The result is a transcript where Nick's words are tagged "nick" and other
    speakers get Pyannote labels (SPEAKER_01, SPEAKER_02, etc.).

    AUDIO_PATH: Path to WAV/MP3 audio file

    Examples:
        # Full stream
        python main.py enhance-transcript stream.wav -t transcript.json -v nick_voiceprint.json

        # Last 2 hours only (saves cost)
        python main.py enhance-transcript stream.wav -t transcript.json -v nick_voiceprint.json -s 10714
    """
    from src.voice_fingerprinter import (
        VoiceFingerprinter, Voiceprint,
        trim_audio, merge_pyannote_speakers_with_transcript,
        collapse_words_to_utterances, build_readable_transcript,
        build_structured_transcript,
    )

    click.echo(f"Enhancing transcript with Pyannote speaker identification")
    click.echo(f"   Audio: {audio_path}")
    click.echo(f"   Transcript: {transcript}")
    click.echo(f"   Voiceprint: {voiceprint}")
    total_start = time.time()

    try:
        # Load voiceprint
        vp = Voiceprint.load(voiceprint)
        click.echo(f"   Nick voiceprint loaded: {vp.voiceprint_id[:30]}...")

        # Load transcript
        with open(transcript, 'r', encoding='utf-8') as f:
            transcript_data = json.load(f)
        total_words = len(transcript_data.get('words', []))
        click.echo(f"   Transcript loaded: {total_words} words")

        # Trim audio if start_time specified
        actual_audio = audio_path
        temp_trimmed = None
        if start_time > 0 or duration is not None:
            trim_output = str(Path(audio_path).parent / "trimmed_for_pyannote.wav")
            click.echo(f"\n   Trimming audio: start={start_time}s, duration={duration}s")
            trim_audio(audio_path, trim_output, start_time, duration)
            actual_audio = trim_output
            temp_trimmed = trim_output

            file_size_mb = Path(trim_output).stat().st_size / (1024 * 1024)
            click.echo(f"   Trimmed file: {file_size_mb:.1f} MB")

        # Run Pyannote identification
        click.echo(f"\n   Running Pyannote speaker identification...")
        click.echo(f"   Match threshold: {match_threshold}%")
        click.echo(f"   This may take 10-30 minutes for long audio...")

        fingerprinter = VoiceFingerprinter()
        segments, speaker_mapping, job_id = fingerprinter.identify_speakers_sync(
            actual_audio,
            {"nick": vp.voiceprint_id},
            match_threshold=match_threshold,
        )

        click.echo(f"   Pyannote job complete: {job_id}")
        click.echo(f"   Segments: {len(segments)}")
        click.echo(f"   Speaker mapping: {speaker_mapping}")

        # Count unique speakers
        unique_speakers = set(seg.speaker_label for seg in segments)
        click.echo(f"   Unique speakers detected: {len(unique_speakers)}")

        # Merge with Deepgram transcript
        click.echo(f"\n   Merging Pyannote speakers with Deepgram words...")
        enhanced = merge_pyannote_speakers_with_transcript(
            segments, speaker_mapping, transcript_data,
            time_offset=start_time,
        )

        # Collapse words into speaker utterances
        click.echo(f"\n   Collapsing words into speaker utterances...")
        utterances = collapse_words_to_utterances(enhanced, max_pause=2.0)
        click.echo(f"   {len(utterances)} utterances created from {len(enhanced.get('words', []))} words")

        # Build outputs
        output_base = Path(output).stem
        output_dir = Path(output).parent

        # 1. Structured JSON (utterances - for LLM analysis)
        structured_path = output_dir / f"{output_base}.json"
        merge_meta = enhanced.get('merge_metadata', {})
        structured = build_structured_transcript(utterances, metadata=merge_meta)
        with open(structured_path, 'w', encoding='utf-8') as f:
            json.dump(structured, f, indent=2, ensure_ascii=False)

        # 2. Readable text transcript (for human review + LLM context)
        txt_path = output_dir / f"{output_base}.txt"
        readable = build_readable_transcript(utterances)
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(readable)

        # 3. Raw word-level JSON (keep for precise timestamp lookups)
        raw_path = output_dir / f"{output_base}_raw_words.json"
        with open(raw_path, 'w', encoding='utf-8') as f:
            json.dump(enhanced, f, indent=2, ensure_ascii=False)

        # Summary
        speakers_named = structured.get('summary', {}).get('speakers', {})
        elapsed = time.time() - total_start

        click.echo(f"\nTranscript enhancement complete!")
        click.echo(f"   Structured JSON (for LLM): {structured_path}")
        click.echo(f"   Readable text:             {txt_path}")
        click.echo(f"   Raw word-level:            {raw_path}")
        click.echo(f"   Utterances: {len(utterances)}")
        click.echo(f"   Words matched to Pyannote: {merge_meta.get('words_matched', 0)}")
        click.echo(f"   Words unmatched (fallback): {merge_meta.get('words_unmatched', 0)}")
        click.echo(f"   Speakers:")
        for name, stats in sorted(speakers_named.items(), key=lambda x: -x[1]['total_words']):
            click.echo(f"      {name}: {stats['total_words']} words, {stats['total_utterances']} turns")
        click.echo(f"   Total time: {elapsed / 60:.1f} minutes")

        # Clean up trimmed file
        if temp_trimmed and os.path.exists(temp_trimmed):
            os.unlink(temp_trimmed)
            click.echo(f"   Cleaned up trimmed audio")

    except Exception as e:
        logger.exception("Transcript enhancement failed")
        raise click.ClickException(f"Failed: {e}")


@cli.command("map-visual")
@click.argument("video_path", type=click.Path(exists=True))
@click.option("--interval", "-i", default=30, help="Seconds between frames (default: 30)")
@click.option("--output", "-o", default="visual_map.json", help="Output JSON file")
@click.option("--frames-dir", "-f", default=None, help="Directory for extracted frames")
@click.option("--nick-description", "-n", default=None, help="Description of Nick to help identify him")
def map_visual(video_path: str, interval: int, output: str, frames_dir: str, nick_description: str):
    """
    Extract frames and analyze who is on screen.
    
    VIDEO_PATH: Path to video file (MP4/MKV/MOV)
    """
    from src.visual_mapper import VisualMapper
    
    click.echo(f"Analyzing video frames: {video_path}")
    click.echo(f"   Interval: every {interval} seconds")
    start_time = time.time()
    
    try:
        mapper = VisualMapper()
        
        # Step 1: Extract frames
        click.echo("\nStep 1/2: Extracting frames...")
        step_start = time.time()
        frame_paths = mapper.extract_frames(video_path, frames_dir, interval)
        click.echo(f"   Extracted {len(frame_paths)} frames")
        click.echo(f"   Time: {time.time() - step_start:.1f}s")
        
        # Step 2: Analyze frames
        click.echo("\nStep 2/2: Analyzing frames with Gemini...")
        step_start = time.time()
        visual_map = mapper.analyze_frames_sync(frame_paths, interval, nick_description)
        visual_map.save(output)
        click.echo(f"   Time: {time.time() - step_start:.1f}s")
        
        elapsed = time.time() - start_time
        click.echo(f"\nVisual mapping complete!")
        click.echo(f"   Frames analyzed: {visual_map.total_frames}")
        click.echo(f"   Duration covered: {visual_map.total_duration / 60:.1f} minutes")
        click.echo(f"   Saved to: {output}")
        click.echo(f"   Total time: {elapsed:.1f}s")
        
        # Estimate cost
        cost = len(frame_paths) * 0.001
        click.echo(f"   Estimated cost: ${cost:.2f}")
        
    except Exception as e:
        logger.exception("Visual mapping failed")
        raise click.ClickException(f"Failed: {e}")


@cli.command("segment")
@click.option("--voice", "-v", required=True, type=click.Path(exists=True),
              help="Voice map JSON file")
@click.option("--visual", "-s", required=True, type=click.Path(exists=True),
              help="Visual map JSON file")
@click.option("--output", "-o", default="conversations.json", help="Output JSON file")
@click.option("--min-duration", "-d", default=60, help="Minimum conversation duration (seconds)")
def segment(voice: str, visual: str, output: str, min_duration: int):
    """
    Segment conversations from voice + visual data.
    """
    from src.speaker_mapper import VoiceMap
    from src.visual_mapper import VisualMap
    from src.conversation_segmenter import ConversationSegmenter
    
    click.echo("Segmenting conversations...")
    start_time = time.time()
    
    try:
        # Load data
        voice_map = VoiceMap.load(voice)
        visual_map = VisualMap.load(visual)
        
        click.echo(f"   Voice segments: {len(voice_map.segments)}")
        click.echo(f"   Visual frames: {len(visual_map.frames)}")
        
        # Segment
        segmenter = ConversationSegmenter(min_duration=min_duration)
        conversation_map = segmenter.segment_conversations(voice_map, visual_map)
        conversation_map.save(output)
        
        elapsed = time.time() - start_time
        click.echo(f"\nConversation segmentation complete!")
        click.echo(f"   Conversations found: {conversation_map.total_conversations}")
        click.echo(f"   Guests identified: {len(conversation_map.guests)}")
        click.echo(f"   Saved to: {output}")
        click.echo(f"   Time: {elapsed:.1f}s")
        
        # List conversations
        if conversation_map.conversations:
            click.echo("\nConversations:")
            for conv in conversation_map.conversations:
                click.echo(
                    f"   {conv.conversation_id}: {conv.guest_description[:30]}... "
                    f"({conv.duration / 60:.1f} min)"
                )
        
    except Exception as e:
        logger.exception("Segmentation failed")
        raise click.ClickException(f"Failed: {e}")


@cli.command("find-clips")
@click.option("--conversations", "-c", required=True, type=click.Path(exists=True),
              help="Conversations JSON file")
@click.option("--transcript", "-t", required=True, type=click.Path(exists=True),
              help="Transcript JSON file")
@click.option("--voice", "-v", required=True, type=click.Path(exists=True),
              help="Voice map JSON file")
@click.option("--output", "-o", default="clips.json", help="Output JSON file")
@click.option("--min-virality", "-m", default=5, help="Minimum virality score (1-10)")
def find_clips(conversations: str, transcript: str, voice: str, output: str, min_virality: int):
    """
    Find clip-worthy moments within conversations.
    """
    from src.speaker_mapper import VoiceMap
    from src.conversation_segmenter import ConversationMap
    from src.clip_analyzer import ClipAnalyzer
    
    click.echo("Analyzing conversations for clips...")
    start_time = time.time()
    
    try:
        # Load data
        conversation_map = ConversationMap.load(conversations)
        voice_map = VoiceMap.load(voice)
        
        with open(transcript, 'r', encoding='utf-8') as f:
            transcript_data = json.load(f)
        
        click.echo(f"   Conversations: {conversation_map.total_conversations}")
        click.echo(f"   Minimum virality: {min_virality}")
        
        # Analyze
        analyzer = ClipAnalyzer()
        result = analyzer.analyze_all_conversations_sync(
            conversation_map, transcript_data, voice_map, min_virality
        )
        result.save(output)
        
        elapsed = time.time() - start_time
        click.echo(f"\nClip analysis complete!")
        click.echo(f"   Clips found: {result.total_clips}")
        click.echo(f"   Average virality: {result.average_virality:.1f}")
        click.echo(f"   Saved to: {output}")
        click.echo(f"   Time: {elapsed:.1f}s")
        
        # List top clips
        top_clips = result.get_top_clips(5)
        if top_clips:
            click.echo("\nTop clips:")
            for clip in top_clips:
                click.echo(
                    f"   {clip.clip_id}: {clip.suggested_title[:40]}... "
                    f"(score: {clip.virality_score}, {clip.duration:.0f}s)"
                )
        
    except Exception as e:
        logger.exception("Clip analysis failed")
        raise click.ClickException(f"Failed: {e}")


@cli.command("pipeline")
@click.argument("video_path", type=click.Path(exists=True))
@click.option("--nick-sample", "-n", required=True, type=click.Path(exists=True),
              help="30-second audio sample of Nick speaking")
@click.option("--output", "-o", default="./outputs", help="Output directory")
@click.option("--frame-interval", "-f", default=30, help="Seconds between frames (default: 30)")
@click.option("--min-virality", "-m", default=5, help="Minimum virality score (1-10)")
@click.option("--skip-transcribe", is_flag=True, help="Skip transcription (use existing)")
@click.option("--transcript", "-t", default=None, help="Path to existing transcript JSON")
def pipeline(
    video_path: str, 
    nick_sample: str, 
    output: str, 
    frame_interval: int,
    min_virality: int,
    skip_transcribe: bool,
    transcript: str
):
    """
    Run the full clip detection pipeline.
    
    VIDEO_PATH: Path to video file
    
    Steps:
    1. Create Nick voiceprint (if not exists)
    2. Transcribe video (if not skipping)
    3. Map speakers (Nick vs guests)
    4. Map visual (who's on screen)
    5. Segment conversations
    6. Find clips
    """
    from src.ingester import VideoIngester
    from src.transcriber import Transcriber
    from src.speaker_mapper import SpeakerMapper
    from src.visual_mapper import VisualMapper
    from src.conversation_segmenter import ConversationSegmenter
    from src.clip_analyzer import ClipAnalyzer
    
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    video_file = Path(video_path)
    base_name = video_file.stem
    
    click.echo(f"Running full pipeline on: {video_file.name}")
    click.echo(f"Output directory: {output_dir}")
    total_start = time.time()
    
    try:
        # Step 1: Create voiceprint
        click.echo("\n" + "="*50)
        click.echo("STEP 1/6: Creating Nick voiceprint")
        click.echo("="*50)
        step_start = time.time()
        
        voiceprint_path = output_dir / "nick_voiceprint.json"
        if voiceprint_path.exists():
            click.echo("   Using existing voiceprint")
            with open(voiceprint_path, 'r') as f:
                voiceprint_id = json.load(f)['voiceprint_id']
        else:
            mapper = SpeakerMapper()
            voiceprint_id = mapper.create_nick_voiceprint_sync(nick_sample)
            with open(voiceprint_path, 'w') as f:
                json.dump({'voiceprint_id': voiceprint_id}, f, indent=2)
        
        click.echo(f"   Voiceprint ID: {voiceprint_id[:20]}...")
        click.echo(f"   Time: {time.time() - step_start:.1f}s")
        
        # Step 2: Transcribe
        click.echo("\n" + "="*50)
        click.echo("STEP 2/6: Transcribing video")
        click.echo("="*50)
        step_start = time.time()
        
        transcript_path = output_dir / f"{base_name}_transcript.json"
        
        if skip_transcribe and transcript:
            transcript_path = Path(transcript)
            click.echo(f"   Using existing transcript: {transcript_path}")
        elif transcript_path.exists():
            click.echo(f"   Using existing transcript: {transcript_path}")
        else:
            ingester = VideoIngester(video_path)
            audio_path = ingester.extract_audio()
            click.echo(f"   Audio extracted: {Path(audio_path).name}")
            
            transcriber = Transcriber()
            transcript_data = transcriber.transcribe_sync(audio_path)
            transcript_data.save(str(transcript_path))
            click.echo(f"   Words: {transcript_data.word_count}")
        
        click.echo(f"   Time: {time.time() - step_start:.1f}s")
        
        # Load transcript
        with open(transcript_path, 'r', encoding='utf-8') as f:
            transcript_data = json.load(f)
        
        # Get audio path for speaker mapping
        audio_path = output_dir / f"{base_name}.wav"
        if not audio_path.exists():
            # Extract audio if not exists
            ingester = VideoIngester(video_path)
            audio_path = ingester.extract_audio()
        
        # Step 3: Map speakers
        click.echo("\n" + "="*50)
        click.echo("STEP 3/6: Mapping speakers (Nick vs guests)")
        click.echo("="*50)
        step_start = time.time()
        
        voice_map_path = output_dir / f"{base_name}_voice_map.json"
        
        if voice_map_path.exists():
            click.echo("   Using existing voice map")
            from src.speaker_mapper import VoiceMap
            voice_map = VoiceMap.load(str(voice_map_path))
        else:
            mapper = SpeakerMapper()
            voice_map = mapper.map_speakers_sync(str(audio_path), voiceprint_id)
            voice_map.save(str(voice_map_path))
        
        click.echo(f"   Segments: {len(voice_map.segments)}")
        click.echo(f"   Nick: {voice_map.nick_talk_time / 60:.1f} min")
        click.echo(f"   Guest: {voice_map.guest_talk_time / 60:.1f} min")
        click.echo(f"   Time: {time.time() - step_start:.1f}s")
        
        # Step 4: Map visual
        click.echo("\n" + "="*50)
        click.echo("STEP 4/6: Mapping visual (who's on screen)")
        click.echo("="*50)
        step_start = time.time()
        
        visual_map_path = output_dir / f"{base_name}_visual_map.json"
        
        if visual_map_path.exists():
            click.echo("   Using existing visual map")
            from src.visual_mapper import VisualMap
            visual_map = VisualMap.load(str(visual_map_path))
        else:
            visual_mapper = VisualMapper()
            frames_dir = output_dir / f"{base_name}_frames"
            frame_paths = visual_mapper.extract_frames(video_path, str(frames_dir), frame_interval)
            click.echo(f"   Extracted {len(frame_paths)} frames")
            
            visual_map = visual_mapper.analyze_frames_sync(frame_paths, frame_interval)
            visual_map.save(str(visual_map_path))
        
        click.echo(f"   Frames: {visual_map.total_frames}")
        click.echo(f"   Time: {time.time() - step_start:.1f}s")
        
        # Step 5: Segment conversations
        click.echo("\n" + "="*50)
        click.echo("STEP 5/6: Segmenting conversations")
        click.echo("="*50)
        step_start = time.time()
        
        conversations_path = output_dir / f"{base_name}_conversations.json"
        
        if conversations_path.exists():
            click.echo("   Using existing conversations")
            from src.conversation_segmenter import ConversationMap
            conversation_map = ConversationMap.load(str(conversations_path))
        else:
            segmenter = ConversationSegmenter()
            conversation_map = segmenter.segment_conversations(voice_map, visual_map)
            conversation_map.save(str(conversations_path))
        
        click.echo(f"   Conversations: {conversation_map.total_conversations}")
        click.echo(f"   Guests: {len(conversation_map.guests)}")
        click.echo(f"   Time: {time.time() - step_start:.1f}s")
        
        # Step 6: Find clips
        click.echo("\n" + "="*50)
        click.echo("STEP 6/6: Finding clips")
        click.echo("="*50)
        step_start = time.time()
        
        clips_path = output_dir / f"{base_name}_clips.json"
        
        analyzer = ClipAnalyzer()
        clip_result = analyzer.analyze_all_conversations_sync(
            conversation_map, transcript_data, voice_map, min_virality
        )
        clip_result.save(str(clips_path))
        
        click.echo(f"   Clips found: {clip_result.total_clips}")
        click.echo(f"   Avg virality: {clip_result.average_virality:.1f}")
        click.echo(f"   Time: {time.time() - step_start:.1f}s")
        
        # Summary
        total_elapsed = time.time() - total_start
        click.echo("\n" + "="*50)
        click.echo("PIPELINE COMPLETE!")
        click.echo("="*50)
        click.echo(f"   Total time: {total_elapsed / 60:.1f} minutes")
        click.echo(f"\nOutputs:")
        click.echo(f"   Transcript: {transcript_path}")
        click.echo(f"   Voice map: {voice_map_path}")
        click.echo(f"   Visual map: {visual_map_path}")
        click.echo(f"   Conversations: {conversations_path}")
        click.echo(f"   Clips: {clips_path}")
        
        # Top clips
        top_clips = clip_result.get_top_clips(5)
        if top_clips:
            click.echo(f"\nTop {len(top_clips)} clips:")
            for clip in top_clips:
                duration_str = f"{clip.duration:.0f}s"
                click.echo(
                    f"   [{clip.virality_score}/10] {clip.suggested_title[:45]}... ({duration_str})"
                )
        
    except Exception as e:
        logger.exception("Pipeline failed")
        raise click.ClickException(f"Pipeline failed: {e}")


# =============================================================================
# V3 CLIP FINDER
# =============================================================================

@cli.command('find-clips-v3')
@click.argument('transcript_path', type=click.Path(exists=True))
@click.option('-o', '--output', default='outputs/clips_v3', help='Output directory')
@click.option('--max-clips', default=20, help='Maximum clips to return')
@click.option('--min-score', default=45.0, help='Minimum composite score (0-100)')
@click.option('--profile', default=None, help='Path to nick_clip_profile.json')
@click.option('-Q', '--query', default=None, help='Search query to focus clip detection on a specific topic')
def find_clips_v3(transcript_path: str, output: str, max_clips: int, min_score: float, profile: str, query: str):
    """
    Find clip-worthy moments using V3 data-driven pipeline.
    
    Uses the Nick Clip Profile (extracted from 15 real clips) with a 5-pass pipeline:
    detect -> score -> filter -> reflect -> debate -> rank
    
    Optional --query flag focuses detection on a specific topic or instruction.
    
    \b
    Examples:
        python main.py find-clips-v3 transcript_v3.json -o outputs/clips_v3
        python main.py find-clips-v3 transcript_v3.json -Q "child marriage"
    """
    from src.clip_finder_v3 import find_clips_sync
    
    query_intent = None
    if query:
        from src.story_clip_finder import StoryClipFinder, QueryIntent
        from src.conversation_segmenter_v3 import segment_conversations
        import asyncio
        click.echo(f"Interpreting query: \"{query}\"")
        conv_map = segment_conversations(transcript_path)
        async def _interpret():
            finder = StoryClipFinder()
            return await finder.interpret_query(query, conv_map)
        query_intent = asyncio.run(_interpret())
        click.echo(f"  -> type={query_intent.query_type}, topic={query_intent.topic}")
    
    click.echo("=" * 60)
    click.echo("CLIP FINDER V3 — Data-Driven 5-Pass Pipeline")
    click.echo("=" * 60)
    click.echo(f"Transcript: {transcript_path}")
    click.echo(f"Output dir: {output}")
    click.echo(f"Max clips:  {max_clips}")
    click.echo(f"Min score:  {min_score}")
    if query:
        click.echo(f"Query:      {query}")
    click.echo()
    
    start_time = time.time()
    
    try:
        clips = find_clips_sync(
            transcript_path=transcript_path,
            output_dir=output,
            max_clips=max_clips,
            min_score=min_score,
            profile_path=profile,
            query_intent=query_intent,
        )
        
        elapsed = time.time() - start_time
        click.echo()
        click.echo("=" * 60)
        click.echo(f"COMPLETE — {len(clips)} clips found in {elapsed:.1f}s")
        click.echo("=" * 60)
        click.echo()
        
        for i, clip in enumerate(clips):
            time_str = f"{int(clip.start_time // 3600)}:{int((clip.start_time % 3600) // 60):02d}:{int(clip.start_time % 60):02d}"
            click.echo(
                f"  #{i+1} [{clip.composite_score:.0f}/100] {clip.clip_type} @ {time_str} "
                f"({clip.duration:.0f}s) — {clip.hook[:50]}..."
            )
        
        click.echo(f"\nResults: {output}/clips_v3_results.json")
        click.echo(f"Report:  {output}/clips_v3_report.md")
        
    except Exception as e:
        logger.exception("V3 Clip Finder failed")
        raise click.ClickException(f"V3 Clip Finder failed: {e}")


# =============================================================================
# TOPIC MAPPER (Standalone)
# =============================================================================

@cli.command('map-topics')
@click.argument('transcript_path', type=click.Path(exists=True))
@click.option('-o', '--output', default='outputs/topic_map.json', help='Output JSON path')
def map_topics(transcript_path: str, output: str):
    """
    Create a granular topic map of every conversation in a stream.

    Segments each conversation into named topic blocks (~15-60s each)
    using Claude. Output is designed for timeline visualization.

    \b
    Example:
        python main.py map-topics outputs/episode_258_transcript_v3.json
    """
    from src.conversation_segmenter_v3 import segment_conversations
    from src.topic_mapper import TopicMapper, save_topic_map
    import asyncio

    click.echo("=" * 60)
    click.echo("TOPIC MAPPER — LLM-Enhanced Topic Segmentation")
    click.echo("=" * 60)
    click.echo(f"Transcript: {transcript_path}")
    click.echo(f"Output:     {output}")
    click.echo()

    start_time = time.time()

    try:
        click.echo("Step 1: Segmenting conversations...")
        conv_map = segment_conversations(transcript_path)
        click.echo(f"  Found {conv_map.total_conversations} conversations")

        click.echo("\nStep 2: Mapping topics (Claude LLM)...")

        async def _run():
            mapper = TopicMapper()
            return await mapper.map_topics(transcript_path, conv_map)

        topic_map = asyncio.run(_run())
        save_topic_map(topic_map, output)

        elapsed = time.time() - start_time
        click.echo()
        click.echo("=" * 60)
        click.echo(f"COMPLETE — {topic_map.total_topics} topic blocks in {elapsed:.1f}s")
        click.echo("=" * 60)
        click.echo(f"  Unique topics: {len(topic_map.all_topic_ids)}")
        click.echo(f"  Output: {output}")

    except Exception as e:
        logger.exception("Topic Mapper failed")
        raise click.ClickException(f"Topic Mapper failed: {e}")


# =============================================================================
# UNIFIED CLIP FINDER (Scout + Editor)
# =============================================================================

@cli.command('find-clips-unified')
@click.argument('transcript_path', type=click.Path(exists=True))
@click.option('-o', '--output', default='outputs/clips_unified', help='Output directory')
@click.option('--max-clips', default=15, help='Maximum clips to return')
@click.option('-Q', '--query', default=None, help='Free-form search query')
@click.option('--video', default=None, type=click.Path(exists=True),
              help='Source video to extract clips from')
@click.option('--quality', default='medium', type=click.Choice(['fast', 'medium', 'high']))
@click.option('--skip-topics', is_flag=True, help='Skip LLM topic mapping (faster, cheaper)')
def find_clips_unified(transcript_path: str, output: str, max_clips: int,
                       query: str, video: str, quality: str, skip_topics: bool):
    """
    Find clips using the unified Scout + Editor two-pass system.

    Finds both continuous clips and composite (stitched) clips in one pipeline.
    The AI decides the best assembly strategy for each candidate.

    Optionally maps topics first for richer analysis (disable with --skip-topics).

    \b
    Examples:
        python main.py find-clips-unified transcript_v3.json
        python main.py find-clips-unified transcript_v3.json -Q "child marriage"
        python main.py find-clips-unified transcript_v3.json --video stream.mp4
    """
    from src.conversation_segmenter_v3 import segment_conversations, save_conversation_map
    from src.topic_mapper import TopicMapper, save_topic_map
    from src.clip_finder_unified import ClipFinderUnified
    from src.extractor import ClipExtractor
    import asyncio

    click.echo("=" * 60)
    click.echo("UNIFIED CLIP FINDER — Scout + Editor Pipeline")
    click.echo("=" * 60)
    click.echo(f"Transcript:  {transcript_path}")
    click.echo(f"Output dir:  {output}")
    click.echo(f"Max clips:   {max_clips}")
    if query:
        click.echo(f"Query:       {query}")
    if video:
        click.echo(f"Video:       {video}")
    click.echo(f"Topic map:   {'skip' if skip_topics else 'enabled'}")
    click.echo()

    start_time = time.time()
    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Step 1: Segment conversations
        click.echo("Step 1: Segmenting conversations...")
        conv_map = segment_conversations(transcript_path)
        save_conversation_map(conv_map, str(out_dir / "conversation_map.json"))
        click.echo(f"  Found {conv_map.total_conversations} conversations")

        # Step 2: Topic mapping (optional) — includes continuity index
        topic_map = None
        if not skip_topics:
            click.echo("\nStep 2: Mapping topics (Claude LLM, batched)...")
            async def _map():
                mapper = TopicMapper()
                return await mapper.map_topics(transcript_path, conv_map)
            topic_map = asyncio.run(_map())
            save_topic_map(topic_map, str(out_dir / "topic_map.json"))
            click.echo(f"  Mapped {topic_map.total_topics} topic blocks")
            if topic_map.continuity_index:
                recurring_count = sum(
                    len(v) for v in topic_map.continuity_index.recurring.values()
                )
                click.echo(f"  Recurring topics (composite candidates): {recurring_count}")
        else:
            click.echo("\nStep 2: Topic mapping skipped")

        # Step 3: Find clips (Scout + Editor)
        click.echo("\nStep 3: Finding clips (Scout + Editor)...")
        async def _find():
            finder = ClipFinderUnified()
            intent = None
            if query:
                from src.story_clip_finder import StoryClipFinder
                sf = StoryClipFinder(client=finder.client)
                intent = await sf.interpret_query(query, conv_map)
                click.echo(f"  Query interpreted: type={intent.query_type}, topic={intent.topic}")
            clips = await finder.find_clips(
                transcript_path, conv_map, topic_map, intent, max_clips,
            )
            finder.save_results(clips, output, intent, topic_map)
            return clips, intent

        clips, intent = asyncio.run(_find())

        # Step 4: Extract clips if video provided
        extracted = 0
        if video and clips:
            click.echo(f"\nStep 4: Extracting video clips...")
            clips_out = out_dir / "clips"
            clips_out.mkdir(exist_ok=True)

            async def _extract():
                nonlocal extracted
                extractor = ClipExtractor(video, str(clips_out))
                for clip in clips:
                    if clip.assembly == "composite" and len(clip.segments) > 1:
                        segs = [{"start_time": s.start_time, "end_time": s.end_time}
                                for s in clip.segments]
                        result = await extractor.extract_composite_clip(
                            segments=segs,
                            clip_id=clip.clip_id,
                            title=clip.title,
                            quality=quality,
                        )
                    else:
                        result = await extractor.extract_clip(
                            {
                                "clip_id": clip.clip_id,
                                "start_time": clip.start_time,
                                "end_time": clip.end_time,
                                "title": clip.title,
                            },
                            quality=quality,
                        )
                    if result.status == "success":
                        extracted += 1
                        click.echo(f"  {clip.clip_id}: {result.file_path} ({result.file_size_mb:.1f}MB)")

            asyncio.run(_extract())
            click.echo(f"  Extracted: {extracted}/{len(clips)}")

        elapsed = time.time() - start_time
        continuous = sum(1 for c in clips if c.assembly == "continuous")
        composite = sum(1 for c in clips if c.assembly == "composite")

        click.echo()
        click.echo("=" * 60)
        click.echo(f"COMPLETE — {len(clips)} clips in {elapsed:.1f}s")
        click.echo("=" * 60)
        click.echo(f"  Continuous: {continuous}")
        click.echo(f"  Composite:  {composite}")
        if video:
            click.echo(f"  Extracted:  {extracted}")
        click.echo()

        for i, clip in enumerate(clips, 1):
            st = clip.start_time
            ts = "{}:{:02d}:{:02d}".format(
                int(st // 3600), int((st % 3600) // 60), int(st % 60)
            )
            tag = "C" if clip.assembly == "composite" else " "
            refs_tag = f" [{len(clip.topic_references)} refs]" if clip.topic_references else ""
            click.echo(
                f"  #{i} [{clip.score:.1f}/10] {clip.clip_type} [{tag}] @ {ts} "
                f"({clip.total_duration:.0f}s){refs_tag} -- {clip.hook[:50]}"
            )
            if clip.composite_opportunities:
                click.echo(f"      ^ composite opportunity available")

        click.echo(f"\nResults: {output}/unified_clips_results.json")
        click.echo(f"Report:  {output}/unified_clips_report.md")
        if video and extracted:
            click.echo(f"Clips:   {output}/clips/")

    except Exception as e:
        logger.exception("Unified Clip Finder failed")
        raise click.ClickException(f"Unified Clip Finder failed: {e}")


# =============================================================================
# STORY CLIP FINDER (Composite Clips) [Legacy -- kept for backward compat]
# =============================================================================

@cli.command('find-story-clips')
@click.argument('transcript_path', type=click.Path(exists=True))
@click.option('-o', '--output', default='outputs/stories', help='Output directory')
@click.option('--max-stories', default=10, help='Maximum story clips to return')
@click.option('-Q', '--query', default=None, help='Free-form search query')
@click.option('--video', default=None, type=click.Path(exists=True),
              help='Source video file to extract clips from. Without this, only timestamps + report are saved.')
@click.option('--quality', default='medium', type=click.Choice(['fast', 'medium', 'high']),
              help='Video extraction quality')
def find_story_clips(transcript_path: str, output: str, max_stories: int,
                     query: str, video: str, quality: str):
    """
    Find composite "story clips" -- multi-segment clips stitched from non-contiguous
    moments within the same conversation (contradictions, gotcha arcs, escalations).

    Requires an enhanced transcript. Automatically segments into conversations first.
    
    If --video is provided, extracts and stitches the actual MP4 clips.
    Multi-segment stories become a single composite video; single-segment stories
    become standalone clips.

    \b
    Examples:
        python main.py find-story-clips transcript_v3.json -o outputs/stories
        python main.py find-story-clips transcript_v3.json -Q "find where he supports Iran then contradicts it"
        python main.py find-story-clips transcript_v3.json --video stream.mp4 -Q "child marriage"
    """
    from src.conversation_segmenter_v3 import segment_conversations, save_conversation_map
    from src.story_clip_finder import StoryClipFinder
    from src.extractor import ClipExtractor
    import asyncio

    click.echo("=" * 60)
    click.echo("STORY CLIP FINDER — Composite Clip Detection")
    click.echo("=" * 60)
    click.echo(f"Transcript:  {transcript_path}")
    click.echo(f"Output dir:  {output}")
    click.echo(f"Max stories: {max_stories}")
    if query:
        click.echo(f"Query:       {query}")
    if video:
        click.echo(f"Video:       {video}")
        click.echo(f"Quality:     {quality}")
    else:
        click.echo(f"Video:       (none — timestamps only, no clip extraction)")
    click.echo()

    start_time = time.time()

    try:
        # Step 1: Segment conversations
        click.echo("Step 1: Segmenting conversations...")
        conv_map = segment_conversations(transcript_path)
        click.echo(f"  Found {conv_map.total_conversations} conversations")

        out_dir = Path(output)
        out_dir.mkdir(parents=True, exist_ok=True)
        save_conversation_map(conv_map, str(out_dir / "conversation_map.json"))

        # Step 2: Find stories
        async def _run():
            finder = StoryClipFinder()
            intent = None
            if query:
                click.echo(f"\nStep 2: Interpreting query...")
                intent = await finder.interpret_query(query, conv_map)
                click.echo(f"  -> type={intent.query_type}, topic={intent.topic}")
                if intent.search_targets:
                    for t in intent.search_targets:
                        click.echo(f"  -> target: {t.label} = {t.description}")

            click.echo(f"\nStep 3: Finding story connections...")
            stories = await finder.find_stories(transcript_path, conv_map, intent, max_stories)
            finder.save_results(stories, output, intent)
            return stories, intent

        stories, intent = asyncio.run(_run())

        elapsed_find = time.time() - start_time

        # Step 4: Extract clips if video provided
        extracted_count = 0
        if video and stories:
            click.echo(f"\nStep 4: Extracting video clips...")
            clips_dir = out_dir / "clips"
            clips_dir.mkdir(exist_ok=True)

            async def _extract():
                nonlocal extracted_count
                extractor = ClipExtractor(video, str(clips_dir))
                for story in stories:
                    if len(story.segments) >= 2:
                        # Multi-segment: composite stitch
                        segs = [{"start_time": s.start_time, "end_time": s.end_time}
                                for s in story.segments]
                        result = await extractor.extract_composite_clip(
                            segments=segs,
                            clip_id=story.story_id,
                            title=story.title,
                            quality=quality,
                        )
                        if result.status == "success":
                            extracted_count += 1
                            click.echo(f"  Composite: {result.file_path} ({result.file_size_mb:.1f}MB)")
                    else:
                        # Single segment: one-off clip
                        clip_data = {
                            "clip_id": story.story_id,
                            "start_time": story.segments[0].start_time,
                            "end_time": story.segments[0].end_time,
                            "title": story.title,
                        }
                        result = await extractor.extract_clip(clip_data, quality=quality)
                        if result.status == "success":
                            extracted_count += 1
                            click.echo(f"  Clip: {result.file_path} ({result.file_size_mb:.1f}MB)")

            asyncio.run(_extract())
            click.echo(f"  Extracted: {extracted_count}/{len(stories)} clips")

        elapsed = time.time() - start_time
        click.echo()
        click.echo("=" * 60)
        click.echo(f"COMPLETE — {len(stories)} stories found in {elapsed:.1f}s")
        click.echo("=" * 60)
        click.echo()

        for i, story in enumerate(stories, 1):
            segs = len(story.segments)
            click.echo(
                f"  #{i} [{story.score:.1f}/10] {story.story_type.upper()} — {story.title[:50]}"
                f" ({segs} segments, {story.total_duration:.0f}s)"
            )

        click.echo(f"\nResults: {output}/story_clips_results.json")
        click.echo(f"Report:  {output}/story_clips_report.md")
        if video and extracted_count:
            click.echo(f"Clips:   {output}/clips/")

    except Exception as e:
        logger.exception("Story Clip Finder failed")
        raise click.ClickException(f"Story Clip Finder failed: {e}")


# =============================================================================
# V3 FULL PIPELINE (URL -> Clips)
# =============================================================================

@cli.command('pipeline-v3')
@click.argument('url')
@click.option('--max-clips', '-n', default=10, help='Number of clips to extract (default: 10)')
@click.option('--output', '-o', default=None, help='Output folder name (default: auto from video title)')
@click.option('--voiceprint', '-v', default='nick_voiceprint.json',
              type=click.Path(exists=True), help='Path to Nick voiceprint JSON')
@click.option('--min-score', default=40.0, help='Minimum composite score (0-100)')
@click.option('--quality', '-q', default='medium',
              type=click.Choice(['fast', 'medium', 'high']), help='Clip video quality')
@click.option('-Q', '--query', default=None, help='Free-form search query to focus clip detection')
@click.option('--stories/--no-stories', default=True, help='Also find composite story clips')
def pipeline_v3(url: str, max_clips: int, output: str, voiceprint: str,
                min_score: float, quality: str, query: str, stories: bool):
    """
    Full end-to-end V3 pipeline: YouTube URL -> extracted clips.

    Downloads the video, transcribes it, identifies Nick via Pyannote,
    runs the 5-pass AI clip finder, and extracts the top clips as MP4 files.

    \b
    URL: YouTube video URL

    \b
    Examples:
        python main.py pipeline-v3 "https://youtube.com/watch?v=..." --max-clips 10
        python main.py pipeline-v3 "https://youtube.com/watch?v=..." -n 5 -o my_run
    """
    from src.downloader import YouTubeDownloader
    from src.ingester import VideoIngester
    from src.transcriber import Transcriber
    from src.voice_fingerprinter import (
        VoiceFingerprinter, Voiceprint,
        merge_pyannote_speakers_with_transcript,
        collapse_words_to_utterances, build_readable_transcript,
        build_structured_transcript,
    )
    from src.clip_finder_v3 import ClipFinderV3
    from src.extractor import ClipExtractor
    from src.conversation_segmenter_v3 import segment_conversations, save_conversation_map
    from src.story_clip_finder import StoryClipFinder
    from src.topic_mapper import TopicMapper, save_topic_map
    from src.clip_finder_unified import ClipFinderUnified

    pipeline_start = time.time()
    api_key = get_deepgram_api_key()

    click.echo("=" * 60)
    click.echo("PIPELINE V3 — Full End-to-End Clip Extraction")
    click.echo("=" * 60)
    click.echo(f"URL:        {url}")
    click.echo(f"Max clips:  {max_clips}")
    click.echo(f"Min score:  {min_score}")
    click.echo(f"Quality:    {quality}")
    if query:
        click.echo(f"Query:      {query}")
    click.echo(f"Stories:    {'yes' if stories else 'no'}")
    click.echo()

    try:
        # =================================================================
        # STEP 1: Download
        # =================================================================
        click.echo("=" * 50)
        click.echo("STEP 1/6: Downloading video")
        click.echo("=" * 50)
        step_start = time.time()

        # Download to a temp location first to get the title
        temp_dir = Path("outputs/_temp_download")
        temp_dir.mkdir(parents=True, exist_ok=True)
        downloader = YouTubeDownloader(output_dir=str(temp_dir))
        download_result = downloader.download(url)

        video_title = download_result.title
        duration_min = download_result.duration_seconds / 60
        click.echo(f"   Title:    {video_title}")
        click.echo(f"   Duration: {duration_min:.1f} minutes")
        click.echo(f"   Time:     {time.time() - step_start:.1f}s")

        # Determine output folder
        if output is None:
            safe_name = re.sub(r'[<>:"/\\|?*]', '', video_title)
            safe_name = re.sub(r'\s+', '_', safe_name)[:60]
            output = safe_name
        output_dir = Path("outputs") / output
        output_dir.mkdir(parents=True, exist_ok=True)
        clips_dir = output_dir / "clips"
        clips_dir.mkdir(exist_ok=True)

        # Move video to output dir
        video_src = Path(download_result.video_path)
        video_path = output_dir / video_src.name
        if not video_path.exists():
            shutil.move(str(video_src), str(video_path))
        # Clean up temp dir
        try:
            temp_dir.rmdir()
        except OSError:
            pass

        click.echo(f"   Output:   {output_dir}")

        # =================================================================
        # STEP 2: Extract Audio
        # =================================================================
        click.echo("\n" + "=" * 50)
        click.echo("STEP 2/6: Extracting audio")
        click.echo("=" * 50)
        step_start = time.time()

        audio_path = output_dir / (video_path.stem + ".wav")
        if audio_path.exists():
            click.echo(f"   Using existing: {audio_path.name}")
        else:
            ingester = VideoIngester(str(video_path))
            extracted = ingester.extract_audio(str(audio_path))
            click.echo(f"   Audio: {Path(extracted).name}")
        click.echo(f"   Time:  {time.time() - step_start:.1f}s")

        # =================================================================
        # STEP 3: Transcribe with Deepgram
        # =================================================================
        click.echo("\n" + "=" * 50)
        click.echo("STEP 3/6: Transcribing with Deepgram")
        click.echo("=" * 50)
        step_start = time.time()

        transcript_path = output_dir / "transcript.json"
        if transcript_path.exists():
            click.echo(f"   Using existing transcript")
            with open(transcript_path, 'r', encoding='utf-8') as f:
                transcript_data = json.load(f)
            word_count = len(transcript_data.get('words', []))
        else:
            transcriber = Transcriber(api_key)
            transcript_obj = transcriber.transcribe_sync(str(audio_path))
            transcript_obj.save(str(transcript_path))
            word_count = transcript_obj.word_count
            with open(transcript_path, 'r', encoding='utf-8') as f:
                transcript_data = json.load(f)

        click.echo(f"   Words: {word_count}")
        deepgram_cost = (download_result.duration_seconds / 60) * 0.0043
        click.echo(f"   Cost:  ~${deepgram_cost:.2f}")
        click.echo(f"   Time:  {time.time() - step_start:.1f}s")

        # =================================================================
        # STEP 4: Enhance with Pyannote (identify Nick)
        # =================================================================
        click.echo("\n" + "=" * 50)
        click.echo("STEP 4/6: Enhancing transcript (Pyannote + Nick ID)")
        click.echo("=" * 50)
        step_start = time.time()

        enhanced_path = output_dir / "enhanced_transcript.json"
        if enhanced_path.exists():
            click.echo(f"   Using existing enhanced transcript")
        else:
            vp = Voiceprint.load(voiceprint)
            click.echo(f"   Nick voiceprint: {vp.voiceprint_id[:20]}...")
            click.echo(f"   Running Pyannote identification (may take 5-30 min)...")

            fingerprinter = VoiceFingerprinter()
            segments, speaker_mapping, job_id = fingerprinter.identify_speakers_sync(
                str(audio_path),
                {"nick": vp.voiceprint_id},
                match_threshold=50,
            )

            click.echo(f"   Pyannote job:  {job_id}")
            click.echo(f"   Segments:      {len(segments)}")
            click.echo(f"   Nick mapping:  {speaker_mapping}")

            # Merge with Deepgram
            enhanced = merge_pyannote_speakers_with_transcript(
                segments, speaker_mapping, transcript_data, time_offset=0.0,
            )
            utterances = collapse_words_to_utterances(enhanced, max_pause=2.0)
            click.echo(f"   Utterances:    {len(utterances)}")

            # Save all three formats
            merge_meta = enhanced.get('merge_metadata', {})
            structured = build_structured_transcript(utterances, metadata=merge_meta)
            with open(enhanced_path, 'w', encoding='utf-8') as f:
                json.dump(structured, f, indent=2, ensure_ascii=False)

            txt_path = output_dir / "enhanced_transcript.txt"
            readable = build_readable_transcript(utterances)
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(readable)

            raw_path = output_dir / "enhanced_transcript_raw_words.json"
            with open(raw_path, 'w', encoding='utf-8') as f:
                json.dump(enhanced, f, indent=2, ensure_ascii=False)

        click.echo(f"   Time:  {(time.time() - step_start) / 60:.1f} min")

        # =================================================================
        # STEP 5: Segment Conversations
        # =================================================================
        click.echo("\n" + "=" * 50)
        click.echo("STEP 5/8: Segmenting conversations")
        click.echo("=" * 50)
        step_start = time.time()

        conv_map = segment_conversations(str(enhanced_path))
        save_conversation_map(conv_map, str(output_dir / "conversation_map.json"))
        click.echo(f"   Conversations: {conv_map.total_conversations}")
        click.echo(f"   Time: {time.time() - step_start:.1f}s")

        # =================================================================
        # STEP 6: Topic Mapping (LLM)
        # =================================================================
        click.echo("\n" + "=" * 50)
        click.echo("STEP 6/8: Mapping topics (Claude LLM)")
        click.echo("=" * 50)
        step_start = time.time()

        topic_map_path = output_dir / "topic_map.json"
        if topic_map_path.exists():
            click.echo("   Using existing topic map")
            with open(topic_map_path, 'r', encoding='utf-8') as f:
                from src.topic_mapper import TopicMap as TM, ConversationTopics as CT, TopicBlock as TB
                raw_tm = json.load(f)
                convs_topics = []
                for ct_raw in raw_tm.get("conversations", []):
                    blocks = [TB(**tb) for tb in ct_raw.get("topics", [])]
                    convs_topics.append(CT(
                        conversation_id=ct_raw["conversation_id"],
                        guest_speakers=ct_raw.get("guest_speakers", []),
                        topics=blocks,
                        topic_summary=ct_raw.get("topic_summary", ""),
                        unique_topic_ids=ct_raw.get("unique_topic_ids", []),
                    ))
                topic_map = TM(
                    conversations=convs_topics,
                    all_topic_ids=raw_tm.get("all_topic_ids", []),
                    total_topics=raw_tm.get("total_topics", 0),
                    source_file=raw_tm.get("source_file", ""),
                )
        else:
            async def _map_topics():
                mapper = TopicMapper()
                return await mapper.map_topics(str(enhanced_path), conv_map)
            topic_map = asyncio.run(_map_topics())
            save_topic_map(topic_map, str(topic_map_path))

        click.echo(f"   Topic blocks: {topic_map.total_topics}")
        click.echo(f"   Unique topics: {len(topic_map.all_topic_ids)}")
        click.echo(f"   Time: {(time.time() - step_start) / 60:.1f} min")

        # =================================================================
        # STEP 7: Unified Clip Finder (Scout + Editor)
        # =================================================================
        click.echo("\n" + "=" * 50)
        click.echo("STEP 7/8: Finding clips (Scout + Editor)")
        click.echo("=" * 50)
        step_start = time.time()

        async def _find_clips():
            finder = ClipFinderUnified()
            intent = None
            if query:
                click.echo(f"   Interpreting query: \"{query}\"")
                sf = StoryClipFinder(client=finder.client)
                intent = await sf.interpret_query(query, conv_map)
                click.echo(f"   -> type={intent.query_type}, topic={intent.topic}")
            clips = await finder.find_clips(
                str(enhanced_path), conv_map, topic_map, intent, max_clips,
            )
            finder.save_results(clips, str(clips_dir), intent, topic_map)
            return clips

        unified_clips = asyncio.run(_find_clips())
        continuous = sum(1 for c in unified_clips if c.assembly == "continuous")
        composite = sum(1 for c in unified_clips if c.assembly == "composite")
        click.echo(f"   Found: {len(unified_clips)} clips ({continuous} continuous, {composite} composite)")
        click.echo(f"   Time: {(time.time() - step_start) / 60:.1f} min")

        # =================================================================
        # STEP 8: Extract video clips with FFmpeg
        # =================================================================
        click.echo("\n" + "=" * 50)
        click.echo("STEP 8/8: Extracting video clips")
        click.echo("=" * 50)
        step_start = time.time()

        success_count = 0
        async def _extract():
            nonlocal success_count
            extractor = ClipExtractor(str(video_path), str(clips_dir))
            for clip in unified_clips:
                if clip.assembly == "composite" and len(clip.segments) > 1:
                    segs = [{"start_time": s.start_time, "end_time": s.end_time}
                            for s in clip.segments]
                    result = await extractor.extract_composite_clip(
                        segments=segs,
                        clip_id=clip.clip_id,
                        title=clip.title,
                        quality=quality,
                    )
                else:
                    result = await extractor.extract_clip(
                        {
                            "clip_id": clip.clip_id,
                            "start_time": clip.start_time,
                            "end_time": clip.end_time,
                            "title": clip.title,
                        },
                        quality=quality,
                    )
                if result.status == "success":
                    success_count += 1

        asyncio.run(_extract())
        click.echo(f"   Extracted: {success_count}/{len(unified_clips)} clips")
        click.echo(f"   Time: {time.time() - step_start:.1f}s")

        # =================================================================
        # SUMMARY
        # =================================================================
        total_elapsed = time.time() - pipeline_start
        click.echo("\n" + "=" * 60)
        click.echo("PIPELINE V3 COMPLETE!")
        click.echo("=" * 60)
        click.echo(f"   Video:        {video_title}")
        click.echo(f"   Duration:     {duration_min:.1f} min")
        click.echo(f"   Topics:       {topic_map.total_topics} blocks")
        click.echo(f"   Clips:        {len(unified_clips)} ({continuous} continuous, {composite} composite)")
        click.echo(f"   Extracted:    {success_count}")
        if query:
            click.echo(f"   Query:        {query}")
        click.echo(f"   Total time:   {total_elapsed / 60:.1f} min")
        click.echo(f"   Output:       {output_dir}")
        click.echo()

        click.echo("Top clips:")
        for i, c in enumerate(unified_clips, 1):
            st = c.start_time
            ts = "{}:{:02d}:{:02d}".format(
                int(st // 3600), int((st % 3600) // 60), int(st % 60)
            )
            tag = "[C]" if c.assembly == "composite" else "   "
            click.echo(
                "  #{} [{:.1f}/10] {} {} @ {} ({}s) -- {}".format(
                    i, c.score, c.clip_type, tag, ts,
                    int(c.total_duration), c.hook[:50],
                )
            )

        click.echo(f"\nClip files:  {clips_dir}")
        click.echo(f"Topic map:   {topic_map_path}")
        click.echo(f"Report:      {clips_dir / 'unified_clips_report.md'}")
        click.echo(f"Results:     {clips_dir / 'unified_clips_results.json'}")

    except Exception as e:
        logger.exception("Pipeline V3 failed")
        raise click.ClickException(f"Pipeline V3 failed: {e}")


# =============================================================================
# LEGACY COMMANDS (Placeholders)
# =============================================================================

@cli.command()
@click.argument("video_path", type=click.Path(exists=True))
@click.option("--output", "-o", default="./outputs", help="Output directory")
@click.option("--config", "-c", default="./config/config.yaml", help="Config file")
@click.option("--skip-sheets", is_flag=True, help="Skip Google Sheets upload")
@click.option("--quality", default="medium", type=click.Choice(["fast", "medium", "high"]))
def process(video_path: str, output: str, config: str, skip_sheets: bool, quality: str):
    """
    [LEGACY] Process a video through the old pipeline.
    
    Use 'pipeline' command instead for the new speaker-aware pipeline.
    """
    click.echo("Note: 'process' is deprecated. Use 'pipeline' instead.")
    raise click.ClickException("Use 'python main.py pipeline' for full processing")


@cli.command()
@click.argument("transcript_path", type=click.Path(exists=True))
@click.option("--output", "-o", default="clips.json", help="Output JSON file")
def analyze(transcript_path: str, output: str):
    """
    [LEGACY] Analyze a transcript for clips.
    
    Use 'find-clips' command instead for speaker-aware analysis.
    """
    click.echo("Note: 'analyze' is deprecated. Use 'find-clips' instead.")
    raise click.ClickException("Use 'python main.py find-clips' for clip analysis")


@cli.command()
@click.argument("video_path", type=click.Path(exists=True))
@click.option("--clips", "-c", required=True, type=click.Path(exists=True), help="Clips JSON")
@click.option("--output", "-o", default="./outputs", help="Output directory")
@click.option("--quality", default="medium", type=click.Choice(["fast", "medium", "high"]))
def extract(video_path: str, clips: str, output: str, quality: str):
    """Extract clips from a video using clip definitions."""
    click.echo(f"Extracting clips from: {video_path}")
    click.echo("Note: Clip extraction not yet implemented")
    raise click.ClickException("Extract command requires extractor implementation")


if __name__ == "__main__":
    cli()
