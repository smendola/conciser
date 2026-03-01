"""CLI command for extracting key takeaways from videos."""

import sys
from pathlib import Path
import time

import click
from colorama import Fore, Style

from ...config import get_settings
from ...modules.downloader import VideoDownloader
from ...modules.transcriber import Transcriber
from ...modules.condenser import ContentCondenser
from ...modules.edge_tts import EdgeTTS
from ...modules.azure_tts import AzureTTS
from ...modules.tts import VoiceCloner
from ..common import _load_videos_txt


def _suppress_httpx_info_logs() -> None:
    import logging as stdlib_logging
    stdlib_logging.getLogger('httpx').setLevel(stdlib_logging.WARNING)


from ..app import cli  # noqa: E402


@cli.command()
@click.argument('url')
@click.option(
    '--top',
    type=int,
    default=None,
    help='Number of key takeaways (3-10, or any number). Default: auto (AI determines optimal number)'
)
@click.option(
    '--format', '-f',
    type=click.Choice(['text', 'audio']),
    default='text',
    help='Output format: text (markdown) or audio (mp3). Default: text'
)
@click.option(
    '--voice',
    type=str,
    default=None,
    help='Voice for audio output (e.g., "ryan", "edge/ryan", "azure/aria"). Only used with --format=audio'
)
@click.option(
    '--tts-provider',
    type=click.Choice(['elevenlabs', 'edge', 'azure']),
    default='edge',
    help='TTS provider for audio output. Default: edge'
)
@click.option(
    '--speech-rate',
    type=str,
    default='+0%',
    help='Speech speed adjustment (e.g., "+50%", "-25%"). Works with Edge and Azure TTS.'
)
@click.option(
    '--output', '-o',
    type=str,
    default=None,
    help='Output file path (without extension). Default: auto-generated'
)
@click.option(
    '--resume/--no-resume',
    default=True,
    help='Resume from cached intermediate files (default: resume)'
)
def takeaways(url, top, format, voice, tts_provider, speech_rate, output, resume):
    """
    Extract key takeaways from a video.

    Generates a concise list of the most important concepts from a video,
    optionally with audio narration. Much faster and cheaper than full condensation.

    Examples:

        # Text output (default)
        nbj takeaways https://youtube.com/watch?v=...

        # Specific number of points
        nbj takeaways https://youtube.com/watch?v=... --top=5

        # Audio output with voice
        nbj takeaways https://youtube.com/watch?v=... --format=audio --voice=ryan

        # Azure TTS with SSML (no aggressiveness needed for takeaways)
        nbj takeaways https://youtube.com/watch?v=... --format=audio --voice=azure/aria

        # From videos.txt index
        nbj takeaways 1 --top=10

        # Auto-determine optimal number of points
        nbj takeaways https://youtube.com/watch?v=... --top=auto
    """
    _suppress_httpx_info_logs()

    import logging
    logger = logging.getLogger(__name__)

    try:
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}NBJ Takeaways - Key Concepts Extractor{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")

        # Resolve 1-based index into videos.txt
        name_override = None
        if url.isdigit():
            idx = int(url)
            entries = _load_videos_txt()
            if not entries:
                click.echo(f"{Fore.RED}Error: videos.txt not found or empty.{Style.RESET_ALL}")
                sys.exit(1)
            if idx < 1 or idx > len(entries):
                click.echo(f"{Fore.RED}Error: index {idx} out of range — videos.txt has {len(entries)} entries.{Style.RESET_ALL}")
                sys.exit(1)

            video_id_resolved, label = entries[idx - 1]
            name_override = label  # None if no label text on that line
            url = video_id_resolved
            print(f"Video index: {idx} → {video_id_resolved}" + (f"  ({label})" if label else ""))

        print(f"URL: {url}")

        # Show top setting
        if top is None:
            print(f"Takeaways: Auto (AI determines optimal number)")
        else:
            print(f"Takeaways: Top {top}")

        print(f"Output format: {format}")

        # Parse voice shortcut if provided (e.g., edge/ryan, azure/aria)
        if voice and '/' in voice:
            parts = voice.split('/', 1)
            if len(parts) == 2:
                provider_from_voice, voice_name = parts
                provider_from_voice = provider_from_voice.lower().strip()
                voice_name = voice_name.strip()

                # Validate provider
                if provider_from_voice not in ['elevenlabs', 'edge', 'azure']:
                    click.echo(f"{Fore.RED}Error: Invalid provider '{provider_from_voice}' in --voice parameter.{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Valid providers: elevenlabs, edge, azure{Style.RESET_ALL}")
                    sys.exit(1)

                # Set provider and voice
                tts_provider = provider_from_voice
                voice = voice_name

        # Handle voice selection for audio output
        voice_id = None
        if format == 'audio':
            if voice:
                if tts_provider == 'edge':
                    edge = EdgeTTS()
                    voice_id = edge.resolve_voice_name(voice)
                    if not voice_id:
                        click.echo(f"{Fore.RED}Error: Voice '{voice}' not found.{Style.RESET_ALL}")
                        click.echo(f"{Fore.YELLOW}Run 'nbj voices --provider=edge' to see available voices.{Style.RESET_ALL}")
                        sys.exit(1)
                    print(f"Voice: {voice} -> {voice_id}")
                elif tts_provider == 'azure':
                    settings = get_settings()
                    if not settings.azure_speech_key or not settings.azure_speech_region:
                        click.echo(f"{Fore.RED}Error: AZURE_SPEECH_KEY and AZURE_SPEECH_REGION not set.{Style.RESET_ALL}")
                        sys.exit(1)
                    azure = AzureTTS(settings.azure_speech_key, settings.azure_speech_region)
                    voice_id = azure.resolve_voice_name(voice)
                    if not voice_id:
                        click.echo(f"{Fore.RED}Error: Voice '{voice}' not found.{Style.RESET_ALL}")
                        click.echo(f"{Fore.YELLOW}Run 'nbj voices --provider=azure' to see available voices.{Style.RESET_ALL}")
                        sys.exit(1)
                    print(f"Voice: {voice} -> {voice_id}")
                else:
                    # ElevenLabs - use voice name directly for now
                    voice_id = voice
                    print(f"Voice: {voice}")
            else:
                # Default voice
                voice_id = "en-US-AriaNeural"
                print(f"Voice: {voice_id} (default)")

            if speech_rate != '+0%':
                if tts_provider in ['edge', 'azure']:
                    print(f"Speech Rate: {speech_rate}")
                else:
                    click.echo(f"{Fore.YELLOW}Warning: --speech-rate only works with Edge and Azure TTS. Ignoring.{Style.RESET_ALL}")
                    speech_rate = '+0%'

        print()

        # Check API keys
        settings = get_settings()

        if not settings.openai_api_key and not settings.anthropic_api_key:
            click.echo(f"{Fore.RED}Error: No API key set for condensation. Set OPENAI_API_KEY or ANTHROPIC_API_KEY.{Style.RESET_ALL}")
            sys.exit(1)

        if format == 'audio':
            if tts_provider == 'elevenlabs' and not settings.elevenlabs_api_key:
                click.echo(f"{Fore.RED}Error: ELEVENLABS_API_KEY not set.{Style.RESET_ALL}")
                click.echo(f"{Fore.YELLOW}Hint: Use --tts-provider=edge for free TTS without API key.{Style.RESET_ALL}")
                sys.exit(1)
            if tts_provider == 'azure' and (not settings.azure_speech_key or not settings.azure_speech_region):
                click.echo(f"{Fore.RED}Error: AZURE_SPEECH_KEY and AZURE_SPEECH_REGION not set.{Style.RESET_ALL}")
                click.echo(f"{Fore.YELLOW}Hint: Use --tts-provider=edge for free TTS without API key.{Style.RESET_ALL}")
                sys.exit(1)

        # Initialize modules
        downloader = VideoDownloader(settings.temp_dir)
        transcriber = Transcriber(
            api_key=settings.openai_api_key,
            provider=settings.transcription_service,
            groq_api_key=settings.groq_api_key
        )
        condenser = ContentCondenser(
            provider=settings.condenser_service,
            openai_api_key=settings.openai_api_key,
            anthropic_api_key=settings.anthropic_api_key
        )

        # Stage 1: Download video
        print(f"{Fore.CYAN}[1/4] Downloading video...{Style.RESET_ALL}")
        video_info = downloader.download(url)
        video_path = video_info['video_path']
        metadata = video_info.get('metadata', {})
        video_title = metadata.get('title', '')
        video_id = metadata.get('video_id', url)

        if name_override:
            video_title = name_override

        print(f"  Title: {video_title}")
        print(f"  Downloaded: {video_path}\n")

        # Stage 2: Transcribe
        video_folder = video_path.parent
        transcript_path = video_folder / f"transcript_{video_id}.txt"

        if resume and transcript_path.exists():
            print(f"{Fore.CYAN}[2/4] Loading cached transcript...{Style.RESET_ALL}")
            transcript = transcript_path.read_text(encoding='utf-8')
        else:
            print(f"{Fore.CYAN}[2/4] Fetching transcript...{Style.RESET_ALL}")

            # Try YouTube transcript first
            youtube_transcript = transcriber.fetch_youtube_transcript(video_id)

            if youtube_transcript:
                logger.info("Using YouTube transcript (no Whisper API cost)")
                transcript = youtube_transcript['text']
            else:
                logger.warning("YouTube transcript not available, falling back to Whisper transcription")
                print(f"{Fore.YELLOW}  YouTube transcript unavailable, using Whisper...{Style.RESET_ALL}")
                transcript_result = transcriber.transcribe(video_path)
                transcript = transcript_result['text']

            transcript_path.write_text(transcript, encoding='utf-8')

        print(f"  Transcript: {len(transcript)} characters\n")

        # Stage 3: Extract takeaways
        takeaways_path = video_folder / f"takeaways_{video_id}_top{top if top else 'auto'}.md"

        if resume and takeaways_path.exists():
            print(f"{Fore.CYAN}[3/4] Loading cached takeaways...{Style.RESET_ALL}")
            takeaways_text = takeaways_path.read_text(encoding='utf-8')
        else:
            print(f"{Fore.CYAN}[3/4] Extracting key takeaways...{Style.RESET_ALL}")
            takeaways_text = condenser.extract_takeaways(
                transcript=transcript,
                video_title=video_title,
                top=top
            )

            # Save markdown
            header = f"# Key Takeaways: {video_title}\n\n"
            if top:
                header += f"*Top {top} key concepts*\n\n"
            else:
                header += f"*Auto-selected key concepts*\n\n"

            full_text = header + takeaways_text
            takeaways_path.write_text(full_text, encoding='utf-8')

        print(f"  Takeaways saved: {takeaways_path}\n")

        # Stage 4: Generate audio (if requested)
        if format == 'audio':
            print(f"{Fore.CYAN}[4/4] Generating audio...{Style.RESET_ALL}")

            # Build audio script with intro
            audio_script = f"Here are the key takeaways from {video_title}.\n\n{takeaways_text}"

            # Generate audio
            audio_path = video_folder / f"takeaways_{video_id}_top{top if top else 'auto'}_{tts_provider}.mp3"

            if tts_provider == 'edge':
                edge_tts = EdgeTTS()
                edge_tts.generate_speech(
                    text=audio_script,
                    output_path=audio_path,
                    voice=voice_id,
                    rate=speech_rate
                )
            elif tts_provider == 'azure':
                azure_tts = AzureTTS(settings.azure_speech_key, settings.azure_speech_region)
                azure_tts.generate_speech(
                    text=audio_script,
                    output_path=audio_path,
                    voice=voice_id,
                    rate=speech_rate,
                    is_ssml=False  # Plain text for takeaways
                )
            else:  # elevenlabs
                voice_cloner = VoiceCloner(settings.elevenlabs_api_key)
                voice_cloner.generate_speech_chunked(
                    text=audio_script,
                    voice_id=voice_id,
                    output_path=audio_path,
                    chunk_size=5000
                )

            print(f"  Audio saved: {audio_path}\n")
        else:
            print(f"{Fore.CYAN}[4/4] Skipping audio (text output only){Style.RESET_ALL}\n")

        # Summary
        print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}✓ Takeaways extraction complete!{Style.RESET_ALL}")
        print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}\n")

        print(f"Output files:")
        print(f"  Text: {takeaways_path}")
        if format == 'audio':
            print(f"  Audio: {audio_path}")
        print()

    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Interrupted by user{Style.RESET_ALL}")
        sys.exit(130)
    except Exception as e:
        click.echo(f"\n{Fore.RED}Error: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
