# NBJ Condenser - Chrome Extension

Chrome extension to submit YouTube videos to your NBJ Condenser server for AI-powered condensation.

## Installation

### Quick Install (Recommended)
1. Go to `chrome://extensions/`
2. Drag and drop `conciser-chrome-extension.zip` onto the page
3. Chrome will automatically install it

### Manual Install
1. Open Chrome and go to `chrome://extensions/`
2. Enable "Developer mode" (toggle in top right)
3. Click "Load unpacked"
4. Select the `chrome-extension` directory
5. Extension icon should appear in toolbar

## Features

### Smart Icon State
- **Active (colored icon)**: When on a YouTube video page - click to condense
- **Disabled (grayed out)**: When not on a YouTube video page
- The icon automatically updates as you browse

### Persistent State
- **Remembers active jobs**: Close and reopen the popup - it remembers your processing job
- **Resume anywhere**: Check progress from any tab, the extension tracks your active job
- **Auto-cleanup**: Clears state when job completes or fails

### Usage

1. Navigate to any YouTube video page
2. Click the NBJ Condenser extension icon (it will be colored/active)
3. Click "Condense Video"
4. Wait for processing (status updates every 3 seconds)
5. You can close the popup and reopen it later - it will resume tracking
6. Click "Watch Video" when ready

## What It Does

- Detects YouTube video URLs automatically
- Shows visual feedback via icon state (active/disabled)
- Submits URL to your NBJ Condenser server
- Polls for status every 3 seconds
- Opens video in new tab when complete

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
