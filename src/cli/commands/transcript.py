import json
import re
import sys
from pathlib import Path

import click
from colorama import Fore, Style

from ...config import get_settings
from ...modules.downloader import VideoDownloader
from ...modules.transcriber import Transcriber
from ..common import _load_videos_txt


def _suppress_httpx_info_logs() -> None:
    import logging as stdlib_logging
    stdlib_logging.getLogger('httpx').setLevel(stdlib_logging.WARNING)


from ..app import cli  # noqa: E402


def _extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from URL, or return bare ID if one was passed."""
    if re.fullmatch(r'[a-zA-Z0-9_-]{11}', url):
        return url

    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


@cli.command()
@click.argument('url')
@click.option(
    '--no-transcribe',
    is_flag=True,
    default=False,
    help='Only fetch YouTube transcript. If unavailable, fail without Whisper fallback.'
)
@click.option(
    '--output', '-o',
    type=str,
    default=None,
    help='Output transcript path (default: output/transcript_<video_id>.txt)'
)
@click.option(
    '--resume/--no-resume',
    default=True,
    help='Use existing transcript file if present (default: resume)'
)
def transcript(url, no_transcribe, output, resume):
    """Get transcript text from a video URL or videos.txt index."""
    _suppress_httpx_info_logs()

    import logging
    logger = logging.getLogger(__name__)

    try:
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}NBJ Transcript Extractor{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")

        if url.isdigit():
            idx = int(url)
            entries = _load_videos_txt()
            if not entries:
                click.echo(f"{Fore.RED}Error: videos.txt not found or empty.{Style.RESET_ALL}")
                sys.exit(1)
            if idx < 1 or idx > len(entries):
                click.echo(f"{Fore.RED}Error: index {idx} out of range — videos.txt has {len(entries)} entries.{Style.RESET_ALL}")
                sys.exit(1)

            video_id_resolved, label = entries[idx - 1]
            url = video_id_resolved
            print(f"Video index: {idx} → {video_id_resolved}" + (f"  ({label})" if label else ""))

        print(f"URL: {url}")
        print(f"Mode: {'YouTube transcript only' if no_transcribe else 'YouTube transcript with Whisper fallback'}\n")

        settings = get_settings()
        downloader = VideoDownloader(
            settings.temp_dir,
            youtube_cookie_file=settings.youtube_cookie_file,
            youtube_proxy_url=settings.youtube_proxy_url
        )
        transcriber = Transcriber(
            api_key=settings.openai_api_key,
            provider=settings.transcription_service,
            groq_api_key=settings.groq_api_key,
            youtube_proxy_url=settings.youtube_proxy_url
        )

        video_id = _extract_video_id(url)
        output_path = Path(output).with_suffix('.txt') if output else None

        if output_path is None:
            transcript_name = f"transcript_{video_id if video_id else 'video'}.txt"
            output_path = settings.output_dir / transcript_name

        if resume and output_path.exists():
            print(f"{Fore.CYAN}[1/2] Loading cached transcript...{Style.RESET_ALL}")
            transcript_text = output_path.read_text(encoding='utf-8')
            print(f"  Loaded: {output_path}")
            print(f"  Transcript: {len(transcript_text)} characters\n")
            print(f"{Fore.GREEN}✓ Done{Style.RESET_ALL}\n")
            return

        print(f"{Fore.CYAN}[1/2] Fetching YouTube transcript...{Style.RESET_ALL}")
        youtube_transcript = None
        if video_id:
            youtube_transcript = transcriber.fetch_youtube_transcript(video_id)

        if not youtube_transcript:
            logger.warning("YouTube transcript API unavailable, trying yt-dlp caption fallback")
            print(f"{Fore.YELLOW}  Warning: YouTube transcript API unavailable, trying yt-dlp captions.{Style.RESET_ALL}")
            youtube_transcript = downloader.fetch_transcript_via_yt_dlp(url)

        if youtube_transcript:
            logger.info("Using YouTube transcript")
            transcript_text = youtube_transcript['text']
            source_label = youtube_transcript.get('source', 'youtube_transcript_api')
            if source_label in {'subtitles', 'automatic_captions'}:
                format_label = youtube_transcript.get('format', 'unknown')
                print(f"  Source: yt-dlp captions ({source_label}, {format_label})")
            else:
                print(f"  Source: YouTube transcript")

            raw_payload = youtube_transcript.get('raw')
            if raw_payload is not None:
                raw_path = settings.temp_dir / f"yt_transcript_raw_{video_id if video_id else 'video'}.json"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text(
                    json.dumps(raw_payload, indent=2, ensure_ascii=False),
                    encoding='utf-8'
                )
                print(f"  Raw YT payload: {raw_path}")
        else:
            if no_transcribe:
                raise RuntimeError(
                    "YouTube transcript unavailable and --no-transcribe was set. "
                    "No Whisper fallback allowed."
                )

            logger.warning("YouTube transcript not available, falling back to Whisper transcription")
            print(f"{Fore.YELLOW}  Warning: YouTube transcript unavailable, falling back to Whisper.{Style.RESET_ALL}")

            if settings.transcription_service == 'groq':
                if not settings.groq_api_key and not settings.openai_api_key:
                    raise RuntimeError(
                        "Whisper fallback requires GROQ_API_KEY or OPENAI_API_KEY."
                    )
            elif not settings.openai_api_key:
                raise RuntimeError(
                    "Whisper fallback requires OPENAI_API_KEY when TRANSCRIPTION_SERVICE=openai."
                )

            print(f"{Fore.CYAN}[2/2] Downloading video for Whisper transcription...{Style.RESET_ALL}")
            video_info = downloader.download(url, metadata_only=False)
            video_path = video_info['video_path']
            print(f"  Downloaded: {video_path}")

            transcript_result = transcriber.transcribe(video_path)
            transcript_text = transcript_result['text']
            print(f"  Source: Whisper ({settings.transcription_service})")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(transcript_text, encoding='utf-8')

        print(f"\nTranscript: {len(transcript_text)} characters")
        print(f"Saved: {Fore.CYAN}{output_path}{Style.RESET_ALL}")
        print(f"\n{Fore.GREEN}✓ Transcript extraction complete!{Style.RESET_ALL}\n")

    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Interrupted by user{Style.RESET_ALL}")
        sys.exit(130)
    except Exception as e:
        click.echo(f"\n{Fore.RED}Error: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
