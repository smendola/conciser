import sys

import click
from colorama import Fore, Style

from ...config import get_settings

from ..app import cli


@cli.command()
def init():
    """
    Pre-initialize OpenAI Responses API chains for all 10 aggressiveness levels.

    Sends the system prompt for each level to the model once and stores the
    resulting response IDs in condenser_chains.json. Subsequent condense jobs
    continue from the appropriate chain tip instead of re-sending system prompts.

    Re-run this command whenever you update the prompt templates.
    """
    from ...modules.condenser import ContentCondenser
    from ...utils.chain_store import CHAINS_FILE

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
