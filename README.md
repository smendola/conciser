# NBJ Condenser - AI-Powered Video Condensation

NBJ Condenser intelligently shortens YouTube videos by removing filler, repetitions, and tangents while preserving key insights. It uses AI transcription, LLM condensation, and text-to-speech to produce a condensed version — typically 30–70% shorter.

## Features

- **Intelligent Content Analysis**: OpenAI or Claude condenses the transcript, preserving key insights
- **Free TTS**: Microsoft Edge TTS voices (no API key needed) — dozens of natural neural voices
- **Adjustable Aggressiveness**: 1–10 scale controls how much content is removed
- **Multiple Output Modes**: Slideshow (default), audio-only MP3, static frame, or D-ID avatar
- **Resume Support**: Skips already-completed pipeline stages automatically
- **Three Interfaces**: CLI, Chrome extension (via server), Android app (via server)

## Quick Start

### 1. Install

```bash
git clone <repo>
cd nbj-condenser
python -m venv venv && source venv/bin/activate
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env and add your API keys:
#   OPENAI_API_KEY=sk-...   (required: Whisper + condensation)
```

### 3. Condense a video

```bash
nbj condense https://youtu.be/VIDEO_ID
```

Output file is saved to `output/` and opened automatically.

## CLI Usage

```bash
# Basic (slideshow output, Edge TTS, aggressiveness 5)
nbj condense https://youtu.be/VIDEO_ID

# Audio only (fastest — no video)
nbj condense https://youtu.be/VIDEO_ID --video-gen-mode audio_only

# Choose a voice and speed
nbj condense https://youtu.be/VIDEO_ID --voice en-US-AriaNeural --speech-rate "+20%"

# Maximum condensation
nbj condense https://youtu.be/VIDEO_ID --aggressiveness 10

# Add key take-aways intro
nbj condense https://youtu.be/VIDEO_ID --prepend-intro

# List available voices
nbj voices --provider edge

# Check your configuration
nbj check
```

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--aggressiveness`, `-a` | `5` | Condensing level 1–10 |
| `--quality`, `-q` | `1080p` | Video quality: `720p`, `1080p`, `4k` |
| `--video-gen-mode` | `slideshow` | `slideshow`, `audio_only`, `static`, `avatar` |
| `--voice` | auto | Edge voice (e.g., `en-GB-RyanNeural`) or `edge/ryan` |
| `--tts-provider` | `edge` | `edge` (free) or `elevenlabs` (paid) |
| `--speech-rate` | `+0%` | TTS speed: `+50%` faster, `-25%` slower |
| `--prepend-intro` | off | Prepend numbered key take-aways to speech |
| `--resume/--no-resume` | resume | Resume from existing intermediate files |

## Server Mode (for Chrome Extension / Android App)

Run the Flask server to use the Chrome extension or Android app:

```bash
# From project root (with venv active)
python server/app.py
```

Then expose it via ngrok:
```bash
ngrok start nbj
```

Users can install the Chrome extension from: `https://your-ngrok-url/start`

## API Keys

| Key | Required | Used For |
|-----|----------|---------|
| `OPENAI_API_KEY` | **Yes** | Whisper transcription + LLM condensation (default) |
| `ANTHROPIC_API_KEY` | No | Alternative Claude condensation provider |
| `ELEVENLABS_API_KEY` | No | Voice cloning TTS (paid alternative to Edge TTS) |
| `DID_API_KEY` | No | Avatar video mode only |

Run `nbj init` for interactive setup, or `nbj check` to verify configuration.

## Output Modes

| Mode | Output | Speed | Description |
|------|--------|-------|-------------|
| `slideshow` | MP4 | Medium | Scene-detected keyframes synced to TTS audio |
| `audio_only` | MP3 | Fast | TTS audio only, no video |
| `static` | MP4 | Medium | Single frame as video background |
| `avatar` | MP4 | Slow | D-ID talking head (requires DID_API_KEY) |

## Project Structure

```
src/          Python pipeline (download, transcribe, condense, TTS, video)
server/       Flask REST server (used by extension and Android app)
chrome-extension/   Chrome/Edge browser extension
android/      Native Android app (Kotlin)
test/         Batch testing and quality evaluation tools
tts_samples/  Pre-generated voice preview audio files
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for full technical details.
See [QUICKSTART.md](QUICKSTART.md) for step-by-step setup.
