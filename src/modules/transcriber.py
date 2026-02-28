"""Audio transcription module using OpenAI Whisper."""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging
from openai import OpenAI
from src.utils.audio_utils import split_audio_by_size, get_audio_duration

logger = logging.getLogger(__name__)


class Transcriber:
    """Transcribes audio using Whisper (via Groq or OpenAI)."""

    GROQ_BASE_URL = "https://api.groq.com/openai/v1"
    GROQ_MODEL = "whisper-large-v3"
    OPENAI_MODEL = "whisper-1"

    def __init__(self, api_key: str, provider: str = "openai", groq_api_key: str = ""):
        """
        Initialize the transcriber.

        Args:
            api_key: OpenAI API key (used when provider="openai", or as fallback)
            provider: "groq" (free, whisper-large-v3) or "openai" (paid, whisper-1)
            groq_api_key: Groq API key (required when provider="groq")
        """
        if provider == "groq" and groq_api_key:
            self.client = OpenAI(api_key=groq_api_key, base_url=self.GROQ_BASE_URL)
            self.model = self.GROQ_MODEL
            logger.info("Transcriber using Groq (free whisper-large-v3)")
        else:
            if provider == "groq":
                logger.warning("Groq provider requested but no GROQ_API_KEY set — falling back to OpenAI Whisper")
            self.client = OpenAI(api_key=api_key)
            self.model = self.OPENAI_MODEL
            logger.info("Transcriber using OpenAI (whisper-1)")

    def fetch_youtube_transcript(self, video_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch transcript directly from YouTube if available.

        Args:
            video_id: YouTube video ID

        Returns:
            Dictionary with same format as transcribe():
                - text: Full transcript text
                - segments: List of transcript segments with timestamps
                - language: Detected language
                - duration: Audio duration
            Returns None if transcript is not available
        """
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            from youtube_transcript_api._errors import (
                TranscriptsDisabled,
                NoTranscriptFound,
                VideoUnavailable
            )

            logger.info(f"Attempting to fetch YouTube transcript for video: {video_id}")

            # Fetch transcript from YouTube using correct API
            ytt_api = YouTubeTranscriptApi()
            transcript_list = ytt_api.fetch(video_id)

            # Convert to our format
            # Segments are FetchedTranscriptSnippet objects with .text, .start, .duration attributes
            segments = []
            all_text = []

            for entry in transcript_list:
                start_time = entry.start
                duration = entry.duration
                text = entry.text

                segments.append({
                    'start': start_time,
                    'end': start_time + duration,
                    'text': text
                })
                all_text.append(text)

            # Calculate total duration from last segment
            total_duration = segments[-1]['end'] if segments else 0

            result = {
                'text': ' '.join(all_text),
                'segments': segments,
                'language': 'unknown',  # YouTube API doesn't always provide language
                'duration': total_duration
            }

            logger.info(f"Successfully fetched YouTube transcript: {len(segments)} segments, {total_duration:.1f}s")
            return result

        except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as e:
            logger.debug(f"YouTube transcript not available: {e}")
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch YouTube transcript: {e}")
            return None

    def transcribe(
        self,
        audio_path: Path,
        language: str = None,
        include_timestamps: bool = True
    ) -> Dict[str, Any]:
        """
        Transcribe audio file, automatically chunking if it exceeds size limits.

        Args:
            audio_path: Path to audio file
            language: Optional language code (e.g., 'en')
            include_timestamps: Include word-level timestamps

        Returns:
            Dictionary with:
                - text: Full transcript text
                - segments: List of transcript segments with timestamps
                - language: Detected language
                - duration: Audio duration
        """
        try:
            logger.info(f"Starting transcription of: {audio_path}")

            # Check file size and split if necessary
            file_size_mb = audio_path.stat().st_size / (1024 * 1024)
            max_size_mb = 24.0  # Stay under 25MB API limit

            if file_size_mb > max_size_mb:
                logger.info(f"File size ({file_size_mb:.1f}MB) exceeds limit, splitting into chunks")
                return self._transcribe_chunked(audio_path, language, include_timestamps)
            else:
                return self._transcribe_single(audio_path, language, include_timestamps)

        except Exception as e:
            from ..utils.audio_utils import extract_api_error_message
            from ..utils.exceptions import ApiError
            error_msg = extract_api_error_message(e, "OpenAI")
            if error_msg:
                from colorama import Fore, Style
                print(f"\n{Fore.RED}{error_msg}{Style.RESET_ALL}\n")
                raise ApiError(error_msg) from None
            else:
                logger.error(f"Transcription failed: {e}")
                raise RuntimeError(f"Failed to transcribe audio: {e}")

    def _transcribe_single(
        self,
        audio_path: Path,
        language: str = None,
        include_timestamps: bool = True
    ) -> Dict[str, Any]:
        """Transcribe a single audio file."""
        with open(audio_path, 'rb') as audio_file:
            # Use timestamp granularities for word-level timing
            kwargs = {
                'file': audio_file,
                'model': self.model,
                'response_format': 'verbose_json',
            }

            if language:
                kwargs['language'] = language

            if include_timestamps:
                kwargs['timestamp_granularities'] = ['segment']

            transcript = self.client.audio.transcriptions.create(**kwargs)

        logger.info("Transcription completed")

        # Parse the response
        result = {
            'text': transcript.text,
            'language': getattr(transcript, 'language', 'unknown'),
            'duration': getattr(transcript, 'duration', 0),
            'segments': []
        }

        # Extract segments with timestamps if available
        if hasattr(transcript, 'segments') and transcript.segments:
            result['segments'] = [
                {
                    'start': getattr(seg, 'start', 0),
                    'end': getattr(seg, 'end', 0),
                    'text': getattr(seg, 'text', ''),
                }
                for seg in transcript.segments
            ]

        return result

    def _transcribe_chunked(
        self,
        audio_path: Path,
        language: str = None,
        include_timestamps: bool = True
    ) -> Dict[str, Any]:
        """Transcribe audio file by splitting into chunks."""
        # Split audio into manageable chunks
        chunks = split_audio_by_size(audio_path, max_size_mb=24.0)

        try:
            all_text = []
            all_segments = []
            time_offset = 0
            detected_language = None
            total_duration = 0

            for i, chunk_path in enumerate(chunks):
                logger.info(f"Transcribing chunk {i+1}/{len(chunks)}")

                # Get chunk duration for time offset
                chunk_duration = get_audio_duration(chunk_path)

                # Transcribe chunk
                chunk_result = self._transcribe_single(chunk_path, language, include_timestamps)

                # Accumulate text
                all_text.append(chunk_result['text'])

                # Adjust segment timestamps and accumulate
                if chunk_result['segments']:
                    for seg in chunk_result['segments']:
                        all_segments.append({
                            'start': seg['start'] + time_offset,
                            'end': seg['end'] + time_offset,
                            'text': seg['text']
                        })

                # Update offsets and metadata
                time_offset += chunk_duration
                total_duration += chunk_duration

                if detected_language is None:
                    detected_language = chunk_result['language']

            logger.info(f"Chunked transcription completed: {len(chunks)} chunks processed")

            return {
                'text': ' '.join(all_text),
                'language': detected_language or 'unknown',
                'duration': total_duration,
                'segments': all_segments
            }

        finally:
            # Clean up chunk files (but keep the original)
            if len(chunks) > 1:
                for chunk_path in chunks:
                    if chunk_path != audio_path:
                        try:
                            chunk_path.unlink()
                            logger.debug(f"Deleted chunk: {chunk_path}")
                        except Exception as e:
                            logger.warning(f"Failed to delete chunk {chunk_path}: {e}")

    def save_transcript(self, transcript: Dict[str, Any], output_path: Path) -> Path:
        """
        Save transcript to JSON file.

        Args:
            transcript: Transcript dictionary
            output_path: Path to output JSON file

        Returns:
            Path to saved file
        """
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(transcript, f, indent=2, ensure_ascii=False)

            logger.info(f"Transcript saved to: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Failed to save transcript: {e}")
            raise RuntimeError(f"Failed to save transcript: {e}")

    def load_transcript(self, transcript_path: Path) -> Dict[str, Any]:
        """
        Load transcript from JSON file.

        Args:
            transcript_path: Path to transcript JSON file

        Returns:
            Transcript dictionary
        """
        try:
            with open(transcript_path, 'r', encoding='utf-8') as f:
                transcript = json.load(f)

            logger.info(f"Transcript loaded from: {transcript_path}")
            return transcript

        except Exception as e:
            logger.error(f"Failed to load transcript: {e}")
            raise RuntimeError(f"Failed to load transcript: {e}")

    def extract_clean_speech_segments(
        self,
        transcript: Dict[str, Any],
        min_duration: float = 120,
        max_duration: float = 300
    ) -> List[Dict[str, float]]:
        """
        Extract clean speech segments suitable for voice cloning.

        Args:
            transcript: Transcript with segments
            min_duration: Minimum total duration needed (seconds)
            max_duration: Maximum total duration (seconds)

        Returns:
            List of segments with start/end times
        """
        if not transcript.get('segments'):
            logger.warning("No segments available for extraction")
            return []

        # Select segments that are clear and substantial
        # Avoid very short segments (< 2 seconds) as they may be incomplete
        clean_segments = []
        total_duration = 0

        for segment in transcript['segments']:
            duration = segment['end'] - segment['start']

            # Skip very short or very long segments
            if duration < 2.0 or duration > 30.0:
                continue

            # Skip segments with too few words (likely incomplete)
            word_count = len(segment['text'].split())
            if word_count < 5:
                continue

            clean_segments.append({
                'start': segment['start'],
                'end': segment['end'],
                'duration': duration,
                'text': segment['text']
            })

            total_duration += duration

            # Stop when we have enough
            if total_duration >= max_duration:
                break

        logger.info(f"Extracted {len(clean_segments)} clean segments, total {total_duration:.1f}s")

        return clean_segments
