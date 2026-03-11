from pathlib import Path
from unittest.mock import Mock

from src.cli.app import cli
from src.cli.commands import condense as condense_module
from src.cli.commands import takeaways as takeaways_module
from src.cli.commands import transcript as transcript_module


class _FakePipeline:
    def __init__(self, settings, result):
        self.settings = settings
        self.result = result
        self.calls = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def test_condense_happy_path_defaults(runner, monkeypatch, settings_factory, fake_condense_result):
    settings = settings_factory()
    pipeline = _FakePipeline(settings, fake_condense_result)

    monkeypatch.setattr(condense_module, "get_settings", lambda: settings)
    monkeypatch.setattr(condense_module, "CondenserPipeline", lambda s: pipeline)

    result = runner.invoke(cli, ["condense", "https://youtube.com/watch?v=ABCDEFGHIJK"])

    assert result.exit_code == 0
    assert "Condensation Complete!" in result.output
    assert len(pipeline.calls) == 1
    assert pipeline.calls[0]["aggressiveness"] == 5
    assert pipeline.calls[0]["quality"] == "1080p"
    assert pipeline.calls[0]["video_gen_mode"] == "slideshow"
    assert pipeline.calls[0]["resume"] is True


def test_condense_edge_voice_shortcut(runner, monkeypatch, settings_factory, fake_condense_result):
    settings = settings_factory()
    pipeline = _FakePipeline(settings, fake_condense_result)

    class FakeEdgeTTS:
        def resolve_voice_name(self, name):
            assert name == "ryan"
            return "en-GB-RyanNeural"

    monkeypatch.setattr(condense_module, "get_settings", lambda: settings)
    monkeypatch.setattr(condense_module, "CondenserPipeline", lambda s: pipeline)
    monkeypatch.setattr("src.modules.edge_tts.EdgeTTS", FakeEdgeTTS)

    result = runner.invoke(cli, ["condense", "https://youtube.com/watch?v=ABCDEFGHIJK", "--voice=edge/ryan"])

    assert result.exit_code == 0
    call = pipeline.calls[0]
    assert call["tts_provider"] == "edge"
    assert call["skip_voice_clone"] is True
    assert call["voice_id"] == "en-GB-RyanNeural"


def test_condense_invalid_voice_provider_exits(runner, monkeypatch, settings_factory):
    monkeypatch.setattr(condense_module, "get_settings", lambda: settings_factory())

    result = runner.invoke(cli, ["condense", "https://youtube.com/watch?v=ABCDEFGHIJK", "--voice=badprovider/ryan"])

    assert result.exit_code == 1
    assert "Invalid provider" in result.output


def test_condense_invalid_speech_rate_exits(runner, monkeypatch, settings_factory):
    monkeypatch.setattr(condense_module, "get_settings", lambda: settings_factory())

    result = runner.invoke(cli, ["condense", "https://youtube.com/watch?v=ABCDEFGHIJK", "--speech-rate=25%"])

    assert result.exit_code == 1
    assert "Invalid speech rate format" in result.output


def test_condense_speech_rate_ignored_for_elevenlabs(
    runner, monkeypatch, settings_factory, fake_condense_result
):
    settings = settings_factory()
    pipeline = _FakePipeline(settings, fake_condense_result)

    monkeypatch.setattr(condense_module, "get_settings", lambda: settings)
    monkeypatch.setattr(condense_module, "CondenserPipeline", lambda s: pipeline)
    monkeypatch.setattr(condense_module, "_resolve_voice", lambda voice, api_key: "voice-id")

    result = runner.invoke(
        cli,
        [
            "condense",
            "https://youtube.com/watch?v=ABCDEFGHIJK",
            "--tts-provider=elevenlabs",
            "--voice=George",
            "--speech-rate=+20%",
        ],
    )

    assert result.exit_code == 0
    assert "Warning: --speech-rate only works with Edge and Azure" in result.output
    assert pipeline.calls[0]["tts_rate"] == "+0%"


def test_condense_videos_txt_index_out_of_range(runner, monkeypatch, settings_factory):
    monkeypatch.setattr(condense_module, "get_settings", lambda: settings_factory())
    monkeypatch.setattr(condense_module, "_load_videos_txt", lambda: [("AAA", None), ("BBB", "Label")])

    result = runner.invoke(cli, ["condense", "99"])

    assert result.exit_code == 1
    assert "index 99 out of range" in result.output


def test_condense_avatar_without_did_key(runner, monkeypatch, settings_factory):
    settings = settings_factory(did_api_key="")
    monkeypatch.setattr(condense_module, "get_settings", lambda: settings)

    result = runner.invoke(
        cli,
        ["condense", "https://youtube.com/watch?v=ABCDEFGHIJK", "--video-gen-mode=avatar"],
    )

    assert result.exit_code == 1
    assert "DID_API_KEY not set" in result.output


def test_takeaways_text_default_flow(runner, monkeypatch, settings_factory, tmp_path):
    settings = settings_factory()
    video_folder = tmp_path / "temp" / "ABCDEFGHIJK"
    video_folder.mkdir(parents=True, exist_ok=True)

    downloader = Mock()
    downloader.download.return_value = {
        "video_folder": video_folder,
        "metadata": {"video_id": "ABCDEFGHIJK", "title": "A video"},
    }

    transcriber = Mock()
    transcriber.fetch_youtube_transcript.return_value = {"text": "transcript text"}

    condenser = Mock()
    condenser.extract_takeaways.return_value = "- One\n- Two"

    monkeypatch.setattr(takeaways_module, "get_settings", lambda: settings)
    monkeypatch.setattr(takeaways_module, "VideoDownloader", lambda *a, **k: downloader)
    monkeypatch.setattr(takeaways_module, "Transcriber", lambda *a, **k: transcriber)
    monkeypatch.setattr(takeaways_module, "ContentCondenser", lambda *a, **k: condenser)

    result = runner.invoke(cli, ["takeaways", "https://youtube.com/watch?v=ABCDEFGHIJK"])

    assert result.exit_code == 0
    assert "Takeaways extraction complete" in result.output
    expected = video_folder / "takeaways_ABCDEFGHIJK_topauto.md"
    assert expected.exists()


def test_takeaways_audio_edge_with_rate(runner, monkeypatch, settings_factory, tmp_path):
    settings = settings_factory()
    video_folder = tmp_path / "temp" / "ABCDEFGHIJK"
    video_folder.mkdir(parents=True, exist_ok=True)

    downloader = Mock()
    downloader.download.return_value = {
        "video_folder": video_folder,
        "metadata": {"video_id": "ABCDEFGHIJK", "title": "A video"},
    }

    transcriber = Mock()
    transcriber.fetch_youtube_transcript.return_value = {"text": "transcript text"}

    condenser = Mock()
    condenser.extract_takeaways.return_value = "- One\n- Two"

    edge = Mock()
    edge.resolve_voice_name.return_value = "en-GB-RyanNeural"

    monkeypatch.setattr(takeaways_module, "get_settings", lambda: settings)
    monkeypatch.setattr(takeaways_module, "VideoDownloader", lambda *a, **k: downloader)
    monkeypatch.setattr(takeaways_module, "Transcriber", lambda *a, **k: transcriber)
    monkeypatch.setattr(takeaways_module, "ContentCondenser", lambda *a, **k: condenser)
    monkeypatch.setattr(takeaways_module, "EdgeTTS", lambda *a, **k: edge)

    result = runner.invoke(
        cli,
        [
            "takeaways",
            "https://youtube.com/watch?v=ABCDEFGHIJK",
            "--format=audio",
            "--voice=ryan",
            "--speech-rate=+15%",
        ],
    )

    assert result.exit_code == 0
    edge.generate_speech.assert_called_once()
    assert edge.generate_speech.call_args.kwargs["rate"] == "+15%"


def test_takeaways_invalid_voice_provider_shortcut(runner, monkeypatch, settings_factory):
    monkeypatch.setattr(takeaways_module, "get_settings", lambda: settings_factory())

    result = runner.invoke(
        cli,
        ["takeaways", "https://youtube.com/watch?v=ABCDEFGHIJK", "--voice=foo/ryan", "--format=audio"],
    )

    assert result.exit_code == 1
    assert "Invalid provider" in result.output


def test_takeaways_fallback_to_whisper(runner, monkeypatch, settings_factory, tmp_path):
    settings = settings_factory()
    video_folder = tmp_path / "temp" / "ABCDEFGHIJK"
    video_folder.mkdir(parents=True, exist_ok=True)

    downloader = Mock()
    downloader.download.side_effect = [
        {"video_folder": video_folder, "metadata": {"video_id": "ABCDEFGHIJK", "title": "A video"}},
        {"video_path": video_folder / "video.mp4"},
    ]

    transcriber = Mock()
    transcriber.fetch_youtube_transcript.return_value = None
    transcriber.transcribe.return_value = {"text": "whisper text"}

    condenser = Mock()
    condenser.extract_takeaways.return_value = "- One"

    monkeypatch.setattr(takeaways_module, "get_settings", lambda: settings)
    monkeypatch.setattr(takeaways_module, "VideoDownloader", lambda *a, **k: downloader)
    monkeypatch.setattr(takeaways_module, "Transcriber", lambda *a, **k: transcriber)
    monkeypatch.setattr(takeaways_module, "ContentCondenser", lambda *a, **k: condenser)

    result = runner.invoke(cli, ["takeaways", "https://youtube.com/watch?v=ABCDEFGHIJK"])

    assert result.exit_code == 0
    assert "downloading video for Whisper" in result.output
    assert downloader.download.call_count == 2
    transcriber.transcribe.assert_called_once()


def test_transcript_youtube_success(runner, monkeypatch, settings_factory, tmp_path):
    settings = settings_factory(output_dir=tmp_path / "output")
    downloader = Mock()
    transcriber = Mock()
    transcriber.fetch_youtube_transcript.return_value = {"text": "yt transcript"}

    monkeypatch.setattr(transcript_module, "get_settings", lambda: settings)
    monkeypatch.setattr(transcript_module, "VideoDownloader", lambda *a, **k: downloader)
    monkeypatch.setattr(transcript_module, "Transcriber", lambda *a, **k: transcriber)

    result = runner.invoke(cli, ["transcript", "https://youtube.com/watch?v=ABCDEFGHIJK"])

    assert result.exit_code == 0
    output_file = settings.output_dir / "transcript_ABCDEFGHIJK.txt"
    assert output_file.exists()
    assert output_file.read_text(encoding="utf-8") == "yt transcript"


def test_transcript_no_transcribe_hard_fail(runner, monkeypatch, settings_factory):
    settings = settings_factory()
    downloader = Mock()
    downloader.fetch_transcript_via_yt_dlp.return_value = None
    transcriber = Mock()
    transcriber.fetch_youtube_transcript.return_value = None

    monkeypatch.setattr(transcript_module, "get_settings", lambda: settings)
    monkeypatch.setattr(transcript_module, "VideoDownloader", lambda *a, **k: downloader)
    monkeypatch.setattr(transcript_module, "Transcriber", lambda *a, **k: transcriber)

    result = runner.invoke(cli, ["transcript", "https://youtube.com/watch?v=ABCDEFGHIJK", "--no-transcribe"])

    assert result.exit_code == 1
    assert "YouTube transcript not available" in result.output


def test_transcript_resume_uses_cached_output(runner, monkeypatch, settings_factory, tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / "transcript_ABCDEFGHIJK.txt"
    out_file.write_text("cached", encoding="utf-8")

    settings = settings_factory(output_dir=output_dir)
    downloader = Mock()
    transcriber = Mock()

    monkeypatch.setattr(transcript_module, "get_settings", lambda: settings)
    monkeypatch.setattr(transcript_module, "VideoDownloader", lambda *a, **k: downloader)
    monkeypatch.setattr(transcript_module, "Transcriber", lambda *a, **k: transcriber)

    result = runner.invoke(cli, ["transcript", "https://youtube.com/watch?v=ABCDEFGHIJK", "--resume"])

    assert result.exit_code == 0
    assert "Loading cached transcript" in result.output
    transcriber.fetch_youtube_transcript.assert_not_called()
