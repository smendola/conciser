import click
from colorama import Fore, Style
from pathlib import Path

from ...config import get_settings

from ..app import cli


@cli.command(name='voice-samples')
@click.option(
    '--provider',
    type=click.Choice(['edge', 'elevenlabs', 'azure']),
    default='azure',
    help='TTS provider to generate samples for. Default: azure'
)
@click.option(
    '--file', '-f',
    type=click.Path(exists=True),
    help='Custom text file to use for sample (instead of default "To be or not to be")'
)
@click.option(
    '--output-dir', '-o',
    type=click.Path(),
    default='voice_samples',
    help='Output directory for samples (default: voice_samples)'
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
@click.option(
    '--resume',
    is_flag=True,
    help='Skip voices whose output already exists on disk'
)
def tts_samples(provider, file, output_dir, rate, lang, resume):
    """
    Generate TTS samples for Edge TTS voices.

    For each voice, generates audio saying:
    "Hello, I'm [VoiceName], and this is what my voice sounds like. [sample text]"

    Examples:

        # Generate samples for all English voices with default text
        nbj voice-samples

        # Use custom sample text from file
        nbj voice-samples -f my_sample.txt

        # Only test en-GB voices
        nbj voice-samples --lang=en-GB

        # Test multiple specific locales
        nbj voice-samples --lang=en-US,en-GB,en-IN

        # Test all Spanish voices
        nbj voice-samples --lang=es

        # Custom output directory and speech rate
        nbj voice-samples -o voice_samples -r +20%
    """
    # Suppress httpx INFO logs
    import logging as stdlib_logging
    stdlib_logging.getLogger('httpx').setLevel(stdlib_logging.WARNING)

    DEFAULT_SAMPLE_TEXT = '"To be, or not to be. That is the question."'

    def locale_dir_parts(locale: str) -> tuple[str, str]:
        parts = (locale or '').split('-', 1)
        if len(parts) == 2 and parts[0] and parts[1]:
            return parts[0], parts[1]
        return (locale or 'unknown'), 'unknown'

    def voice_dir_name(locale: str, full_voice_id: str) -> str:
        """Directory name for a voice: full voice ID minus the locale prefix."""
        prefix = f"{locale}-"
        if full_voice_id.startswith(prefix):
            return full_voice_id[len(prefix):]
        return full_voice_id

    def intro_voice_name(locale: str, full_voice_id: str) -> str:
        """Friendly first-name-only for spoken intro, derived from full voice ID."""
        base = voice_dir_name(locale or 'unknown', full_voice_id)
        for token in ("Multilingual", "Expressive", "Turbo", "Neural"):
            base = base.replace(token, "")
        base = base.strip()
        return (base.split(" ", 1)[0] or base) if base else full_voice_id

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

    # Provider subdirectory
    provider_output_path = output_path / provider
    provider_output_path.mkdir(parents=True, exist_ok=True)

    if provider == 'edge':
        # Initialize TTS
        from ...modules.edge_tts import EdgeTTS
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
    elif provider == 'azure':
        # Azure TTS
        settings = get_settings()
        if not settings.azure_speech_key or not settings.azure_speech_region:
            print(f"{Fore.RED}Error: AZURE_SPEECH_KEY and AZURE_SPEECH_REGION not set.{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Set these environment variables to use Azure TTS.{Style.RESET_ALL}")
            return

        from ...modules.azure_tts import AzureTTS
        tts = AzureTTS(settings.azure_speech_key, settings.azure_speech_region)

        # Get all voices
        print(f"{Fore.CYAN}Fetching available Azure TTS voices...{Style.RESET_ALL}")

        # Parse language filter
        if ',' in lang:
            # Comma-separated list of specific locales
            requested_locales = [l.strip() for l in lang.split(',')]
            all_voices = []
            for locale in requested_locales:
                all_voices.extend(tts.list_voices(locale_filter=locale))
            filtered_voices = all_voices
            print(f"Found {len(filtered_voices)} voices for locales: {', '.join(requested_locales)}\n")
        elif '-' in lang:
            # Specific locale (e.g., "en-GB")
            filtered_voices = tts.list_voices(locale_filter=lang)
            print(f"Found {len(filtered_voices)} voices for locale: {lang}\n")
        else:
            # Language prefix (e.g., "en" matches all "en-*")
            filtered_voices = tts.list_voices(locale_filter=lang)
            print(f"Found {len(filtered_voices)} voices for language: {lang}\n")
    else:
        # ElevenLabs
        settings = get_settings()
        if not settings.elevenlabs_api_key:
            print(f"{Fore.RED}Error: ELEVENLABS_API_KEY not set.{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Run 'nbj setup' to configure.{Style.RESET_ALL}")
            return

        if lang and lang != 'en':
            print(f"{Fore.YELLOW}Warning: --lang is not supported for ElevenLabs voices. Ignoring.{Style.RESET_ALL}")
        if rate and rate != '+0%':
            print(f"{Fore.YELLOW}Warning: --rate only applies to Edge TTS. Ignoring.{Style.RESET_ALL}")

        from ...modules.tts import VoiceCloner
        tts = VoiceCloner(settings.elevenlabs_api_key)

        print(f"{Fore.CYAN}Fetching available ElevenLabs voices...{Style.RESET_ALL}")
        filtered_voices = tts.list_voices()
        print(f"Found {len(filtered_voices)} voices\n")

    if not filtered_voices:
        print(f"{Fore.RED}No voices found matching criteria{Style.RESET_ALL}")
        return

    # Group for organized output
    voices_by_group = {}
    if provider in ['edge', 'azure']:
        for voice in filtered_voices:
            group_key = voice['locale']
            if group_key not in voices_by_group:
                voices_by_group[group_key] = []
            voices_by_group[group_key].append(voice)
    else:
        for voice in filtered_voices:
            group_key = voice.get('category') or 'unknown'
            if group_key not in voices_by_group:
                voices_by_group[group_key] = []
            voices_by_group[group_key].append(voice)

    # Generate samples
    success_count = 0
    error_count = 0
    skipped_count = 0
    total_voices = len(filtered_voices)

    for idx, (group_name, voices) in enumerate(sorted(voices_by_group.items()), 1):
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
        if provider in ['edge', 'azure']:
            print(f"{Fore.CYAN}Locale: {group_name} ({len(voices)} voices){Style.RESET_ALL}")
        else:
            print(f"{Fore.CYAN}Category: {group_name} ({len(voices)} voices){Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")

        for voice in sorted(voices, key=lambda v: v['name']):
            if provider in ['edge', 'azure']:
                locale = voice.get('locale') or ''
                full_voice_id = voice['name']
                voice_name = full_voice_id
                gender = voice.get('gender', 'Unknown')
                voice_id_for_generation = full_voice_id
                spoken_name = intro_voice_name(locale, full_voice_id)
            else:
                locale = 'unknown'
                voice_id_for_generation = voice['voice_id']
                voice_name = voice.get('name') or voice_id_for_generation
                gender = voice.get('labels', {}).get('gender', 'Unknown') if isinstance(voice.get('labels'), dict) else 'Unknown'
                spoken_name = voice_name

            # Build full text with introduction
            intro = f"Hello, I'm {spoken_name}, and this is what my voice sounds like. "
            full_text = intro + sample_text

            # Output directory: provider/lang/country
            lang_part, country_part = locale_dir_parts(locale)
            output_dir_path = provider_output_path / lang_part / country_part
            output_dir_path.mkdir(parents=True, exist_ok=True)

            # Output filename: voice name minus locale prefix
            import re
            voice_file_stem = voice_dir_name(locale or 'unknown', str(voice_name))
            safe_stem = re.sub(r'[^a-zA-Z0-9._-]+', '_', str(voice_file_stem)).strip('_')
            output_filename = f"{safe_stem or 'voice'}.mp3"
            output_file = output_dir_path / output_filename

            if resume and output_file.exists():
                skipped_count += 1
                print(f"  [{success_count + error_count + skipped_count}/{total_voices}] {voice_name} ({gender})... {Fore.YELLOW}skipped{Style.RESET_ALL}")
                continue

            # Handle collisions (e.g., duplicate friendly names)
            if output_file.exists():
                stem = output_file.stem
                suffix = output_file.suffix
                counter = 2
                while True:
                    candidate = output_dir_path / f"{stem}_{counter}{suffix}"
                    if not candidate.exists():
                        output_file = candidate
                        break
                    counter += 1

            print(f"  [{success_count + error_count + 1}/{total_voices}] {voice_name} ({gender})... ", end='', flush=True)

            try:
                if provider in ['edge', 'azure']:
                    tts.generate_speech(
                        text=full_text,
                        output_path=output_file,
                        voice=voice_id_for_generation,
                        rate=rate
                    )
                else:
                    tts.generate_speech(
                        text=full_text,
                        voice_id=voice_id_for_generation,
                        output_path=output_file
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
    print(f"  Skipped: {Fore.YELLOW}{skipped_count}{Style.RESET_ALL}")
    print(f"  Output directory: {provider_output_path}")
    print()
