"""Configuration management for Conciser."""

from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root directory (where src/ and server/ are located)
PROJECT_ROOT = Path(__file__).parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file='.env',
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
    default_output_quality: str = Field(default="1080p")
    
    # Use absolute paths anchored to project root (not relative to cwd)
    # This ensures CLI and server use the same directories
    temp_dir: Path = Field(default=PROJECT_ROOT / "temp")
    output_dir: Path = Field(default=PROJECT_ROOT / "output")

    # Service preferences
    transcription_method: str = Field(default="chained", description="youtube (YouTube API only), whisper (Whisper only), or chained (try YouTube, fallback to Whisper)")
    transcription_service: str = Field(default="groq", description="groq (free Whisper via Groq) or openai (paid Whisper via OpenAI)")
    condenser_service: str = Field(default="openai", description="openai or anthropic")
    tts_provider: str = Field(default="edge", description="edge (free), elevenlabs (paid), or azure (paid with SSML)")
    video_service: str = Field(default="did", description="did, heygen, or wav2lip")

    # LLM provider and model selection
    condensation_provider: str = Field(default="openai", description="Provider for condensation: openai or anthropic")
    takeaways_extraction_provider: str = Field(default="openai", description="Provider for takeaways extraction: openai or anthropic")

    # Model configuration (model IDs for each provider and task)
    condensation_model_openai: str = Field(default="gpt-5.2", description="OpenAI model for condensation")
    condensation_model_anthropic: str = Field(default="claude-sonnet-4.6", description="Anthropic model for condensation")
    takeaways_model_openai: str = Field(default="gpt-5-nano", description="OpenAI model for takeaways extraction")
    takeaways_model_anthropic: str = Field(default="claude-haiku-4-5-20251001", description="Anthropic model for takeaways extraction")

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
        # Create directories if they don't exist
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Get application settings singleton."""
    return Settings()
