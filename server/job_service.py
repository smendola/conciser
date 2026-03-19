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
from src.utils.project_root import get_project_root
from src.modules.downloader import VideoDownloader
from src.modules.transcriber import Transcriber
from src.modules.condenser import ContentCondenser
from src.modules.edge_tts import EdgeTTS
from src.modules.azure_tts import AzureTTS
from src.utils.audio_utils import embed_cover_art_mp3

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

    def get_active_job_for_client(self, client_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """Get the current active job (queued/processing) for a client, if any."""
        if not client_id:
            return None
        return self.store.get_active_job_for_client(client_id)

    def update_progress(self, job_id: str, stage: str, message: str) -> None:
        """Update job progress."""
        progress = f"[{stage}] {message}"
        self.store.update_status(job_id, "processing", progress)
        self.store.add_event(job_id, stage, message)

    def mark_completed(self, job_id: str, output_file: str) -> None:
        """Mark job as completed with output file."""
        self.store.set_output_file(job_id, output_file)
        self.store.update_status(job_id, "completed")
        job = self.store.get_job(job_id)
        client_id = job.get("client_id") if job else None
        self.store.create_shareable(job_id, client_id)
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

        video_mode = (params.get("video_mode") or "slideshow").strip().lower()

        if video_mode == "text":
            output_path = jobs_dir / f"{job_id}_condensed_script.md"
        elif video_mode == "audio_only":
            output_path = jobs_dir / f"{job_id}_audio.mp3"
        else:
            output_path = jobs_dir / f"{job_id}_slideshow.json"

        result = pipeline.run(
            video_url=job["url"],
            aggressiveness=params.get("aggressiveness", 5),
            output_path=output_path,
            quality="1080p",
            video_gen_mode=video_mode,
            tts_provider=params.get("tts_provider", self.settings.tts_provider),
            voice_id=params.get("voice", "en-US-AriaNeural"),
            tts_rate=params.get("speech_rate", "+0%"),
            skip_voice_clone=True,
            progress_callback=lambda s, m: self.update_progress(job_id, s, m),
            resume=self.settings.resume,
            prepend_intro=params.get("prepend_intro", False),
        )

        # For slideshow mode, copy the generated audio as a named artifact
        if video_mode == "slideshow":
            import shutil as _shutil
            audio_src = result.get("audio_path")
            if audio_src:
                audio_dest = jobs_dir / f"{job_id}_audio.mp3"
                if not (self.settings.resume and audio_dest.exists()):
                    _shutil.copy(str(audio_src), str(audio_dest))

        # For audio/video modes, also write the condensed script as a text artifact
        if video_mode != "text":
            script_path = jobs_dir / f"{job_id}_condensed_script.md"
            if not (self.settings.resume and script_path.exists()):
                video_title = result.get("metadata", {}).get("title", "")
                condensed_script = result.get("condensed_result", {}).get("condensed_script", "")
                md_content = f"# {video_title}\n\n{condensed_script}\n"
                script_path.write_text(md_content, encoding="utf-8")

        self.mark_completed(job_id, str(output_path))

    def _process_takeaways(self, job: Dict[str, Any]) -> None:
        """Process a takeaways job in-process (same execution model as condense)."""
        job_id = job["id"]
        params = job.get("params", {})

        # Determine output path
        jobs_dir = self.settings.output_dir / "jobs"
        jobs_dir.mkdir(parents=True, exist_ok=True)

        output_ext = "mp3" if params.get("format_type") == "audio" else "md"
        output_path = jobs_dir / f"{job_id}_takeaways.{output_ext}"

        format_type = (params.get("format_type") or "text").strip().lower()
        top = params.get("top")
        voice = params.get("voice")
        tts_provider = (params.get("tts_provider") or self.settings.tts_provider or "azure").strip().lower()
        speech_rate = (params.get("speech_rate") or "+0%").strip()

        if format_type not in {"text", "audio"}:
            raise ValueError(f"Invalid takeaways format_type: {format_type}")

        self.update_progress(job_id, "FETCH", "Starting takeaways job")

        downloader = VideoDownloader(
            self.settings.temp_dir,
            youtube_cookie_file=self.settings.youtube_cookie_file,
            youtube_proxy_url=self.settings.youtube_proxy_url,
        )
        transcriber = Transcriber(
            api_key=self.settings.openai_api_key,
            provider=self.settings.transcription_service,
            groq_api_key=self.settings.groq_api_key,
            youtube_proxy_url=self.settings.youtube_proxy_url,
        )
        condenser = ContentCondenser(
            provider=self.settings.takeaways_extraction_provider,
            openai_api_key=self.settings.openai_api_key,
            anthropic_api_key=self.settings.anthropic_api_key,
            condensation_model_openai=self.settings.condensation_model_openai,
            condensation_model_anthropic=self.settings.condensation_model_anthropic,
            takeaways_model_openai=self.settings.takeaways_model_openai,
            takeaways_model_anthropic=self.settings.takeaways_model_anthropic,
        )

        self.update_progress(job_id, "FETCH", "Fetching video metadata...")
        video_info = downloader.download(job["url"], metadata_only=True)
        video_folder = video_info["video_folder"]
        metadata = video_info.get("metadata", {})
        video_title = metadata.get("title", "")
        video_id_resolved = metadata.get("video_id", job["url"])

        transcript_path = video_folder / f"transcript_{video_id_resolved}.txt"
        transcript: str
        if self.settings.resume and transcript_path.exists():
            self.update_progress(job_id, "FETCH", "Loading cached transcript...")
            transcript = transcript_path.read_text(encoding="utf-8")
        else:
            self.update_progress(job_id, "FETCH", "Fetching transcript...")
            youtube_transcript = transcriber.fetch_youtube_transcript(video_id_resolved)
            if youtube_transcript:
                transcript = youtube_transcript["text"]
            else:
                logger.warning("YouTube transcript unavailable for takeaways job; falling back to Whisper transcription")
                self.update_progress(job_id, "FETCH", "YouTube transcript unavailable; downloading video for Whisper...")
                video_info_full = downloader.download(
                    job["url"],
                    metadata_only=False,
                    existing_folder=video_folder,
                )
                video_path = video_info_full["video_path"]
                transcript_result = transcriber.transcribe(video_path)
                transcript = transcript_result["text"]

            transcript_path.write_text(transcript, encoding="utf-8")

        takeaways_md_path = output_path if format_type == "text" else output_path.with_suffix(".md")
        takeaways_text: str
        if self.settings.resume and takeaways_md_path.exists():
            self.update_progress(job_id, "EXTRACT", "Loading cached takeaways...")
            takeaways_text = takeaways_md_path.read_text(encoding="utf-8")
        else:
            self.update_progress(job_id, "EXTRACT", "Extracting key takeaways...")
            takeaways_text_only = condenser.extract_takeaways(
                transcript=transcript,
                video_title=video_title,
                top=top,
                format=format_type,
            )

            header = f"# {video_title}\n\n"
            header += f"*Top {top} key concepts*\n\n" if top else "*Key concepts*\n\n"
            takeaways_text = header + takeaways_text_only
            takeaways_md_path.parent.mkdir(parents=True, exist_ok=True)
            takeaways_md_path.write_text(takeaways_text, encoding="utf-8")

        if format_type == "text":
            self.update_progress(job_id, "FINALIZE", "Takeaways extraction complete")
            self.mark_completed(job_id, str(takeaways_md_path))
            return

        self.update_progress(job_id, "FINALIZE", "Generating audio...")

        audio_script = takeaways_text
        audio_path = output_path
        audio_path.parent.mkdir(parents=True, exist_ok=True)

        if tts_provider == "edge":
            edge_tts = EdgeTTS()
            edge_tts.generate_speech(
                text=audio_script,
                output_path=audio_path,
                voice=voice or "en-US-AriaNeural",
                rate=speech_rate,
            )
        elif tts_provider == "azure":
            azure_tts = AzureTTS(self.settings.azure_speech_key, self.settings.azure_speech_region)
            azure_tts.generate_speech(
                text=audio_script,
                output_path=audio_path,
                voice=voice or "en-US-AriaNeural",
                rate=speech_rate,
                is_ssml=False,
            )
        else:
            raise ValueError(f"Unsupported tts_provider for takeaways audio: {tts_provider}")

        try:
            thumb_candidates = [
                p
                for p in video_folder.glob("thumbnail.*")
                if p.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]
            ]
            if not thumb_candidates:
                thumb_candidates = [
                    p
                    for p in video_folder.glob("source_video.*")
                    if p.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]
                ]
            if thumb_candidates:
                embed_cover_art_mp3(audio_path, thumb_candidates[0])
        except Exception as e:
            logger.warning(f"Failed to embed cover art into takeaways MP3: {e}")

        self.mark_completed(job_id, str(audio_path))

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
