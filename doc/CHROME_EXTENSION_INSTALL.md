# NBJ Condenser Chrome Extension

## Installation

The extension package is at `dist/nbj-chrome-extension.zip`.

The server also serves it at `https://your-server/extension.zip` with a full install guide at `https://your-server/start`.

### Option 1: Drag-and-drop (easiest)

1. Open `chrome://extensions/` (or `edge://extensions/`)
2. Enable **Developer mode** (toggle in top-right corner)
3. Drag `nbj-chrome-extension.zip` onto the extensions page
4. Chrome installs it automatically — no extraction needed

### Option 2: Load unpacked

1. Extract `nbj-chrome-extension.zip` to a folder
2. Open `chrome://extensions/`
3. Enable **Developer mode**
4. Click **Load unpacked** → select the extracted folder

### Option 3: Install from server

Navigate to `https://your-ngrok-url/start` — the server provides a download button and step-by-step install instructions.

---

## Features

- **Smart icon**: Icon is colored on YouTube video pages, gray elsewhere
- **Settings panel**: Configure server URL, voice, aggressiveness (1–10), speech speed, output mode, prepend-intro
- **Video title**: Shown bold below the video ID (fetched via YouTube oEmbed)
- **Persistent state**: Close and reopen — the popup remembers your active job
- **Real-time progress**: Polls server every 3 seconds
- **Auto-watch**: Opens condensed video in new tab when complete

---

## Usage

1. Navigate to any YouTube video page (`youtube.com/watch?v=...`)
2. The extension icon turns colored (blue/active) — click it
3. Adjust settings if desired (voice, aggressiveness, etc.)
4. Click **Condense Video**
5. The popup shows live progress updates
6. When done: click **Watch Video** to open the condensed output

---

## Settings

| Setting | Description |
|---------|-------------|
| Server URL | NBJ Condenser server URL (e.g., ngrok URL) |
| Voice | Edge TTS voice (populated from server) |
| Aggressiveness | 1–10 condensation level |
| Speech Speed | TTS rate (e.g., +10%) |
| Output Mode | Slideshow (MP4) or Audio Only (MP3) |
| Prepend key take-aways intro | Adds numbered summary intro to speech |

Settings are saved to `chrome.storage.local` and persist across browser sessions.

---

## Files

| File | Purpose |
|------|---------|
| `manifest.json` | Extension config, permissions, icons |
| `popup.html` | Popup UI |
| `popup.js` | Extension logic (settings, API calls, polling, title fetch) |
| `background.js` | Icon state management (active/inactive) |
| `icons/icon{16,48,128}.png` | Colored icons (active state) |
| `icons/icon{16,48,128}-disabled.png` | Grayscale icons (inactive state) |

---

## Building

```bash
python chrome-extension/build_extension.py
# Output: dist/nbj-chrome-extension.zip
```

Run this after any changes to rebuild the package.
