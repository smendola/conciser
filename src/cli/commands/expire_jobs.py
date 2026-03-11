import os
import sqlite3
from datetime import datetime, timezone

import click
from colorama import Fore, Style

from ...config import get_settings
from ..app import cli
from ..common import parse_age_to_timedelta


def _suppress_httpx_info_logs() -> None:
    import logging as stdlib_logging
    stdlib_logging.getLogger('httpx').setLevel(stdlib_logging.WARNING)


def _parse_sqlite_timestamp(ts: str) -> datetime:
    if not ts:
        return None
    ts = str(ts)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _safe_unlink(path) -> bool:
    try:
        if path.exists() and path.is_file():
            path.unlink()
            return True
    except Exception:
        return False
    return False


@cli.command(name="expire-jobs")
@click.option(
    '--age',
    required=True,
    help="Expire jobs older than this age. Format: 3h or 2d (e.g. 6h, 2d)"
)
def expire_jobs(age):
    """Expire old jobs: mark as deleted and delete associated output artifacts."""
    _suppress_httpx_info_logs()

    try:
        cutoff_delta = parse_age_to_timedelta(age)
        settings = get_settings()
        output_dir = settings.output_dir
        db_path = settings.data_dir / "jobs.db"

        if not db_path.exists():
            print(f"{Fore.YELLOW}No jobs database found at: {db_path}{Style.RESET_ALL}")
            return

        now = datetime.now(timezone.utc)
        cutoff = now - cutoff_delta

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """
            SELECT id, status, output_file, created_at, completed_at
            FROM jobs
            WHERE status != 'deleted'
            """
        ).fetchall()

        to_expire = []
        for r in rows:
            created_at = _parse_sqlite_timestamp(r['created_at'])
            completed_at = _parse_sqlite_timestamp(r['completed_at'])
            job_ts = completed_at or created_at
            if job_ts and job_ts < cutoff:
                to_expire.append(dict(r))

        expired = 0
        deleted_files = 0

        for job in to_expire:
            job_id = job['id']

            output_file = job.get('output_file')
            if output_file:
                output_path = output_dir / output_file if not os.path.isabs(str(output_file)) else None
                if output_path is None:
                    # If absolute, only allow deletions inside output_dir
                    try:
                        output_path = (output_dir / os.path.relpath(str(output_file), str(output_dir))).resolve()
                    except Exception:
                        output_path = None

                if output_path is not None:
                    try:
                        resolved_output_dir = output_dir.resolve()
                        resolved_output_path = output_path.resolve()
                        if resolved_output_dir in resolved_output_path.parents or resolved_output_path == resolved_output_dir:
                            if _safe_unlink(resolved_output_path):
                                deleted_files += 1
                    except Exception:
                        pass

            # Best-effort: delete any artifacts with job_id prefix in output_dir
            try:
                for p in output_dir.glob(f"{job_id}*"):
                    if p.is_file():
                        if _safe_unlink(p):
                            deleted_files += 1
            except Exception:
                pass

            conn.execute("UPDATE jobs SET status = 'deleted' WHERE id = ?", (job_id,))
            expired += 1

        conn.commit()
        conn.close()

        if not to_expire:
            print(f"{Fore.YELLOW}No jobs older than cutoff found.{Style.RESET_ALL}")
            return

        print(f"{Fore.GREEN}Expired {expired} job(s).{Style.RESET_ALL}")
        print(f"{Fore.GREEN}Deleted {deleted_files} output file(s).{Style.RESET_ALL}")

    except ValueError as e:
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        raise SystemExit(2)
    except Exception as e:
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        raise SystemExit(1)
