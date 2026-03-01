import sys
from pathlib import Path

import click
from colorama import Fore, Style

from ..app import cli


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
    from ...modules.edge_tts import EdgeTTS
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
