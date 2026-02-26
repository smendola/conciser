"""Final video composition and assembly module."""

import subprocess
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class VideoCompositor:
    """Assembles final video from components."""

    def __init__(self, temp_dir: Path):
        """
        Initialize compositor.

        Args:
            temp_dir: Directory for temporary files
        """
        self.temp_dir = temp_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._drawtext_available = None  # Cache for drawtext filter availability

    def _check_drawtext_available(self) -> bool:
        """Check if FFmpeg has drawtext filter available."""
        if self._drawtext_available is not None:
            return self._drawtext_available

        try:
            result = subprocess.run(
                ['ffmpeg', '-filters'],
                capture_output=True,
                text=True,
                check=True
            )
            self._drawtext_available = 'drawtext' in result.stdout
            if not self._drawtext_available:
                logger.info("FFmpeg drawtext filter not available - watermarks will be skipped")
            return self._drawtext_available
        except Exception:
            self._drawtext_available = False
            return False

    def compose_final_video(
        self,
        video_path: Path,
        audio_path: Path,
        output_path: Path,
        resolution: str = "1080p",
        add_watermark: bool = True,
        watermark_text: str = "Generated with Conciser AI"
    ) -> Path:
        """
        Compose final video from talking head video and audio.

        Args:
            video_path: Path to generated talking head video
            audio_path: Path to generated audio
            output_path: Path to save final video
            resolution: Target resolution
            add_watermark: Add AI-generated watermark
            watermark_text: Text for watermark

        Returns:
            Path to final composed video
        """
        try:
            logger.info("Composing final video")

            # If watermark is requested, check if drawtext is available first
            if add_watermark and self._check_drawtext_available():
                video_with_watermark = self.temp_dir / f"watermarked_{video_path.name}"
                self._add_watermark(video_path, video_with_watermark, watermark_text)
                # Only use watermarked version if it was successfully created
                if video_with_watermark.exists():
                    video_path = video_with_watermark
                else:
                    logger.debug("Watermark file not created, using original video")
            elif add_watermark and not self._check_drawtext_available():
                logger.debug("Watermark requested but drawtext filter not available, skipping")

            # Combine video and audio
            resolution_map = {
                "720p": "1280:720",
                "1080p": "1920:1080",
                "4k": "3840:2160"
            }

            scale = resolution_map.get(resolution, resolution_map["1080p"])

            cmd = [
                'ffmpeg',
                '-i', str(video_path),
                '-i', str(audio_path),
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '23',
                '-vf', f'scale={scale}:force_original_aspect_ratio=decrease,pad={scale}:(ow-iw)/2:(oh-ih)/2',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-shortest',
                '-movflags', '+faststart',  # Optimize for streaming
                '-y',
                str(output_path)
            ]

            logger.info(f"Running ffmpeg to create final video")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)

            logger.info(f"Final video created: {output_path}")

            # Clean up temporary watermarked video if created
            if add_watermark:
                try:
                    if 'video_with_watermark' in locals() and video_with_watermark.exists():
                        video_with_watermark.unlink()
                except:
                    pass  # Ignore cleanup errors

            return output_path

        except subprocess.CalledProcessError as e:
            logger.error(f"Video composition failed: {e.stderr}")
            raise RuntimeError(f"Failed to compose video: {e.stderr}")

    def _add_watermark(
        self,
        input_path: Path,
        output_path: Path,
        watermark_text: str
    ):
        """
        Add text watermark to video.

        Args:
            input_path: Input video path
            output_path: Output video path
            watermark_text: Text to display
        """
        try:
            # Add semi-transparent watermark at bottom
            drawtext_filter = (
                f"drawtext=text='{watermark_text}':"
                f"fontcolor=white@0.7:"
                f"fontsize=16:"
                f"x=(w-text_w)/2:"
                f"y=h-th-10"
            )

            cmd = [
                'ffmpeg',
                '-i', str(input_path),
                '-vf', drawtext_filter,
                '-c:a', 'copy',
                '-y',
                str(output_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

            if result.returncode == 0:
                logger.info("Watermark added")
            else:
                # Check if it's a drawtext filter issue
                if 'drawtext' in result.stderr or 'No such filter' in result.stderr:
                    logger.debug("FFmpeg drawtext filter not available - skipping watermark")
                else:
                    logger.warning(f"Failed to add watermark: {result.stderr[:200]}")
                # Continue without watermark rather than failing

        except Exception as e:
            logger.debug(f"Watermark error: {e}")
            # Continue without watermark rather than failing

    def add_intro_outro(
        self,
        main_video_path: Path,
        output_path: Path,
        intro_path: Optional[Path] = None,
        outro_path: Optional[Path] = None
    ) -> Path:
        """
        Add intro and/or outro to video.

        Args:
            main_video_path: Main video path
            output_path: Output path
            intro_path: Optional intro video path
            outro_path: Optional outro video path

        Returns:
            Path to video with intro/outro
        """
        try:
            videos_to_concat = []

            if intro_path and intro_path.exists():
                videos_to_concat.append(intro_path)

            videos_to_concat.append(main_video_path)

            if outro_path and outro_path.exists():
                videos_to_concat.append(outro_path)

            if len(videos_to_concat) == 1:
                # No intro/outro, just copy
                import shutil
                shutil.copy(main_video_path, output_path)
                return output_path

            # Create concat file
            concat_file = self.temp_dir / "concat_list.txt"
            with open(concat_file, 'w') as f:
                for video in videos_to_concat:
                    f.write(f"file '{video.absolute()}'\n")

            cmd = [
                'ffmpeg',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(concat_file),
                '-c', 'copy',
                '-y',
                str(output_path)
            ]

            subprocess.run(cmd, capture_output=True, text=True, check=True)

            concat_file.unlink()

            logger.info("Intro/outro added")
            return output_path

        except Exception as e:
            logger.error(f"Failed to add intro/outro: {e}")
            raise RuntimeError(f"Failed to add intro/outro: {e}")

    def create_thumbnail(
        self,
        video_path: Path,
        output_path: Path,
        timestamp: float = 5.0
    ) -> Path:
        """
        Create thumbnail from video.

        Args:
            video_path: Video path
            output_path: Output image path
            timestamp: Timestamp to extract

        Returns:
            Path to thumbnail
        """
        try:
            cmd = [
                'ffmpeg',
                '-ss', str(timestamp),
                '-i', str(video_path),
                '-vframes', '1',
                '-vf', 'scale=1280:720',
                '-q:v', '2',
                '-y',
                str(output_path)
            ]

            subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Thumbnail created: {output_path}")
            return output_path

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create thumbnail: {e.stderr}")
            raise RuntimeError(f"Failed to create thumbnail: {e.stderr}")
