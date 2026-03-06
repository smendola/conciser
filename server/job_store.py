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

from src.config import get_settings


class JobStore:
    """SQLite-backed job storage."""

    def __init__(self, db_path: Optional[Path] = None):
        self.settings = get_settings()
        self.db_path = db_path or (self.settings.output_dir / "jobs.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_schema()

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
                    job_type TEXT NOT NULL,  -- 'condense' or 'takeaways'
                    status TEXT NOT NULL DEFAULT 'queued',  -- queued, processing, completed, error
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

                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
                CREATE INDEX IF NOT EXISTS idx_jobs_client_id ON jobs(client_id);
                CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id);
            """)
            conn.commit()

    def create_job(
        self,
        job_id: str,
        url: str,
        title: Optional[str],
        job_type: str,
        client_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new job record."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO jobs (id, url, title, job_type, client_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, url, title or "", job_type, client_id),
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
            query += " ORDER BY created_at DESC"
            if limit:
                query += " LIMIT ?"
                args.append(limit)

            rows = conn.execute(query, args).fetchall()
            return [dict(r) for r in rows]

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
