"""Video processing utilities."""

import subprocess
from pathlib import Path
from typing import List, Dict
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


def detect_scene_changes(
    video_path: Path,
    threshold: int = 27,
    min_scenes: int = 5
) -> List[Dict]:
    """
    Detect scene changes in video using PySceneDetect.

    Uses content-aware detection that's robust to camera shake and zooms,
    making it ideal for educational/presentation videos.

    Args:
        video_path: Path to video file
        threshold: Detection threshold (20-35, lower = more sensitive)
        min_scenes: Minimum expected scenes (triggers retry with lower threshold)

    Returns:
        List of scene dictionaries with:
            - scene_id: Scene number
            - start_time: Start timestamp in seconds
            - end_time: End timestamp in seconds
            - duration: Scene duration in seconds
    """
    try:
        from scenedetect import detect, ContentDetector

        logger.info(f"Detecting scenes in {video_path.name} (threshold={threshold})")

        # First pass with standard threshold
        scene_list = detect(
            str(video_path),
            ContentDetector(threshold=threshold),
            show_progress=False
        )

        # If too few scenes detected, retry with lower threshold
        if len(scene_list) < min_scenes:
            logger.info(f"Only {len(scene_list)} scenes detected, retrying with lower threshold")
            scene_list = detect(
                str(video_path),
                ContentDetector(threshold=threshold - 4),  # More sensitive
                show_progress=False
            )

        # Convert to our format
        scenes = []
        for i, (start_time, end_time) in enumerate(scene_list):
            scenes.append({
                'scene_id': i,
                'start_time': start_time.get_seconds(),
                'end_time': end_time.get_seconds(),
                'duration': (end_time - start_time).get_seconds()
            })

        logger.info(f"Detected {len(scenes)} scene changes")
        return scenes

    except ImportError as e:
        logger.warning(f"PySceneDetect not installed: {e}, falling back to evenly-spaced frames")
        return []
    except Exception as e:
        logger.error(f"Scene detection failed: {type(e).__name__}: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return []


def extract_scene_keyframes(
    video_path: Path,
    scenes: List[Dict],
    output_dir: Path,
    max_frames: int = 15
) -> List[Path]:
    """
    Extract keyframes for detected scenes.

    Args:
        video_path: Path to video file
        scenes: List of scene dictionaries from detect_scene_changes()
        output_dir: Directory to save extracted frames
        max_frames: Maximum number of frames to extract

    Returns:
        List of paths to extracted frames
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # If too many scenes, sample them proportionally
    if len(scenes) > max_frames:
        step = len(scenes) / max_frames
        selected_scenes = [scenes[int(i * step)] for i in range(max_frames)]
    else:
        selected_scenes = scenes

    frame_paths = []
    for i, scene in enumerate(selected_scenes):
        # Extract frame from middle of scene for better representation
        timestamp = scene['start_time'] + (scene['duration'] / 2)
        frame_path = output_dir / f"scene_{scene['scene_id']:03d}.jpg"

        try:
            extract_frame(video_path, frame_path, timestamp)
            frame_paths.append(frame_path)
        except Exception as e:
            logger.warning(f"Failed to extract frame {i}: {e}")

    logger.info(f"Extracted {len(frame_paths)} keyframes")
    return frame_paths
