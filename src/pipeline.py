"""Main pipeline orchestrator for video condensation."""

import logging
from pathlib import Path
from typing import Dict, Any, Optional
import json

from .config import Settings
from .modules.downloader import VideoDownloader
from .modules.transcriber import Transcriber
from .modules.condenser import ContentCondenser
from .modules.voice_cloner import VoiceCloner
from .modules.edge_tts import EdgeTTS
from .modules.video_generator import VideoGenerator
from .modules.compositor import VideoCompositor
from .utils.audio_utils import extract_audio, extract_audio_segment, normalize_audio, get_audio_duration
from .utils.video_utils import extract_frame, detect_scene_changes, extract_scene_keyframes

logger = logging.getLogger(__name__)


class CondenserPipeline:
    """Main pipeline for video condensation."""

    def __init__(self, settings: Settings):
        """
        Initialize the pipeline.

        Args:
            settings: Application settings
        """
        self.settings = settings

        # Initialize modules
        self.downloader = VideoDownloader(settings.temp_dir)
        self.transcriber = Transcriber(settings.openai_api_key)
        self.condenser = ContentCondenser(
            provider=settings.condenser_service,
            openai_api_key=settings.openai_api_key,
            anthropic_api_key=settings.anthropic_api_key
        )
        # TTS providers
        self.voice_cloner = VoiceCloner(settings.elevenlabs_api_key) if settings.elevenlabs_api_key else None
        self.edge_tts = EdgeTTS()  # Always available (free)
        # D-ID video generator only needed for avatar mode
        self.video_generator = VideoGenerator(settings.did_api_key) if settings.did_api_key else None
        self.compositor = VideoCompositor(settings.temp_dir)

    def run(
        self,
        video_url: str,
        aggressiveness: int = 5,
        output_path: Optional[Path] = None,
        quality: str = "1080p",
        video_gen_mode: str = "static",
        progress_callback: Optional[callable] = None,
        resume: bool = True,
        skip_voice_clone: bool = False,
        voice_id: str = None,
        tts_provider: str = "elevenlabs",
        slideshow_max_frames: int = None,
        tts_rate: str = "+0%"
    ) -> Dict[str, Any]:
        """
        Run the complete condensation pipeline.

        Args:
            video_url: YouTube or video URL
            aggressiveness: Condensing aggressiveness (1-10)
            output_path: Optional output path (default: auto-generated)
            quality: Output quality (720p, 1080p, 4k)
            video_gen_mode: Video generation mode (static, slideshow, avatar)
            progress_callback: Optional callback for progress updates
            resume: Resume from existing intermediate files
            skip_voice_clone: Skip voice cloning and use premade voice
            voice_id: Voice ID to use if skipping voice cloning
            tts_provider: TTS provider (elevenlabs or edge)

        Returns:
            Dictionary with results:
                - output_video: Path to final video
                - metadata: Processing metadata
                - stats: Processing statistics
        """
        def update_progress(stage: str, message: str):
            """Update progress."""
            logger.info(f"[{stage}] {message}")
            if progress_callback:
                progress_callback(stage, message)

        video_folder = None  # Track video-specific folder
        cleanup_voice = False  # Track if we need to cleanup cloned voice

        try:
            # Extract video ID from URL for resume matching
            video_id = self._extract_video_id(video_url)

            # Stage 1: Download video
            if resume:
                # Check for existing video files FOR THIS SPECIFIC VIDEO ID
                existing_video = self._find_existing_video(video_id)
                existing_metadata = self._find_existing_metadata(video_id)

                if existing_video and existing_metadata:
                    update_progress("FETCH", f"Resuming from step FETCH - found existing video: {existing_video.name}")
                    video_path = existing_video
                    metadata = existing_metadata
                    video_folder = video_path.parent  # Video folder is parent of video file
                else:
                    update_progress("FETCH", f"Fetching video {video_id}...")
                    download_result = self._download_video(video_url, quality)
                    video_path = download_result['video_path']
                    metadata = download_result['metadata']
                    video_folder = download_result['video_folder']
            else:
                update_progress("FETCH", f"Fetching video {video_id}...")
                download_result = self._download_video(video_url, quality)
                video_path = download_result['video_path']
                metadata = download_result['metadata']
                video_folder = download_result['video_folder']

            # Store video_id for output filename (will add tts/voice info later)
            video_id = metadata.get('video_id', 'unknown')
            normalized_title = metadata.get('normalized_title', metadata['title'])
            # Output filename will be generated after we know TTS provider and voice

            # Stage 2: Start frame extraction in parallel (for slideshow mode only)
            frame_extraction_future = None
            if video_gen_mode == "slideshow":
                import concurrent.futures
                import threading

                frames_dir = video_folder / "frames"
                frames_dir.mkdir(exist_ok=True)

                # Check if frames already exist (check both formats)
                existing_frames = list(frames_dir.glob("scene_*.jpg"))
                if not existing_frames:
                    existing_frames = list(frames_dir.glob("slideshow_frame_*.jpg"))

                if not existing_frames:
                    update_progress("FRAME_EXTRACT", "Detecting scenes and extracting frames (parallel)...")
                    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                    frame_extraction_future = executor.submit(
                        self._extract_frames_early,
                        video_path,
                        frames_dir,
                        slideshow_max_frames
                    )
                else:
                    logger.info(f"Found {len(existing_frames)} existing frames, skipping extraction")

            # Stage 2: Extract and transcribe audio
            if resume:
                # Check for existing transcript
                existing_transcript = self._find_existing_transcript(video_path)

                if existing_transcript:
                    update_progress("TRANSCRIBE", f"Resuming from step TRANSCRIBE - found existing transcript")
                    transcript_result = existing_transcript
                    transcript = transcript_result['text']
                    segments = transcript_result['segments']
                    duration_minutes = metadata['duration'] / 60.0
                else:
                    update_progress("TRANSCRIBE", "Extracting and transcribing audio...")
                    transcript_result = self._transcribe_video(video_path, video_folder, video_id)
                    transcript = transcript_result['text']
                    segments = transcript_result['segments']
                    duration_minutes = metadata['duration'] / 60.0
            else:
                update_progress("TRANSCRIBE", "Extracting and transcribing audio...")
                transcript_result = self._transcribe_video(video_path, video_folder, video_id)
                transcript = transcript_result['text']
                segments = transcript_result['segments']
                duration_minutes = metadata['duration'] / 60.0

            # Stage 3: Condense content
            if resume:
                # Check for existing condensed script
                existing_condensed = self._find_existing_condensed_script(video_folder)

                if existing_condensed:
                    update_progress("CONDENSE", f"Resuming from step CONDENSE - found existing condensed script")
                    condensed_result = existing_condensed
                    condensed_script = condensed_result['condensed_script']
                else:
                    update_progress("CONDENSE", f"Condensing content; aggressiveness {aggressiveness}/10...")
                    condensed_result = self._condense_transcript(
                        transcript,
                        duration_minutes,
                        aggressiveness,
                        video_folder
                    )
                    condensed_script = condensed_result['condensed_script']
            else:
                update_progress("CONDENSE", f"Condensing content; aggressiveness {aggressiveness}/10...")
                condensed_result = self._condense_transcript(
                    transcript,
                    duration_minutes,
                    aggressiveness,
                    video_folder
                )
                condensed_script = condensed_result['condensed_script']

            # Stage 4: Clone voice (or use premade voice)
            if tts_provider == 'edge':
                # Edge TTS doesn't need voice cloning
                update_progress("VOICE_CLONE", f"Using Edge TTS; voice {voice_id}...")
                used_voice_id = voice_id
                cleanup_voice = False
            elif skip_voice_clone:
                update_progress("VOICE_CLONE", f"Using premade voice; ID: {voice_id}...")
                used_voice_id = voice_id
                cleanup_voice = False
            else:
                update_progress("VOICE_CLONE", "Cloning speaker's voice...")
                used_voice_id = self._clone_voice(video_path, segments, metadata['title'], video_folder)
                cleanup_voice = True

            # Stage 5: Generate speech
            if resume:
                # Check for existing generated speech
                existing_speech = self._find_existing_generated_speech(video_folder, tts_provider, used_voice_id)

                if existing_speech:
                    update_progress("VOICE_GENERATE", f"Resuming from step VOICE_GENERATE - found existing speech: {existing_speech.name}")
                    generated_audio_path = existing_speech
                else:
                    update_progress("VOICE_GENERATE", "Generating speech with voice...")
                    generated_audio_path = self._generate_speech(condensed_script, used_voice_id, video_folder, tts_provider, tts_rate)
            else:
                update_progress("VOICE_GENERATE", "Generating speech with voice...")
                generated_audio_path = self._generate_speech(condensed_script, used_voice_id, video_folder, tts_provider, tts_rate)

            # Stage 6: Generate video (or skip for audio-only)
            if video_gen_mode == "audio_only":
                update_progress("AUDIO_ONLY", "Skipping video generation; audio-only mode...")
                logger.info("Audio-only mode: skipping video generation")

                # Generate output filename for MP3
                if output_path is None:
                    import re
                    voice_snake = re.sub(r'[^a-z0-9_]', '', used_voice_id.lower().replace('-', '_'))
                    output_filename = f"{video_id}_{normalized_title}_{tts_provider}_{voice_snake}.mp3"
                    output_path = self.settings.output_dir / output_filename

                # Copy the generated audio as the final output
                import shutil
                shutil.copy(generated_audio_path, output_path)
                logger.info(f"Audio-only output saved to: {output_path}")

                # Build stats structure to match normal return
                stats = {
                    'original_duration_minutes': duration_minutes,
                    'condensed_duration_minutes': condensed_result['estimated_condensed_duration_minutes'],
                    'reduction_percentage': condensed_result['reduction_percentage'],
                    'aggressiveness': aggressiveness,
                    'quality': quality,
                }

                update_progress("COMPLETE", f"Audio condensed successfully: {output_path}")

                return {
                    'output_video': output_path,
                    'metadata': metadata,
                    'stats': stats,
                    'condensed_result': condensed_result
                }

            elif video_gen_mode == "avatar":
                update_progress("VIDEO_GENERATE", "Generating talking head video with D-ID...")
                generated_video_path = self._generate_video_avatar(video_path, generated_audio_path, video_folder)
            elif video_gen_mode == "slideshow":
                # Wait for frame extraction if it's still running
                if frame_extraction_future:
                    update_progress("VIDEO_GENERATE", "Waiting for frame extraction to complete...")
                    try:
                        frame_extraction_future.result(timeout=300)  # 5 minute timeout
                        logger.info("Frame extraction completed in parallel")
                    except Exception as e:
                        logger.warning(f"Parallel frame extraction failed: {e}, will retry during video generation")

                update_progress("VIDEO_GENERATE", "Creating slideshow video...")
                generated_video_path = self._generate_video_slideshow(video_path, generated_audio_path, video_folder, slideshow_max_frames)
            else:  # static
                update_progress("VIDEO_GENERATE", "Creating static image video...")
                generated_video_path = self._generate_video_static(video_path, generated_audio_path, video_folder)

            # Generate output filename if not provided
            if output_path is None:
                # Normalize voice_id to snake_case
                import re
                voice_snake = re.sub(r'[^a-z0-9_]', '', used_voice_id.lower().replace('-', '_'))
                # Format: {video_id}_{title_snake_60}_{tts_provider}_{voice_snake}.mp4
                output_filename = f"{video_id}_{normalized_title}_{tts_provider}_{voice_snake}.mp4"
                output_path = self.settings.output_dir / output_filename

            # Stage 7: Compose final video
            update_progress("COMPOSE", "Composing final video...")
            final_video_path = self._compose_final_video(
                generated_video_path,
                generated_audio_path,
                output_path,
                quality
            )

            # Cleanup voice clone (only if we created it)
            if cleanup_voice:
                update_progress("CLEANUP", "Cleaning up cloned voice...")
                self.voice_cloner.delete_voice(used_voice_id)
            else:
                update_progress("CLEANUP", "Cleaning up...")

            # Generate statistics
            stats = {
                'original_duration_minutes': duration_minutes,
                'condensed_duration_minutes': condensed_result['estimated_condensed_duration_minutes'],
                'reduction_percentage': condensed_result['reduction_percentage'],
                'aggressiveness': aggressiveness,
                'quality': quality,
            }

            update_progress("COMPLETE", f"Video condensed successfully: {final_video_path}")

            return {
                'output_video': final_video_path,
                'metadata': metadata,
                'stats': stats,
                'condensed_result': condensed_result
            }

        except Exception as e:
            from .utils.exceptions import ApiError
            if not isinstance(e, ApiError):
                logger.error(f"Pipeline failed: {e}")
            raise

    def _download_video(self, url: str, quality: str) -> Dict[str, Any]:
        """Download video from URL."""
        return self.downloader.download(url, quality=quality)

    def _transcribe_video(self, video_path: Path, video_folder: Path, video_id: str = None) -> Dict[str, Any]:
        """
        Extract audio and transcribe.

        Tries to fetch YouTube transcript first if video_id is provided.
        Falls back to Whisper transcription if YouTube transcript is unavailable.
        """
        from colorama import Fore, Style

        # Try YouTube transcript first if we have a video ID
        if video_id:
            logger.info("Checking for YouTube transcript...")
            youtube_transcript = self.transcriber.fetch_youtube_transcript(video_id)

            if youtube_transcript:
                logger.info("Using YouTube transcript (no Whisper API cost)")
                # Save transcript
                transcript_json_path = video_folder / "transcript.json"
                self.transcriber.save_transcript(youtube_transcript, transcript_json_path)
                return youtube_transcript
            else:
                # Log in yellow that we're falling back to Whisper
                print(f"{Fore.RED}YouTube transcript not available, falling back to Whisper transcription...{Style.RESET_ALL}")
                logger.warning("YouTube transcript not available, falling back to Whisper transcription")

        # Fallback: Extract audio and use Whisper
        audio_path = video_folder / "extracted_audio.wav"

        if not audio_path.exists():
            extract_audio(video_path, audio_path)

        # Transcribe
        transcript_result = self.transcriber.transcribe(audio_path, include_timestamps=True)

        # Save transcript
        transcript_json_path = video_folder / "transcript.json"
        self.transcriber.save_transcript(transcript_result, transcript_json_path)

        return transcript_result

    def _condense_transcript(
        self,
        transcript: str,
        duration_minutes: float,
        aggressiveness: int,
        video_folder: Path
    ) -> Dict[str, Any]:
        """Condense transcript using LLM."""
        condensed_result = self.condenser.condense(
            transcript,
            duration_minutes,
            aggressiveness
        )

        # Validate
        self.condenser.validate_condensed_script(condensed_result)

        # Save condensed script
        script_path = video_folder / "condensed_script.json"
        self.condenser.save_condensed_script(condensed_result, script_path)

        return condensed_result

    def _clone_voice(
        self,
        video_path: Path,
        segments: list,
        title: str,
        video_folder: Path
    ) -> str:
        """Clone voice from video."""
        from .modules.downloader import normalize_name

        # Get audio path
        audio_path = video_folder / "extracted_audio.wav"

        # Extract clean speech segments
        clean_segments = self.transcriber.extract_clean_speech_segments(
            {'segments': segments},
            min_duration=120,
            max_duration=180
        )

        if not clean_segments:
            # Fallback: use first 2 minutes
            logger.warning("No clean segments found, using first 2 minutes")
            clean_segments = [{'start': 30, 'end': 150, 'duration': 120}]

        # Create voice_samples subdirectory
        voice_samples_dir = video_folder / "voice_samples"
        voice_samples_dir.mkdir(exist_ok=True)

        # Extract audio samples
        sample_paths = []
        for i, segment in enumerate(clean_segments[:3]):  # Max 3 samples
            sample_path = voice_samples_dir / f"voice_sample_{i}.wav"
            extract_audio_segment(
                audio_path,
                sample_path,
                segment['start'],
                min(segment['duration'], 60)  # Max 60 seconds per sample
            )

            # Normalize the sample
            normalized_path = voice_samples_dir / f"voice_sample_{i}_normalized.wav"
            normalize_audio(sample_path, normalized_path)
            sample_paths.append(normalized_path)

        # Clone voice
        voice_name = f"conciser_{normalize_name(title, max_length=30)}"
        voice_id = self.voice_cloner.clone_voice(voice_name, sample_paths)

        # Cleanup samples
        for sample_path in sample_paths:
            sample_path.unlink()

        return voice_id

    def _generate_speech(self, script: str, voice_id: str, video_folder: Path, tts_provider: str = "elevenlabs", tts_rate: str = "+0%") -> Path:
        """Generate speech from script."""
        # Create unique filename based on provider and voice
        import re
        voice_normalized = re.sub(r'[^a-z0-9_]', '', voice_id.lower().replace('-', '_'))
        output_path = video_folder / f"generated_speech_{tts_provider}_{voice_normalized}.mp3"

        if tts_provider == "edge":
            # Use Edge TTS
            self.edge_tts.generate_speech(
                script,
                output_path,
                voice=voice_id,
                rate=tts_rate
            )
        else:
            # Use ElevenLabs with chunked generation for long scripts
            self.voice_cloner.generate_speech_chunked(
                script,
                voice_id,
                output_path,
                chunk_size=5000
            )

        # Normalize audio
        normalized_path = video_folder / f"generated_speech_{tts_provider}_{voice_normalized}_normalized.mp3"
        normalize_audio(output_path, normalized_path)

        return normalized_path

    def _generate_video_avatar(self, source_video_path: Path, audio_path: Path, video_folder: Path) -> Path:
        """Generate talking head video using D-ID."""
        # Create frames subdirectory
        frames_dir = video_folder / "frames"
        frames_dir.mkdir(exist_ok=True)

        # Extract a good frame from the source video
        frame_path = frames_dir / "avatar_source_frame.jpg"
        extract_frame(source_video_path, frame_path, timestamp=10.0)
        logger.info(f"Saved avatar source frame to: {frame_path}")

        # Generate video
        output_path = video_folder / "generated_video.mp4"
        self.video_generator.generate_from_local_files(
            frame_path,
            audio_path,
            output_path
        )

        return output_path

    def _generate_video_static(self, source_video_path: Path, audio_path: Path, video_folder: Path) -> Path:
        """Generate video with static image and audio (low cost alternative)."""
        import subprocess

        # Create frames subdirectory
        frames_dir = video_folder / "frames"
        frames_dir.mkdir(exist_ok=True)

        # Extract a good frame from the source video
        frame_path = frames_dir / "static_frame.jpg"
        extract_frame(source_video_path, frame_path, timestamp=10.0)
        logger.info(f"Saved static frame to: {frame_path}")

        # Get audio duration
        duration = get_audio_duration(audio_path)

        # Create video with ffmpeg
        output_path = video_folder / "generated_video.mp4"

        cmd = [
            'ffmpeg', '-y',
            '-loop', '1',
            '-i', str(frame_path),
            '-i', str(audio_path),
            '-c:v', 'libx264',
            '-tune', 'stillimage',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-pix_fmt', 'yuv420p',
            '-shortest',
            '-t', str(duration),
            str(output_path)
        ]

        subprocess.run(cmd, check=True, capture_output=True)
        logger.info(f"Created static video: {output_path}")

        return output_path

    def _extract_frames_early(
        self,
        source_video_path: Path,
        frames_dir: Path,
        max_frames: int = None
    ):
        """
        Extract frames early in pipeline to parallelize with other tasks.

        Args:
            source_video_path: Path to original video
            frames_dir: Directory to save frames
            max_frames: Maximum frames to extract
        """
        from src.utils.video_utils import detect_scene_changes, extract_frame
        from src.utils.audio_utils import get_audio_duration
        import json

        try:
            logger.info("Starting early frame extraction in parallel thread...")
            source_duration = get_audio_duration(source_video_path)

            # Detect scene changes
            logger.info(f"Detecting scenes in source video ({source_duration:.1f}s)...")
            scenes = detect_scene_changes(source_video_path, threshold=27)

            # Fallback to evenly-spaced frames if scene detection fails
            if not scenes:
                logger.warning("Scene detection failed in parallel extraction, using evenly-spaced frames")

                # Use evenly-spaced fallback
                num_frames = 10 if max_frames is None else max_frames
                for i in range(num_frames):
                    timestamp = (source_duration / (num_frames + 1)) * (i + 1)
                    frame_path = frames_dir / f"slideshow_frame_{i:03d}.jpg"
                    extract_frame(source_video_path, frame_path, timestamp=timestamp)

                logger.info(f"Extracted {num_frames} evenly-spaced frames in parallel")
            else:
                # Extract keyframes from scenes
                logger.info(f"Found {len(scenes)} scenes in parallel extraction")

                # Save scene data for later use (only when we have scenes)
                scenes_file = frames_dir / "scenes.json"
                with open(scenes_file, 'w') as f:
                    json.dump(scenes, f, indent=2)
                logger.info(f"Saved scene timing data to {scenes_file}")

                # Calculate frames to extract
                if max_frames is None:
                    num_frames = min(len(scenes), 15)
                else:
                    num_frames = min(len(scenes), max_frames)

                # Sample scenes proportionally
                if len(scenes) > num_frames:
                    step = len(scenes) / num_frames
                    selected_scenes = [scenes[int(i * step)] for i in range(num_frames)]
                else:
                    selected_scenes = scenes

                # Extract frame from middle of each scene
                # Use scene_id in filename for proper synchronization later
                for i, scene in enumerate(selected_scenes):
                    mid_time = (scene['start_time'] + scene['end_time']) / 2
                    frame_path = frames_dir / f"scene_{scene['scene_id']:03d}.jpg"
                    extract_frame(source_video_path, frame_path, timestamp=mid_time)

                logger.info(f"Extracted {len(selected_scenes)} scene keyframes in parallel")

        except Exception as e:
            logger.error(f"Early frame extraction failed: {e}")
            # Don't raise - let _generate_video_slideshow handle it

    def _generate_video_slideshow(
        self,
        source_video_path: Path,
        audio_path: Path,
        video_folder: Path,
        max_frames: int = None
    ) -> Path:
        """
        Generate slideshow video with scene-detected frames.

        Uses PySceneDetect to identify scene changes in the original video,
        then proportionally maps those scenes to the condensed audio timeline.

        Args:
            source_video_path: Path to original video
            audio_path: Path to condensed audio
            video_folder: Working directory
            max_frames: Maximum frames to extract (None = auto-calculate)
        """
        import subprocess

        # Get durations
        condensed_duration = get_audio_duration(audio_path)
        source_duration = get_audio_duration(source_video_path)

        # Create frames subdirectory for preservation
        frames_dir = video_folder / "frames"
        frames_dir.mkdir(exist_ok=True)

        # Check if frames were already extracted in parallel
        # Check for both old format (slideshow_frame_*.jpg) and new format (scene_*.jpg)
        existing_frames = sorted(frames_dir.glob("scene_*.jpg"))
        if not existing_frames:
            existing_frames = sorted(frames_dir.glob("slideshow_frame_*.jpg"))

        if existing_frames:
            logger.info(f"Using {len(existing_frames)} pre-extracted frames from parallel extraction")
            frame_paths = existing_frames

            # Try to load scene data from parallel extraction
            scenes_file = frames_dir / "scenes.json"
            if scenes_file.exists():
                import json
                with open(scenes_file, 'r') as f:
                    scenes = json.load(f)
                logger.info(f"Loaded scene timing data for {len(scenes)} scenes from parallel extraction")
            else:
                logger.warning("No scene data found from parallel extraction, using equal-duration timing")
                scenes = []
        else:
            # Frames not extracted yet, do it now
            logger.info(f"Detecting scenes in source video ({source_duration:.1f}s)...")

            # Detect scene changes in source video
            scenes = detect_scene_changes(source_video_path, threshold=27)

            # Fallback to evenly-spaced frames if scene detection fails
            if not scenes:
                logger.warning("Scene detection failed, using evenly-spaced frames")

                # Calculate fallback frame count
                if max_frames is None:
                    num_frames = min(10, int(condensed_duration / 5))
                    logger.info(f"Auto-calculated fallback frames: {num_frames} (use --slideshow-frames to override)")
                else:
                    num_frames = max_frames
                    logger.info(f"Using user-specified frames for fallback: {num_frames}")

                frame_paths = []
                for i in range(num_frames):
                    timestamp = (source_duration / (num_frames + 1)) * (i + 1)
                    frame_path = frames_dir / f"slideshow_frame_{i:03d}.jpg"
                    extract_frame(source_video_path, frame_path, timestamp=timestamp)
                    frame_paths.append(frame_path)
            else:
                # Extract keyframes from detected scenes
                logger.info(f"Found {len(scenes)} scenes, extracting keyframes...")

                # Save scene data (only when we have scenes)
                import json
                scenes_file = frames_dir / "scenes.json"
                with open(scenes_file, 'w') as f:
                    json.dump(scenes, f, indent=2)
                logger.info(f"Saved scene timing data to {scenes_file}")

                # Calculate max frames if not specified
                if max_frames is None:
                    # Conservative default: 1 frame per 4 seconds, max 15
                    max_frames = min(15, int(condensed_duration / 4))
                    logger.info(f"Auto-calculated max frames: {max_frames} (use --slideshow-frames to override)")
                else:
                    logger.info(f"Using user-specified max frames: {max_frames}")

                frame_paths = extract_scene_keyframes(
                    source_video_path,
                    scenes,
                    frames_dir,  # Save to frames/ subdirectory
                    max_frames=max_frames
                )
                logger.info(f"Saved {len(frame_paths)} frames to {frames_dir}")

        # Proportional synchronization: map frames to condensed timeline
        # If scene was at 25% through original, show at 25% through condensed
        frame_timings = []
        if scenes and any('scene_' in str(fp.name) for fp in frame_paths):
            # We have scene timing info - use proportional mapping
            # Build a dict for quick scene lookup by scene_id
            scene_dict = {s['scene_id']: s for s in scenes}

            for frame_path in frame_paths:
                # Extract scene_id from filename (e.g., "scene_042.jpg" -> 42)
                if 'scene_' in frame_path.name:
                    scene_id = int(frame_path.stem.split('_')[-1])

                    # Find the scene by its scene_id
                    scene = scene_dict.get(scene_id)
                    if scene:
                        # Calculate proportional position
                        original_position = scene['start_time'] / source_duration  # 0.0 to 1.0
                        condensed_position = original_position * condensed_duration  # Map to condensed timeline

                        frame_timings.append({
                            'path': frame_path,
                            'show_at': condensed_position,
                            'scene_id': scene_id
                        })

            if frame_timings:
                # Sort by show_at time
                frame_timings.sort(key=lambda x: x['show_at'])
                logger.info(f"Synchronized {len(frame_timings)} frames to condensed timeline using proportional mapping")

        # Fallback to equal duration if we don't have proportional timings
        if not frame_timings:
            logger.info("Using equal-duration timing for frames")
            # Fallback: equal duration for each frame
            frame_duration = condensed_duration / len(frame_paths)
            for i, frame_path in enumerate(frame_paths):
                frame_timings.append({
                    'path': frame_path,
                    'show_at': i * frame_duration,
                    'scene_id': i
                })
            logger.info(f"Using equal duration ({frame_duration:.1f}s) for {len(frame_paths)} frames")

        # Calculate durations for each frame
        for i in range(len(frame_timings)):
            if i < len(frame_timings) - 1:
                # Duration until next frame
                frame_timings[i]['duration'] = frame_timings[i + 1]['show_at'] - frame_timings[i]['show_at']
            else:
                # Last frame shows until end
                frame_timings[i]['duration'] = condensed_duration - frame_timings[i]['show_at']

        # Create concat file with timed durations (use absolute paths)
        concat_file = video_folder / "slideshow_concat.txt"
        with open(concat_file, 'w') as f:
            for ft in frame_timings:
                # Convert to absolute path for ffmpeg concat demuxer
                abs_path = ft['path'].resolve() if hasattr(ft['path'], 'resolve') else Path(ft['path']).resolve()
                f.write(f"file '{abs_path}'\n")
                f.write(f"duration {ft['duration']:.3f}\n")
            # Add last frame again to ensure proper duration
            last_path = frame_timings[-1]['path'].resolve() if hasattr(frame_timings[-1]['path'], 'resolve') else Path(frame_timings[-1]['path']).resolve()
            f.write(f"file '{last_path}'\n")

        # Create slideshow video
        temp_video = video_folder / "slideshow_no_audio.mp4"

        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(concat_file),
            '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2',
            '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            '-g', '1',               # keyframe at every frame — makes all scene cuts seekable
            '-movflags', '+faststart',
            str(temp_video)
        ]

        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg slideshow creation failed: {e.stderr}")
            raise RuntimeError(f"Failed to create slideshow video: {e.stderr}")

        # Combine with audio
        output_path = video_folder / "generated_video.mp4"

        cmd = [
            'ffmpeg', '-y',
            '-i', str(temp_video),
            '-i', str(audio_path),
            '-c:v', 'libx264',       # re-encode (not copy) to preserve keyframes and movflags
            '-pix_fmt', 'yuv420p',
            '-g', '1',
            '-movflags', '+faststart',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-shortest',
            str(output_path)
        ]

        subprocess.run(cmd, check=True, capture_output=True)
        logger.info(f"Created slideshow video with {len(frame_timings)} scene-synchronized frames")
        logger.info(f"Extracted frames saved to: {frames_dir}")

        # Cleanup temporary files (but keep frames in frames/ directory)
        concat_file.unlink(missing_ok=True)
        temp_video.unlink(missing_ok=True)

        return output_path

    def _compose_final_video(
        self,
        video_path: Path,
        audio_path: Path,
        output_path: Path,
        quality: str
    ) -> Path:
        """Compose final video."""
        return self.compositor.compose_final_video(
            video_path,
            audio_path,
            output_path,
            resolution=quality,
            add_watermark=True
        )

    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from URL."""
        import re
        # Match YouTube URLs
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})',
            r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _find_existing_video(self, video_id: str = None) -> Optional[Path]:
        """Find existing downloaded video in temp directory for specific video ID."""
        # Look for video-specific folders (format: {video_id}_{normalized_title}/)
        video_extensions = ['*.mp4', '*.webm', '*.mkv', '*.avi', '*.mov']
        for folder in self.settings.temp_dir.iterdir():
            if folder.is_dir():
                # If video_id specified, only check folders that start with it
                if video_id and not folder.name.startswith(f"{video_id}_"):
                    continue

                # Look for main video file in folder (any video format)
                for ext in video_extensions:
                    for video_file in folder.glob(ext):
                        # Skip generated files
                        if not any(x in video_file.name.lower() for x in ['generated', 'condensed', 'final', 'slideshow']):
                            logger.info(f"Found existing video: {video_file}")
                            return video_file
        return None

    def _find_existing_metadata(self, video_id: str = None) -> Optional[Dict[str, Any]]:
        """Find or generate metadata from existing video for specific video ID."""
        video_path = self._find_existing_video(video_id)
        if not video_path:
            return None

        # Extract info from folder name (format: {video_id}_{normalized_title})
        folder_name = video_path.parent.name
        parts = folder_name.split('_', 1)

        if len(parts) == 2:
            video_id, normalized_title = parts
        else:
            video_id = 'unknown'
            normalized_title = folder_name

        # Convert normalized_title back to readable format
        title = normalized_title.replace('_', ' ').title()

        # Get duration from video
        try:
            duration = get_audio_duration(video_path)
            return {
                'video_id': video_id,
                'title': title,
                'normalized_title': normalized_title,
                'duration': duration,
                'uploader': 'Unknown',
            }
        except Exception as e:
            logger.warning(f"Could not extract metadata: {e}")
            return None

    def _find_existing_transcript(self, video_path: Path) -> Optional[Dict[str, Any]]:
        """Find existing transcript JSON file."""
        # Look for transcript JSON in video folder
        video_folder = video_path.parent
        transcript_json = video_folder / "transcript.json"

        if transcript_json.exists():
            logger.info(f"Found existing transcript: {transcript_json}")
            return self.transcriber.load_transcript(transcript_json)

        return None

    def _find_existing_condensed_script(self, video_folder: Path) -> Optional[Dict[str, Any]]:
        """Find existing condensed script JSON file."""
        condensed_script_json = video_folder / "condensed_script.json"

        if condensed_script_json.exists():
            logger.info(f"Found existing condensed script: {condensed_script_json}")
            return self.condenser.load_condensed_script(condensed_script_json)

        return None

    def _find_existing_generated_speech(self, video_folder: Path, tts_provider: str, voice_id: str) -> Optional[Path]:
        """Find existing generated speech file for this provider and voice."""
        import re
        voice_normalized = re.sub(r'[^a-z0-9_]', '', voice_id.lower().replace('-', '_'))
        speech_path = video_folder / f"generated_speech_{tts_provider}_{voice_normalized}_normalized.mp3"

        if speech_path.exists():
            logger.info(f"Found existing generated speech: {speech_path}")
            return speech_path

        return None

    def save_pipeline_state(self, output_path: Path, state: Dict[str, Any]):
        """Save pipeline state for resume capability."""
        with open(output_path, 'w') as f:
            json.dump(state, f, indent=2, default=str)

    def load_pipeline_state(self, state_path: Path) -> Dict[str, Any]:
        """Load pipeline state."""
        with open(state_path, 'r') as f:
            return json.load(f)
