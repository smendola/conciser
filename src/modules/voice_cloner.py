"""Voice cloning module using ElevenLabs API."""

import time
from pathlib import Path
from typing import Optional, List
import logging
from elevenlabs.client import ElevenLabs
from elevenlabs import save

logger = logging.getLogger(__name__)


class VoiceCloner:
    """Clones voice and generates speech using ElevenLabs API."""

    def __init__(self, api_key: str):
        """
        Initialize the voice cloner.

        Args:
            api_key: ElevenLabs API key
        """
        self.client = ElevenLabs(api_key=api_key)

    def clone_voice(
        self,
        name: str,
        audio_files: List[Path],
        description: str = "Cloned voice for video condensation"
    ) -> str:
        """
        Clone a voice from audio samples.

        Args:
            name: Name for the cloned voice
            audio_files: List of audio file paths for cloning
            description: Description of the voice

        Returns:
            Voice ID of the cloned voice
        """
        try:
            logger.info(f"Cloning voice '{name}' from {len(audio_files)} sample(s)")

            # Open all audio files as binary
            files = [open(str(f), 'rb') for f in audio_files]

            try:
                # Create the voice using Instant Voice Cloning (IVC)
                voice = self.client.voices.ivc.create(
                    name=name,
                    description=description,
                    files=files
                )

                voice_id = voice.voice_id
                logger.info(f"Voice cloned successfully: {voice_id}")

                return voice_id

            finally:
                # Close all files
                for f in files:
                    f.close()

        except Exception as e:
            from ..utils.audio_utils import extract_api_error_message
            from colorama import Fore, Style
            error_msg = extract_api_error_message(e)
            if error_msg:
                logger.error(f"Voice cloning failed: {error_msg}")
                print(f"\n{Fore.RED}API Error: {error_msg}{Style.RESET_ALL}\n")
            else:
                logger.error(f"Voice cloning failed: {e}")
            raise RuntimeError(f"Failed to clone voice: {e}")

    def generate_speech(
        self,
        text: str,
        voice_id: str,
        output_path: Path,
        model: str = "eleven_multilingual_v2",
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        style: float = 0.0,
        use_speaker_boost: bool = True
    ) -> Path:
        """
        Generate speech from text using cloned voice.

        Args:
            text: Text to convert to speech
            voice_id: ElevenLabs voice ID
            output_path: Path to save generated audio
            model: ElevenLabs model to use
            stability: Voice stability (0-1)
            similarity_boost: Voice similarity boost (0-1)
            style: Style exaggeration (0-1)
            use_speaker_boost: Enable speaker boost

        Returns:
            Path to generated audio file
        """
        try:
            logger.info(f"Generating speech ({len(text)} characters)")

            # Generate audio using text_to_speech API
            audio = self.client.text_to_speech.convert(
                voice_id=voice_id,
                text=text,
                model_id=model,
                voice_settings={
                    "stability": stability,
                    "similarity_boost": similarity_boost,
                    "style": style,
                    "use_speaker_boost": use_speaker_boost
                }
            )

            # Save to file
            save(audio, str(output_path))

            logger.info(f"Speech generated and saved to: {output_path}")
            return output_path

        except Exception as e:
            from ..utils.audio_utils import extract_api_error_message
            from colorama import Fore, Style
            error_msg = extract_api_error_message(e)
            if error_msg:
                logger.error(f"Speech generation failed: {error_msg}")
                print(f"\n{Fore.RED}API Error: {error_msg}{Style.RESET_ALL}\n")
            else:
                logger.error(f"Speech generation failed: {e}")
            raise RuntimeError(f"Failed to generate speech: {e}")

    def generate_speech_chunked(
        self,
        text: str,
        voice_id: str,
        output_path: Path,
        chunk_size: int = 5000,
        **kwargs
    ) -> Path:
        """
        Generate speech from long text by chunking it.

        Args:
            text: Text to convert to speech
            voice_id: ElevenLabs voice ID
            output_path: Path to save generated audio
            chunk_size: Maximum characters per chunk
            **kwargs: Additional arguments for generate_speech

        Returns:
            Path to generated audio file
        """
        # For very long texts, we need to chunk them
        if len(text) <= chunk_size:
            return self.generate_speech(text, voice_id, output_path, **kwargs)

        try:
            logger.info(f"Generating speech in chunks (total: {len(text)} chars)")

            # Split text into sentences to avoid cutting mid-sentence
            sentences = self._split_into_sentences(text)

            # Group sentences into chunks
            chunks = []
            current_chunk = []
            current_length = 0

            for sentence in sentences:
                sentence_length = len(sentence)

                if current_length + sentence_length > chunk_size and current_chunk:
                    # Save current chunk and start new one
                    chunks.append(" ".join(current_chunk))
                    current_chunk = [sentence]
                    current_length = sentence_length
                else:
                    current_chunk.append(sentence)
                    current_length += sentence_length

            # Add the last chunk
            if current_chunk:
                chunks.append(" ".join(current_chunk))

            logger.info(f"Split into {len(chunks)} chunks")

            # Generate audio for each chunk
            chunk_paths = []
            for i, chunk_text in enumerate(chunks):
                chunk_path = output_path.with_stem(f"{output_path.stem}_chunk{i}")
                self.generate_speech(chunk_text, voice_id, chunk_path, **kwargs)
                chunk_paths.append(chunk_path)

                # Small delay to avoid rate limits
                if i < len(chunks) - 1:
                    time.sleep(1)

            # Combine all chunks using ffmpeg
            logger.info("Combining audio chunks")
            self._combine_audio_files(chunk_paths, output_path)

            # Clean up chunk files
            for chunk_path in chunk_paths:
                chunk_path.unlink()

            logger.info(f"Complete speech generated and saved to: {output_path}")
            return output_path

        except Exception as e:
            from ..utils.audio_utils import extract_api_error_message
            from colorama import Fore, Style
            error_msg = extract_api_error_message(e)
            if error_msg:
                logger.error(f"Chunked speech generation failed: {error_msg}")
                print(f"\n{Fore.RED}API Error: {error_msg}{Style.RESET_ALL}\n")
            else:
                logger.error(f"Chunked speech generation failed: {e}")
            raise RuntimeError(f"Failed to generate speech: {e}")

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        import re

        # Simple sentence splitter
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    def _combine_audio_files(self, input_paths: List[Path], output_path: Path):
        """Combine multiple audio files into one using ffmpeg."""
        import subprocess

        # Create a concat file
        concat_file = output_path.with_suffix('.txt')

        with open(concat_file, 'w') as f:
            for path in input_paths:
                f.write(f"file '{path.absolute()}'\n")

        try:
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

        finally:
            concat_file.unlink()

    def delete_voice(self, voice_id: str) -> bool:
        """
        Delete a cloned voice.

        Args:
            voice_id: Voice ID to delete

        Returns:
            True if successful
        """
        try:
            self.client.voices.delete(voice_id)
            logger.info(f"Voice deleted: {voice_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete voice: {e}")
            return False

    def list_voices(self) -> List[dict]:
        """
        List all available voices.

        Returns:
            List of voice dictionaries
        """
        try:
            voices = self.client.voices.get_all()
            return [
                {
                    'voice_id': v.voice_id,
                    'name': v.name,
                    'category': v.category
                }
                for v in voices.voices
            ]

        except Exception as e:
            logger.error(f"Failed to list voices: {e}")
            return []
