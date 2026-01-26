"""
Nick Matau AI Content Clipper - CLI Entry Point

Owner: Gabriel
Status: Implemented (Full pipeline)

Usage:
    # Existing commands
    python main.py download "https://youtube.com/watch?v=..." --output ./data
    python main.py transcribe video.mp4 --output transcript.json
    python main.py transcribe-url "https://youtube.com/watch?v=..." --output ./outputs
    
    # New pipeline commands
    python main.py create-voiceprint nick_sample.wav --output nick_voiceprint.json
    python main.py map-speakers audio.wav --voiceprint nick_voiceprint.json --output voice_map.json
    python main.py map-visual video.mp4 --interval 30 --output visual_map.json
    python main.py segment --voice voice_map.json --visual visual_map.json --output conversations.json
    python main.py find-clips --conversations conversations.json --transcript transcript.json --voice voice_map.json --output clips.json
    
    # Full pipeline
    python main.py pipeline video.mp4 --nick-sample nick_sample.wav --output ./outputs
"""

import asyncio
import json
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
@click.version_option(version="0.2.0")
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
def create_voiceprint(sample_path: str, output: str):
    """
    Create a voiceprint from a clean audio sample of Nick.
    
    SAMPLE_PATH: Path to 30-second audio of Nick speaking alone (no overlapping voices)
    """
    from src.speaker_mapper import SpeakerMapper
    
    click.echo(f"Creating voiceprint from: {sample_path}")
    start_time = time.time()
    
    try:
        mapper = SpeakerMapper()
        voiceprint_id = mapper.create_nick_voiceprint_sync(sample_path)
        
        # Save voiceprint ID to file
        with open(output, 'w') as f:
            json.dump({'voiceprint_id': voiceprint_id}, f, indent=2)
        
        elapsed = time.time() - start_time
        click.echo(f"Voiceprint created!")
        click.echo(f"   ID: {voiceprint_id}")
        click.echo(f"   Saved to: {output}")
        click.echo(f"   Time: {elapsed:.1f}s")
        
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
