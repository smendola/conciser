"""CLI interface for NBJ Condenser."""

import sys
import logging
from pathlib import Path
import click
from colorama import init as colorama_init, Fore, Style

from .config import get_settings
from .pipeline import CondenserPipeline

# Initialize colorama for cross-platform colored output
colorama_init()


def _resolve_voice(voice: str, api_key: str) -> str:
    """
    Resolve voice name or ID to voice ID.

    Args:
        voice: Voice ID or name (e.g., "George" or "JBFqnCBsd6RMkjVDRZzb")
        api_key: ElevenLabs API key

    Returns:
        Voice ID if found, None otherwise
    """
    # If it looks like a voice ID (20+ alphanumeric chars), return as-is
    if len(voice) > 15 and voice.replace('-', '').isalnum():
        return voice

    # Otherwise, look up by name
    try:
        from .modules.tts import VoiceCloner
        cloner = VoiceCloner(api_key)
        voices = cloner.list_voices()

        # Case-insensitive search
        voice_lower = voice.lower()
        for v in voices:
            # Check if name matches (partial or full)
            if voice_lower in v['name'].lower() or v['name'].lower().startswith(voice_lower):
                return v['voice_id']

        return None
    except Exception as e:
        logger.error(f"Failed to resolve voice: {e}")
        return None


def _format_script_into_paragraphs(script_text: str, api_key: str) -> str:
    """Format a script into paragraphs using Claude."""
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)

    prompt = f"""Format this script into natural paragraphs for better readability. Add paragraph breaks (using double newlines) at logical topic transitions and natural breaks. Each paragraph should cover a cohesive idea.

Rules:
- Use \\n\\n (double newline) to separate paragraphs
- Keep all the original text - don't summarize or change wording
- Only add paragraph breaks at natural transitions
- Aim for paragraphs of 3-5 sentences each
- Return ONLY the formatted text, no explanations

Script to format:
{script_text}"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            # temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )

        formatted_text = message.content[0].text.strip()
        return formatted_text
    except Exception as e:
        logger.error(f"Failed to format script: {e}")
        return None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('nbj.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class ProgressDisplay:
    """Display progress updates with colors."""

    STAGE_COLORS = {
        'DOWNLOAD': Fore.CYAN,
        'TRANSCRIBE': Fore.BLUE,
        'CONDENSE': Fore.MAGENTA,
        'VOICE_CLONE': Fore.YELLOW,
        'VOICE_GENERATE': Fore.YELLOW,
        'VIDEO_GENERATE': Fore.GREEN,
        'COMPOSE': Fore.GREEN,
        'CLEANUP': Fore.WHITE,
        'COMPLETE': Fore.GREEN,
    }

    @staticmethod
    def show(stage: str, message: str):
        """Show progress message."""
        color = ProgressDisplay.STAGE_COLORS.get(stage, Fore.WHITE)
        print(f"{color}[{stage}]{Style.RESET_ALL} {message}")


def _load_videos_txt(filepath: Path = None) -> list:
    """
    Load (video_id, label_or_None) pairs from videos.txt.

    Format: one entry per line — "<video_id>  [optional label text]"
    Lines starting with # are comments and are ignored.

    Returns list of (video_id, label) tuples; label is None if the line has
    only a video ID with no following text.
    """
    if filepath is None:
        filepath = Path("videos.txt")
    if not filepath.exists():
        return []
    entries = []
    for line in filepath.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split(None, 1)  # split on first whitespace, max 2 parts
        video_id = parts[0]
        label = parts[1].strip() if len(parts) > 1 else None
        entries.append((video_id, label))
    return entries


@click.group()
@click.version_option(version='0.1.0')
def cli():
    """
    NBJ Condenser - AI-Powered Video Condensation Tool

    Condense videos by removing filler content while preserving key insights,
    using AI voice cloning and video generation.
    """
    pass


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
    '--reduction',
    type=click.IntRange(10, 90),
    help='Target reduction percentage (overrides aggressiveness)'
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
def condense(url, aggressiveness, quality, output, reduction, resume, video_gen_mode, voice, tts_provider, slideshow_frames, speech_rate, prepend_intro, llm_progress):
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
    # Suppress httpx INFO logs
    import logging as stdlib_logging
    stdlib_logging.getLogger('httpx').setLevel(stdlib_logging.WARNING)

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
        if reduction:
            print(f"Target Reduction: {reduction}%")
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
                from .modules.edge_tts import EdgeTTS
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

        # Set target reduction if specified
        if reduction:
            settings.target_reduction_percentage = reduction

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
        from .utils.exceptions import ApiError
        if isinstance(e, ApiError):
            # Error message already printed, just exit
            sys.exit(1)
        logger.exception("Pipeline failed")
        print(f"\n{Fore.RED}Error: {e}{Style.RESET_ALL}")
        print(f"{Fore.RED}Check nbj.log for details.{Style.RESET_ALL}")
        sys.exit(1)


@cli.command()
@click.argument('url')
def info(url):
    """
    Get information about a video without downloading.

    URL: Video URL to analyze
    """
    # Suppress httpx INFO logs
    import logging as stdlib_logging
    stdlib_logging.getLogger('httpx').setLevel(stdlib_logging.WARNING)

    try:
        settings = get_settings()
        from .modules.downloader import VideoDownloader

        downloader = VideoDownloader(settings.temp_dir)
        info = downloader.get_video_info(url)

        print(f"\n{Fore.CYAN}Video Information:{Style.RESET_ALL}\n")
        print(f"Title: {info['title']}")
        print(f"Duration: {info['duration'] / 60:.1f} minutes")
        print(f"Uploader: {info['uploader']}")
        print(f"Views: {info.get('view_count', 'N/A'):,}")
        print()

        # Estimate processing time and cost
        duration_min = info['duration'] / 60
        condensed_min = duration_min * 0.4  # Assume 60% reduction

        # Base costs (same for all modes)
        whisper_cost = duration_min * 0.006
        claude_cost = 0.05
        voice_clone_cost = 1.00
        voice_gen_cost = 1.80
        base_cost = whisper_cost + claude_cost + voice_clone_cost + voice_gen_cost

        # Video generation costs
        static_cost = base_cost
        slideshow_cost = base_cost
        avatar_cost = base_cost + (condensed_min * 60 * 0.10)  # D-ID ~$0.10/sec

        print(f"{Fore.YELLOW}Estimated Cost by Mode:{Style.RESET_ALL}")
        print(f"  Static (single frame):    ${static_cost:.2f}")
        print(f"  Slideshow (multi-frame):  ${slideshow_cost:.2f}")
        print(f"  Avatar (D-ID animated):   ${avatar_cost:.2f}")
        print()
        print(f"{Fore.YELLOW}Estimated Processing Time:{Style.RESET_ALL}")
        print(f"  Static/Slideshow: ~{duration_min * 0.5:.0f}-{duration_min:.0f} minutes")
        print(f"  Avatar: ~{duration_min * 1.5:.0f}-{duration_min * 3:.0f} minutes")
        print()

    except Exception as e:
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@cli.command()
def setup():
    """
    Interactive setup wizard to configure API keys.
    """
    print(f"\n{Fore.CYAN}NBJ Condenser Setup Wizard{Style.RESET_ALL}\n")

    print("This wizard will help you configure API keys for Conciser.\n")

    env_file = Path('.env')

    if env_file.exists():
        print(f"{Fore.YELLOW}.env file already exists.{Style.RESET_ALL}")
        if not click.confirm("Do you want to overwrite it?"):
            print("Setup cancelled.")
            return

    print("\nYou will need API keys from:")
    print("  1. OpenAI (https://platform.openai.com/api-keys)")
    print("  2. Anthropic (https://console.anthropic.com/)")
    print("  3. ElevenLabs (https://elevenlabs.io/)")
    print("  4. D-ID (https://www.d-id.com/) - OPTIONAL, only for avatar mode")
    print()

    openai_key = click.prompt("OpenAI API Key", type=str)
    anthropic_key = click.prompt("Anthropic API Key", type=str)
    elevenlabs_key = click.prompt("ElevenLabs API Key", type=str)
    did_key = click.prompt("D-ID API Key (press Enter to skip for static/slideshow mode)", type=str, default="", show_default=False)

    # Write .env file
    env_content = f"""# NBJ Condenser API Configuration

# OpenAI (for Whisper transcription)
OPENAI_API_KEY={openai_key}

# Anthropic (for script condensing)
ANTHROPIC_API_KEY={anthropic_key}

# ElevenLabs (for voice cloning)
ELEVENLABS_API_KEY={elevenlabs_key}

# D-ID (for video generation)
DID_API_KEY={did_key}

# Configuration
DEFAULT_AGGRESSIVENESS=5
DEFAULT_OUTPUT_QUALITY=1080p
TEMP_DIR=./temp
OUTPUT_DIR=./output
"""

    with open('.env', 'w') as f:
        f.write(env_content)

    print(f"\n{Fore.GREEN}Setup complete! .env file created.{Style.RESET_ALL}")
    print(f"\nYou can now run: {Fore.CYAN}conciser condense <youtube_url>{Style.RESET_ALL}\n")


@cli.command()
def init():
    """
    Pre-initialize OpenAI Responses API chains for all 10 aggressiveness levels.

    Sends the system prompt for each level to the model once and stores the
    resulting response IDs in condenser_chains.json. Subsequent condense jobs
    continue from the appropriate chain tip instead of re-sending system prompts.

    Re-run this command whenever you update the prompt templates.
    """
    from .modules.condenser import ContentCondenser
    from .utils.chain_store import CHAINS_FILE

    settings = get_settings()
    if not settings.openai_api_key:
        print(f"{Fore.RED}OpenAI API key not configured. Run 'nbj setup' first.{Style.RESET_ALL}")
        sys.exit(1)

    print(f"\n{Fore.CYAN}Initializing condenser chains (10 aggressiveness levels)...{Style.RESET_ALL}\n")

    condenser = ContentCondenser(
        provider="openai",
        openai_api_key=settings.openai_api_key,
    )

    try:
        chains = condenser.init_chains()
        print(f"\n{Fore.GREEN}Initialized {len(chains)} chains.{Style.RESET_ALL}")
        print(f"Saved to: {CHAINS_FILE}\n")
    except Exception as e:
        print(f"{Fore.RED}Init failed: {e}{Style.RESET_ALL}")
        sys.exit(1)


@cli.command()
@click.option(
    '--provider',
    type=click.Choice(['elevenlabs', 'edge']),
    default='elevenlabs',
    help='TTS provider to list voices for. Default: elevenlabs'
)
@click.option(
    '--lang',
    type=str,
    default=None,
    help='Filter by language/locale (e.g., "en", "US", "en-US", "fr-FR")'
)
def voices(provider, lang):
    """
    List available TTS voices.

    Shows all voices that can be used with --voice option.
    Use --lang to filter by language/locale (e.g., "en", "US", "en-US", "fr-FR").
    """
    # Suppress httpx INFO logs
    import logging as stdlib_logging
    stdlib_logging.getLogger('httpx').setLevel(stdlib_logging.WARNING)

    try:
        settings = get_settings()

        if provider == 'edge':
            # List Edge TTS voices
            from .modules.edge_tts import EdgeTTS

            title = f"Available Edge TTS Voices (Free)"
            if lang:
                title += f" - Filtered by: {lang}"
            print(f"\n{Fore.CYAN}{title}:{Style.RESET_ALL}\n")

            edge = EdgeTTS()
            voices = edge.list_voices()

            if not voices:
                print(f"{Fore.RED}No voices found or API error.{Style.RESET_ALL}")
                sys.exit(1)

            # Group by locale
            locales = {}
            for v in voices:
                locale = v['locale']
                if locale not in locales:
                    locales[locale] = []
                locales[locale].append(v)

            # Filter locales if --lang is specified
            if lang:
                lang_lower = lang.lower()
                filtered_locales = {}
                for locale, voice_list in locales.items():
                    locale_lower = locale.lower()
                    # Match: exact, starts with, ends with, or contains
                    if (locale_lower == lang_lower or
                        locale_lower.startswith(lang_lower + '-') or
                        locale_lower.endswith('-' + lang_lower) or
                        lang_lower in locale_lower):
                        filtered_locales[locale] = voice_list
                locales = filtered_locales

                if not locales:
                    print(f"{Fore.RED}No voices found for language: {lang}{Style.RESET_ALL}")
                    sys.exit(1)

            # Show all locales, sorted alphabetically
            all_locales = sorted(locales.keys())

            for locale in all_locales:
                print(f"{Fore.GREEN}{locale}:{Style.RESET_ALL}")
                for v in locales[locale]:
                    gender_icon = "♂" if v['gender'] == 'Male' else "♀" if v['gender'] == 'Female' else ""
                    # Extract short name from full name (e.g., "en-US-AriaNeural" -> "Aria")
                    short_name = v['name'].split('-')[-1].replace('Neural', '').replace('Multilingual', '')
                    print(f"  {gender_icon} {Fore.GREEN}{short_name}{Style.RESET_ALL} {Style.DIM}({v['name']}){Style.RESET_ALL}")
                print()

            print(f"{Fore.YELLOW}Filter voices:{Style.RESET_ALL}")
            print(f"  nbj voices --provider=edge --lang=en       # All English variants")
            print(f"  nbj voices --provider=edge --lang=US       # US English only")
            print(f"  nbj voices --provider=edge --lang=en-US    # US English only")
            print(f"  nbj voices --provider=edge --lang=fr-FR    # French (France)")
            print(f"\n{Fore.YELLOW}Usage (short names):{Style.RESET_ALL}")
            print(f"  nbj condense URL --tts-provider=edge --voice=Aria")
            print(f"  nbj condense URL --tts-provider=edge --voice=Ryan")
            print(f"  nbj condense URL --tts-provider=edge --voice=Denise")
            print(f"\n{Fore.YELLOW}Usage (full names):{Style.RESET_ALL}")
            print(f"  nbj condense URL --tts-provider=edge --voice=en-US-AriaNeural")
            print(f"  nbj condense URL --tts-provider=edge --voice=en-GB-RyanNeural\n")
            return

        # ElevenLabs
        if not settings.elevenlabs_api_key:
            print(f"{Fore.RED}Error: ELEVENLABS_API_KEY not set.{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Run 'nbj setup' to configure.{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Or use --provider=edge for free voices without API key.{Style.RESET_ALL}")
            sys.exit(1)

        from .modules.tts import VoiceCloner

        print(f"\n{Fore.CYAN}Available ElevenLabs Voices:{Style.RESET_ALL}\n")

        cloner = VoiceCloner(settings.elevenlabs_api_key)
        voices = cloner.list_voices()

        if not voices:
            print(f"{Fore.RED}No voices found or API error.{Style.RESET_ALL}")
            sys.exit(1)

        # Group by category
        premade = [v for v in voices if v['category'] == 'premade']
        cloned = [v for v in voices if v['category'] == 'cloned']
        generated = [v for v in voices if v['category'] == 'generated']

        def format_voice_name(name):
            """Format voice name with green name and italic description."""
            if ' - ' in name:
                parts = name.split(' - ', 1)
                # ANSI code \033[3m for italic, \033[23m to end italic
                return f"{Fore.GREEN}{parts[0]}{Style.RESET_ALL} - \033[3m{parts[1]}\033[23m"
            else:
                return f"{Fore.GREEN}{name}{Style.RESET_ALL}"

        if premade:
            print(f"{Fore.GREEN}Premade Voices:{Style.RESET_ALL}")
            for v in sorted(premade, key=lambda x: x['name'].lower()):
                print(f"  {Style.DIM}{Fore.CYAN}{v['voice_id']}{Style.RESET_ALL} {format_voice_name(v['name'])}")
            print()

        if cloned:
            print(f"{Fore.GREEN}Your Cloned Voices:{Style.RESET_ALL}")
            for v in sorted(cloned, key=lambda x: x['name'].lower()):
                print(f"  {Style.DIM}{Fore.CYAN}{v['voice_id']}{Style.RESET_ALL} {format_voice_name(v['name'])}")
            print()

        if generated:
            print(f"{Fore.GREEN}Generated Voices:{Style.RESET_ALL}")
            for v in sorted(generated, key=lambda x: x['name'].lower()):
                print(f"  {Style.DIM}{Fore.CYAN}{v['voice_id']}{Style.RESET_ALL} {format_voice_name(v['name'])}")
            print()

        print(f"{Fore.YELLOW}Usage:{Style.RESET_ALL}")
        print(f"  nbj condense URL --tts-provider=elevenlabs --voice=George")
        print(f"  nbj condense URL --tts-provider=elevenlabs --voice=JBFqnCBsd6RMkjVDRZzb\n")

    except Exception as e:
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@cli.command()
@click.argument('url_or_video_id')
@click.option(
    '--format/--no-format',
    default=True,
    help='Format script into paragraphs using AI (default: enabled)'
)
def show_script(url_or_video_id, format):
    """
    Display the condensed script for a video.

    URL_OR_VIDEO_ID: YouTube URL or video ID (e.g., IZD9jIOLPAw)

    Examples:

        nbj show-script https://youtube.com/watch?v=IZD9jIOLPAw

        nbj show-script IZD9jIOLPAw

        nbj show-script IZD9jIOLPAw --no-format  # Skip paragraph formatting
    """
    # Suppress httpx INFO logs
    import logging as stdlib_logging
    stdlib_logging.getLogger('httpx').setLevel(stdlib_logging.WARNING)

    try:
        settings = get_settings()

        # Extract video ID from URL if needed
        video_id = url_or_video_id
        if 'youtube.com' in url_or_video_id or 'youtu.be' in url_or_video_id:
            import re
            match = re.search(r'(?:v=|/)([a-zA-Z0-9_-]{11})', url_or_video_id)
            if match:
                video_id = match.group(1)
            else:
                click.echo(f"{Fore.RED}Error: Could not extract video ID from URL{Style.RESET_ALL}")
                sys.exit(1)

        # Find video folder
        video_folder = None
        for folder in settings.temp_dir.iterdir():
            if folder.is_dir() and folder.name.startswith(video_id):
                video_folder = folder
                break

        if not video_folder:
            click.echo(f"{Fore.RED}Error: No condensed content found for video ID: {video_id}{Style.RESET_ALL}")
            click.echo(f"{Fore.YELLOW}Hint: Run 'nbj condense' first to generate the condensed script.{Style.RESET_ALL}")
            sys.exit(1)

        # Load condensed script
        script_path = video_folder / "condensed_script.json"
        if not script_path.exists():
            click.echo(f"{Fore.RED}Error: Condensed script not found at: {script_path}{Style.RESET_ALL}")
            sys.exit(1)

        import json
        with open(script_path, 'r', encoding='utf-8') as f:
            condensed_result = json.load(f)

        # Format script into paragraphs if requested
        if format:
            if not settings.anthropic_api_key:
                click.echo(f"{Fore.YELLOW}Warning: ANTHROPIC_API_KEY not set, skipping formatting{Style.RESET_ALL}\n")
            else:
                script_text = condensed_result.get('condensed_script', '')
                # Check if already formatted (has paragraph breaks)
                if '\n\n' not in script_text:
                    click.echo(f"{Fore.YELLOW}Formatting script into paragraphs...{Style.RESET_ALL}")
                    formatted_script = _format_script_into_paragraphs(script_text, settings.anthropic_api_key)
                    if formatted_script:
                        condensed_result['condensed_script'] = formatted_script
                        # Save the formatted version
                        with open(script_path, 'w', encoding='utf-8') as f:
                            json.dump(condensed_result, f, indent=2, ensure_ascii=False)
                        click.echo(f"{Fore.GREEN}Script formatted and saved!{Style.RESET_ALL}\n")
                    else:
                        click.echo(f"{Fore.RED}Failed to format script{Style.RESET_ALL}\n")

        # Display the script
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Condensed Script{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")

        print(f"{Fore.GREEN}Statistics:{Style.RESET_ALL}")
        print(f"  Original Duration: {condensed_result.get('original_duration_minutes', 'N/A'):.1f} minutes")
        print(f"  Condensed Duration: {condensed_result.get('estimated_condensed_duration_minutes', 'N/A'):.1f} minutes")
        print(f"  Reduction: {condensed_result.get('reduction_percentage', 'N/A'):.1f}%")
        print()

        if 'key_points_preserved' in condensed_result:
            print(f"{Fore.GREEN}Key Points Preserved:{Style.RESET_ALL}")
            for i, point in enumerate(condensed_result['key_points_preserved'][:5], 1):
                print(f"  {i}. {point}")
            print()

        print(f"{Fore.GREEN}Condensed Script:{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'─'*60}{Style.RESET_ALL}\n")

        # Display script with proper paragraph formatting
        script_text = condensed_result.get('condensed_script', 'No script found')
        paragraphs = script_text.split('\n\n')
        for para in paragraphs:
            if para.strip():
                print(para.strip())
                print()  # Add spacing between paragraphs

        print(f"{Fore.CYAN}{'─'*60}{Style.RESET_ALL}\n")

        # Character and word count
        script_text = condensed_result.get('condensed_script', '')
        char_count = len(script_text)
        word_count = len(script_text.split())
        print(f"{Fore.YELLOW}Script Stats: {word_count} words, {char_count} characters{Style.RESET_ALL}\n")

    except Exception as e:
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


@cli.command()
@click.option(
    '--verbose', '-v',
    is_flag=True,
    default=False,
    help='Show detailed error messages from API servers'
)
def check(verbose):
    """
    Check configuration and API connectivity.
    """
    # Suppress httpx INFO logs
    import logging as stdlib_logging
    stdlib_logging.getLogger('httpx').setLevel(stdlib_logging.WARNING)

    print(f"\n{Fore.CYAN}Checking NBJ Condenser Configuration...{Style.RESET_ALL}\n")

    settings = get_settings()

    # Check directories
    print("Directories:")
    temp_exists = settings.temp_dir.exists()
    output_exists = settings.output_dir.exists()
    print(f"  Temp: {settings.temp_dir} {Style.BRIGHT}{Fore.GREEN}✓{Style.RESET_ALL}" if temp_exists else f"  Temp: {settings.temp_dir} {Style.BRIGHT}{Fore.RED}✗{Style.RESET_ALL}")
    print(f"  Output: {settings.output_dir} {Style.BRIGHT}{Fore.GREEN}✓{Style.RESET_ALL}" if output_exists else f"  Output: {settings.output_dir} {Style.BRIGHT}{Fore.RED}✗{Style.RESET_ALL}")
    print()

    # Check dependencies
    print("Dependencies:")
    import subprocess

    def check_command(cmd, version_flag='--version'):
        try:
            subprocess.run([cmd, version_flag], capture_output=True, check=True)
            return True
        except:
            return False

    # ffmpeg/ffprobe use -version (single dash), not --version
    ffmpeg_found = check_command('ffmpeg', '-version')
    ffprobe_found = check_command('ffprobe', '-version')
    print(f"  ffmpeg: {Style.BRIGHT}{Fore.GREEN}✓{Style.RESET_ALL}" if ffmpeg_found else f"  ffmpeg: {Style.BRIGHT}{Fore.RED}✗{Style.RESET_ALL} Not found")
    print(f"  ffprobe: {Style.BRIGHT}{Fore.GREEN}✓{Style.RESET_ALL}" if ffprobe_found else f"  ffprobe: {Style.BRIGHT}{Fore.RED}✗{Style.RESET_ALL} Not found")
    print()

    # Check API keys with parallel validation
    print("API Keys:")

    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Prepare validation tasks
    tasks = []
    if settings.openai_api_key:
        tasks.append(('OpenAI', settings.openai_api_key, _validate_openai_key))
    else:
        print(f"  OpenAI: {Style.BRIGHT}{Fore.RED}✗{Style.RESET_ALL} Not set")

    if settings.anthropic_api_key:
        tasks.append(('Anthropic', settings.anthropic_api_key, _validate_anthropic_key))
    else:
        print(f"  Anthropic: {Style.BRIGHT}{Fore.RED}✗{Style.RESET_ALL} Not set")

    if settings.elevenlabs_api_key:
        tasks.append(('ElevenLabs', settings.elevenlabs_api_key, _validate_elevenlabs_key))
    else:
        print(f"  ElevenLabs: {Style.BRIGHT}{Fore.RED}✗{Style.RESET_ALL} Not set")

    if settings.did_api_key:
        tasks.append(('D-ID', settings.did_api_key, _validate_did_key))
    else:
        print(f"  D-ID: {Style.BRIGHT}{Fore.RED}✗{Style.RESET_ALL} Not set (optional - only needed for avatar mode)")

    # Run validations in parallel
    results = {}
    if tasks:
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_service = {
                executor.submit(validate_fn, api_key): service_name
                for service_name, api_key, validate_fn in tasks
            }

            for future in as_completed(future_to_service):
                service_name = future_to_service[future]
                try:
                    status, error = future.result()
                    results[service_name] = (status, error)
                except Exception as e:
                    results[service_name] = (False, str(e))

    # Display results in order
    all_valid = True
    for service_name in ['OpenAI', 'Anthropic', 'ElevenLabs', 'D-ID']:
        if service_name in results:
            status, error = results[service_name]
            if status:
                print(f"  {service_name}: {Style.BRIGHT}{Fore.GREEN}✓{Style.RESET_ALL} Valid")
            else:
                print(f"  {service_name}: {Style.BRIGHT}{Fore.RED}✗{Style.RESET_ALL} Invalid")
                if verbose and error:
                    print(f"    {Fore.RED}Error: {error}{Style.RESET_ALL}")
                if service_name != 'D-ID':  # D-ID is optional
                    all_valid = False

    print()

    if all_valid and len(results) >= 3:  # At least OpenAI, Anthropic, ElevenLabs
        print(f"{Style.BRIGHT}{Fore.GREEN}✓{Style.RESET_ALL} All required API keys are valid and working!\n")
    else:
        print(f"{Fore.YELLOW}⚠ Some API keys are missing or invalid.{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Run 'nbj setup' to configure missing keys.{Style.RESET_ALL}")
        if not verbose:
            print(f"{Fore.YELLOW}Use 'nbj check --verbose' for detailed error messages.{Style.RESET_ALL}")
        print()


def _validate_openai_key(api_key: str) -> tuple[bool, str]:
    """Validate OpenAI API key."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        # Try to list models (lightweight call)
        client.models.list()
        return True, None
    except Exception as e:
        error_msg = str(e)
        # Extract the meaningful part of the error
        if "authentication" in error_msg.lower() or "unauthorized" in error_msg.lower():
            return False, "Invalid API key or authentication failed"
        elif "quota" in error_msg.lower() or "insufficient" in error_msg.lower():
            return False, "Insufficient quota or credits"
        return False, error_msg


def _validate_anthropic_key(api_key: str) -> tuple[bool, str]:
    """Validate Anthropic API key."""
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        # Try a minimal message (very cheap test)
        client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1,
            messages=[{"role": "user", "content": "test"}]
        )
        return True, None
    except Exception as e:
        error_msg = str(e)
        if "authentication" in error_msg.lower() or "invalid" in error_msg.lower():
            return False, "Invalid API key or authentication failed"
        elif "credit" in error_msg.lower() or "insufficient" in error_msg.lower():
            return False, "Insufficient credits"
        return False, error_msg


def _validate_elevenlabs_key(api_key: str) -> tuple[bool, str]:
    """Validate ElevenLabs API key."""
    try:
        from elevenlabs.client import ElevenLabs
        client = ElevenLabs(api_key=api_key)
        # Try to get user info or list voices (lightweight call)
        client.voices.get_all()
        return True, None
    except Exception as e:
        error_msg = str(e)
        if "unauthorized" in error_msg.lower() or "invalid" in error_msg.lower():
            return False, "Invalid API key or authentication failed"
        elif "quota" in error_msg.lower() or "limit" in error_msg.lower():
            return False, "Quota exceeded or limit reached"
        return False, error_msg


def _validate_did_key(api_key: str) -> tuple[bool, str]:
    """Validate D-ID API key."""
    try:
        import requests
        # Try to get credits (lightweight call)
        response = requests.get(
            "https://api.d-id.com/credits",
            headers={"Authorization": f"Basic {api_key}"},
            timeout=10
        )
        if response.status_code == 200:
            return True, None
        elif response.status_code == 401:
            return False, "Invalid API key or authentication failed"
        else:
            return False, f"HTTP {response.status_code}: {response.text}"
    except Exception as e:
        return False, str(e)


@cli.command()
@click.argument('files', nargs=-1, type=click.Path(exists=True), required=True)
@click.option('--voice', '-v', default='ryan', help='Voice name or ID (e.g., ryan, edge/ryan, en-GB-RyanNeural)')
@click.option('--rate', '-r', default='+12%', help='Speech rate (e.g., +12%, -10%, +0%)')
def tts(files, voice, rate):
    """
    Convert condensed text files to MP3 using Edge TTS.

    Examples:

        # Single file with voice shortcut
        nbj tts --voice=ryan test_outputs/yt_AnOduBHzmHs_agg_1.txt

        # Multiple files with full voice ID
        nbj tts --voice=en-GB-RyanNeural test_outputs/yt_*.txt

        # With custom speech rate
        nbj tts --voice=ryan --rate=+20% test_outputs/yt_AnOduBHzmHs_agg_1.txt

        # Process multiple files
        nbj tts --voice=ryan test_outputs/yt_*_agg_5.txt
    """
    # Suppress httpx INFO logs
    import logging as stdlib_logging
    stdlib_logging.getLogger('httpx').setLevel(stdlib_logging.WARNING)

    # Voice shortcuts for common Edge TTS voices
    VOICE_SHORTCUTS = {
        'ryan': 'en-GB-RyanNeural',
        'sonia': 'en-GB-SoniaNeural',
        'aria': 'en-US-AriaNeural',
        'guy': 'en-US-GuyNeural',
        'jenny': 'en-US-JennyNeural',
        'davis': 'en-US-DavisNeural',
        'jane': 'en-US-JaneNeural',
    }

    def extract_condensed_script(file_path: Path) -> str:
        """Extract condensed script from test output file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find text between first and second "===" lines
        parts = content.split('=' * 80)

        if len(parts) < 3:
            raise ValueError(f"Invalid file format: expected metadata + script + footer, got {len(parts)} sections")

        # The condensed script is in parts[1] (between first and second === lines)
        script = parts[1].strip()

        if not script:
            raise ValueError("No condensed script found in file")

        return script

    # Initialize TTS provider
    from .modules.edge_tts import EdgeTTS
    tts_provider = EdgeTTS()

    # Parse voice specification
    if voice.startswith('edge/'):
        voice = voice[5:]

    # Apply shortcuts first, then try to resolve as voice name
    if voice in VOICE_SHORTCUTS:
        voice_id = VOICE_SHORTCUTS[voice]
    else:
        voice_id = tts_provider.resolve_voice_name(voice)
        if not voice_id:
            click.echo(f"{Fore.RED}Error: Voice '{voice}' not found.{Style.RESET_ALL}")
            click.echo(f"{Fore.YELLOW}Run 'nbj voices --provider=edge' to see available voices.{Style.RESET_ALL}")
            sys.exit(1)

    print(f"{Fore.CYAN}Using Edge TTS{Style.RESET_ALL}")
    print(f"  Voice: {voice_id}")
    print(f"  Rate: {rate}\n")

    # Process each file
    success_count = 0
    error_count = 0

    for file_path_str in files:
        file_path = Path(file_path_str)

        print(f"{Fore.CYAN}Processing: {file_path.name}{Style.RESET_ALL}")

        try:
            # Extract condensed script
            script = extract_condensed_script(file_path)
            word_count = len(script.split())
            print(f"  Extracted script: {word_count:,} words")

            # Generate output path
            output_path = file_path.with_suffix('.mp3')

            # Generate TTS
            print(f"  Generating audio...")
            tts_provider.generate_speech(
                text=script,
                output_path=output_path,
                voice=voice_id,
                rate=rate
            )

            print(f"  {Fore.GREEN}✓ Saved to: {output_path}{Style.RESET_ALL}\n")
            success_count += 1

        except Exception as e:
            print(f"  {Fore.RED}✗ Error: {e}{Style.RESET_ALL}\n")
            error_count += 1

    # Summary
    print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Summary{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
    print(f"  Total files: {len(files)}")
    print(f"  Successful: {Fore.GREEN}{success_count}{Style.RESET_ALL}")
    print(f"  Failed: {Fore.RED}{error_count}{Style.RESET_ALL}")


@cli.command(name='tts-samples')
@click.option(
    '--file', '-f',
    type=click.Path(exists=True),
    help='Custom text file to use for sample (instead of default "To be or not to be")'
)
@click.option(
    '--output-dir', '-o',
    type=click.Path(),
    default='tts_samples',
    help='Output directory for samples (default: tts_samples)'
)
@click.option(
    '--rate', '-r',
    default='+0%',
    help='Speech rate (e.g., +12%, -10%, +0%)'
)
@click.option(
    '--lang', '-l',
    default='en',
    help='Language filter: prefix (e.g., "en") or comma-separated locales (e.g., "en-US,en-GB,en-IN")'
)
def tts_samples(file, output_dir, rate, lang):
    """
    Generate TTS samples for Edge TTS voices.

    For each voice, generates audio saying:
    "Hello, I'm [VoiceName], and this is what my voice sounds like. [sample text]"

    Examples:

        # Generate samples for all English voices with default text
        nbj tts-samples

        # Use custom sample text from file
        nbj tts-samples -f my_sample.txt

        # Only test en-GB voices
        nbj tts-samples --lang=en-GB

        # Test multiple specific locales
        nbj tts-samples --lang=en-US,en-GB,en-IN

        # Test all Spanish voices
        nbj tts-samples --lang=es

        # Custom output directory and speech rate
        nbj tts-samples -o voice_samples -r +20%
    """
    # Suppress httpx INFO logs
    import logging as stdlib_logging
    stdlib_logging.getLogger('httpx').setLevel(stdlib_logging.WARNING)

    DEFAULT_SAMPLE_TEXT = '"To be, or not to be. That is the question."'

    def extract_voice_name(full_voice_id: str) -> str:
        """Extract friendly name from full voice ID."""
        parts = full_voice_id.split('-')
        if len(parts) >= 3:
            name = parts[-1].replace('Neural', '').replace('Multilingual', '')
            return name
        return full_voice_id

    # Load sample text
    if file:
        sample_text = Path(file).read_text(encoding='utf-8').strip()
        print(f"{Fore.CYAN}Using custom sample text from: {file}{Style.RESET_ALL}")
    else:
        sample_text = DEFAULT_SAMPLE_TEXT
        print(f"{Fore.CYAN}Using default sample text{Style.RESET_ALL}")

    print(f"Sample text: {Fore.YELLOW}{sample_text[:100]}{'...' if len(sample_text) > 100 else ''}{Style.RESET_ALL}\n")

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Initialize TTS
    from .modules.edge_tts import EdgeTTS
    tts = EdgeTTS()

    # Get all voices
    print(f"{Fore.CYAN}Fetching available Edge TTS voices...{Style.RESET_ALL}")
    all_voices = tts.list_voices()

    # Parse language filter
    if ',' in lang:
        # Comma-separated list of specific locales
        requested_locales = [l.strip() for l in lang.split(',')]
        filtered_voices = [v for v in all_voices if v['locale'] in requested_locales]
        print(f"Found {len(filtered_voices)} voices for locales: {', '.join(requested_locales)}\n")
    elif '-' in lang:
        # Specific locale (e.g., "en-GB")
        filtered_voices = [v for v in all_voices if v['locale'] == lang]
        print(f"Found {len(filtered_voices)} voices for locale: {lang}\n")
    else:
        # Language prefix (e.g., "en" matches all "en-*")
        filtered_voices = [v for v in all_voices if v['locale'].startswith(f"{lang}-")]
        print(f"Found {len(filtered_voices)} voices for language: {lang}\n")

    if not filtered_voices:
        print(f"{Fore.RED}No voices found matching criteria{Style.RESET_ALL}")
        return

    # Group by locale for organized output
    voices_by_locale = {}
    for voice in filtered_voices:
        locale_key = voice['locale']
        if locale_key not in voices_by_locale:
            voices_by_locale[locale_key] = []
        voices_by_locale[locale_key].append(voice)

    # Generate samples
    success_count = 0
    error_count = 0
    total_voices = len(filtered_voices)

    for idx, (locale_name, voices) in enumerate(sorted(voices_by_locale.items()), 1):
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Locale: {locale_name} ({len(voices)} voices){Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")

        for voice in sorted(voices, key=lambda v: v['name']):
            full_voice_id = voice['name']
            voice_name = extract_voice_name(full_voice_id)
            gender = voice.get('gender', 'Unknown')

            # Build full text with introduction
            intro = f"Hello, I'm {voice_name}, and this is what my voice sounds like. "
            full_text = intro + sample_text

            # Output filename: locale_VoiceName_Gender.mp3
            output_filename = f"{locale_name}_{voice_name}_{gender}.mp3"
            output_file = output_path / output_filename

            print(f"  [{success_count + error_count + 1}/{total_voices}] {voice_name} ({gender})... ", end='', flush=True)

            try:
                tts.generate_speech(
                    text=full_text,
                    output_path=output_file,
                    voice=full_voice_id,
                    rate=rate
                )
                print(f"{Fore.GREEN}✓{Style.RESET_ALL}")
                success_count += 1

            except Exception as e:
                print(f"{Fore.RED}✗ Error: {e}{Style.RESET_ALL}")
                error_count += 1

        print()  # Blank line between locales

    # Summary
    print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Summary{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
    print(f"  Total voices: {total_voices}")
    print(f"  Successful: {Fore.GREEN}{success_count}{Style.RESET_ALL}")
    print(f"  Failed: {Fore.RED}{error_count}{Style.RESET_ALL}")
    print(f"  Output directory: {Fore.CYAN}{output_path.absolute()}{Style.RESET_ALL}")
    print()


if __name__ == '__main__':
    cli()
