from pathlib import Path

import click

from colorama import Fore, Style

from ..app import cli


@cli.command()
def setup():
    """
    Interactive setup wizard to configure API keys.
    """
    import logging

    logger = logging.getLogger(__name__)

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

    logger.info("Writing configuration: .env")
    with open('.env', 'w') as f:
        f.write(env_content)

    print(f"\n{Fore.GREEN}Setup complete! .env file created.{Style.RESET_ALL}")
    print(f"\nYou can now run: {Fore.CYAN}conciser condense <youtube_url>{Style.RESET_ALL}\n")
