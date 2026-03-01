import click
from colorama import Fore, Style
from pathlib import Path

from ...config import get_settings

from ..app import cli


@cli.command(name='tts-samples')
@click.option(
    '--provider',
    type=click.Choice(['edge', 'elevenlabs']),
    default='edge',
    help='TTS provider to generate samples for. Default: edge'
)
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
def tts_samples(provider, file, output_dir, rate, lang):
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
    if provider == 'edge':
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
    total_voices = len(filtered_voices)

    for idx, (group_name, voices) in enumerate(sorted(voices_by_group.items()), 1):
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
        if provider == 'edge':
            print(f"{Fore.CYAN}Locale: {group_name} ({len(voices)} voices){Style.RESET_ALL}")
        else:
            print(f"{Fore.CYAN}Category: {group_name} ({len(voices)} voices){Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")

        for voice in sorted(voices, key=lambda v: v['name']):
            if provider == 'edge':
                full_voice_id = voice['name']
                voice_name = extract_voice_name(full_voice_id)
                gender = voice.get('gender', 'Unknown')
                voice_id_for_generation = full_voice_id
            else:
                voice_id_for_generation = voice['voice_id']
                voice_name = voice.get('name') or voice_id_for_generation
                gender = voice.get('labels', {}).get('gender', 'Unknown') if isinstance(voice.get('labels'), dict) else 'Unknown'

            # Build full text with introduction
            intro = f"Hello, I'm {voice_name}, and this is what my voice sounds like. "
            full_text = intro + sample_text

            # Output filename
            import re
            safe_voice = re.sub(r'[^a-zA-Z0-9._-]+', '_', str(voice_name)).strip('_')
            output_filename = f"{safe_voice or 'voice'}.mp3"
            output_file = provider_output_path / output_filename

            # Handle collisions (e.g., duplicate friendly names)
            if output_file.exists():
                stem = output_file.stem
                suffix = output_file.suffix
                counter = 2
                while True:
                    candidate = provider_output_path / f"{stem}_{counter}{suffix}"
                    if not candidate.exists():
                        output_file = candidate
                        break
                    counter += 1

            print(f"  [{success_count + error_count + 1}/{total_voices}] {voice_name} ({gender})... ", end='', flush=True)

            try:
                if provider == 'edge':
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
    print(f"  Output directory: {provider_output_path}")
    print()
