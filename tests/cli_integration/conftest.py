from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def settings_factory(tmp_path):
    def _make(**overrides):
        temp_dir = overrides.pop("temp_dir", tmp_path / "temp")
        output_dir = overrides.pop("output_dir", tmp_path / "output")
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        base = {
            "openai_api_key": "openai-key",
            "anthropic_api_key": "anthropic-key",
            "elevenlabs_api_key": "eleven-key",
            "did_api_key": "did-key",
            "groq_api_key": "groq-key",
            "azure_speech_key": "azure-key",
            "azure_speech_region": "eastus",
            "youtube_cookie_file": "",
            "youtube_proxy_url": "",
            "temp_dir": temp_dir,
            "output_dir": output_dir,
            "resume": True,
            "transcription_service": "groq",
            "transcription_method": "chained",
            "takeaways_extraction_provider": "openai",
            "condensation_model_openai": "gpt-test",
            "condensation_model_anthropic": "claude-test",
            "takeaways_model_openai": "gpt-test",
            "takeaways_model_anthropic": "claude-test",
            "tts_provider": "edge",
        }
        base.update(overrides)
        return SimpleNamespace(**base)

    return _make


@pytest.fixture
def fake_condense_result(tmp_path):
    return {
        "output_video": str(tmp_path / "output" / "video.mp4"),
        "stats": {
            "original_duration_minutes": 10.0,
            "condensed_duration_minutes": 4.0,
            "reduction_percentage": 60.0,
        },
        "condensed_result": {
            "key_points_preserved": ["Point A", "Point B"],
        },
    }
