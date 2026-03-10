import os
import sys
import subprocess
from pathlib import Path

import click
from colorama import Fore, Style

from ..app import cli


@cli.command(
    context_settings={
        'ignore_unknown_options': True,
        'allow_extra_args': True,
    }
)
@click.pass_context
def serve(ctx: click.Context) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    server_app = repo_root / 'server' / 'app.py'

    if not server_app.exists():
        print(f"{Fore.RED}Error: server entrypoint not found at {server_app}{Style.RESET_ALL}")
        sys.exit(1)

    python_exe = sys.executable or 'python'
    cmd = [python_exe, str(server_app), *ctx.args]

    try:
        subprocess.run(cmd, cwd=str(repo_root), env=os.environ.copy(), check=False)
    except FileNotFoundError:
        print(f"{Fore.RED}Error: failed to execute Python interpreter: {python_exe}{Style.RESET_ALL}")
        sys.exit(1)
    except KeyboardInterrupt:
        raise
