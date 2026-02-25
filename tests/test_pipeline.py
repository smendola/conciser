"""Tests for the condensation pipeline."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from src.config import Settings
from src.pipeline import CondenserPipeline


@pytest.fixture
def mock_settings(tmp_path):
    """Create mock settings with temporary directories."""
    settings = Settings(
        openai_api_key="test-key",
        anthropic_api_key="test-key",
        elevenlabs_api_key="test-key",
        did_api_key="test-key",
        temp_dir=tmp_path / "temp",
        output_dir=tmp_path / "output"
    )
    settings.temp_dir.mkdir(exist_ok=True)
    settings.output_dir.mkdir(exist_ok=True)
    return settings


def test_pipeline_initialization(mock_settings):
    """Test that pipeline initializes correctly."""
    pipeline = CondenserPipeline(mock_settings)

    assert pipeline.downloader is not None
    assert pipeline.transcriber is not None
    assert pipeline.condenser is not None
    assert pipeline.voice_cloner is not None
    assert pipeline.video_generator is not None
    assert pipeline.compositor is not None


def test_settings_validation():
    """Test settings validation."""
    with pytest.raises(Exception):
        # Missing API keys should be handled gracefully
        Settings(
            openai_api_key="",
            anthropic_api_key="",
            elevenlabs_api_key="",
            did_api_key=""
        )


# Additional tests would go here for each module
# These are placeholders for the full test suite

class TestDownloader:
    """Tests for VideoDownloader."""

    def test_format_string_selection(self):
        """Test that correct format strings are selected."""
        from src.modules.downloader import VideoDownloader

        downloader = VideoDownloader(Path("temp"))

        assert "720" in downloader._get_format_string("720p")
        assert "1080" in downloader._get_format_string("1080p")
        assert "2160" in downloader._get_format_string("4k")


class TestTranscriber:
    """Tests for Transcriber."""

    def test_transcript_save_load(self, tmp_path):
        """Test saving and loading transcripts."""
        from src.modules.transcriber import Transcriber

        transcriber = Transcriber("test-key")

        test_transcript = {
            "text": "Hello world",
            "language": "en",
            "duration": 10.0,
            "segments": []
        }

        output_path = tmp_path / "test_transcript.json"
        transcriber.save_transcript(test_transcript, output_path)

        loaded = transcriber.load_transcript(output_path)
        assert loaded["text"] == "Hello world"


class TestCondenser:
    """Tests for ContentCondenser."""

    def test_script_validation(self):
        """Test condensed script validation."""
        from src.modules.condenser import ContentCondenser

        condenser = ContentCondenser("test-key")

        valid_script = {
            "condensed_script": "This is a test.",
            "original_duration_minutes": 10.0,
            "estimated_condensed_duration_minutes": 5.0,
            "reduction_percentage": 50.0
        }

        assert condenser.validate_condensed_script(valid_script)

        invalid_script = {
            "condensed_script": "",
            "original_duration_minutes": 10.0
        }

        with pytest.raises(ValueError):
            condenser.validate_condensed_script(invalid_script)


class TestPromptTemplates:
    """Tests for prompt templates."""

    def test_strategy_descriptions(self):
        """Test that all aggressiveness levels have strategies."""
        from src.utils.prompt_templates import get_strategy_description

        for level in range(1, 11):
            strategy = get_strategy_description(level)
            assert len(strategy) > 0
            assert "retention" in strategy.lower()

    def test_prompt_generation(self):
        """Test prompt generation."""
        from src.utils.prompt_templates import get_condense_prompt

        system_prompt, user_prompt = get_condense_prompt(
            transcript="Hello world",
            duration_minutes=10.0,
            aggressiveness=5
        )

        assert "Hello world" in user_prompt
        assert "10.0" in system_prompt
        assert "aggressiveness" in system_prompt.lower()
        assert isinstance(system_prompt, str)
        assert isinstance(user_prompt, str)


# Run tests with: pytest tests/
