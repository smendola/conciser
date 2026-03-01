import sys

import click
from colorama import Fore, Style

from ...config import get_settings

from ..app import cli


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
            from ...modules.edge_tts import EdgeTTS

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

        from ...modules.tts import VoiceCloner

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
