# Quick Start Guide

Get started with NBJ Condenser in minutes.

## Prerequisites

1. **Python 3.10+**
2. **ffmpeg** (required for video/audio processing)
3. **OpenAI API key** (required — for Whisper transcription and condensation)

Optional API keys:
- `ANTHROPIC_API_KEY` — use Claude as the condensation provider instead of OpenAI
- `ELEVENLABS_API_KEY` — paid voice cloning (Edge TTS is free and used by default)
- `DID_API_KEY` — D-ID avatar video mode only

## Installation

### 1. Install ffmpeg

**Ubuntu/Debian:**
```bash
sudo apt update && sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**
Download from https://ffmpeg.org/download.html and add to PATH.

### 2. Install NBJ Condenser

```bash
cd nbj-condenser
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -e .
```

### 3. Configure API Keys

```bash
cp .env.example .env
# Edit .env and add at minimum:
#   OPENAI_API_KEY=sk-...
```

Or run the interactive wizard:
```bash
nbj init
```

### 4. Verify Setup

```bash
nbj check
```

---

## Your First Condensed Video

### Option A: Slideshow (default, MP4 output)

```bash
nbj condense "https://youtube.com/watch?v=VIDEO_ID"
```

Pipeline stages:
1. **Download** — yt-dlp fetches the video (~30s)
2. **Transcribe** — Whisper API transcribes audio (~1–2 min)
3. **Condense** — OpenAI/Claude rewrites the script (~15–30s)
4. **TTS** — Edge TTS generates speech (~5–15s)
5. **Slideshow** — ffmpeg builds a video from scene keyframes (~30–90s)

Total: **3–5 minutes** for a typical 10-minute video.

### Option B: Audio Only (fastest, MP3 output)

```bash
nbj condense "https://youtube.com/watch?v=VIDEO_ID" --video-gen-mode audio_only
```

No video generation step — just the condensed speech as an MP3.
Total: **1–3 minutes**.

---

## Common Options

### Adjust condensation level

```bash
# Conservative — remove ~20%
nbj condense "URL" --aggressiveness 3

# Moderate (default) — remove ~50%
nbj condense "URL" --aggressiveness 5

# Aggressive — remove ~75%
nbj condense "URL" --aggressiveness 8
```

### Choose a voice

```bash
# List all English voices
nbj voices --provider edge

# Use a specific voice
nbj condense "URL" --voice en-US-AriaNeural

# Shortcut names also work
nbj condense "URL" --voice ryan
```

### Adjust speech speed

```bash
nbj condense "URL" --speech-rate "+20%"   # 20% faster
nbj condense "URL" --speech-rate "-15%"   # 15% slower
```

### Add key take-aways intro

```bash
nbj condense "URL" --prepend-intro
```

Prepends a numbered list of key take-aways to the TTS output.

### Resume interrupted jobs

Resume is **on by default**. If a run was interrupted, just re-run the same command and it will skip already-completed stages.

```bash
nbj condense "URL"              # resumes automatically
nbj condense "URL" --no-resume  # force restart from scratch
```

---

## Output

Files are saved to `output/` with auto-generated names:
```
output/<video_id>_<title>_edge_<voice>.mp4
output/<video_id>_<title>_edge_<voice>.mp3
```

---

## Server Mode (Chrome Extension / Android App)

To use the Chrome extension or Android app, run the Flask server:

```bash
python server/app.py
```

Expose it with ngrok:
```bash
ngrok start nbj
```

Then share the install link: `https://your-ngrok-url/start`

---

## Tips for Best Results

- **Clear audio** with a single speaker works best
- Start at aggressiveness **5**, then adjust up/down
- Very high levels (9–10) may lose important context
- Audio-only mode is great for listening while commuting

---

## Troubleshooting

**"API key not set"** → Run `nbj check` to see which keys are missing, then edit `.env`.

**"ffmpeg not found"** → Install ffmpeg (see above) and ensure it's on your PATH.

**Output sounds cut off** → Try `--no-resume` to regenerate the condensed script fresh.

**TTS sounds wrong** → Try a different voice: `nbj voices` to browse, then `--voice <name>`.
