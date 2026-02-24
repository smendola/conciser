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
from .modules.video_generator import VideoGenerator
from .modules.compositor import VideoCompositor
from .utils.audio_utils import extract_audio, extract_audio_segment, normalize_audio, get_audio_duration
from .utils.video_utils import extract_frame

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
        self.condenser = ContentCondenser(settings.anthropic_api_key)
        self.voice_cloner = VoiceCloner(settings.elevenlabs_api_key)
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
        voice_id: str = None
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
            # Stage 1: Download video
            if resume:
                # Check for existing video files
                existing_video = self._find_existing_video()
                existing_metadata = self._find_existing_metadata()

                if existing_video and existing_metadata:
                    update_progress("DOWNLOAD", f"Resuming from step DOWNLOAD - found existing video: {existing_video.name}")
                    video_path = existing_video
                    metadata = existing_metadata
                    video_folder = video_path.parent  # Video folder is parent of video file
                else:
                    update_progress("DOWNLOAD", "Downloading video...")
                    download_result = self._download_video(video_url, quality)
                    video_path = download_result['video_path']
                    metadata = download_result['metadata']
                    video_folder = download_result['video_folder']
            else:
                update_progress("DOWNLOAD", "Downloading video...")
                download_result = self._download_video(video_url, quality)
                video_path = download_result['video_path']
                metadata = download_result['metadata']
                video_folder = download_result['video_folder']

            # Generate output filename if not provided
            normalized_title = metadata.get('normalized_title', metadata['title'])
            if output_path is None:
                output_path = self.settings.output_dir / f"{normalized_title}_condensed.mp4"

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
                    transcript_result = self._transcribe_video(video_path, video_folder)
                    transcript = transcript_result['text']
                    segments = transcript_result['segments']
                    duration_minutes = metadata['duration'] / 60.0
            else:
                update_progress("TRANSCRIBE", "Extracting and transcribing audio...")
                transcript_result = self._transcribe_video(video_path, video_folder)
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
                    update_progress("CONDENSE", f"Condensing content (aggressiveness: {aggressiveness}/10)...")
                    condensed_result = self._condense_transcript(
                        transcript,
                        duration_minutes,
                        aggressiveness,
                        video_folder
                    )
                    condensed_script = condensed_result['condensed_script']
            else:
                update_progress("CONDENSE", f"Condensing content (aggressiveness: {aggressiveness}/10)...")
                condensed_result = self._condense_transcript(
                    transcript,
                    duration_minutes,
                    aggressiveness,
                    video_folder
                )
                condensed_script = condensed_result['condensed_script']

            # Stage 4: Clone voice (or use premade voice)
            if skip_voice_clone:
                update_progress("VOICE_CLONE", f"Using premade voice (ID: {voice_id})...")
                used_voice_id = voice_id
                cleanup_voice = False
            else:
                update_progress("VOICE_CLONE", "Cloning speaker's voice...")
                used_voice_id = self._clone_voice(video_path, segments, metadata['title'], video_folder)
                cleanup_voice = True

            # Stage 5: Generate speech
            update_progress("VOICE_GENERATE", "Generating speech with voice...")
            generated_audio_path = self._generate_speech(condensed_script, used_voice_id, video_folder)

            # Stage 6: Generate video
            if video_gen_mode == "avatar":
                update_progress("VIDEO_GENERATE", "Generating talking head video with D-ID...")
                generated_video_path = self._generate_video_avatar(video_path, generated_audio_path, video_folder)
            elif video_gen_mode == "slideshow":
                update_progress("VIDEO_GENERATE", "Creating slideshow video...")
                generated_video_path = self._generate_video_slideshow(video_path, generated_audio_path, video_folder)
            else:  # static
                update_progress("VIDEO_GENERATE", "Creating static image video...")
                generated_video_path = self._generate_video_static(video_path, generated_audio_path, video_folder)

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
            logger.error(f"Pipeline failed: {e}")
            raise

    def _download_video(self, url: str, quality: str) -> Dict[str, Any]:
        """Download video from URL."""
        return self.downloader.download(url, quality=quality)

    def _transcribe_video(self, video_path: Path, video_folder: Path) -> Dict[str, Any]:
        """Extract audio and transcribe."""
        from .modules.downloader import normalize_name

        # Extract audio to video folder with normalized name
        base_name = normalize_name(video_path.stem)
        audio_path = video_folder / f"{base_name}_audio.wav"

        if not audio_path.exists():
            extract_audio(video_path, audio_path)

        # Transcribe
        transcript_result = self.transcriber.transcribe(audio_path, include_timestamps=True)

        # Save transcript
        transcript_json_path = video_folder / f"{base_name}_transcript.json"
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
        base_name = normalize_name(video_path.stem)
        audio_path = video_folder / f"{base_name}_audio.wav"

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

        # Extract audio samples
        sample_paths = []
        for i, segment in enumerate(clean_segments[:3]):  # Max 3 samples
            sample_path = video_folder / f"voice_sample_{i}.wav"
            extract_audio_segment(
                audio_path,
                sample_path,
                segment['start'],
                min(segment['duration'], 60)  # Max 60 seconds per sample
            )

            # Normalize the sample
            normalized_path = video_folder / f"voice_sample_{i}_normalized.wav"
            normalize_audio(sample_path, normalized_path)
            sample_paths.append(normalized_path)

        # Clone voice
        voice_name = f"conciser_{normalize_name(title[:30])}"
        voice_id = self.voice_cloner.clone_voice(voice_name, sample_paths)

        # Cleanup samples
        for sample_path in sample_paths:
            sample_path.unlink()

        return voice_id

    def _generate_speech(self, script: str, voice_id: str, video_folder: Path) -> Path:
        """Generate speech from script."""
        output_path = video_folder / "generated_speech.mp3"

        # Use chunked generation for long scripts
        self.voice_cloner.generate_speech_chunked(
            script,
            voice_id,
            output_path,
            chunk_size=5000
        )

        # Normalize audio
        normalized_path = video_folder / "generated_speech_normalized.mp3"
        normalize_audio(output_path, normalized_path)

        return normalized_path

    def _generate_video_avatar(self, source_video_path: Path, audio_path: Path, video_folder: Path) -> Path:
        """Generate talking head video using D-ID."""
        # Extract a good frame from the source video
        frame_path = video_folder / "source_frame.jpg"
        extract_frame(source_video_path, frame_path, timestamp=10.0)

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

        # Extract a good frame from the source video
        frame_path = video_folder / "source_frame.jpg"
        extract_frame(source_video_path, frame_path, timestamp=10.0)

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

    def _generate_video_slideshow(self, source_video_path: Path, audio_path: Path, video_folder: Path) -> Path:
        """Generate slideshow video with multiple frames from source video."""
        import subprocess

        # Get audio duration
        duration = get_audio_duration(audio_path)

        # Extract multiple frames evenly distributed
        num_frames = min(10, int(duration / 5))  # One frame every 5 seconds, max 10
        frame_paths = []

        # Get source video duration
        source_duration = get_audio_duration(source_video_path)

        for i in range(num_frames):
            timestamp = (source_duration / (num_frames + 1)) * (i + 1)
            frame_path = video_folder / f"slideshow_frame_{i:03d}.jpg"
            extract_frame(source_video_path, frame_path, timestamp=timestamp)
            frame_paths.append(frame_path)

        # Create a concat file for ffmpeg
        concat_file = video_folder / "slideshow_concat.txt"
        frame_duration = duration / num_frames

        with open(concat_file, 'w') as f:
            for frame_path in frame_paths:
                f.write(f"file '{frame_path}'\n")
                f.write(f"duration {frame_duration}\n")
            # Add last frame again to ensure proper duration
            f.write(f"file '{frame_paths[-1]}'\n")

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
            str(temp_video)
        ]

        subprocess.run(cmd, check=True, capture_output=True)

        # Combine with audio
        output_path = video_folder / "generated_video.mp4"

        cmd = [
            'ffmpeg', '-y',
            '-i', str(temp_video),
            '-i', str(audio_path),
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-shortest',
            str(output_path)
        ]

        subprocess.run(cmd, check=True, capture_output=True)
        logger.info(f"Created slideshow video: {output_path}")

        # Cleanup
        for frame_path in frame_paths:
            frame_path.unlink(missing_ok=True)
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

    def _find_existing_video(self) -> Optional[Path]:
        """Find existing downloaded video in temp directory."""
        # Look for video-specific folders (format: {video_id}_{normalized_title}/)
        video_extensions = ['*.mp4', '*.webm', '*.mkv', '*.avi', '*.mov']
        for folder in self.settings.temp_dir.iterdir():
            if folder.is_dir():
                # Look for main video file in folder (any video format)
                for ext in video_extensions:
                    for video_file in folder.glob(ext):
                        # Skip generated files
                        if not any(x in video_file.name.lower() for x in ['generated', 'condensed', 'final', 'slideshow']):
                            logger.info(f"Found existing video: {video_file}")
                            return video_file
        return None

    def _find_existing_metadata(self) -> Optional[Dict[str, Any]]:
        """Find or generate metadata from existing video."""
        video_path = self._find_existing_video()
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
        from .modules.downloader import normalize_name

        # Look for transcript JSON in video folder
        video_folder = video_path.parent
        base_name = normalize_name(video_path.stem)
        transcript_json = video_folder / f"{base_name}_transcript.json"

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

    def save_pipeline_state(self, output_path: Path, state: Dict[str, Any]):
        """Save pipeline state for resume capability."""
        with open(output_path, 'w') as f:
            json.dump(state, f, indent=2, default=str)

    def load_pipeline_state(self, state_path: Path) -> Dict[str, Any]:
        """Load pipeline state."""
        with open(state_path, 'r') as f:
            return json.load(f)
