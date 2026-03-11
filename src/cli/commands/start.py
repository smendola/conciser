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
@click.option(
    '-d',
    '--detach',
    is_flag=True,
    default=False,
    help='Run server in the background (logs to nbj.log).',
)
@click.pass_context
def start(ctx: click.Context, detach: bool) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    server_app = repo_root / 'server' / 'app.py'
    log_path = repo_root / 'nbj.log'
    pid_path = repo_root / 'nbj.pid'

    if not server_app.exists():
        print(f"{Fore.RED}Error: server entrypoint not found at {server_app}{Style.RESET_ALL}")
        sys.exit(1)

    python_exe = sys.executable or 'python'
    cmd = [python_exe, str(server_app), *ctx.args]

    try:
        if detach:
            with log_path.open('ab', buffering=0) as log_f:
                popen_kwargs: dict = {
                    'cwd': str(repo_root),
                    'env': os.environ.copy(),
                    'stdout': log_f,
                    'stderr': subprocess.STDOUT,
                    'stdin': subprocess.DEVNULL,
                }

                if os.name != 'nt':
                    popen_kwargs['start_new_session'] = True

                proc = subprocess.Popen(cmd, **popen_kwargs)

                try:
                    pid_path.write_text(str(proc.pid))
                except OSError:
                    pass

                print(
                    f"{Fore.GREEN}Server started in background (pid {proc.pid}). "
                    f"Logs: {log_path}{Style.RESET_ALL}"
                )
        else:
            subprocess.run(cmd, cwd=str(repo_root), env=os.environ.copy(), check=False)
    except FileNotFoundError:
        print(f"{Fore.RED}Error: failed to execute Python interpreter: {python_exe}{Style.RESET_ALL}")
        sys.exit(1)
    except KeyboardInterrupt:
        raise
