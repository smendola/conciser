# Conciser Remote - Chrome Extension

Chrome extension to submit YouTube videos to your Conciser server for AI-powered condensation.

## Installation

### 1. Load Extension in Chrome

1. Open Chrome and go to `chrome://extensions/`
2. Enable "Developer mode" (toggle in top right)
3. Click "Load unpacked"
4. Select the `chrome-extension` directory
5. Extension icon should appear in toolbar

## Usage

1. Navigate to any YouTube video page
2. Click the Conciser extension icon
3. Click "Condense Video"
4. Wait for processing (status updates every 3 seconds)
5. Click "Download Condensed Video" when ready

## What It Does

- Detects YouTube video URLs automatically
- Submits URL to your Conciser server
- Polls for status every 3 seconds
- Opens download in new tab when complete

## Default Settings

Videos are processed with:
- Aggressiveness: 5 (medium)
- Video mode: slideshow (scene-detected frames)
- TTS: Edge (Aria voice, free)
- Quality: 1080p

## Troubleshooting

**"Not a YouTube video page"**
- Make sure you're on `youtube.com/watch?v=...` page
- Not on homepage, search results, or channel page

**"Connection error"**
- Make sure ngrok is running: `ngrok start conciser`
- Make sure server is running: `cd server && python app.py`
- Server URL is hardcoded to: `https://conciser-aurora.ngrok.dev`

**"Server is busy"**
- Server is processing another video
- Wait for current job to finish

**No icons showing**
- Icons are optional, extension works without them
- See `icons/README.md` for how to add icons

## Files

- `manifest.json` - Extension configuration
- `popup.html` - Extension UI
- `popup.js` - Extension logic
- `icons/` - Extension icons (optional)
