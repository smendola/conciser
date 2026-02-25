"""Configuration management for Conciser."""

from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False
    )

    # API Keys
    openai_api_key: str = Field(default="", description="OpenAI API key for Whisper")
    anthropic_api_key: str = Field(default="", description="Anthropic API key for Claude")
    elevenlabs_api_key: str = Field(default="", description="ElevenLabs API key for voice cloning")
    did_api_key: str = Field(default="", description="D-ID API key for video generation")
    heygen_api_key: str = Field(default="", description="HeyGen API key (alternative to D-ID)")

    # Default settings
    default_aggressiveness: int = Field(default=5, ge=1, le=10)
    default_output_quality: str = Field(default="1080p")
    temp_dir: Path = Field(default=Path("./temp"))
    output_dir: Path = Field(default=Path("./output"))

    # Service preferences
    transcription_service: str = Field(default="openai", description="openai or local")
    condenser_service: str = Field(default="openai", description="openai or claude")
    voice_service: str = Field(default="elevenlabs", description="elevenlabs or coqui")
    video_service: str = Field(default="did", description="did, heygen, or wav2lip")

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
