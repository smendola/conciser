import sys

import click
from colorama import Fore, Style

from ...config import get_settings

from ..app import cli


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
        from ...modules.downloader import VideoDownloader

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
