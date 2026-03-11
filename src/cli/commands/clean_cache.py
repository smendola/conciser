import os
import time
from pathlib import Path

import click
from colorama import Fore, Style

from ...config import get_settings
from ..app import cli
from ..common import parse_age_to_timedelta


def _suppress_httpx_info_logs() -> None:
    import logging as stdlib_logging
    stdlib_logging.getLogger('httpx').setLevel(stdlib_logging.WARNING)


def _iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip hidden dirs? keep as-is to avoid missing files.
        for fname in filenames:
            yield Path(dirpath) / fname


def _safe_unlink(path: Path) -> bool:
    try:
        if path.exists() and path.is_file():
            path.unlink()
            return True
    except Exception:
        return False
    return False


@cli.command(name="clean-cache")
@click.option(
    '--age',
    required=False,
    help="Only delete files with access time older than this age. Format: 3h or 2d (e.g. 6h, 2d)"
)
def clean_cache(age):
    """Clean temp/cache files in temp_dir (never touches output_dir)."""
    _suppress_httpx_info_logs()

    try:
        settings = get_settings()
        temp_dir = settings.temp_dir

        if not temp_dir.exists():
            print(f"{Fore.YELLOW}Temp directory not found: {temp_dir}{Style.RESET_ALL}")
            return

        cutoff_ts = None
        if age:
            delta = parse_age_to_timedelta(age)
            cutoff_ts = time.time() - delta.total_seconds()

        deleted = 0
        scanned = 0

        for p in _iter_files(temp_dir):
            scanned += 1
            try:
                st = p.stat()
            except Exception:
                continue

            if cutoff_ts is not None:
                # Access time filter
                if st.st_atime >= cutoff_ts:
                    continue

            if _safe_unlink(p):
                deleted += 1

        print(f"{Fore.GREEN}Deleted {deleted} file(s) from temp cache.{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Scanned {scanned} file(s).{Style.RESET_ALL}")

    except ValueError as e:
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        raise SystemExit(2)
    except Exception as e:
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        raise SystemExit(1)
