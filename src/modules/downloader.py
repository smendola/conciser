"""YouTube video downloader module."""

import yt_dlp
from pathlib import Path
import logging
import re
from typing import Dict, Any

logger = logging.getLogger(__name__)


def normalize_name(name: str) -> str:
    """
    Normalize a name to lowercase with underscores, alphanumeric only.

    Args:
        name: Input name

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
                'quiet': False,
                'no_warnings': False,
                'extract_flat': False,
                'writethumbnail': True,
                'writesubtitles': False,
                'writeautomaticsub': False,
                # No postprocessors - use native format (webm, mp4, mkv, etc.)
                # ffmpeg can handle all formats in later pipeline stages
                # Use web client to avoid JS runtime requirement for most videos
                'extractor_args': {
                    'youtube': {
                        'player_client': ['web', 'ios'],
                    }
                },
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Download the video
                ydl.download([url])

                # Get the actual filename (native format: webm, mp4, mkv, etc.)
                video_filename = ydl.prepare_filename(info)
                video_path = Path(video_filename)

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
            logger.error(f"Download failed: {e}")
            raise RuntimeError(f"Failed to download video: {e}")

    def _get_format_string(self, quality: str) -> str:
        """
        Get yt-dlp format string based on quality preference.

        Args:
            quality: Quality string (720p, 1080p, 4k, best)

        Returns:
            Format string for yt-dlp
        """
        quality_map = {
            '720p': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
            '1080p': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
            '4k': 'bestvideo[height<=2160]+bestaudio/best[height<=2160]',
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
