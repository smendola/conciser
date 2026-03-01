import sys
from pathlib import Path

import click
from colorama import Fore, Style

from ...config import get_settings
from ...pipeline import CondenserPipeline
from ..common import _load_videos_txt, _resolve_voice
from ..progress import ProgressDisplay


def _suppress_httpx_info_logs() -> None:
    import logging as stdlib_logging

    stdlib_logging.getLogger('httpx').setLevel(stdlib_logging.WARNING)


from ..app import cli  # noqa: E402


@cli.command()
@click.argument('url')
@click.option(
    '--aggressiveness', '-a',
    type=click.IntRange(1, 10),
    default=5,
    help='Condensing aggressiveness (1=conservative, 10=maximum). Default: 5'
)
@click.option(
    '--quality', '-q',
    type=click.Choice(['720p', '1080p', '4k']),
    default='1080p',
    help='Output video quality. Default: 1080p'
)
@click.option(
    '--output', '-o',
    type=click.Path(),
    help='Output file path (default: auto-generated in output/ directory)'
)
@click.option(
    '--resume/--no-resume',
    default=True,
    help='Resume from existing intermediate files (default: enabled)'
)
@click.option(
    '--video-gen-mode',
    type=click.Choice(['static', 'slideshow', 'avatar', 'audio_only']),
    default='slideshow',
    help='Video generation mode: static (single frame), slideshow (scene-detected frames), avatar (expensive, D-ID), audio_only (MP3 output, fastest). Default: slideshow'
)
@click.option(
    '--voice',
    type=str,
    default=None,
    help='Use a premade voice instead of cloning. Formats: "name" (e.g., "George"), "provider/voice" (e.g., "edge/ryan", "elevenlabs/George"). If not specified, voice will be cloned from video.'
)
@click.option(
    '--tts-provider',
    type=click.Choice(['elevenlabs', 'edge']),
    default='elevenlabs',
    help='TTS provider: elevenlabs (paid, high quality) or edge (free, good quality). Default: elevenlabs'
)
@click.option(
    '--slideshow-frames',
    type=int,
    default=None,
    help='Max frames for slideshow mode (default: auto). Use 30-50 for most scene changes, 100+ for all.'
)
@click.option(
    '--speech-rate',
    type=str,
    default='+0%',
    help='Speech speed for Edge TTS (e.g., "+50%" for faster, "-25%" for slower, "+0%" for normal). Only works with Edge TTS provider.'
)
@click.option(
    '--prepend-intro',
    is_flag=True,
    default=False,
    help='Prepend a numbered list of key take-aways to the TTS script.'
)
@click.option(
    '--llm-progress',
    type=click.Choice(['dots', 'text']),
    default=None,
    help='Show LLM streaming output: dots (one dot per chunk) or text (raw streamed text).'
)
def condense(url, aggressiveness, quality, output, resume, video_gen_mode, voice, tts_provider, slideshow_frames, speech_rate, prepend_intro, llm_progress):
    """
    Condense a video from URL.

    URL: YouTube or other video URL to condense

    Examples:

        nbj condense https://youtube.com/watch?v=... -a 5

        nbj condense https://youtube.com/watch?v=... -a 7 -q 720p

        nbj condense https://youtube.com/watch?v=... --reduction 60

        nbj condense https://youtube.com/watch?v=... --video-gen-mode=static

        nbj condense https://youtube.com/watch?v=... --video-gen-mode=slideshow

        nbj condense https://youtube.com/watch?v=... --video-gen-mode=avatar

        # Voice shortcuts (provider/voice format)
        nbj condense https://youtube.com/watch?v=... --voice=edge/ryan

        nbj condense https://youtube.com/watch?v=... --voice=edge/aria

        nbj condense https://youtube.com/watch?v=... --voice=elevenlabs/George

        # Speech speed control (Edge TTS only)
        nbj condense https://youtube.com/watch?v=... --voice=edge/ryan --speech-rate="+25%"

        nbj condense https://youtube.com/watch?v=... --voice=edge/aria --speech-rate="-10%"

        # Legacy format (still supported)
        nbj condense https://youtube.com/watch?v=... --tts-provider=edge --voice=Aria

        nbj condense https://youtube.com/watch?v=... --tts-provider=edge --voice=Ryan

        # ElevenLabs TTS (default provider)
        nbj condense https://youtube.com/watch?v=... --voice=George

        nbj condense https://youtube.com/watch?v=... --voice=Sarah
    """
    _suppress_httpx_info_logs()

    import logging

    logger = logging.getLogger(__name__)

    try:
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}NBJ Condenser - Video Condensation Pipeline{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")

        # Resolve 1-based index into videos.txt → video ID + optional name override
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
        print(f"Aggressiveness: {aggressiveness}/10")
        print(f"Quality: {quality}")
        print(f"Video Mode: {video_gen_mode}")

        # Load settings first
        settings = get_settings()

        # Validate speech rate format
        import re
        if speech_rate != '+0%':
            if not re.match(r'^[+-]\d+%$', speech_rate):
                click.echo(f"{Fore.RED}Error: Invalid speech rate format '{speech_rate}'.{Style.RESET_ALL}")
                click.echo(f"{Fore.YELLOW}Format should be like '+25%', '-10%', or '+0%'.{Style.RESET_ALL}")
                sys.exit(1)

        # Parse shortcut format: --voice=provider/voice (e.g., --voice=edge/ryan)
        if voice and '/' in voice:
            parts = voice.split('/', 1)
            if len(parts) == 2:
                provider_from_voice, voice_name = parts
                provider_from_voice = provider_from_voice.lower().strip()
                voice_name = voice_name.strip()

                # Validate provider
                if provider_from_voice not in ['elevenlabs', 'edge']:
                    click.echo(f"{Fore.RED}Error: Invalid provider '{provider_from_voice}' in --voice parameter.{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Valid providers: elevenlabs, edge{Style.RESET_ALL}")
                    sys.exit(1)

                # Set provider and voice
                tts_provider = provider_from_voice
                voice = voice_name
                print(f"TTS Provider: {tts_provider} (from --voice)")
            else:
                print(f"TTS Provider: {tts_provider}")
        else:
            print(f"TTS Provider: {tts_provider}")

        # Show speech rate if non-default
        if speech_rate != '+0%':
            if tts_provider == 'edge':
                print(f"Speech Rate: {speech_rate}")
            else:
                click.echo(f"{Fore.YELLOW}Warning: --speech-rate only works with Edge TTS. Ignoring.{Style.RESET_ALL}")
                speech_rate = '+0%'  # Reset to default for non-Edge providers

        # Handle voice selection based on TTS provider
        if tts_provider == 'edge':
            # Edge TTS: resolve voice name or use default
            if voice:
                from ...modules.edge_tts import EdgeTTS
                edge = EdgeTTS()
                voice_id = edge.resolve_voice_name(voice)
                if not voice_id:
                    click.echo(f"{Fore.RED}Error: Voice '{voice}' not found.{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Run 'nbj voices --provider=edge' to see available voices.{Style.RESET_ALL}")
                    sys.exit(1)
                print(f"Voice: {voice} -> {voice_id}")
            else:
                voice_id = "en-US-AriaNeural"  # Default Edge voice
                print(f"Voice: {voice_id} (default)")
            skip_voice_clone = True
        else:
            # ElevenLabs: resolve voice name/ID or clone
            if voice:
                # Resolve voice name to ID if needed
                voice_id = _resolve_voice(voice, settings.elevenlabs_api_key)
                if not voice_id:
                    click.echo(f"{Fore.RED}Error: Voice '{voice}' not found.{Style.RESET_ALL}")
                    click.echo(f"{Fore.YELLOW}Run 'nbj voices' to see available voices.{Style.RESET_ALL}")
                    sys.exit(1)
                print(f"Voice: {voice} (ID: {voice_id})")
                skip_voice_clone = True
            else:
                print(f"Voice: Clone from video")
                voice_id = None  # Will be set during pipeline
                skip_voice_clone = False
        print()

        # Check API keys
        if not settings.openai_api_key:
            click.echo(f"{Fore.RED}Error: OPENAI_API_KEY not set. Please configure in .env file.{Style.RESET_ALL}")
            sys.exit(1)
        if not settings.anthropic_api_key:
            click.echo(f"{Fore.RED}Error: ANTHROPIC_API_KEY not set. Please configure in .env file.{Style.RESET_ALL}")
            sys.exit(1)
        # ElevenLabs only required if using elevenlabs provider
        if tts_provider == 'elevenlabs' and not settings.elevenlabs_api_key:
            click.echo(f"{Fore.RED}Error: ELEVENLABS_API_KEY not set. Please configure in .env file.{Style.RESET_ALL}")
            click.echo(f"{Fore.YELLOW}Hint: Use --tts-provider=edge for free TTS without API key.{Style.RESET_ALL}")
            sys.exit(1)
        # D-ID only required for avatar mode
        if video_gen_mode == 'avatar' and not settings.did_api_key:
            click.echo(f"{Fore.RED}Error: DID_API_KEY not set. Required for avatar mode.{Style.RESET_ALL}")
            click.echo(f"{Fore.YELLOW}Hint: Use --video-gen-mode=static or --video-gen-mode=slideshow for lower cost alternatives.{Style.RESET_ALL}")
            sys.exit(1)

        # Initialize pipeline
        pipeline = CondenserPipeline(settings)

        # Parse output path
        output_path = Path(output) if output else None

        # Run pipeline
        print(f"{Fore.GREEN}Starting condensation pipeline...{Style.RESET_ALL}\n")

        result = pipeline.run(
            video_url=url,
            aggressiveness=aggressiveness,
            output_path=output_path,
            quality=quality,
            video_gen_mode=video_gen_mode,
            progress_callback=ProgressDisplay.show,
            resume=resume,
            skip_voice_clone=skip_voice_clone,
            voice_id=voice_id if skip_voice_clone else None,
            tts_provider=tts_provider,
            slideshow_max_frames=slideshow_frames,
            tts_rate=speech_rate,
            prepend_intro=prepend_intro,
            llm_progress=llm_progress,
            name_override=name_override
        )

        # Display results
        print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}Condensation Complete!{Style.RESET_ALL}")
        print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}\n")

        print(f"Output video: {Fore.CYAN}{result['output_video']}{Style.RESET_ALL}")
        print(f"\nStatistics:")
        print(f"  Original duration: {result['stats']['original_duration_minutes']:.1f} minutes")
        print(f"  Condensed duration: {result['stats']['condensed_duration_minutes']:.1f} minutes")
        print(f"  Reduction: {result['stats']['reduction_percentage']:.1f}%")
        print(f"\nKey points preserved:")
        for i, point in enumerate(result['condensed_result'].get('key_points_preserved', [])[:5], 1):
            print(f"  {i}. {point}")

        print(f"\n{Fore.YELLOW}Note: This video was AI-generated and may contain artifacts.{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Please review for quality before sharing.{Style.RESET_ALL}\n")

    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Operation cancelled by user.{Style.RESET_ALL}")
        sys.exit(1)
    except Exception as e:
        from ...utils.exceptions import ApiError
        if isinstance(e, ApiError):
            # Error message already printed, just exit
            sys.exit(1)
        logger.exception("Pipeline failed")
        print(f"\n{Fore.RED}Error: {e}{Style.RESET_ALL}")
        print(f"{Fore.RED}Check nbj.log for details.{Style.RESET_ALL}")
        sys.exit(1)
