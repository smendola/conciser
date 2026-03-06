"""Audio processing utilities."""

import subprocess
from pathlib import Path
from typing import Tuple, List, Optional
import logging
import ast

logger = logging.getLogger(__name__)


def extract_api_error_message(error: Exception, service_name: str = "API") -> Optional[str]:
    """
    Extract human-readable message from API error JSON response.

    Expected formats:
    - OpenAI: body: {'error': {'message': '...'}}
    - Anthropic: similar structure
    - ElevenLabs: body: {'detail': {'message': '...'}} or {'detail': 'string'}
    - D-ID: body: {'message': '...'}

    Args:
        error: Exception object
        service_name: Name of the service (e.g., "OpenAI", "ElevenLabs")

    Returns:
        Extracted message string with service prefix if found, None otherwise
    """
    error_str = str(error)

    # Look for body: {...} in error string
    if "body: {" not in error_str:
        return None

    try:
        # Extract dict from "body: {...}"
        start = error_str.index("body: {") + 6
        # Find matching closing brace
        brace_count = 0
        end = start
        for i, char in enumerate(error_str[start:], start):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    end = i + 1
                    break

        dict_str = error_str[start:end]
        # Use ast.literal_eval to parse Python dict string (with single quotes)
        body = ast.literal_eval(dict_str)

        # OpenAI: {'error': {'message': '...'}}
        if 'error' in body and isinstance(body['error'], dict):
            msg = body['error'].get('message')
            if msg and msg.strip():
                return f"{service_name}: {msg.strip()}"

        # ElevenLabs: {'detail': {'message': '...'}} or {'detail': 'string'}
        if 'detail' in body:
            detail = body['detail']
            if isinstance(detail, dict):
                msg = detail.get('message')
                if msg and msg.strip():
                    return f"{service_name}: {msg.strip()}"
            elif isinstance(detail, str) and detail.strip():
                return f"{service_name}: {detail.strip()}"

        # Generic: {'message': '...'}
        if 'message' in body:
            msg = body['message']
            if msg and msg.strip():
                return f"{service_name}: {msg.strip()}"

    except (SyntaxError, ValueError, KeyError, IndexError):
        pass

    return None


def extract_audio(video_path: Path, output_path: Path, sample_rate: int = 16000) -> Path:
    """
    Extract audio from video file using ffmpeg.

    Args:
        video_path: Path to input video file
        output_path: Path to output audio file
        sample_rate: Audio sample rate in Hz

    Returns:
        Path to extracted audio file
    """
    try:
        cmd = [
            'ffmpeg',
            '-i', str(video_path),
            '-vn',  # No video
            '-acodec', 'pcm_s16le',  # PCM audio codec
            '-ar', str(sample_rate),  # Sample rate
            '-ac', '1',  # Mono
            '-y',  # Overwrite output
            str(output_path)
        ]

        logger.info(f"Extracting audio from {video_path} to {output_path}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info("Audio extraction completed")
        return output_path

    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error: {e.stderr}")
        raise RuntimeError(f"Failed to extract audio: {e.stderr}")


def embed_cover_art_mp3(mp3_path: Path, image_path: Path, output_path: Optional[Path] = None) -> Path:
    """Embed cover art into an MP3 file using ffmpeg.

    Args:
        mp3_path: Path to input MP3
        image_path: Path to image (jpg/png/webp)
        output_path: Optional path for output MP3 (defaults to mp3_path)

    Returns:
        Path to MP3 with embedded cover art
    """
    if output_path is None:
        output_path = mp3_path

    if not mp3_path.exists():
        raise RuntimeError(f"MP3 not found: {mp3_path}")
    if not image_path.exists():
        raise RuntimeError(f"Cover image not found: {image_path}")

    # Many players (notably Windows Media Player) are unreliable with WebP cover art in MP3.
    # Convert to JPEG for maximum compatibility.
    cover_path = image_path
    tmp_cover = None
    if image_path.suffix.lower() == ".webp":
        tmp_cover = image_path.with_name(image_path.stem + ".cover.jpg")
        try:
            cmd_img = [
                'ffmpeg',
                '-i', str(image_path),
                '-frames:v', '1',
                '-q:v', '2',
                '-y',
                str(tmp_cover)
            ]
            subprocess.run(cmd_img, capture_output=True, text=True, check=True)
            cover_path = tmp_cover
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to convert WebP cover to JPEG; embedding WebP as-is. ffmpeg error: {e.stderr}")
            cover_path = image_path

    # Never write the ffmpeg output to the same path as the input.
    # For in-place embedding (output_path == mp3_path), also avoid reading directly from the
    # destination file while we replace it.
    tmp_in = None
    if output_path.resolve() == mp3_path.resolve():
        tmp_in = mp3_path.with_name(mp3_path.stem + ".cover.in" + mp3_path.suffix)
    tmp_out = output_path.with_name(output_path.stem + ".cover.tmp" + output_path.suffix)

    try:
        if tmp_in is not None:
            import shutil
            shutil.copy(mp3_path, tmp_in)

        cmd = [
            'ffmpeg',
            '-i', str(tmp_in if tmp_in is not None else mp3_path),
            '-i', str(cover_path),
            '-map', '0:a',
            '-map', '1:v',
            '-c', 'copy',
            '-id3v2_version', '3',
            '-metadata:s:v', 'title=Album cover',
            '-metadata:s:v', 'comment=Cover (front)',
            '-disposition:v:0', 'attached_pic',
            '-y',
            str(tmp_out)
        ]

        logger.info(f"Embedding cover art into MP3: {mp3_path} -> {output_path}")
        subprocess.run(cmd, capture_output=True, text=True, check=True)

        # Atomic replace of output
        tmp_out.replace(output_path)
        return output_path

    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error: {e.stderr}")
        raise RuntimeError(f"Failed to embed cover art: {e.stderr}")
    finally:
        tmp_out.unlink(missing_ok=True)
        if tmp_in is not None:
            tmp_in.unlink(missing_ok=True)
        if tmp_cover is not None:
            tmp_cover.unlink(missing_ok=True)


def get_audio_duration(audio_path: Path) -> float:
    """
    Get duration of audio file in seconds.

    Args:
        audio_path: Path to audio file

    Returns:
        Duration in seconds
    """
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(audio_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        duration = float(result.stdout.strip())
        return duration

    except (subprocess.CalledProcessError, ValueError) as e:
        logger.error(f"Failed to get audio duration: {e}")
        raise RuntimeError(f"Failed to get audio duration: {e}")


def extract_audio_segment(
    audio_path: Path,
    output_path: Path,
    start_time: float,
    duration: float
) -> Path:
    """
    Extract a segment of audio for voice cloning sample.

    Args:
        audio_path: Path to input audio file
        output_path: Path to output segment file
        start_time: Start time in seconds
        duration: Duration in seconds

    Returns:
        Path to extracted segment
    """
    try:
        cmd = [
            'ffmpeg',
            '-i', str(audio_path),
            '-ss', str(start_time),
            '-t', str(duration),
            '-acodec', 'copy',
            '-y',
            str(output_path)
        ]

        logger.info(f"Extracting audio segment: {start_time}s to {start_time + duration}s")
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return output_path

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to extract audio segment: {e.stderr}")
        raise RuntimeError(f"Failed to extract audio segment: {e.stderr}")


def normalize_audio(audio_path: Path, output_path: Path) -> Path:
    """
    Normalize audio volume levels.

    Args:
        audio_path: Path to input audio
        output_path: Path to output normalized audio

    Returns:
        Path to normalized audio
    """
    try:
        cmd = [
            'ffmpeg',
            '-i', str(audio_path),
            '-af', 'loudnorm=I=-16:LRA=11:TP=-1.5',
            '-ar', '44100',
            '-y',
            str(output_path)
        ]

        logger.info(f"Normalizing audio: {audio_path}")
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return output_path

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to normalize audio: {e.stderr}")
        raise RuntimeError(f"Failed to normalize audio: {e.stderr}")


def split_audio_by_size(
    audio_path: Path,
    max_size_mb: float = 24.0,
    output_dir: Path = None
) -> List[Path]:
    """
    Split audio file into chunks based on file size.

    Args:
        audio_path: Path to input audio file
        max_size_mb: Maximum size per chunk in MB (default 24MB to stay under 25MB limit)
        output_dir: Directory for output chunks (defaults to same as input)

    Returns:
        List of paths to audio chunks
    """
    try:
        # Get file size
        file_size_mb = audio_path.stat().st_size / (1024 * 1024)

        if file_size_mb <= max_size_mb:
            return [audio_path]

        # Get duration
        duration = get_audio_duration(audio_path)

        # Calculate number of chunks needed
        num_chunks = int(file_size_mb / max_size_mb) + 1
        chunk_duration = duration / num_chunks

        # Prepare output directory
        if output_dir is None:
            output_dir = audio_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)

        # Clean up any stale chunks from previous failed runs
        base_name = audio_path.stem
        import glob
        stale_chunks = glob.glob(str(output_dir / f"{base_name}_chunk_*.mp3"))
        for chunk in stale_chunks:
            Path(chunk).unlink(missing_ok=True)
            logger.debug(f"Removed stale chunk: {chunk}")

        # Split audio into chunks
        chunks = []

        for i in range(num_chunks):
            start_time = i * chunk_duration
            chunk_path = output_dir / f"{base_name}_chunk_{i:03d}.mp3"

            cmd = [
                'ffmpeg',
                '-i', str(audio_path),
                '-ss', str(start_time),
                '-t', str(chunk_duration),
                '-vn',  # No video
                '-acodec', 'libmp3lame',  # Re-encode to MP3
                '-q:a', '2',  # High quality MP3
                '-y',
                str(chunk_path)
            ]

            logger.info(f"Creating chunk {i+1}/{num_chunks}: {chunk_path}")
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            chunks.append(chunk_path)

        logger.info(f"Split audio into {len(chunks)} chunks")
        return chunks

    except Exception as e:
        logger.error(f"Failed to split audio: {e}")
        raise RuntimeError(f"Failed to split audio: {e}")


def get_video_resolution(video_path: Path) -> Tuple[int, int]:
    """
    Get video resolution (width, height).

    Args:
        video_path: Path to video file

    Returns:
        Tuple of (width, height)
    """
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height',
            '-of', 'csv=s=x:p=0',
            str(video_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        width, height = map(int, result.stdout.strip().split('x'))
        return width, height

    except (subprocess.CalledProcessError, ValueError) as e:
        logger.error(f"Failed to get video resolution: {e}")
        raise RuntimeError(f"Failed to get video resolution: {e}")
