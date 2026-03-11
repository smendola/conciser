"""
Job service layer: orchestrates job lifecycle, queue, and worker pool.
Provides the bridge between HTTP handlers and the underlying job store/workers.
"""

import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
import concurrent.futures

from server.job_store import JobStore
from src.config import get_settings
from src.pipeline import CondenserPipeline

logger = logging.getLogger(__name__)


class JobService:
    """Central job management service with queue and worker pool."""

    def __init__(self, max_workers: int = 3):
        self.store = JobStore()
        self.settings = get_settings()
        self.max_workers = max_workers
        self.executor = None
        self._shutdown = False
        self._workers_lock = threading.Lock()
        self._running_jobs = set()  # job_ids currently being processed

        # Reset any stale jobs on startup
        stale = self.store.reset_stale_processing_jobs()
        if stale:
            logger.info(f"Reset {stale} stale jobs to queued")

    def start(self):
        """Start the worker pool."""
        if self.executor:
            return
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="JobWorker",
        )
        logger.info(f"JobService started with {self.max_workers} workers")

    def stop(self, wait: bool = True):
        """Stop the worker pool gracefully."""
        if not self.executor:
            return
        self._shutdown = True
        self.executor.shutdown(wait=wait)
        self.executor = None
        logger.info("JobService stopped")

    def create_job(
        self,
        url: str,
        job_type: str,
        title: Optional[str] = None,
        channel_name: Optional[str] = None,
        client_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new job and queue it for processing."""
        job_id = str(uuid.uuid4())[:8]
        self.store.create_job(job_id, url, title, channel_name, job_type, client_id, params)
        logger.info(f"Created job {job_id} ({job_type}) for client {client_id}")
        return job_id

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job details."""
        return self.store.get_job(job_id)

    def list_jobs(
        self,
        client_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """List jobs with optional filters."""
        return self.store.list_jobs(client_id, status, limit)

    def update_progress(self, job_id: str, stage: str, message: str) -> None:
        """Update job progress."""
        progress = f"[{stage}] {message}"
        self.store.update_status(job_id, "processing", progress)
        self.store.add_event(job_id, stage, message)

    def mark_completed(self, job_id: str, output_file: str) -> None:
        """Mark job as completed with output file."""
        self.store.set_output_file(job_id, output_file)
        self.store.update_status(job_id, "completed")
        logger.info(f"Job {job_id} completed: {output_file}")

    def mark_error(self, job_id: str, error: str) -> None:
        """Mark job as errored."""
        self.store.set_error(job_id, error)
        logger.error(f"Job {job_id} error: {error}")

    def get_queue_position(self, job_id: str) -> Optional[int]:
        """Get position of a queued job in the queue (0-based)."""
        job = self.store.get_job(job_id)
        if not job or job["status"] != "queued":
            return None
        # Count queued jobs created before this one
        queued_jobs = self.store.list_jobs(status="queued")
        earlier = [j for j in queued_jobs if j["created_at"] <= job["created_at"]]
        return len(earlier) - 1

    def _process_job(self, job_id: str) -> None:
        """Worker function to process a single job."""
        logger.info(f"Starting to process job {job_id}")
        try:
            with self._workers_lock:
                self._running_jobs.add(job_id)

            job = self.store.get_job(job_id)
            if not job:
                logger.error(f"Job {job_id} not found in database")
                return

            logger.info(f"Found job {job_id} with type {job['job_type']}")
            # Status is already set to 'processing' in get_next_queued_job

            if job["job_type"] == "condense":
                self._process_condense(job)
            elif job["job_type"] == "takeaways":
                self._process_takeaways(job)
            else:
                raise ValueError(f"Unknown job type: {job['job_type']}")

        except Exception as e:
            logger.exception(f"Error processing job {job_id}: {e}")
            self.mark_error(job_id, str(e))
        finally:
            with self._workers_lock:
                self._running_jobs.discard(job_id)
            logger.info(f"Finished processing job {job_id}")

    def _process_condense(self, job: Dict[str, Any]) -> None:
        """Process a condense job."""
        job_id = job["id"]
        params = job.get("params", {})

        pipeline = CondenserPipeline(self.settings)

        # Determine output path
        jobs_dir = self.settings.output_dir / "jobs"
        jobs_dir.mkdir(parents=True, exist_ok=True)

        video_id = None
        try:
            video_id = CondenserPipeline._extract_video_id(job["url"])
        except Exception:
            pass

        suffix = f"_vid-{video_id}" if video_id else ""
        output_ext = "mp3" if params.get("video_mode") == "audio_only" else "mp4"
        output_path = jobs_dir / f"{job_id}{suffix}.{output_ext}"

        result = pipeline.run(
            video_url=job["url"],
            aggressiveness=params.get("aggressiveness", 5),
            output_path=output_path,
            quality="1080p",
            video_gen_mode=params.get("video_mode", "slideshow"),
            tts_provider=params.get("tts_provider", self.settings.tts_provider),
            voice_id=params.get("voice", "en-US-AriaNeural"),
            tts_rate=params.get("speech_rate", "+0%"),
            skip_voice_clone=True,
            progress_callback=lambda s, m: self.update_progress(job_id, s, m),
            resume=self.settings.resume,
            prepend_intro=params.get("prepend_intro", False),
        )

        self.mark_completed(job_id, str(output_path))

    def _process_takeaways(self, job: Dict[str, Any]) -> None:
        """Process a takeaways job using subprocess."""
        import subprocess
        import re

        job_id = job["id"]
        params = job.get("params", {})

        # Determine output path
        jobs_dir = self.settings.output_dir / "jobs"
        jobs_dir.mkdir(parents=True, exist_ok=True)

        video_id = None
        try:
            video_id = CondenserPipeline._extract_video_id(job["url"])
        except Exception:
            pass

        suffix = f"_vid-{video_id}" if video_id else ""
        output_ext = "mp3" if params.get("format_type") == "audio" else "md"
        output_path = jobs_dir / f"{job_id}{suffix}.{output_ext}"

        # Build command
        cmd = [
            "nbj",
            "takeaways",
            job["url"],
            "--format",
            params.get("format_type", "text"),
            "--output",
            str(output_path.with_suffix("")),  # nbj adds extension
        ]

        if params.get("top"):
            cmd.extend(["--top", str(params["top"])])

        if params.get("voice"):
            cmd.extend(["--voice", params["voice"]])

        # Add resume flag based on settings
        if self.settings.resume:
            cmd.append("--resume")
        else:
            cmd.append("--no-resume")

        self.update_progress(job_id, "FETCH", "Starting takeaways job")
        logger.info(f"[{job_id}] Running: {' '.join(cmd)}")

        stage_line_re = re.compile(r"^\[(?P<stage>[A-Z_]+)\]\s*(?P<message>.*)$")
        stderr_lines = []

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=Path(__file__).parent.parent,
        )

        assert proc.stdout is not None
        assert proc.stderr is not None

        def _drain_stderr():
            for line in proc.stderr:
                line = line.rstrip("\n")
                if line:
                    stderr_lines.append(line)
                    logger.info(f"[{job_id}] STDERR: {line}")

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        for raw_line in proc.stdout:
            line = raw_line.rstrip("\n")
            if not line:
                continue

            logger.info(f"[{job_id}] STDOUT: {line}")
            m = stage_line_re.match(line)
            if m:
                self.update_progress(job_id, m.group("stage"), m.group("message"))

        return_code = proc.wait()
        stderr_thread.join(timeout=1)

        if return_code != 0:
            stderr_text = "\n".join(stderr_lines).strip()
            raise RuntimeError(
                f"Takeaways extraction failed (exit={return_code}): {stderr_text or 'No stderr'}"
            )

        if not output_path.exists():
            raise RuntimeError(f"Takeaways file not found at expected location: {output_path}")

        self.mark_completed(job_id, str(output_path))

    def get_next_job(self, job_types: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Get the next queued job (called by workers)."""
        return self.store.get_next_queued_job(job_types)

    def start_worker_loop(self):
        """Main worker loop - pulls jobs and processes them."""
        logger.info("Worker loop started")
        while not self._shutdown:
            try:
                # Get next job from database queue
                job = self.get_next_job()
                if job and self.executor:
                    job_id = job['id']
                    logger.info(f"Submitting job {job_id} to worker pool")
                    self.executor.submit(self._process_job, job_id)
                else:
                    # No jobs available, wait a bit
                    threading.Event().wait(2.0)
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                threading.Event().wait(2.0)
        logger.info("Worker loop stopped")

    def get_running_jobs(self) -> List[str]:
        """Get list of currently running job IDs."""
        with self._workers_lock:
            return list(self._running_jobs)
