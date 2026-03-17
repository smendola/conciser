# NBJ Condenser Architecture

This document provides a technical overview of NBJ Condenser's architecture and
implementation.

## System Overview

NBJ Condenser is a YouTube video condensation system with three interfaces:

- **CLI** (`nbj condense …`) — direct command-line use
- **Flask Server** (`server/app.py`) — REST API backend, used by the Chrome
  extension and Android app
- **Chrome Extension** (`chrome-extension/`) — browser popup that submits videos
  to the server
- **Android App** (`android/`) — native app that accepts YouTube share intents
  and submits to the server

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

Two-strategy approach — YouTube captions are tried first, Whisper is the
fallback:

1. **YouTube Transcript API** (primary, free): fetches captions directly from
   YouTube via `youtube_transcript_api`. Succeeds for most public videos that
   have auto-generated or manual captions.
2. **Whisper** (fallback): if YouTube captions are unavailable (disabled,
   private, or missing), ffmpeg extracts audio (WAV, 16kHz) and sends it to
   Whisper. Large files are auto-chunked at the 25MB limit and timestamps are
   stitched back together. Two providers supported:
   - **Groq** (default, free): `whisper-large-v3` via Groq's OpenAI-compatible
     API. Significantly faster than OpenAI due to Groq's LPU hardware.
   - **OpenAI** (fallback if no `GROQ_API_KEY`): `whisper-1`, paid at
     ~$0.006/min.

Resume support: skips both strategies if `transcript.json` already exists in the
video's temp folder.

**External Dependencies**: `youtube_transcript_api` (primary); Groq API or
OpenAI API + ffmpeg (fallback)

---

### Stage 3: Content Condensation

**Module**: `src/modules/condenser.py`

- Supports two LLM providers: **OpenAI** (default, `gpt-5.2`) or **Anthropic**
  (`claude-sonnet-4.6`)
- Configured via `CONDENSATION_PROVIDER=openai|anthropic` in `.env`
- Uses a three-level prompt structure:
  - **System prompt (L1)**: Core condensation instructions
  - **Strategy prompt (L2)**: Aggressiveness-level-specific rules (1–10 scale)
  - **User prompt (L3)**: Transcript + video metadata
- Returns structured JSON: `condensed_script`, `key_points_preserved`,
  `original_duration_estimate`, etc.
- Optional **Responses API pre-initialization** (`init_chains()` in
  `condenser.py`, stored in `condenser_chains.json` via
  `src/utils/chain_store.py`)
  - Caches L1+L2 prompts as OpenAI conversation history for faster repeat
    requests
- Optional **prepend_intro**: builds a numbered key take-aways list from
  `key_points_preserved` and prepends it to the TTS script

**External Dependencies**: OpenAI API or Anthropic API

---

### Stage 4: Text-to-Speech

**Module**: `src/modules/azure_tts.py` (default), `src/modules/edge_tts.py`
(Edge), or `src/modules/tts.py` (ElevenLabs)

**Azure TTS** (default, paid):

- Uses Azure Cognitive Services Speech SDK
- Requires `AZURE_SPEECH_KEY` and `AZURE_SPEECH_REGION`
- Supports SSML input for richer prosody control (see SSML rewrite section)
- Configurable voice and speech rate
- Voice list browsable via `nbj voices --provider azure`

**Edge TTS** (free, optional):

- Uses Microsoft Edge TTS via the `edge-tts` Python package
- No API key required
- Configurable voice (e.g., `en-GB-RyanNeural`, `en-US-AriaNeural`)
- Configurable speech rate (e.g., `+10%`, `-25%`)
- Voice list browsable via `nbj voices --provider edge`

**ElevenLabs** (paid, optional):

- Voice cloning: extracts 2–5 min of clean speech, uploads to ElevenLabs,
  receives a voice ID
- Generates speech from condensed script using the cloned voice
- Handles long scripts via sentence-aware chunking (5000 chars max)

**Resume / caching keying rule**:

- All intermediate artifacts that can be resumed (e.g., transcripts, condensed
  scripts, SSML rewrites, generated audio) must be keyed (in filename and/or
  metadata) by **all parameters that influence the bytes of that artifact**.
- This is required so `--resume` never incorrectly reuses an artifact produced
  under different settings.
- Example: generated speech audio must be keyed by at least aggressiveness, TTS
  provider, voice selection, rate, and whether the input to TTS was plain text
  vs SSML.

**SSML rewrite (Azure TTS only, aggressiveness >= 4)**:

- For aggressiveness levels 4 and up, when using `tts_provider=azure`, the
  pipeline adds an additional LLM step that rewrites the condensed script into
  **valid SSML** optimized for listening.
- The SSML rewrite includes any optional `prepend_intro` content so the final
  TTS input is a single valid `<speak>...</speak>` document.
- The SSML output is cached in the video temp folder (keyed according to the
  resume rule above) so resume can skip recomputation.
- If the SSML output is invalid (not parseable as XML / SSML), the pipeline
  falls back to plain text for TTS and logs an error.

**External Dependencies**: `edge-tts` package (Edge TTS); Azure Cognitive
Services Speech SDK + keys (Azure TTS); ElevenLabs API (optional)

---

### Stage 5: Video Generation

**Module**: `src/modules/video_generator.py`, `src/modules/compositor.py`

Three modes, selectable via `--format` (CLI supports `slideshow`, `audio_only`,
`avatar`; `static` is available in the pipeline but not exposed via the CLI):

| Mode         | Description                                                        | Output                      |
| ------------ | ------------------------------------------------------------------ | --------------------------- |
| `slideshow`  | Scene-detected keyframes + JS player (no ffmpeg encode)            | `.json` manifest (default)  |
| `audio_only` | Skip video entirely, output TTS audio as-is                        | `.mp3` (fastest)            |
| `static`     | Single extracted frame as video background                         | `.mp4`                      |
| `avatar`     | D-ID talking-head video (expensive, rarely used)                   | `.mp4`                      |

**Slideshow details** (`pipeline.py` — `_build_slideshow_package()`):

- Detects scene changes using PySceneDetect
- Extracts keyframe JPEGs at scene boundaries (runs in parallel with Transcribe → Condense → TTS)
- Proportionally maps original scene timestamps to the condensed audio timeline
- Outputs a JSON timing manifest + a `{job_id}_slideshow_frames/` directory of sequentially-named JPEGs
- No ffmpeg video encoding — the server renders the slideshow as a JS player in the browser
- `--slideshow-frames N` limits number of frames used

**External Dependencies**: PySceneDetect (slideshow); D-ID API (avatar mode only)

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

**Module**: `src/main.py` **Entry point**: `nbj` (or `python -m src.main`)

### Commands

| Command                  | Purpose                                             |
| ------------------------ | --------------------------------------------------- |
| `nbj condense <url>`     | Main condensation command                           |
| `nbj info <url>`         | Display video metadata                              |
| `nbj init`               | Interactive setup wizard (API keys)                 |
| `nbj setup`              | Interactive setup wizard (alias for init)           |
| `nbj check`              | Configuration diagnostics                           |
| `nbj voices`             | List available TTS voices                           |
| `nbj tts <file>`         | Convert text file to speech                         |
| `nbj tts-samples`        | Generate audio samples for all voices               |
| `nbj show-script <url>`  | Display transcript or condensed script              |
| `nbj transcript <url>`   | Fetch and display video transcript                  |
| `nbj takeaways <url>`    | Extract key takeaways from a video                  |
| `nbj jobs`               | List recent jobs                                    |
| `nbj start`              | Start the Flask server                              |
| `nbj stop`               | Stop the Flask server                               |
| `nbj logs`               | View server/pipeline logs                           |
| `nbj expire-jobs`        | Remove stale job records                            |
| `nbj clean-cache`        | Clean up cached intermediate files                  |

### `nbj condense` Options

| Option                   | Default     | Description                                                              |
| ------------------------ | ----------- | ------------------------------------------------------------------------ |
| `--aggressiveness`, `-a` | `5`         | Condensing level 1–10 (1=conservative, 10=maximum)                       |
| `--quality`, `-q`        | `1080p`     | Output quality: `720p`, `1080p`, `4k`                                    |
| `--output`, `-o`         | auto        | Output file path                                                         |
| `--resume/--no-resume`   | `--resume`  | Resume from existing intermediate files                                  |
| `--format`               | `slideshow` | `slideshow`, `audio_only`, `avatar`                                      |
| `--voice`                | None        | Voice (e.g., `edge/ryan`, `azure/aria`, `en-GB-RyanNeural`)              |
| `--tts-provider`         | `azure`     | `azure` (paid, SSML), `edge` (free), or `elevenlabs` (paid)             |
| `--slideshow-frames`     | auto        | Max frames for slideshow mode                                            |
| `--speech-rate`          | `+0%`       | TTS speed (e.g., `+50%`, `-25%`). Works with Edge and Azure providers.  |
| `--prepend-intro`        | off         | Prepend numbered key take-aways to TTS script                            |
| `--llm-progress`         | None        | Show LLM streaming output: `dots`, `text`, or `wordcount`               |
| `--xdg-open`, `-O`       | off         | Open output file with xdg-open after completion                          |

---

## Flask Server

**Module**: `server/app.py` **Start**: `python server/app.py` **Default port**:
`5000` **Auto-reload**: enabled (`debug=True, use_reloader=True`)

### API Endpoints

| Method | Endpoint                 | Description                                  |
| ------ | ------------------------ | -------------------------------------------- |
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

- up to n jobs can be queued and processed concurrently
- job info persisted to sqlite
- each installed user (client) has a unique identifier and can only access their
  own jobs

---

## Chrome Extension

**Location**: `chrome-extension/`

| File            | Purpose                                               |
| --------------- | ----------------------------------------------------- |
| `manifest.json` | Extension config, permissions                         |
| `popup.html`    | Extension popup UI                                    |
| `popup.js`      | Extension logic (settings, API calls, polling)        |
| `background.js` | Icon color management (active on YouTube video pages) |
| `icons/`        | 16/48/128px color + disabled (grayscale) icons        |

**Features**:

- Smart icon: colored on YouTube video pages, grayscale otherwise
- Settings: server URL, voice, aggressiveness, speech rate, output mode,
  prepend-intro
- Persistent job tracking (closes and reopens while job is running)
- Shows video title below video ID (fetched via YouTube oEmbed API)
- Polls job status every 3 seconds
- Built with `chrome-extension/build_extension.py` →
  `dist/nbj-chrome-extension.zip`

---

## Android App

**Location**: `android/` **Package**: `com.nbj` **Language**: Kotlin

### Key Files

| File                  | Purpose                                          |
| --------------------- | ------------------------------------------------ |
| `MainActivity.kt`     | Main UI, AppState machine, share intent handling |
| `SettingsActivity.kt` | Server URL configuration                         |
| `ConciSerApi.kt`      | Retrofit API client + data classes               |
| `activity_main.xml`   | Single-screen NestedScrollView layout            |
| `strings.xml`         | String resources                                 |

### AppState Machine

```
NO_URL → READY → SUBMITTING → PROCESSING → COMPLETED
                                         → ERROR
```

### Features

- Registered as share target for YouTube videos
- Settings on main screen: voice, aggressiveness (1–10), speech speed, output
  mode, prepend-intro
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

**Module**: `src/config.py` Uses Pydantic Settings with `.env` file loading.

### Key Settings

| Variable                          | Description                                                              |
| --------------------------------- | ------------------------------------------------------------------------ |
| `OPENAI_API_KEY`                  | OpenAI key (condensation; Whisper fallback if no Groq key)               |
| `ANTHROPIC_API_KEY`               | Anthropic key (optional Claude condensation)                             |
| `GROQ_API_KEY`                    | Groq key (free Whisper transcription, default)                           |
| `ELEVENLABS_API_KEY`              | ElevenLabs key (optional voice cloning TTS)                              |
| `DID_API_KEY`                     | D-ID key (optional avatar video mode only)                               |
| `AZURE_SPEECH_KEY`                | Azure Speech Services key (optional Azure TTS)                           |
| `AZURE_SPEECH_REGION`             | Azure region (e.g., `eastus`); required with `AZURE_SPEECH_KEY`          |
| `HEYGEN_API_KEY`                  | HeyGen key (alternative to D-ID; not yet wired up)                       |
| `YOUTUBE_COOKIE_FILE`             | Path to Netscape-format YouTube cookies file for yt-dlp authentication   |
| `YOUTUBE_PROXY_URL`               | Optional proxy URL for YouTube access                                    |
| `CONDENSATION_PROVIDER`           | `openai` (default) or `anthropic`                                        |
| `TAKEAWAYS_EXTRACTION_PROVIDER`   | `openai` (default) or `anthropic`                                        |
| `CONDENSATION_MODEL_OPENAI`       | OpenAI model for condensation (default: `gpt-5.2`)                       |
| `CONDENSATION_MODEL_ANTHROPIC`    | Anthropic model for condensation (default: `claude-sonnet-4.6`)          |
| `TAKEAWAYS_MODEL_OPENAI`          | OpenAI model for takeaways (default: `gpt-5-nano`)                       |
| `TAKEAWAYS_MODEL_ANTHROPIC`       | Anthropic model for takeaways (default: `claude-haiku-4-5-20251001`)     |
| `TTS_PROVIDER`                    | `azure` (default, paid, SSML), `edge` (free), or `elevenlabs` (paid)    |
| `TRANSCRIPTION_SERVICE`           | `groq` (default, free) or `openai`                                       |
| `TRANSCRIPTION_METHOD`            | `chained` (default), `youtube` (captions only), or `whisper` (only)      |
| `TEMP_DIR`                        | Temporary files directory (default: `temp/`)                             |
| `OUTPUT_DIR`                      | Final output directory (default: `output/`)                              |

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
    │         └─ fallback: Whisper via Groq (free/fast)    │
    │                      or OpenAI (if no Groq key)      │
    │                                                      │
    ▼                                                      │
[CONDENSE] OpenAI/Claude → condensed_script + key_points   │
    │                                                      │
    ├─ prepend_intro=True → numbered intro prepended       │
    │                                                      │
    ▼                                                      │
[TTS] Azure TTS (default) → generated_speech.mp3            │
    │                                                      │
    ├── audio_only → output/*.mp3 → DONE                   │
    │                                                      │
    ▼          waits for frame extraction to finish ───────┘
[SLIDESHOW] timing manifest + copied JPEGs → output/*.json + frames/
    │          (no ffmpeg — browser JS player syncs frames to audio)
    ├── slideshow → output/{id}_slideshow.json + {id}_slideshow_frames/ → DONE
    │
    ▼   (static / avatar only)
[VIDEO] static / avatar → ffmpeg composition → output/*.mp4
```

**Parallelism**: In `slideshow` mode, scene detection and frame extraction
(`_extract_frames_early`) starts immediately after the download completes, in a
background `ThreadPoolExecutor` thread. This runs concurrently with Transcribe →
Condense → TTS. By the time TTS finishes, the frames are typically ready,
eliminating the scene detection wait entirely.

**Slideshow manifest format** (`{job_id}_slideshow.json`):
```json
{
  "duration": 187.4,
  "frames": [
    {"file": "000.jpg", "t": 0.0},
    {"file": "001.jpg", "t": 15.2},
    ...
  ]
}
```
The browser player listens to `audio.ontimeupdate` and swaps the displayed JPEG
whenever `currentTime >= frame.t`.

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
│   │   ├── transcriber.py      # Stage 2: Transcription (YouTube captions → Whisper via Groq/OpenAI)
│   │   ├── condenser.py        # Stage 3: LLM condensation
│   │   ├── azure_tts.py        # Stage 4: Azure TTS (default, paid, SSML)
│   │   ├── edge_tts.py         # Stage 4 alt: Edge TTS (free)
│   │   ├── tts.py              # Stage 4 alt: ElevenLabs voice cloning
│   │   ├── video_generator.py  # Stage 5: D-ID avatar (optional)
│   │   └── compositor.py       # Stage 5: ffmpeg composition (static/avatar modes only)
│   └── utils/
│       ├── audio_utils.py      # Audio processing helpers
│       ├── video_utils.py      # Video processing + scene detection
│       ├── prompt_templates.py # LLM prompt templates (L1/L2/L3)
│       ├── llm_schemas.py      # JSON schema definitions for LLM structured output
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
│   ├── test_condense.py        # Batch condensation quality tester
│   ├── test_speech_rate.py     # TTS rate validation
│   ├── test_rate_validation.py # Speech rate format tests
│   └── test_voice_shortcut.py  # Voice name resolution tests
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
- **Download errors**: Network issues, invalid URLs, private/age-restricted
  videos
- **API errors**: Rate limits, authentication, quota exhaustion
- **Processing errors**: ffmpeg failures, file I/O errors
- **Validation errors**: Invalid JSON output from LLM

---

## Performance

### Pipeline Stage Timing (typical 10-min video)

1. **Download**: 30–120s (network-dependent)
2. **Transcribe**: ~5s via YouTube captions; or ~10–60s via Whisper (Groq is
   much faster than OpenAI)
3. **Condense**: 10–30s (LLM API call)
4. **TTS (Azure)**: 5–15s
5. **Slideshow package**: ~1–2s (file copy + JSON write, no ffmpeg)

### Resource Usage

- **Disk**: ~500MB–2GB per video in `temp/` (cleaned up optionally)
- **Memory**: <1GB typical
- **Network**: High bandwidth for video download; small for API calls

---

## API Usage and Cost

| Service                         | Use                                     | Cost Estimate       |
| ------------------------------- | --------------------------------------- | ------------------- |
| YouTube Transcript API          | Transcription (primary)                 | Free                |
| Groq Whisper (whisper-large-v3) | Transcription fallback (default)        | Free                |
| OpenAI Whisper (whisper-1)      | Transcription fallback (if no Groq key) | ~$0.006/min audio   |
| OpenAI (gpt-5.2)                | Condensation (default)                  | varies              |
| Anthropic (claude-sonnet-4.6)   | Condensation (optional)                 | ~$3–15/M tokens     |
| Azure TTS                       | Speech generation (default, SSML)       | varies              |
| Edge TTS                        | Speech generation (optional, free)      | Free                |
| ElevenLabs                      | Speech generation (optional)            | ~$0.24/1K chars     |
| D-ID                            | Avatar video (optional)                 | per second of video |

---

## Dependencies

### Required

- Python 3.10+
- ffmpeg, ffprobe
- `yt-dlp` — Video downloading
- `youtube_transcript_api` — YouTube captions (primary transcription)
- `openai` — OpenAI SDK used for both Groq and OpenAI endpoints (condensation +
  Whisper fallback)
- Groq API key — free Whisper transcription fallback (recommended; get one at
  console.groq.com)
- `edge-tts` — Free TTS
- `flask`, `flask-cors` — Server
- `click` — CLI framework
- `pydantic`, `pydantic-settings` — Configuration
- `colorama` — Terminal colors

### Optional

- `anthropic` — Claude condensation provider
- `elevenlabs` — Voice cloning TTS
- `azure-cognitiveservices-speech` — Azure TTS with SSML support
- `scenedetect` — Scene change detection for slideshow
- `requests` — D-ID API calls (avatar mode)

### Android App

- Kotlin, Retrofit2, OkHttp3, Gson, Coroutines, Material3, ViewBinding
