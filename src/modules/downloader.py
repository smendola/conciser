"""YouTube video downloader module."""

import yt_dlp
from pathlib import Path
import logging
import re
import json
from urllib import request
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def truncate_at_punctuation(title: str) -> str:
    """
    Truncate a YouTube title at the first 'hard' punctuation character.

    Keeps apostrophes and hyphens (common within words) but stops at anything
    that typically introduces a subtitle or parenthetical, e.g.:
      "James Carville: yo mama..."  ->  "James Carville"
      "US Panic: Japan's Debt..."   ->  "US Panic"
      "Claude's Brain (stuff)"      ->  "Claude's Brain "  ->  "Claude's Brain"

    If the truncated result is empty (e.g. title starts with '#'), the original
    title is returned unchanged.
    """
    # Characters that signal a subtitle / parenthetical boundary
    STOP_CHARS = set('!"#$%()*+,./:;<=>?@[\\]^{|}~')
    for i, ch in enumerate(title):
        if ch in STOP_CHARS:
            result = title[:i].strip()
            return result if result else title
    return title


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

    def __init__(self, output_dir: Path, youtube_cookie_file: str = "", youtube_proxy_url: str = ""):
        """
        Initialize the downloader.

        Args:
            output_dir: Directory to save downloaded videos
            youtube_cookie_file: Optional path to Netscape-format YouTube cookies file
            youtube_proxy_url: Optional proxy URL for yt-dlp/caption requests
        """
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.youtube_cookie_file = youtube_cookie_file.strip()
        self.youtube_proxy_url = youtube_proxy_url.strip()

    def _apply_youtube_auth(self, ydl_opts: Dict[str, Any]) -> Dict[str, Any]:
        """Add optional YouTube authentication options to yt-dlp config."""
        if not self.youtube_cookie_file:
            return ydl_opts

        cookie_path = Path(self.youtube_cookie_file).expanduser()
        if not cookie_path.exists():
            logger.warning(f"YOUTUBE_COOKIE_FILE not found: {cookie_path}")
            return ydl_opts

        ydl_opts['cookiefile'] = str(cookie_path)
        return ydl_opts

    def _apply_youtube_proxy(self, ydl_opts: Dict[str, Any]) -> Dict[str, Any]:
        """Add optional proxy configuration to yt-dlp config."""
        if not self.youtube_proxy_url:
            return ydl_opts

        ydl_opts['proxy'] = self.youtube_proxy_url
        return ydl_opts

    @staticmethod
    def _choose_caption_track(info: Dict[str, Any]) -> tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
        """Pick the best available subtitle/caption track from yt-dlp metadata."""
        ext_preference = {'json3': 0, 'vtt': 1, 'srv3': 2, 'srv2': 3, 'srv1': 4, 'ttml': 5, 'srt': 6}
        lang_preference = ('en-orig', 'en', 'en-US', 'en-GB')

        candidates: list[tuple[int, int, str, Dict[str, Any]]] = []
        for source_name, source in (
            ('subtitles', info.get('subtitles') or {}),
            ('automatic_captions', info.get('automatic_captions') or {}),
        ):
            if not isinstance(source, dict):
                continue

            for lang, tracks in source.items():
                if not isinstance(tracks, list):
                    continue

                for track in tracks:
                    if not isinstance(track, dict):
                        continue
                    if not track.get('url'):
                        continue

                    ext = (track.get('ext') or '').lower()
                    lang_rank = lang_preference.index(lang) if lang in lang_preference else len(lang_preference)
                    ext_rank = ext_preference.get(ext, 99)
                    source_rank = 0 if source_name == 'subtitles' else 1
                    candidates.append((lang_rank, source_rank, ext_rank, lang, track))

        if not candidates:
            return None, None, None

        candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        _, _, _, selected_lang, selected_track = candidates[0]
        selected_source = 'subtitles' if selected_track in (info.get('subtitles') or {}).get(selected_lang, []) else 'automatic_captions'
        return selected_track, selected_lang, selected_source

    @staticmethod
    def _caption_payload_to_text(ext: str, payload_text: str) -> str:
        """Convert a subtitle payload to plain transcript text."""
        ext = (ext or '').lower()
        if ext == 'json3':
            data = json.loads(payload_text)
            parts = []
            for event in data.get('events', []):
                if not isinstance(event, dict):
                    continue
                for segment in event.get('segs') or []:
                    if not isinstance(segment, dict):
                        continue
                    text = segment.get('utf8', '')
                    if text:
                        parts.append(text)
            return ''.join(parts).replace('\n', ' ').strip()

        lines = []
        for line in payload_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if '-->' in stripped:
                continue
            if stripped.isdigit():
                continue
            if stripped.startswith('WEBVTT'):
                continue
            if stripped.startswith('NOTE'):
                continue
            lines.append(stripped)
        return ' '.join(lines).strip()

    def fetch_transcript_via_yt_dlp(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Fetch transcript text using yt-dlp metadata + caption URL retrieval.

        Returns:
            Dict with text and raw payload metadata, or None if unavailable.
        """
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'ignoreconfig': True,
            'skip_download': True,
            'extract_flat': False,
            'extractor_args': {
                'youtube': {
                    'player_client': ['web', 'android'],
                }
            },
        }
        ydl_opts = self._apply_youtube_auth(ydl_opts)
        ydl_opts = self._apply_youtube_proxy(ydl_opts)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            track, language, source = self._choose_caption_track(info)
            if not track:
                return None

            caption_url = track.get('url')
            ext = (track.get('ext') or 'json3').lower()
            if self.youtube_proxy_url:
                opener = request.build_opener(request.ProxyHandler({'http': self.youtube_proxy_url, 'https': self.youtube_proxy_url}))
                response = opener.open(caption_url, timeout=30)
            else:
                response = request.urlopen(caption_url, timeout=30)

            with response:
                payload_text = response.read().decode('utf-8', errors='replace')

            text = self._caption_payload_to_text(ext, payload_text)
            if not text:
                return None

            raw_payload = payload_text
            if ext == 'json3':
                try:
                    raw_payload = json.loads(payload_text)
                except json.JSONDecodeError:
                    raw_payload = payload_text

            return {
                'text': text,
                'language': language or 'unknown',
                'source': source or 'automatic_captions',
                'format': ext,
                'caption_url': caption_url,
                'raw': raw_payload,
            }

        except Exception as e:
            logger.warning(f"yt-dlp transcript fallback failed: {e}")
            return None

    def download(
        self,
        url: str,
        quality: str = "1080p",
        output_filename: str = None,
        folder_label: str = None,
        metadata_only: bool = False,
        existing_folder: Path = None
    ) -> Dict[str, Any]:
        """
        Download video from URL into organized folder structure, or just fetch metadata.

        Args:
            url: YouTube or other video URL
            quality: Desired quality (720p, 1080p, 4k, best)
            output_filename: Optional custom filename (overrides normalized naming)
            folder_label: Optional label for folder name (from videos.txt)
            metadata_only: If True, only fetch metadata and create folder, skip video download
            existing_folder: Optional existing folder to reuse instead of creating new one

        Returns:
            Dictionary with:
                - video_path: Path to downloaded video (None if metadata_only=True)
                - metadata: Video metadata (title, duration, etc.)
                - video_folder: Path to video-specific folder
        """
        try:
            if metadata_only:
                logger.info(f"Fetching metadata from: {url}")
            else:
                logger.info(f"Starting download from: {url}")

            # First, extract video info to get ID and title
            ydl_opts_info = {
                'quiet': True,
                'no_warnings': True,
                'ignoreconfig': True,
                # Use web/android clients for consistency with download path.
                'extractor_args': {
                    'youtube': {
                        'player_client': ['web', 'android'],
                    }
                },
            }
            ydl_opts_info = self._apply_youtube_auth(ydl_opts_info)
            ydl_opts_info = self._apply_youtube_proxy(ydl_opts_info)

            with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                info = ydl.extract_info(url, download=False)

            # Extract video ID and title
            video_id = info.get('id', 'unknown')
            title = info.get('title', 'unknown_video')
            # If a label was supplied (e.g. from videos.txt), use it for the folder
            # name instead of the YT title so folder names are human-meaningful.
            if folder_label:
                normalized_title = normalize_name(folder_label)
            else:
                normalized_title = normalize_name(truncate_at_punctuation(title))

            # Create video-specific folder: {video_id}_{normalized_title}/
            # Note: video_id is kept as-is (not lowercased or mangled)
            if existing_folder:
                if existing_folder.exists():
                    video_folder = existing_folder
                    logger.info(f"Using existing folder: {video_folder}")
                else:
                    logger.warning(f"Existing folder {existing_folder} not found, creating new folder")
                    video_folder = self.output_dir / f"{video_id}_{normalized_title}"
                    video_folder.mkdir(parents=True, exist_ok=True)
                    logger.info(f"Created new video folder: {video_folder}")
            else:
                video_folder = self.output_dir / f"{video_id}_{normalized_title}"
                video_folder.mkdir(parents=True, exist_ok=True)
                logger.info(f"Using video folder: {video_folder}")

            # Use generic filename or custom one (folder name already contains video title)
            if output_filename is None:
                output_filename = "source_video.%(ext)s"

            output_template = str(video_folder / output_filename)
            thumbnail_template = str(video_folder / "thumbnail.%(ext)s")

            # If metadata_only, return early without downloading
            if metadata_only:
                # Ensure we have a thumbnail file saved in the folder for cover art embedding.
                try:
                    ydl_thumb_opts = {
                        'quiet': True,
                        'no_warnings': True,
                        'ignoreconfig': True,
                        'skip_download': True,
                        'writethumbnail': True,
                        'outtmpl': thumbnail_template,
                        'extractor_args': {
                            'youtube': {
                                'player_client': ['web', 'android'],
                            }
                        },
                    }
                    ydl_thumb_opts = self._apply_youtube_auth(ydl_thumb_opts)
                    ydl_thumb_opts = self._apply_youtube_proxy(ydl_thumb_opts)
                    with yt_dlp.YoutubeDL(ydl_thumb_opts) as ydl:
                        ydl.download([url])
                except Exception as e:
                    logger.warning(f"Failed to save thumbnail (metadata_only): {e}")

                metadata = {
                    'video_id': video_id,
                    'title': title,
                    'normalized_title': normalized_title,
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                }
                return {
                    'video_path': None,
                    'metadata': metadata,
                    'video_folder': video_folder
                }

            # Quality format selection
            format_string = self._get_format_string(quality)

            ydl_opts = {
                'format': format_string,
                'outtmpl': output_template,
                'paths': {'home': str(video_folder)},  # Explicitly set download directory
                'quiet': True,
                'no_warnings': True,
                'ignoreconfig': True,
                'extract_flat': False,
                'writethumbnail': True,
                'postprocessors': [
                    {
                        'key': 'FFmpegThumbnailsConvertor',
                        'format': 'webp',
                    }
                ],
                'postprocessor_args': [
                    '-update', '1',
                ],
                'writesubtitles': False,
                'writeautomaticsub': False,
                'ignoreerrors': False,
                'writethumbnail': True,
                'outtmpl': {
                    'default': output_template,
                    'thumbnail': thumbnail_template,
                },
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
            ydl_opts = self._apply_youtube_auth(ydl_opts)
            ydl_opts = self._apply_youtube_proxy(ydl_opts)

            # Ensure video folder exists right before download
            video_folder.mkdir(parents=True, exist_ok=True)

            # Verify the folder was created
            if not video_folder.exists():
                raise RuntimeError(f"Failed to create video folder: {video_folder}")

            logger.info(f"Downloading to: {output_template}")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Download the video
                ydl.download([url])

                # Find the actual downloaded file (yt-dlp may choose different format than expected)
                # Look for source_video.* in the video folder
                downloaded_files = list(video_folder.glob("source_video.*"))

                # Filter out image thumbnails
                video_files = [
                    f
                    for f in downloaded_files
                    if f.suffix.lower() not in ['.webp', '.jpg', '.jpeg', '.png']
                ]

                if not video_files:
                    raise RuntimeError(f"Downloaded video not found in {video_folder}")

                video_path = video_files[0]
                logger.info(f"Download completed: {video_path}")
                
                # Find and log thumbnail file
                thumbnail_files = [
                    f
                    for f in video_folder.glob("thumbnail.*")
                    if f.suffix.lower() in ['.webp', '.jpg', '.jpeg', '.png']
                ]
                if thumbnail_files:
                    thumbnail_path = thumbnail_files[0]
                    logger.info(f"Thumbnail saved to: {thumbnail_path}")
                else:
                    logger.warning("No thumbnail file found")

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
            error_msg_lower = error_msg.lower()

            # Provide more helpful error messages
            if "sign in to confirm you" in error_msg_lower and "not a bot" in error_msg_lower:
                hint = (
                    "YouTube blocked this request on the remote host. "
                    "Set YOUTUBE_COOKIE_FILE to a valid Netscape-format cookies file, "
                    "then retry. Example: YOUTUBE_COOKIE_FILE=/root/yt-cookies.txt"
                )
                raise RuntimeError(f"Failed to download video: {error_msg}\nHint: {hint}")
            elif (
                "only images are available" in error_msg_lower
                or "n challenge solving failed" in error_msg_lower
                or ("requested format is not available" in error_msg_lower and "[youtube]" in error_msg_lower)
            ):
                raise RuntimeError(
                    "YouTube did not return usable media formats from this host. "
                    "This is often a bot/challenge restriction on remote VMs. "
                    "Ensure YOUTUBE_COOKIE_FILE points to a fresh Netscape cookies file, "
                    "update yt-dlp, and retry."
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
            'ignoreconfig': True,
            'extract_flat': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['web', 'android'],
                }
            },
        }
        ydl_opts = self._apply_youtube_auth(ydl_opts)
        ydl_opts = self._apply_youtube_proxy(ydl_opts)

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
