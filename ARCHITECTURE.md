# NBJ Condenser Architecture

This document provides a technical overview of NBJ Condenser's architecture and implementation.

## System Overview

NBJ Condenser is a YouTube video condensation system with three interfaces:
- **CLI** (`nbj condense …`) — direct command-line use
- **Flask Server** (`server/app.py`) — REST API backend, used by the Chrome extension and Android app
- **Chrome Extension** (`chrome-extension/`) — browser popup that submits videos to the server
- **Android App** (`android/`) — native app that accepts YouTube share intents and submits to the server

```
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│   Chrome Ext.    │  │   Android App    │  │  CLI (nbj cmd)   │
│  (popup.js)      │  │  (MainActivity)  │  │  (src/main.py)   │
└────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
         │ HTTP POST           │ HTTP POST           │ in-process
         └──────────┬──────────┘                     │
                    ▼                                │
         ┌──────────────────┐                        │
         │  Flask Server    │                        │
         │  server/app.py   │                        │
         └────────┬─────────┘                        │
                  └──────────────────┬───────────────┘
                                     ▼
                        ┌────────────────────────┐
                        │  CondenserPipeline     │
                        │   src/pipeline.py      │
                        └────────────────────────┘
```

## Pipeline Stages

### Stage 1: Video Download
**Module**: `src/modules/downloader.py`

- Downloads video from YouTube using yt-dlp
- Extracts metadata (title, video_id, duration, uploader, etc.)
- Saves video in MP4 format and thumbnail as WebP
- Resume support: skips if video already exists in `temp/`

**External Dependencies**: yt-dlp, ffmpeg

---

### Stage 2: Transcription
**Module**: `src/modules/transcriber.py`

Two-strategy approach — YouTube captions are tried first, Whisper is the fallback:

1. **YouTube Transcript API** (primary, free): fetches captions directly from YouTube via `youtube_transcript_api`. Succeeds for most public videos that have auto-generated or manual captions.
2. **OpenAI Whisper API** (fallback, paid): if YouTube captions are unavailable (disabled, private, or missing), ffmpeg extracts audio (WAV, 16kHz) and sends it to Whisper. Large files are auto-chunked at the 25MB API limit and timestamps are stitched back together.

Resume support: skips both strategies if `transcript.json` already exists in the video's temp folder.

**External Dependencies**: `youtube_transcript_api` (primary); OpenAI Whisper API + ffmpeg (fallback)

---

### Stage 3: Content Condensation
**Module**: `src/modules/condenser.py`

- Supports two LLM providers: **OpenAI** (default, `gpt-5.2`) or **Claude** (`claude-sonnet-4-20250514`)
- Configured via `CONDENSER_SERVICE=openai|claude` in `.env`
- Uses a three-level prompt structure:
  - **System prompt (L1)**: Core condensation instructions
  - **Strategy prompt (L2)**: Aggressiveness-level-specific rules (1–10 scale)
  - **User prompt (L3)**: Transcript + video metadata
- Returns structured JSON: `condensed_script`, `key_points_preserved`, `original_duration_estimate`, etc.
- Optional **Responses API pre-initialization** (`init_chains()` in `condenser.py`, stored in `condenser_chains.json` via `src/utils/chain_store.py`)
  - Caches L1+L2 prompts as OpenAI conversation history for faster repeat requests
- Optional **prepend_intro**: builds a numbered key take-aways list from `key_points_preserved` and prepends it to the TTS script

**External Dependencies**: OpenAI API or Anthropic API

---

### Stage 4: Text-to-Speech
**Module**: `src/modules/edge_tts.py` (default) or `src/modules/voice_cloner.py` (ElevenLabs)

**Edge TTS** (default, free):
- Uses Microsoft Edge TTS via the `edge-tts` Python package
- No API key required
- Configurable voice (e.g., `en-GB-RyanNeural`, `en-US-AriaNeural`)
- Configurable speech rate (e.g., `+10%`, `-25%`)
- Voice list browsable via `nbj voices --provider edge`

**ElevenLabs** (paid, optional):
- Voice cloning: extracts 2–5 min of clean speech, uploads to ElevenLabs, receives a voice ID
- Generates speech from condensed script using the cloned voice
- Handles long scripts via sentence-aware chunking (5000 chars max)

**External Dependencies**: `edge-tts` package (Edge TTS) or ElevenLabs API (optional)

---

### Stage 5: Video Generation
**Module**: `src/modules/video_generator.py`, `src/modules/compositor.py`

Three modes, selected via `--video-gen-mode`:

| Mode | Description | Output |
|------|-------------|--------|
| `slideshow` | Scene-detected keyframes assembled into MP4 | `.mp4` (default) |
| `audio_only` | Skip video entirely, output TTS audio as-is | `.mp3` (fastest) |
| `static` | Single extracted frame as video background | `.mp4` |
| `avatar` | D-ID talking-head video (expensive, rarely used) | `.mp4` |

**Slideshow details** (`video_utils.py`):
- Detects scene changes using PySceneDetect
- Extracts keyframe images at each scene boundary
- Compositor builds timed slideshow synced to TTS audio
- `--slideshow-frames N` limits number of frames used

**External Dependencies**: ffmpeg, PySceneDetect (slideshow); D-ID API (avatar mode only)

---

## Utility Modules

### `src/utils/audio_utils.py`
- `extract_audio()` — Extract audio from video (WAV)
- `get_audio_duration()` — Get audio length in seconds
- `extract_audio_segment()` — Extract a time range
- `normalize_audio()` — Volume normalization (loudnorm, -16 LUFS)
- `get_video_resolution()` — Get video dimensions

### `src/utils/video_utils.py`
- `combine_audio_video()` — Merge audio and video streams
- `extract_frame()` — Extract a single frame as image
- `detect_scene_changes()` — PySceneDetect-based scene detection
- `extract_scene_keyframes()` — Extract frames at scene boundaries
- `get_video_info()` — Get comprehensive metadata via ffprobe

### `src/utils/prompt_templates.py`
- `CONDENSE_SYSTEM_PROMPT` — Core condensation system prompt (L1)
- `STRATEGY_PROMPTS` — Dict of aggressiveness-level prompts (L2), 1–10
- `get_condense_prompt()` — Assembles L1+L2+L3 for a given level
- `get_strategy_description()` — Short human-readable level description
- Uses `textwrap.dedent()` to trim indented strings before sending to LLM

### `src/utils/chain_store.py`
- Loads/saves pre-initialized OpenAI Responses API conversation history
- Stored in `condenser_chains.json` at project root
- Used by `ContentCondenser.init_chains()` to skip re-sending system prompts

### `src/utils/exceptions.py`
- Custom exception types for pipeline errors

---

## CLI Interface

**Module**: `src/main.py`
**Entry point**: `nbj` (or `python -m src.main`)

### Commands

| Command | Purpose |
|---------|---------|
| `nbj condense <url>` | Main condensation command |
| `nbj info <url>` | Display video metadata |
| `nbj init` | Interactive setup wizard (API keys) |
| `nbj check` | Configuration diagnostics |
| `nbj voices` | List available TTS voices |
| `nbj tts <file>` | Convert text file to speech |
| `nbj tts-samples` | Generate audio samples for all voices |
| `nbj show-script <url>` | Display transcript or condensed script |

### `nbj condense` Options

| Option | Default | Description |
|--------|---------|-------------|
| `--aggressiveness`, `-a` | `5` | Condensing level 1–10 (1=conservative, 10=maximum) |
| `--quality`, `-q` | `1080p` | Output quality: `720p`, `1080p`, `4k` |
| `--output`, `-o` | auto | Output file path |
| `--reduction` | None | Target reduction % (overrides aggressiveness) |
| `--resume/--no-resume` | `--resume` | Resume from existing intermediate files |
| `--video-gen-mode` | `slideshow` | `static`, `slideshow`, `avatar`, `audio_only` |
| `--voice` | None | Voice (e.g., `edge/ryan`, `en-GB-RyanNeural`) |
| `--tts-provider` | `elevenlabs` | `elevenlabs` or `edge` |
| `--slideshow-frames` | auto | Max frames for slideshow mode |
| `--speech-rate` | `+0%` | TTS speed (e.g., `+50%`, `-25%`) |
| `--prepend-intro` | off | Prepend numbered key take-aways to TTS script |

---

## Flask Server

**Module**: `server/app.py`
**Start**: `python server/app.py`
**Default port**: `5000`
**Auto-reload**: enabled (`debug=True, use_reloader=True`)

### API Endpoints

| Method | Endpoint                 | Description                                  |
|--------|--------------------------|----------------------------------------------|
| GET    | `/start`                 | Extension download & installation guide page |
| GET    | `/extension.zip`         | Download the packaged Chrome extension       |
| POST   | `/api/condense`          | Submit YouTube URL for processing            |
| GET    | `/api/status/<job_id>`   | Check job status                             |
| GET    | `/api/download/<job_id>` | Stream/download the output file              |
| GET    | `/api/strategies`        | List aggressiveness level descriptions       |
| GET    | `/api/voices?locale=en`  | List Edge TTS voices filtered by locale      |
| GET    | `/api/jobs`              | List all jobs (debugging)                    |
| GET    | `/health`                | Health check                                 |

### POST `/api/condense` Payload

```json
{
  "url": "https://youtu.be/...",
  "aggressiveness": 5,
  "voice": "en-GB-RyanNeural",
  "speech_rate": "+10%",
  "video_mode": "slideshow",
  "prepend_intro": false
}
```

### Concurrency Model
- Processes **one job at a time** (single background thread)
- Returns HTTP 429 if another job is already running
- Jobs stored in-memory (lost on server restart)

---

## Chrome Extension

**Location**: `chrome-extension/`

| File | Purpose |
|------|---------|
| `manifest.json` | Extension config, permissions |
| `popup.html` | Extension popup UI |
| `popup.js` | Extension logic (settings, API calls, polling) |
| `background.js` | Icon color management (active on YouTube video pages) |
| `icons/` | 16/48/128px color + disabled (grayscale) icons |

**Features**:
- Smart icon: colored on YouTube video pages, grayscale otherwise
- Settings: server URL, voice, aggressiveness, speech rate, output mode, prepend-intro
- Persistent job tracking (closes and reopens while job is running)
- Shows video title below video ID (fetched via YouTube oEmbed API)
- Polls job status every 3 seconds
- Built with `chrome-extension/build_extension.py` → `dist/nbj-chrome-extension.zip`

---

## Android App

**Location**: `android/`
**Package**: `com.nbj`
**Language**: Kotlin

### Key Files

| File | Purpose |
|------|---------|
| `MainActivity.kt` | Main UI, AppState machine, share intent handling |
| `SettingsActivity.kt` | Server URL configuration |
| `ConciSerApi.kt` | Retrofit API client + data classes |
| `activity_main.xml` | Single-screen NestedScrollView layout |
| `strings.xml` | String resources |

### AppState Machine
```
NO_URL → READY → SUBMITTING → PROCESSING → COMPLETED
                                         → ERROR
```

### Features
- Registered as share target for YouTube videos
- Settings on main screen: voice, aggressiveness (1–10), speech speed, output mode, prepend-intro
- Server URL in Settings screen (overflow menu)
- Recent jobs list (max 10, stored in SharedPreferences as JSON)
- Video title fetched via YouTube oEmbed API (shown bold in recent jobs)
- Polls server every 3 seconds during processing

### Build
```bash
cd android
./gradlew assembleDebug
adb install app/build/outputs/apk/debug/app-debug.apk
```

---

## Configuration System

**Module**: `src/config.py`
Uses Pydantic Settings with `.env` file loading.

### Key Settings

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI key (Whisper transcription + optional condensation) |
| `ANTHROPIC_API_KEY` | Anthropic key (optional Claude condensation) |
| `ELEVENLABS_API_KEY` | ElevenLabs key (optional voice cloning TTS) |
| `DID_API_KEY` | D-ID key (optional avatar video mode only) |
| `CONDENSER_SERVICE` | `openai` (default) or `claude` |
| `TEMP_DIR` | Temporary files directory (default: `temp/`) |
| `OUTPUT_DIR` | Final output directory (default: `output/`) |

---

## Data Flow

```
YouTube URL
    │
    ▼
[FETCH] yt-dlp → source_video.mp4 + metadata
    │
    ├──────────────────────────────────────────────────────┐
    │  (slideshow mode only)                               │
    │  [FRAME_EXTRACT] PySceneDetect → scene_*.jpg         │
    │  (runs in background thread — parallel with          │
    │   TRANSCRIBE → CONDENSE → TTS)                       │
    │                                                      │
    ▼                                                      │
[TRANSCRIBE] YouTube captions (free) → transcript.json     |
    │         └─ fallback: Whisper API (paid)              │
    │                                                      │
    ▼                                                      │
[CONDENSE] OpenAI/Claude → condensed_script + key_points   │
    │                                                      │
    ├─ prepend_intro=True → numbered intro prepended       │
    │                                                      │
    ▼                                                      │
[TTS] Edge TTS (default) → generated_speech.mp3            │
    │                                                      │
    ├── audio_only → output/*.mp3 → DONE                   │
    │                                                      │
    ▼          waits for frame extraction to finish ───────┘
[VIDEO] slideshow / static / avatar → final composition
    │
    ▼
output/*.mp4
```

**Parallelism**: In `slideshow` mode, scene detection and frame extraction (`_extract_frames_early`) starts immediately after the download completes, in a background `ThreadPoolExecutor` thread. This runs concurrently with Transcribe → Condense → TTS. By the time TTS finishes, the frames are typically ready, eliminating most of the scene detection wait.

---

## File Structure

```
nbj-condenser/
├── src/                        # Core Python pipeline
│   ├── main.py                 # CLI entry point (nbj commands)
│   ├── config.py               # Pydantic settings
│   ├── pipeline.py             # CondenserPipeline orchestrator
│   ├── modules/
│   │   ├── downloader.py       # Stage 1: Video download (yt-dlp)
│   │   ├── transcriber.py      # Stage 2: Whisper transcription
│   │   ├── condenser.py        # Stage 3: LLM condensation
│   │   ├── edge_tts.py         # Stage 4: Edge TTS (free)
│   │   ├── voice_cloner.py     # Stage 4 alt: ElevenLabs voice cloning
│   │   ├── video_generator.py  # Stage 5: D-ID avatar (optional)
│   │   └── compositor.py       # Stage 5: ffmpeg composition
│   └── utils/
│       ├── audio_utils.py      # Audio processing helpers
│       ├── video_utils.py      # Video processing + scene detection
│       ├── prompt_templates.py # LLM prompt templates (L1/L2/L3)
│       ├── chain_store.py      # OpenAI Responses API chain cache
│       └── exceptions.py       # Custom exception types
├── server/
│   ├── app.py                  # Flask server (REST API)
│   └── output/                 # Server-generated output files
├── chrome-extension/
│   ├── manifest.json
│   ├── popup.html
│   ├── popup.js
│   ├── background.js
│   ├── icons/                  # 16/48/128px color + disabled
│   └── build_extension.py      # Packages extension to dist/
├── android/
│   └── app/src/main/java/com/nbj/
│       ├── MainActivity.kt
│       ├── SettingsActivity.kt
│       └── ConciSerApi.kt
├── test/
│   ├── test_condense.py        # Batch condensation tester
│   ├── test_condense.py        # Condensation quality tester
│   └── test_speech_rate.py     # TTS rate validation
├── tts_samples/                # Pre-generated voice preview audio
├── temp/                       # Per-video intermediate files
├── output/                     # CLI output files
├── dist/
│   └── nbj-chrome-extension.zip
├── condenser_chains.json       # Cached OpenAI Responses API chains
├── .env                        # API keys (gitignored)
├── .env.example                # Template
├── requirements.txt
└── setup.py
```

---

## Error Handling

- Fail fast with descriptive errors
- Log all operations to `nbj.log` (project root) and `server/nbj.log`
- Resume support: intermediate files in `temp/<video_id>/` are preserved

### Error Types
- **Configuration errors**: Missing API keys, invalid settings
- **Download errors**: Network issues, invalid URLs, private/age-restricted videos
- **API errors**: Rate limits, authentication, quota exhaustion
- **Processing errors**: ffmpeg failures, file I/O errors
- **Validation errors**: Invalid JSON output from LLM

---

## Performance

### Pipeline Stage Timing (typical 10-min video)
1. **Download**: 30–120s (network-dependent)
2. **Transcribe**: ~60s (Whisper API, ~1/10 real-time)
3. **Condense**: 10–30s (LLM API call)
4. **TTS (Edge)**: 5–15s (async, very fast)
5. **Slideshow composition**: 30–90s (ffmpeg)

### Resource Usage
- **Disk**: ~500MB–2GB per video in `temp/` (cleaned up optionally)
- **Memory**: <1GB typical
- **Network**: High bandwidth for video download; small for API calls

---

## API Usage and Cost

| Service | Use | Cost Estimate |
|---------|-----|---------------|
| YouTube Transcript API | Transcription (primary) | Free |
| OpenAI Whisper | Transcription (fallback) | ~$0.006/min audio |
| OpenAI (gpt-5.2) | Condensation (default) | varies |
| Anthropic Claude | Condensation (optional) | ~$3–15/M tokens |
| Edge TTS | Speech generation (default) | Free |
| ElevenLabs | Speech generation (optional) | ~$0.24/1K chars |
| D-ID | Avatar video (optional) | per second of video |

---

## Dependencies

### Required
- Python 3.10+
- ffmpeg, ffprobe
- `yt-dlp` — Video downloading
- `youtube_transcript_api` — YouTube captions (primary transcription)
- `openai` — Whisper API (fallback transcription) + optional condensation
- `edge-tts` — Free TTS
- `flask`, `flask-cors` — Server
- `click` — CLI framework
- `pydantic`, `pydantic-settings` — Configuration
- `colorama` — Terminal colors

### Optional
- `anthropic` — Claude condensation provider
- `elevenlabs` — Voice cloning TTS
- `scenedetect` — Scene change detection for slideshow
- `requests` — D-ID API calls (avatar mode)

### Android App
- Kotlin, Retrofit2, OkHttp3, Gson, Coroutines, Material3, ViewBinding
