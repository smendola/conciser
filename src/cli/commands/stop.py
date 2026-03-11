import os
import signal
from pathlib import Path

import click
from colorama import Fore, Style

from ..app import cli


@cli.command()
@click.option(
    '-f',
    '--force',
    is_flag=True,
    default=False,
    help='Force kill the server (SIGKILL) if it does not stop gracefully.',
)
def stop(force: bool) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    pid_path = repo_root / 'nbj.pid'

    if not pid_path.exists():
        print(f"{Fore.RED}Error: {pid_path} not found. Is the server running?{Style.RESET_ALL}")
        raise SystemExit(1)

    try:
        pid_str = pid_path.read_text().strip()
        pid = int(pid_str)
    except (OSError, ValueError):
        print(f"{Fore.RED}Error: could not read a valid PID from {pid_path}{Style.RESET_ALL}")
        raise SystemExit(1)

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        try:
            pid_path.unlink()
        except OSError:
            pass
        print(f"{Fore.YELLOW}No process found for pid {pid}. Removed stale pidfile.{Style.RESET_ALL}")
        return
    except PermissionError:
        print(f"{Fore.RED}Error: insufficient permissions to signal pid {pid}{Style.RESET_ALL}")
        raise SystemExit(1)

    try:
        os.kill(pid, signal.SIGTERM)
        print(f"{Fore.GREEN}Sent SIGTERM to server pid {pid}.{Style.RESET_ALL}")
    except OSError as e:
        print(f"{Fore.RED}Error: failed to stop pid {pid}: {e}{Style.RESET_ALL}")
        raise SystemExit(1)

    if force:
        try:
            os.kill(pid, signal.SIGKILL)
            print(f"{Fore.YELLOW}Sent SIGKILL to server pid {pid}.{Style.RESET_ALL}")
        except OSError:
            pass

    try:
        pid_path.unlink()
    except OSError:
        pass
