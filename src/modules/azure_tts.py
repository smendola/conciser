"""Azure TTS module using Microsoft Azure Cognitive Services Speech API."""

import json
import logging
import time
from pathlib import Path
from typing import List, Optional
import azure.cognitiveservices.speech as speechsdk

logger = logging.getLogger(__name__)

_voices_cache: List[dict] = []
_voices_cache_time: float = 0.0
_VOICES_CACHE_TTL = 3600 * 24  # 24 hours — voices list rarely changes
_VOICES_DISK_CACHE = Path(__file__).parent.parent.parent / ".cache" / "azure_voices.json"


def _load_disk_cache() -> tuple[List[dict], float]:
    try:
        if _VOICES_DISK_CACHE.exists():
            data = json.loads(_VOICES_DISK_CACHE.read_text())
            return data.get("voices", []), data.get("time", 0.0)
    except Exception as e:
        logger.debug(f"Could not load disk voice cache: {e}")
    return [], 0.0


def _save_disk_cache(voices: List[dict], ts: float) -> None:
    try:
        _VOICES_DISK_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _VOICES_DISK_CACHE.write_text(json.dumps({"voices": voices, "time": ts}))
    except Exception as e:
        logger.debug(f"Could not save disk voice cache: {e}")


class AzureTTS:
    """Text-to-speech using Azure Cognitive Services Speech API (supports SSML)."""

    def __init__(self, api_key: str, region: str):
        """
        Initialize Azure TTS.

        Args:
            api_key: Azure Speech Services API key
            region: Azure region (e.g., 'eastus', 'westus', 'westeurope')
        """
        self.api_key = api_key
        self.region = region
        self.speech_config = speechsdk.SpeechConfig(
            subscription=api_key,
            region=region
        )

    def generate_speech(
        self,
        text: str,
        output_path: Path,
        voice: str = "en-US-AriaNeural",
        rate: str = "+0%",
        is_ssml: bool = False,
        progress_callback=None,
    ) -> Path:
        """
        Generate speech from text or SSML using Azure TTS.

        Args:
            text: Text or SSML to convert to speech
            output_path: Path to save generated audio
            voice: Voice name (e.g., en-US-AriaNeural, en-GB-RyanNeural)
            rate: Speech speed adjustment (e.g., "+20%", "-10%", "+0%")
            is_ssml: Whether input is SSML format
            progress_callback: Optional callable(pct: int) for progress updates

        Returns:
            Path to generated audio file
        """
        try:
            logger.info(
                f"Generating speech with Azure TTS ({len(text)} characters, "
                f"voice={voice}, rate={rate}, ssml={is_ssml})"
            )

            # Configure output to file
            audio_config = speechsdk.audio.AudioOutputConfig(filename=str(output_path))

            # Set voice
            self.speech_config.speech_synthesis_voice_name = voice

            # Create synthesizer
            synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=self.speech_config,
                audio_config=audio_config
            )

            # Wire up word-boundary progress if requested
            if progress_callback:
                total_words = max(1, len(text.split()))
                word_count = [0]

                def _on_boundary(evt):
                    if evt.boundary_type == speechsdk.SpeechSynthesisBoundaryType.Word:
                        word_count[0] += 1
                        progress_callback(min(99, int(word_count[0] / total_words * 100)))

                synthesizer.synthesis_word_boundary.connect(_on_boundary)

            # Synthesize based on input type
            if is_ssml:
                # Ensure the SSML does not pin a voice internally.
                # The selected voice should be controlled via the `voice` parameter.
                ssml_text = self._ensure_voice_in_ssml(text, voice, rate)
                logger.debug(f"Using SSML synthesis with voice={voice}")
                result = synthesizer.speak_ssml_async(ssml_text).get()
            else:
                # Plain text with rate adjustment
                if rate and rate != "+0%":
                    # Convert plain text to SSML to apply rate
                    ssml_text = self._text_to_ssml(text, voice, rate)
                    result = synthesizer.speak_ssml_async(ssml_text).get()
                else:
                    result = synthesizer.speak_text_async(text).get()

            # Check result
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                logger.info(f"Speech generated and saved to: {output_path}")
                if progress_callback:
                    progress_callback(100)
                return output_path
            elif result.reason == speechsdk.ResultReason.Canceled:
                cancellation = result.cancellation_details
                error_msg = f"Azure TTS synthesis canceled: {cancellation.reason}"
                if cancellation.reason == speechsdk.CancellationReason.Error:
                    error_msg += f"\nError details: {cancellation.error_details}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            else:
                raise RuntimeError(f"Unexpected result reason: {result.reason}")

        except Exception as e:
            logger.error(f"Azure TTS generation failed: {e}")
            raise RuntimeError(f"Failed to generate speech with Azure TTS: {e}")

    def _text_to_ssml(self, text: str, voice: str, rate: str = "+0%") -> str:
        """
        Convert plain text to SSML with voice and rate settings.

        Args:
            text: Plain text
            voice: Voice name
            rate: Speech rate (e.g., "+20%", "-10%")

        Returns:
            SSML string
        """
        # Convert rate format from "+20%" to "20%" or "-10%" to "-10%"
        rate_value = rate if rate.startswith('-') else rate.lstrip('+')

        ssml = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">
    <prosody rate="{rate_value}">
        {text}
    </prosody>
</speak>"""
        return ssml

    def _ensure_voice_in_ssml(self, ssml: str, voice: str, rate: str = "+0%") -> str:
        """
        Ensure SSML has correct voice and rate settings.

        Args:
            ssml: SSML string
            voice: Voice name to use
            rate: Speech rate adjustment

        Returns:
            Modified SSML with voice settings
        """
        # Azure's SSML endpoint requires a <voice> tag. The pipeline SSML rewrite intentionally
        # omits it, so we add it here while keeping the pipeline output cacheable and voice-agnostic.
        import re

        # Strip any embedded voice tags to ensure the selected `voice` param remains authoritative.
        ssml = self._strip_voice_tags_from_ssml(ssml)

        speak_match = re.search(r'(<speak[^>]*>)(.*)(</speak>)', ssml, re.DOTALL | re.IGNORECASE)
        if speak_match:
            speak_open = speak_match.group(1)
            inner = speak_match.group(2).strip()
            speak_close = speak_match.group(3)
            rate_value = rate if rate.startswith('-') else rate.lstrip('+')

            if rate and rate != "+0%":
                wrapped = f"""{speak_open}
    <voice name="{voice}">
        <prosody rate="{rate_value}">
            {inner}
        </prosody>
    </voice>
{speak_close}"""
            else:
                wrapped = f"""{speak_open}
    <voice name="{voice}">
        {inner}
    </voice>
{speak_close}"""
            return wrapped

        # If no <speak> wrapper, treat input as plain text.
        return self._text_to_ssml(ssml, voice, rate)

    def _strip_voice_tags_from_ssml(self, ssml: str) -> str:
        """Remove any <voice ...> wrappers from SSML, preserving inner content."""
        if not isinstance(ssml, str) or not ssml.strip():
            return ssml
        import re

        # Remove <voice ...> opening/closing tags but keep content.
        # This is intentionally simple; the SSML emitted by our pipeline is well-formed.
        stripped = re.sub(r"</?voice\b[^>]*>", "", ssml, flags=re.IGNORECASE)
        return stripped

    def list_voices(self, locale_filter: Optional[str] = None) -> List[dict]:
        """
        List all available Azure TTS voices.

        Args:
            locale_filter: Optional locale filter (e.g., "en-US", "en-GB")

        Returns:
            List of voice dictionaries with name, gender, locale
        """
        global _voices_cache, _voices_cache_time
        # Populate in-memory cache from disk on first call
        if not _voices_cache:
            _voices_cache, _voices_cache_time = _load_disk_cache()
        if _voices_cache and (time.time() - _voices_cache_time) < _VOICES_CACHE_TTL:
            logger.debug(f"list_voices: returning {len(_voices_cache)} cached voices (age={int(time.time()-_voices_cache_time)}s)")
            return [v for v in _voices_cache if not locale_filter or v['locale'].startswith(locale_filter)]
        try:
            logger.debug(f"list_voices called: api_key={self.api_key[:8]}...{self.api_key[-4:]}, region={self.region}, locale_filter={locale_filter!r}")
            import socket
            try:
                endpoint = f"{self.region}.tts.speech.microsoft.com"
                addr = socket.getaddrinfo(endpoint, 443)
                logger.debug(f"DNS OK: {endpoint} -> {addr[0][4][0]}")
            except Exception as dns_err:
                logger.error(f"DNS resolution failed for {endpoint}: {dns_err}")

            for attempt in range(3):
                logger.debug(f"get_voices attempt {attempt + 1}: creating SpeechSynthesizer with region={self.region}")
                synthesizer = speechsdk.SpeechSynthesizer(speech_config=self.speech_config, audio_config=None)
                future = synthesizer.get_voices_async()
                logger.debug(f"get_voices_async() called, awaiting result...")
                result = future.get()
                logger.debug(f"get_voices result: reason={result.reason}, error_details={getattr(result, 'error_details', 'N/A')!r}")
                if result.reason == speechsdk.ResultReason.VoicesListRetrieved:
                    break
                logger.warning(f"get_voices attempt {attempt + 1} failed ({result.reason}), error_details={getattr(result, 'error_details', 'N/A')!r}, retrying...")
                time.sleep(1.5 ** attempt)  # 1s, 1.5s

            if result.reason == speechsdk.ResultReason.VoicesListRetrieved:
                all_voices = []
                for voice in result.voices:
                    # Exclude HD voices because they are much slower to generate
                    if 'DragonHD' in voice.short_name:
                        continue
                    all_voices.append({
                        'name': voice.short_name,
                        'gender': voice.gender.name if hasattr(voice.gender, 'name') else str(voice.gender),
                        'locale': voice.locale,
                        'display_name': voice.local_name
                    })
                _voices_cache = all_voices
                _voices_cache_time = time.time()
                _save_disk_cache(_voices_cache, _voices_cache_time)
            else:
                logger.error(f"Failed to retrieve voices after retries: {result.reason}")
            return [v for v in _voices_cache if not locale_filter or v['locale'].startswith(locale_filter)]

        except Exception as e:
            logger.error(f"Failed to list Azure TTS voices: {e}")
            return [v for v in _voices_cache if not locale_filter or v['locale'].startswith(locale_filter)]

    def find_voice(self, locale: str = "en-US", gender: str = None) -> Optional[str]:
        """
        Find a suitable voice by locale and gender.

        Args:
            locale: Locale like "en-US", "en-GB", "es-ES"
            gender: "Male" or "Female" (optional)

        Returns:
            Voice name if found, None otherwise
        """
        voices = self.list_voices(locale_filter=locale)

        for voice in voices:
            if gender is None or voice['gender'].lower() == gender.lower():
                return voice['name']

        return None

    def resolve_voice_name(self, name: str) -> Optional[str]:
        """
        Resolve a short voice name to full voice ID.

        Args:
            name: Short name like "Aria", "Ryan", or full name like "en-US-AriaNeural"

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
