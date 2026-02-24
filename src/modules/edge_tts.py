"""Edge TTS module using Microsoft Edge's TTS API."""

import asyncio
from pathlib import Path
from typing import List, Optional
import logging
import edge_tts

logger = logging.getLogger(__name__)


class EdgeTTS:
    """Text-to-speech using Microsoft Edge TTS (free, no API key)."""

    def __init__(self):
        """Initialize Edge TTS."""
        pass

    async def _generate_speech_async(
        self,
        text: str,
        voice: str,
        output_path: Path
    ) -> Path:
        """Generate speech asynchronously."""
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))
        return output_path

    def generate_speech(
        self,
        text: str,
        output_path: Path,
        voice: str = "en-US-AriaNeural"
    ) -> Path:
        """
        Generate speech from text using Edge TTS.

        Args:
            text: Text to convert to speech
            output_path: Path to save generated audio
            voice: Voice name (default: en-US-AriaNeural)

        Returns:
            Path to generated audio file
        """
        try:
            logger.info(f"Generating speech with Edge TTS ({len(text)} characters)")

            # Run async function
            asyncio.run(self._generate_speech_async(text, voice, output_path))

            logger.info(f"Speech generated and saved to: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Edge TTS generation failed: {e}")
            raise RuntimeError(f"Failed to generate speech with Edge TTS: {e}")

    def list_voices(self) -> List[dict]:
        """
        List all available Edge TTS voices.

        Returns:
            List of voice dictionaries with name, gender, locale
        """
        try:
            voices = asyncio.run(edge_tts.list_voices())
            return [
                {
                    'name': v['ShortName'],
                    'gender': v.get('Gender', 'Unknown'),
                    'locale': v.get('Locale', 'Unknown')
                }
                for v in voices
            ]
        except Exception as e:
            logger.error(f"Failed to list Edge TTS voices: {e}")
            return []

    def find_voice(self, locale: str = "en-US", gender: str = None) -> Optional[str]:
        """
        Find a suitable voice by locale and gender.

        Args:
            locale: Locale like "en-US", "en-GB", "es-ES"
            gender: "Male" or "Female" (optional)

        Returns:
            Voice name if found, None otherwise
        """
        voices = self.list_voices()

        for voice in voices:
            if voice['locale'] == locale:
                if gender is None or voice['gender'] == gender:
                    return voice['name']

        return None

    def resolve_voice_name(self, name: str) -> Optional[str]:
        """
        Resolve a short voice name to full voice ID.

        Args:
            name: Short name like "Aria", "Denise", or full name like "en-US-AriaNeural"

        Returns:
            Full voice name if found, None otherwise
        """
        # If it looks like a full voice name, return as-is
        if '-' in name and 'Neural' in name:
            return name

        # Search for matching voice
        voices = self.list_voices()
        name_lower = name.lower()

        # Prioritize en-US voices
        preferred_locales = ['en-US', 'en-GB', 'en-AU', 'en-CA']

        # First pass: exact match in preferred locales
        for locale in preferred_locales:
            for voice in voices:
                if voice['locale'] == locale:
                    # Extract short name from full name (e.g., "en-US-AriaNeural" -> "Aria")
                    voice_short = voice['name'].split('-')[-1].replace('Neural', '').replace('Multilingual', '').lower()
                    if voice_short == name_lower:
                        return voice['name']

        # Second pass: exact match in any locale
        for voice in voices:
            voice_short = voice['name'].split('-')[-1].replace('Neural', '').replace('Multilingual', '').lower()
            if voice_short == name_lower:
                return voice['name']

        # Third pass: partial match in preferred locales
        for locale in preferred_locales:
            for voice in voices:
                if voice['locale'] == locale:
                    voice_short = voice['name'].split('-')[-1].replace('Neural', '').replace('Multilingual', '').lower()
                    if name_lower in voice_short or voice_short in name_lower:
                        return voice['name']

        # Fourth pass: partial match in any locale
        for voice in voices:
            voice_short = voice['name'].split('-')[-1].replace('Neural', '').replace('Multilingual', '').lower()
            if name_lower in voice_short or voice_short in name_lower:
                return voice['name']

        return None
