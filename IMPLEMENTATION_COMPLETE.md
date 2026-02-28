# NBJ Condenser - Implementation Notes

This file is kept for historical reference. For current status, see README.md and ARCHITECTURE.md.

## Current Feature Set

### CLI (`nbj condense`)
- Aggressiveness 1–10, quality 720p/1080p/4k
- Output modes: slideshow (default), audio_only, static, avatar
- TTS providers: Edge TTS (free, default) or ElevenLabs (paid)
- Voice selection, speech rate control
- Prepend-intro flag (numbered key take-aways)
- Resume support (skips already-completed stages)
- Commands: condense, info, init, check, voices, tts, tts-samples, show-script

### Server (`server/app.py`)
- Flask REST server, port 5000, auto-reload enabled
- Single-job queue (one video at a time)
- Endpoints: /start, /extension.zip, /api/condense, /api/status, /api/download, /api/strategies, /api/voices, /api/jobs, /health
- Serves Chrome extension ZIP for easy distribution

### Chrome Extension (`chrome-extension/`)
- Smart icon (active on YouTube video pages)
- Settings: server URL, voice, aggressiveness, speech rate, output mode, prepend-intro
- Video title display (oEmbed)
- Persistent job state across popup open/close
- Built via build_extension.py -> dist/nbj-chrome-extension.zip

### Android App (`android/`, package `com.nbj`)
- Share target for YouTube URLs
- AppState machine: NO_URL -> READY -> SUBMITTING -> PROCESSING -> COMPLETED/ERROR
- Main screen settings: voice, aggressiveness, speech speed, output mode, prepend-intro
- Settings screen: server URL
- Recent jobs list with video titles
- Video/audio playback via Android intent chooser

### Pipeline (`src/pipeline.py`)
- Stage 1: Download (yt-dlp)
- Stage 2: Transcribe (Whisper API)
- Stage 3: Condense (OpenAI gpt-5.2 default, or Claude)
- Stage 4: TTS (Edge TTS default, or ElevenLabs)
- Stage 5: Video (slideshow/static/avatar) or audio-only output
