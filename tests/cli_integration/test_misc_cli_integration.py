import json
from pathlib import Path
from unittest.mock import Mock

from src.cli.app import cli
from src.cli.commands import check as check_module
from src.cli.commands import info as info_module
from src.cli.commands import init as init_module
from src.cli.commands import start as start_module
from src.cli.commands import show_script as show_script_module
from src.cli.commands import tts_samples as tts_samples_module
from src.cli.commands import voices as voices_module


def test_voices_edge_lang_filter(runner, monkeypatch, settings_factory):
    settings = settings_factory()

    class FakeEdgeTTS:
        def list_voices(self):
            return [
                {"locale": "en-US", "gender": "Female", "name": "en-US-AriaNeural"},
                {"locale": "fr-FR", "gender": "Male", "name": "fr-FR-HenriNeural"},
            ]

    monkeypatch.setattr(voices_module, "get_settings", lambda: settings)
    monkeypatch.setattr("src.modules.edge_tts.EdgeTTS", FakeEdgeTTS)

    result = runner.invoke(cli, ["voices", "--provider=edge", "--lang=en-US"])

    assert result.exit_code == 0
    assert "en-US" in result.output
    assert "(fr-FR-HenriNeural)" not in result.output


def test_voices_azure_missing_credentials(runner, monkeypatch, settings_factory):
    settings = settings_factory(azure_speech_key="", azure_speech_region="")
    monkeypatch.setattr(voices_module, "get_settings", lambda: settings)

    result = runner.invoke(cli, ["voices", "--provider=azure"])

    assert result.exit_code == 1
    assert "AZURE_SPEECH_KEY and AZURE_SPEECH_REGION not set" in result.output


def test_check_all_required_valid(runner, monkeypatch, settings_factory):
    settings = settings_factory(
        tts_provider="edge",
        transcription_service="groq",
    )

    monkeypatch.setattr(check_module, "get_settings", lambda: settings)
    monkeypatch.setattr(check_module, "_validate_openai_key", lambda *_: (True, None))
    monkeypatch.setattr(check_module, "_validate_groq_key", lambda *_: (True, None))
    monkeypatch.setattr(check_module, "_validate_anthropic_key", lambda *_: (True, None))
    monkeypatch.setattr(check_module, "_validate_elevenlabs_key", lambda *_: (True, None))
    monkeypatch.setattr(check_module, "_validate_did_key", lambda *_: (True, None))
    monkeypatch.setattr(check_module, "_validate_azure_speech", lambda *_: (True, None))
    monkeypatch.setattr("subprocess.run", lambda *a, **k: Mock(returncode=0))

    result = runner.invoke(cli, ["check"])

    assert result.exit_code == 0
    assert "All required API keys are valid and working" in result.output


def test_check_verbose_shows_error(runner, monkeypatch, settings_factory):
    settings = settings_factory(tts_provider="edge")
    monkeypatch.setattr(check_module, "get_settings", lambda: settings)
    monkeypatch.setattr(check_module, "_validate_openai_key", lambda *_: (False, "auth failed detail"))
    monkeypatch.setattr(check_module, "_validate_groq_key", lambda *_: (True, None))
    monkeypatch.setattr(check_module, "_validate_anthropic_key", lambda *_: (True, None))
    monkeypatch.setattr(check_module, "_validate_elevenlabs_key", lambda *_: (True, None))
    monkeypatch.setattr(check_module, "_validate_did_key", lambda *_: (True, None))
    monkeypatch.setattr(check_module, "_validate_azure_speech", lambda *_: (True, None))
    monkeypatch.setattr("subprocess.run", lambda *a, **k: Mock(returncode=0))

    result = runner.invoke(cli, ["check", "--verbose"])

    assert result.exit_code == 0
    assert "Error: auth failed detail" in result.output


def test_info_success(runner, monkeypatch, settings_factory):
    settings = settings_factory()

    class FakeDownloader:
        def __init__(self, *a, **k):
            pass

        def get_video_info(self, url):
            return {
                "title": "Video",
                "duration": 600,
                "uploader": "Uploader",
                "view_count": 1234,
            }

    monkeypatch.setattr(info_module, "get_settings", lambda: settings)
    monkeypatch.setattr("src.modules.downloader.VideoDownloader", FakeDownloader)

    result = runner.invoke(cli, ["info", "https://youtube.com/watch?v=ABCDEFGHIJK"])

    assert result.exit_code == 0
    assert "Estimated Cost by Mode" in result.output


def test_show_script_loads_and_formats(runner, monkeypatch, settings_factory, tmp_path):
    temp_dir = tmp_path / "temp"
    video_folder = temp_dir / "ABCDEFGHIJK_data"
    video_folder.mkdir(parents=True, exist_ok=True)
    script_file = video_folder / "condensed_script_a5.json"
    script_file.write_text(
        json.dumps(
            {
                "condensed_script": "line one line two",
                "original_duration_minutes": 10.0,
                "estimated_condensed_duration_minutes": 4.0,
                "reduction_percentage": 60.0,
                "key_points_preserved": ["Point"],
            }
        ),
        encoding="utf-8",
    )

    settings = settings_factory(temp_dir=temp_dir, anthropic_api_key="anthropic-key")
    monkeypatch.setattr(show_script_module, "get_settings", lambda: settings)
    monkeypatch.setattr(show_script_module, "_format_script_into_paragraphs", lambda text, key: "line one\n\nline two")

    result = runner.invoke(cli, ["show-script", "ABCDEFGHIJK", "--format"])

    assert result.exit_code == 0
    assert "Script formatted and saved" in result.output
    saved = json.loads(script_file.read_text(encoding="utf-8"))
    assert "\n\n" in saved["condensed_script"]


def test_show_script_missing_script_file(runner, monkeypatch, settings_factory, tmp_path):
    temp_dir = tmp_path / "temp"
    (temp_dir / "ABCDEFGHIJK_data").mkdir(parents=True, exist_ok=True)

    settings = settings_factory(temp_dir=temp_dir)
    monkeypatch.setattr(show_script_module, "get_settings", lambda: settings)

    result = runner.invoke(cli, ["show-script", "ABCDEFGHIJK", "-a", "9"])

    assert result.exit_code == 1
    assert "Condensed script not found" in result.output


def test_tts_single_file_success(runner, monkeypatch, tmp_path):
    input_file = tmp_path / "sample.txt"
    input_file.write_text("meta\n" + ("=" * 80) + "\nhello script\n" + ("=" * 80) + "\nfooter", encoding="utf-8")

    edge = Mock()
    edge.resolve_voice_name.return_value = "en-GB-RyanNeural"
    monkeypatch.setattr("src.modules.edge_tts.EdgeTTS", lambda: edge)

    result = runner.invoke(cli, ["tts", "--voice=ryan", str(input_file)])

    assert result.exit_code == 0
    edge.generate_speech.assert_called_once()


def test_tts_unknown_voice_exits(runner, monkeypatch, tmp_path):
    input_file = tmp_path / "sample.txt"
    input_file.write_text("meta\n" + ("=" * 80) + "\nhello script\n" + ("=" * 80) + "\nfooter", encoding="utf-8")

    edge = Mock()
    edge.resolve_voice_name.return_value = None
    monkeypatch.setattr("src.modules.edge_tts.EdgeTTS", lambda: edge)

    result = runner.invoke(cli, ["tts", "--voice=unknownvoice", str(input_file)])

    assert result.exit_code == 1
    assert "Voice 'unknownvoice' not found" in result.output


def test_tts_samples_edge_lang_prefix(runner, monkeypatch, tmp_path):
    class FakeEdgeTTS:
        def list_voices(self):
            return [
                {"locale": "en-US", "name": "en-US-AriaNeural", "gender": "Female"},
                {"locale": "fr-FR", "name": "fr-FR-HenriNeural", "gender": "Male"},
            ]

        def generate_speech(self, **kwargs):
            output_path = Path(kwargs["output_path"])
            output_path.write_text("audio", encoding="utf-8")

    monkeypatch.setattr("src.modules.edge_tts.EdgeTTS", FakeEdgeTTS)

    result = runner.invoke(
        cli,
        ["voice-samples", "--provider=edge", "--lang=en", "--output-dir", str(tmp_path / "samples")],
    )

    assert result.exit_code == 0
    assert "Found 1 voices for language: en" in result.output


def test_tts_samples_azure_missing_credentials(runner, monkeypatch, settings_factory):
    settings = settings_factory(azure_speech_key="", azure_speech_region="")
    monkeypatch.setattr(tts_samples_module, "get_settings", lambda: settings)

    result = runner.invoke(cli, ["voice-samples", "--provider=azure"])

    assert result.exit_code == 0
    assert "AZURE_SPEECH_KEY and AZURE_SPEECH_REGION not set" in result.output


def test_voice_samples_resume_skips_existing(runner, monkeypatch, tmp_path):
    class FakeEdgeTTS:
        def list_voices(self):
            return [
                {"locale": "en-US", "name": "en-US-AnaNeural", "gender": "Female"},
            ]

        def generate_speech(self, **kwargs):
            raise AssertionError("generate_speech should not be called when --resume is set and output exists")

    monkeypatch.setattr("src.modules.edge_tts.EdgeTTS", FakeEdgeTTS)

    out_dir = tmp_path / "samples"
    existing_file = out_dir / "edge" / "en" / "US" / "AnaNeural.mp3"
    existing_file.parent.mkdir(parents=True, exist_ok=True)
    existing_file.write_text("audio", encoding="utf-8")

    result = runner.invoke(
        cli,
        ["voice-samples", "--provider=edge", "--lang=en", "--output-dir", str(out_dir), "--resume"],
    )

    assert result.exit_code == 0
    assert "skipped" in result.output


def test_init_success(runner, monkeypatch, settings_factory):
    settings = settings_factory(openai_api_key="openai-key")

    class FakeCondenser:
        def __init__(self, **kwargs):
            pass

        def init_chains(self):
            return ["a", "b"]

    monkeypatch.setattr(init_module, "get_settings", lambda: settings)
    monkeypatch.setattr("src.modules.condenser.ContentCondenser", FakeCondenser)

    result = runner.invoke(cli, ["init"])

    assert result.exit_code == 0
    assert "Initialized 2 chains" in result.output


def test_setup_cancel_existing_env(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=str(tmp_path)):
        import os
        from pathlib import Path

        os.environ["NBJ_PROJECT_ROOT"] = str(Path(__file__).resolve().parents[2])
        Path(".env").write_text("EXISTING=1\n", encoding="utf-8")

        result = runner.invoke(cli, ["setup"], input="n\n")

        assert result.exit_code == 0
        assert "Setup cancelled" in result.output
        assert Path(".env").read_text(encoding="utf-8") == "EXISTING=1\n"


def test_setup_writes_env(runner, tmp_path):
    user_input = "openai\nanthropic\neleven\n\n"

    with runner.isolated_filesystem(temp_dir=str(tmp_path)):
        import os
        from pathlib import Path

        os.environ["NBJ_PROJECT_ROOT"] = str(Path(__file__).resolve().parents[2])
        result = runner.invoke(cli, ["setup"], input=user_input)

        assert result.exit_code == 0
        env_text = Path(".env").read_text(encoding="utf-8")
        assert "OPENAI_API_KEY=openai" in env_text
        assert "ANTHROPIC_API_KEY=anthropic" in env_text
        assert "ELEVENLABS_API_KEY=eleven" in env_text


def test_start_restart_stops_before_start(runner, monkeypatch):
    stop_mock = Mock()
    run_mock = Mock()
    monkeypatch.setattr(start_module, "stop_server", stop_mock)
    monkeypatch.setattr(start_module.subprocess, "run", run_mock)

    import os
    os.environ.pop("NBJ_PROJECT_ROOT", None)

    # Ensure pidfile exists so -r triggers stop step
    pid_path = Path(start_module.__file__).resolve().parents[3] / "nbj.pid"
    pid_path.write_text("123", encoding="utf-8")

    result = runner.invoke(cli, ["start", "-r"])

    assert result.exit_code == 0
    stop_mock.assert_called_once_with(force=False)
    run_mock.assert_called_once()


def test_start_restart_does_not_fail_when_pidfile_missing(runner, monkeypatch, tmp_path):
    stop_mock = Mock()
    run_mock = Mock()
    monkeypatch.setattr(start_module, "stop_server", stop_mock)
    monkeypatch.setattr(start_module.subprocess, "run", run_mock)

    start_file = Path(start_module.__file__).resolve()
    repo_root = tmp_path / "repo"
    commands_dir = repo_root / "src" / "cli" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    server_dir = repo_root / "server"
    server_dir.mkdir(parents=True, exist_ok=True)
    (server_dir / "app.py").write_text("", encoding="utf-8")
    fake_start = commands_dir / start_file.name
    fake_start.write_text(start_file.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(start_module, "__file__", str(fake_start))

    import os
    os.environ["NBJ_PROJECT_ROOT"] = str(repo_root)

    result = runner.invoke(cli, ["start", "-r"])

    assert result.exit_code == 0
    stop_mock.assert_not_called()
    run_mock.assert_called_once()

    os.environ.pop("NBJ_PROJECT_ROOT", None)


def test_start_restart_propagates_stop_failure(runner, monkeypatch):
    stop_mock = Mock(side_effect=SystemExit(1))
    run_mock = Mock()
    monkeypatch.setattr(start_module, "stop_server", stop_mock)
    monkeypatch.setattr(start_module.subprocess, "run", run_mock)

    import os
    os.environ.pop("NBJ_PROJECT_ROOT", None)

    # Ensure pidfile exists so -r triggers stop step (and failure propagates)
    pid_path = Path(start_module.__file__).resolve().parents[3] / "nbj.pid"
    pid_path.write_text("123", encoding="utf-8")

    result = runner.invoke(cli, ["start", "-r"])

    assert result.exit_code == 1
    stop_mock.assert_called_once_with(force=False)
    run_mock.assert_not_called()
