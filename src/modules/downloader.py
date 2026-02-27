"""YouTube video downloader module."""

import yt_dlp
from pathlib import Path
import logging
import re
from typing import Dict, Any

logger = logging.getLogger(__name__)


def normalize_name(name: str, max_length: int = 60) -> str:
    """
    Normalize a name to lowercase with underscores, alphanumeric only.

    Args:
        name: Input name
        max_length: Maximum length of normalized name (default 60)

    Returns:
        Normalized name (e.g., "The CAPE Ratio — 150 Years" -> "the_cape_ratio_150_years")
    """
    # Convert to lowercase
    name = name.lower()
    # Replace spaces and hyphens with underscores
    name = re.sub(r'[\s\-]+', '_', name)
    # Remove all non-alphanumeric characters except underscores
    name = re.sub(r'[^a-z0-9_]', '', name)
    # Remove multiple consecutive underscores
    name = re.sub(r'_+', '_', name)
    # Strip leading/trailing underscores
    name = name.strip('_')
    # Truncate to max_length
    if len(name) > max_length:
        name = name[:max_length].rstrip('_')
    return name


class VideoDownloader:
    """Downloads videos from YouTube and other platforms using yt-dlp."""

    def __init__(self, output_dir: Path):
        """
        Initialize the downloader.

        Args:
            output_dir: Directory to save downloaded videos
        """
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def download(
        self,
        url: str,
        quality: str = "1080p",
        output_filename: str = None
    ) -> Dict[str, Any]:
        """
        Download video from URL into organized folder structure.

        Args:
            url: YouTube or other video URL
            quality: Desired quality (720p, 1080p, 4k, best)
            output_filename: Optional custom filename (overrides normalized naming)

        Returns:
            Dictionary with:
                - video_path: Path to downloaded video
                - metadata: Video metadata (title, duration, etc.)
                - video_folder: Path to video-specific folder
        """
        try:
            logger.info(f"Starting download from: {url}")

            # First, extract video info to get ID and title
            ydl_opts_info = {
                'quiet': True,
                'no_warnings': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                info = ydl.extract_info(url, download=False)

            # Extract video ID and title
            video_id = info.get('id', 'unknown')
            title = info.get('title', 'unknown_video')
            normalized_title = normalize_name(title)

            # Create video-specific folder: {video_id}_{normalized_title}/
            # Note: video_id is kept as-is (not lowercased or mangled)
            video_folder = self.output_dir / f"{video_id}_{normalized_title}"
            video_folder.mkdir(parents=True, exist_ok=True)
            logger.info(f"Using video folder: {video_folder}")

            # Use generic filename or custom one (folder name already contains video title)
            if output_filename is None:
                output_filename = "source_video.%(ext)s"

            output_template = str(video_folder / output_filename)

            # Quality format selection
            format_string = self._get_format_string(quality)

            ydl_opts = {
                'format': format_string,
                'outtmpl': output_template,
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'writethumbnail': True,
                'writesubtitles': False,
                'writeautomaticsub': False,
                'ignoreerrors': False,
                # No postprocessors - use native format (webm, mp4, mkv, etc.)
                # ffmpeg can handle all formats in later pipeline stages
                # Use web and android clients for better format availability
                'extractor_args': {
                    'youtube': {
                        'player_client': ['web', 'android'],
                    }
                },
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Download the video
                ydl.download([url])

                # Find the actual downloaded file (yt-dlp may choose different format than expected)
                # Look for source_video.* in the video folder
                downloaded_files = list(video_folder.glob("source_video.*"))
                # Filter out .webp thumbnail files
                video_files = [f for f in downloaded_files if f.suffix.lower() not in ['.webp', '.jpg', '.png']]

                if not video_files:
                    raise RuntimeError(f"Downloaded video not found in {video_folder}")

                video_path = video_files[0]
                logger.info(f"Download completed: {video_path}")

                metadata = {
                    'video_id': video_id,
                    'title': title,
                    'normalized_title': normalized_title,
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                    'upload_date': info.get('upload_date', 'Unknown'),
                    'description': info.get('description', ''),
                    'view_count': info.get('view_count', 0),
                    'width': info.get('width', 0),
                    'height': info.get('height', 0),
                }

                return {
                    'video_path': video_path,
                    'video_folder': video_folder,
                    'metadata': metadata
                }

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Download failed: {error_msg}")

            # Provide more helpful error messages
            if "Only images are available" in error_msg or "Requested format is not available" in error_msg:
                raise RuntimeError(
                    "Video not available for download. This may be a YouTube Short, "
                    "premiere, live stream, or restricted content. Try a different video."
                )
            else:
                raise RuntimeError(f"Failed to download video: {error_msg}")

    def _get_format_string(self, quality: str) -> str:
        """
        Get yt-dlp format string based on quality preference.

        Args:
            quality: Quality string (720p, 1080p, 4k, best)

        Returns:
            Format string for yt-dlp with multiple fallbacks
        """
        quality_map = {
            '720p': 'bestvideo[height<=720]+bestaudio/best[height<=720]/bestvideo+bestaudio/best',
            '1080p': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/bestvideo+bestaudio/best',
            '4k': 'bestvideo[height<=2160]+bestaudio/best[height<=2160]/bestvideo+bestaudio/best',
            'best': 'bestvideo+bestaudio/best',
        }

        return quality_map.get(quality, quality_map['1080p'])

    def get_video_info(self, url: str) -> Dict[str, Any]:
        """
        Get video information without downloading.

        Args:
            url: Video URL

        Returns:
            Video metadata dictionary
        """
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                return {
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                    'description': info.get('description', ''),
                    'view_count': info.get('view_count', 0),
                }

        except Exception as e:
            logger.error(f"Failed to get video info: {e}")
            raise RuntimeError(f"Failed to get video info: {e}")
