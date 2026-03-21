"""
Job persistence layer using SQLite.
Provides a thread-safe, durable store for job metadata, parameters, and events.
"""

import sqlite3
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from contextlib import contextmanager
import shutil

from src.config import get_settings


class JobStore:
    """SQLite-backed job storage."""

    def __init__(self, db_path: Optional[Path] = None):
        self.settings = get_settings()
        self.db_path = db_path or (self.settings.data_dir / "jobs.db")
        if db_path is None:
            self._best_effort_migrate_default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_schema()

    def _best_effort_migrate_default_db_path(self) -> None:
        """If an older DB exists in output_dir, copy it into data_dir on first run."""
        try:
            new_path = self.settings.data_dir / "jobs.db"
            old_path = self.settings.output_dir / "jobs.db"

            if new_path.exists():
                return
            if not old_path.exists():
                return

            new_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old_path, new_path)
        except Exception:
            return

    @contextmanager
    def _conn(self):
        """Get a thread-local SQLite connection with WAL mode."""
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0,
            )
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn.row_factory = sqlite3.Row
        try:
            yield self._local.conn
        except Exception:
            self._local.conn.rollback()
            raise

    def _init_schema(self):
        """Create tables if they don't exist."""
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    title TEXT,
                    channel_name TEXT,
                    job_type TEXT NOT NULL,  -- 'condense' or 'takeaways'
                    status TEXT NOT NULL DEFAULT 'queued',  -- queued, processing, completed, error, deleted
                    progress TEXT,
                    output_file TEXT,
                    error TEXT,
                    client_id TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS job_params (
                    job_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT,
                    PRIMARY KEY (job_id, key),
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS job_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    message TEXT,
                    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS shareable (
                    secure_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    client_id TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
                CREATE INDEX IF NOT EXISTS idx_jobs_client_id ON jobs(client_id);
                CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id);
                CREATE INDEX IF NOT EXISTS idx_shareable_job_id ON shareable(job_id);
            """)
            conn.commit()

            # Best-effort migration for older DBs: ensure status column can hold 'deleted'
            # (SQLite doesn't enforce enum-like constraints here; this exists just to keep
            # the in-code comment/schema up to date without requiring manual migrations.)

    def create_job(
        self,
        job_id: str,
        url: str,
        title: Optional[str],
        channel_name: Optional[str],
        job_type: str,
        client_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new job record."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO jobs (id, url, title, channel_name, job_type, client_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, url, title or "", channel_name or "", job_type, client_id),
            )
            if params:
                conn.executemany(
                    """
                    INSERT INTO job_params (job_id, key, value)
                    VALUES (?, ?, ?)
                    """,
                    [(job_id, k, json.dumps(v)) for k, v in params.items()],
                )
            conn.commit()
        return job_id

    def update_status(self, job_id: str, status: str, progress: Optional[str] = None) -> None:
        """Update job status and optional progress message."""
        with self._conn() as conn:
            if status == "completed":
                conn.execute(
                    """
                    UPDATE jobs SET status = ?, progress = ?, completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (status, progress, job_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE jobs SET status = ?, progress = ?
                    WHERE id = ?
                    """,
                    (status, progress, job_id),
                )
            conn.commit()

    def set_error(self, job_id: str, error: str) -> None:
        """Mark job as errored with message."""
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE jobs SET status = 'error', error = ?, completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (error, job_id),
            )
            conn.commit()

    def set_output_file(self, job_id: str, output_file: str) -> None:
        """Set the output file path for a completed job."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET output_file = ? WHERE id = ?",
                (output_file, job_id),
            )
            conn.commit()

    def add_event(self, job_id: str, stage: str, message: str) -> None:
        """Add a progress event for a job."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO job_events (job_id, stage, message)
                VALUES (?, ?, ?)
                """,
                (job_id, stage, message),
            )
            conn.commit()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job details including parameters."""
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM jobs WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
            if not row:
                return None

            job = dict(row)
            # Load parameters
            params_rows = conn.execute(
                """
                SELECT key, value FROM job_params WHERE job_id = ?
                """,
                (job_id,),
            ).fetchall()
            job["params"] = {k: json.loads(v) for k, v in params_rows}
            return job

    def list_jobs(
        self,
        client_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """List jobs with optional filters."""
        with self._conn() as conn:
            query = "SELECT * FROM jobs WHERE 1=1"
            args = []
            if client_id:
                query += " AND client_id = ?"
                args.append(client_id)
            if status:
                query += " AND status = ?"
                args.append(status)
            else:
                query += " AND status != 'deleted'"
            query += " ORDER BY created_at DESC"
            if limit:
                query += " LIMIT ?"
                args.append(limit)

            rows = conn.execute(query, args).fetchall()
            return [dict(r) for r in rows]

    def is_new_client(self, client_id: str) -> bool:
        """Return True if this client_id has never submitted a job before."""
        if not client_id:
            return False
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM jobs WHERE client_id = ? LIMIT 1",
                (client_id,),
            ).fetchone()
            return row is None

    def get_active_job_for_client(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Return the most recent active job (queued/processing) for a client."""
        if not client_id:
            return None
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM jobs
                WHERE client_id = ?
                  AND status IN ('queued', 'processing')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (client_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_next_queued_job(self, job_types: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Get the next queued job for processing."""
        with self._conn() as conn:
            query = """
                UPDATE jobs 
                SET status = 'processing'
                WHERE id = (
                    SELECT id FROM (
                        SELECT id FROM jobs 
                        WHERE status = 'queued'
            """
            args = []
            if job_types:
                placeholders = ",".join(["?"] * len(job_types))
                query += f" AND job_type IN ({placeholders})"
                args.extend(job_types)

            query += """
                        ORDER BY created_at ASC LIMIT 1
                    ) AS subquery
                )
                RETURNING *
            """

            row = conn.execute(query, args).fetchone()
            conn.commit()
            return dict(row) if row else None

    def reset_stale_processing_jobs(self) -> int:
        """Reset jobs stuck in 'processing' back to 'queued' on startup."""
        with self._conn() as conn:
            cursor = conn.execute(
                """
                UPDATE jobs SET status = 'queued', progress = NULL
                WHERE status = 'processing'
                """
            )
            count = cursor.rowcount
            conn.commit()
            return count

    def delete_job(self, job_id: str) -> bool:
        """Delete a job and all its data."""
        with self._conn() as conn:
            cursor = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            conn.commit()
            return cursor.rowcount > 0

    def mark_deleted(self, job_id: str) -> bool:
        """Soft-delete a job (do not remove DB rows or files)."""
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE jobs SET status = 'deleted' WHERE id = ?",
                (job_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def create_shareable(self, job_id: str, client_id: Optional[str]) -> str:
        """Create a shareable token for a job. Idempotent — returns existing token if already created."""
        import secrets
        with self._conn() as conn:
            row = conn.execute(
                "SELECT secure_id FROM shareable WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row:
                return row["secure_id"]
            secure_id = secrets.token_urlsafe(32)
            conn.execute(
                "INSERT INTO shareable (secure_id, job_id, client_id) VALUES (?, ?, ?)",
                (secure_id, job_id, client_id),
            )
            conn.commit()
            return secure_id

    def get_shareable_for_job(self, job_id: str) -> Optional[str]:
        """Return the secure_id for a job, or None if not yet created."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT secure_id FROM shareable WHERE job_id = ?", (job_id,)
            ).fetchone()
            return row["secure_id"] if row else None

    def get_job_by_shareable(self, secure_id: str) -> Optional[Dict[str, Any]]:
        """Resolve a secure_id to its job, or None if not found."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT job_id FROM shareable WHERE secure_id = ?", (secure_id,)
            ).fetchone()
            if not row:
                return None
            return self.get_job(row["job_id"])

    def get_job_events(self, job_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get progress events for a job."""
        with self._conn() as conn:
            query = """
                SELECT stage, message, timestamp 
                FROM job_events 
                WHERE job_id = ?
                ORDER BY timestamp ASC
            """
            args = [job_id]
            if limit:
                query += " LIMIT ?"
                args.append(limit)

            rows = conn.execute(query, args).fetchall()
            return [dict(r) for r in rows]
