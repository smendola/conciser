import sys

import click
from colorama import Fore, Style

from ...config import get_settings
from ..common import _format_script_into_paragraphs

from ..app import cli


@cli.command(name='show-script')
@click.argument('url_or_video_id')
@click.option(
    '--format/--no-format',
    default=True,
    help='Format script into paragraphs using AI (default: enabled)'
)
@click.option(
    '--aggressiveness', '-a',
    type=click.IntRange(1, 10),
    default=5,
    help='Aggressiveness level used when condensing (must match). Default: 5'
)
def show_script(url_or_video_id, format, aggressiveness):
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

    import logging

    logger = logging.getLogger(__name__)

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
        script_path = video_folder / f"condensed_script_a{aggressiveness}.json"
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
                        logger.debug(f"Saving formatted script: {script_path}")
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
