"""Video processing utilities."""

import subprocess
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def combine_audio_video(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    resolution: str = "1080p"
) -> Path:
    """
    Combine video and audio into final output.

    Args:
        video_path: Path to video file
        audio_path: Path to audio file
        output_path: Path to output file
        resolution: Target resolution (720p, 1080p, 4k)

    Returns:
        Path to combined video
    """
    # Map resolution strings to dimensions
    resolution_map = {
        "720p": "1280:720",
        "1080p": "1920:1080",
        "4k": "3840:2160"
    }

    scale = resolution_map.get(resolution, resolution_map["1080p"])

    try:
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
            '-y',
            str(output_path)
        ]

        logger.info(f"Combining video and audio to {output_path}")
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info("Video combination completed")
        return output_path

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to combine audio/video: {e.stderr}")
        raise RuntimeError(f"Failed to combine audio/video: {e.stderr}")


def extract_frame(video_path: Path, output_path: Path, timestamp: float = 5.0) -> Path:
    """
    Extract a single frame from video for reference image.

    Args:
        video_path: Path to video file
        output_path: Path to output image
        timestamp: Timestamp in seconds to extract frame

    Returns:
        Path to extracted frame
    """
    try:
        cmd = [
            'ffmpeg',
            '-ss', str(timestamp),
            '-i', str(video_path),
            '-vframes', '1',
            '-q:v', '2',
            '-y',
            str(output_path)
        ]

        logger.info(f"Extracting frame at {timestamp}s from {video_path}")
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return output_path

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to extract frame: {e.stderr}")
        raise RuntimeError(f"Failed to extract frame: {e.stderr}")


def get_video_info(video_path: Path) -> dict:
    """
    Get comprehensive video information.

    Args:
        video_path: Path to video file

    Returns:
        Dictionary with video metadata
    """
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration,size,bit_rate',
            '-show_entries', 'stream=width,height,codec_name,r_frame_rate',
            '-of', 'json',
            str(video_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        import json
        return json.loads(result.stdout)

    except (subprocess.CalledProcessError, ValueError) as e:
        logger.error(f"Failed to get video info: {e}")
        raise RuntimeError(f"Failed to get video info: {e}")
