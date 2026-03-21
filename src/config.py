"""Configuration management for Conciser."""

from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .utils.project_root import get_project_root, resolve_env_file

# Project root directory (where src/ and server/ are located)
PROJECT_ROOT = get_project_root()

DEFAULT_QUALITY = "720p"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(resolve_env_file()),
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'
    )

    # API Keys
    openai_api_key: str = Field(default="", description="OpenAI API key for condensation (and Whisper fallback if not using Groq)")
    anthropic_api_key: str = Field(default="", description="Anthropic API key for Claude")
    elevenlabs_api_key: str = Field(default="", description="ElevenLabs API key for voice cloning")
    did_api_key: str = Field(default="", description="D-ID API key for video generation")
    heygen_api_key: str = Field(default="", description="HeyGen API key (alternative to D-ID)")
    groq_api_key: str = Field(default="", description="Groq API key for free Whisper transcription (whisper-large-v3)")
    azure_speech_key: str = Field(default="", description="Azure Speech Services API key for TTS with SSML support")
    azure_speech_region: str = Field(default="", description="Azure Speech Services region (e.g., eastus, westus, westeurope)")
    youtube_cookie_file: str = Field(default="", description="Path to Netscape-format YouTube cookies file for yt-dlp authentication")
    youtube_proxy_url: str = Field(default="", description="Optional proxy URL for YouTube access (e.g., http://user:pass@host:port)")

    # Default settings
    default_aggressiveness: int = Field(default=5, ge=1, le=10)
    default_output_quality: str = Field(default=DEFAULT_QUALITY)
    
    # Paths: keep defaults relative in config, but resolve them relative to PROJECT_ROOT
    # (never relative to the current working directory)
    temp_dir: Path = Field(default=Path("./temp"))
    data_dir: Path = Field(default=Path("./data"))
    output_dir: Path = Field(default=Path("./output"))

    # Service preferences
    transcription_method: str = Field(default="chained", description="youtube (YouTube API only), whisper (Whisper only), or chained (try YouTube, fallback to Whisper)")
    transcription_service: str = Field(default="groq", description="groq (free Whisper via Groq) or openai (paid Whisper via OpenAI)")
    condenser_service: str = Field(default="openai", description="openai or anthropic")
    tts_provider: str = Field(default="azure", description="azure (paid, SSML), edge (free), or elevenlabs (paid)")
    video_service: str = Field(default="did", description="did, heygen, or wav2lip")

    # LLM provider and model selection
    condensation_provider: str = Field(default="openai", description="Provider for condensation: openai or anthropic")
    takeaways_extraction_provider: str = Field(default="openai", description="Provider for takeaways extraction: openai or anthropic")

    # Model configuration (model IDs for each provider and task)
    condensation_model_openai: str = Field(default="gpt-5.2", description="OpenAI model for condensation")
    condensation_model_anthropic: str = Field(default="claude-sonnet-4.6", description="Anthropic model for condensation")
    takeaways_model_openai: str = Field(default="gpt-5-nano", description="OpenAI model for takeaways extraction")
    takeaways_model_anthropic: str = Field(default="claude-haiku-4-5-20251001", description="Anthropic model for takeaways extraction")

    # Sentry
    sentry_dsn: str = Field(default="", description="Sentry DSN for error reporting (optional)")

    # Server behavior
    cors: bool = Field(default=False, description="If true, restrict CORS to API routes only; if false, fully unrestricted")

    # Pipeline behavior
    resume: bool = Field(default=True, description="Resume from existing intermediate files (use cached results)")

    # TTS behavior
    text_to_ssml_processing: bool = Field(
        default=True,
        description="If true, perform Azure SSML rewrite processing; if false, skip SSML processing and keep plain text",
    )

    # Processing options
    target_reduction_percentage: Optional[int] = Field(default=None, ge=10, le=90)
    preserve_intro_outro: bool = Field(default=True)
    max_workers: int = Field(default=2, description="Max concurrent API requests")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        root = PROJECT_ROOT

        def _resolve_root_relative(p: Path) -> Path:
            if p.is_absolute():
                return p
            return (root / p).resolve()

        self.temp_dir = _resolve_root_relative(self.temp_dir)
        self.data_dir = _resolve_root_relative(self.data_dir)
        self.output_dir = _resolve_root_relative(self.output_dir)

        if self.youtube_cookie_file:
            self.youtube_cookie_file = str(_resolve_root_relative(Path(self.youtube_cookie_file)))
        # Create directories if they don't exist
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)


def settings_sanity(settings: Settings) -> None:
    errors: list[str] = []

    tts_provider = (settings.tts_provider or '').strip().lower()
    if tts_provider == 'azure':
        if not settings.azure_speech_key or not settings.azure_speech_region:
            errors.append('TTS_PROVIDER=azure requires AZURE_SPEECH_KEY and AZURE_SPEECH_REGION')
    elif tts_provider == 'elevenlabs':
        if not settings.elevenlabs_api_key:
            errors.append('TTS_PROVIDER=elevenlabs requires ELEVENLABS_API_KEY')

    transcription_service = (settings.transcription_service or '').strip().lower()
    if transcription_service == 'groq' and not settings.groq_api_key:
        errors.append('TRANSCRIPTION_SERVICE=groq requires GROQ_API_KEY')
    if transcription_service == 'openai' and not settings.openai_api_key:
        errors.append('TRANSCRIPTION_SERVICE=openai requires OPENAI_API_KEY')

    condensation_provider = (settings.condensation_provider or '').strip().lower()
    if condensation_provider == 'openai' and not settings.openai_api_key:
        errors.append('CONDENSATION_PROVIDER=openai requires OPENAI_API_KEY')
    if condensation_provider == 'anthropic' and not settings.anthropic_api_key:
        errors.append('CONDENSATION_PROVIDER=anthropic requires ANTHROPIC_API_KEY')

    takeaways_provider = (settings.takeaways_extraction_provider or '').strip().lower()
    if takeaways_provider == 'openai' and not settings.openai_api_key:
        errors.append('TAKEAWAYS_EXTRACTION_PROVIDER=openai requires OPENAI_API_KEY')
    if takeaways_provider == 'anthropic' and not settings.anthropic_api_key:
        errors.append('TAKEAWAYS_EXTRACTION_PROVIDER=anthropic requires ANTHROPIC_API_KEY')

    if errors:
        raise ValueError('Invalid configuration:\n' + '\n'.join(f'- {e}' for e in errors))


def get_settings() -> Settings:
    """Get application settings singleton."""
    settings = Settings()
    settings_sanity(settings)
    return settings
