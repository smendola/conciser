# NBJ Condenser Remote Server

HTTP server for remote video condensation via Chrome extension.

## Chrome Extension

A production-ready Chrome extension package is available for easy installation. See `../CHROME_EXTENSION_INSTALL.md` for installation options:

- **Quick Install**: Drag & drop `nbj-chrome-extension.zip` onto `chrome://extensions/`
- **Chrome Web Store**: Submit for public distribution (recommended)
- **Manual Install**: Load unpacked from `../chrome-extension/` directory

The extension allows users to condense YouTube videos directly from their browser by clicking a toolbar icon.

## Setup

### 1. Install Dependencies

```bash
cd server
pip install -r requirements.txt
```

### 2. Start Server

```bash
python app.py
```

Server will start on `http://127.0.0.1:5000`

### 3. Expose with ngrok

In another terminal:

```bash
ngrok start nbj
```

Server will be available at the static URL: `https://conciser-aurora.ngrok.dev`

## Usage

### Via Chrome Extension (Recommended)

1. Install the Chrome extension (see above)
2. Navigate to any YouTube video
3. Click the NBJ Condenser icon in Chrome toolbar
4. Click "Condense Video"
5. Download when complete

### Via API (Direct)

You can also interact with the API directly using curl or other HTTP clients.

## API Endpoints

### POST /api/condense
Submit a YouTube URL for processing.

```bash
curl -X POST https://conciser-aurora.ngrok.dev/api/condense \
  -H "Content-Type: application/json" \
  -d '{"url": "https://youtube.com/watch?v=..."}'
```

Response:
```json
{
  "job_id": "a1b2c3d4",
  "status": "queued",
  "message": "Processing started"
}
```

### GET /api/status/:job_id
Check processing status.

```bash
curl https://conciser-aurora.ngrok.dev/api/status/a1b2c3d4
```

Response (processing):
```json
{
  "job_id": "a1b2c3d4",
  "status": "processing",
  "progress": "[CONDENSE] Condensing content (aggressiveness: 5/10)...",
  "created_at": "2026-02-24T20:30:00"
}
```

Response (completed):
```json
{
  "job_id": "a1b2c3d4",
  "status": "completed",
  "download_url": "/api/download/a1b2c3d4",
  "created_at": "2026-02-24T20:30:00",
  "completed_at": "2026-02-24T20:38:00"
}
```

### GET /api/download/:job_id
Download the processed video.

```bash
curl -O https://conciser-aurora.ngrok.dev/api/download/a1b2c3d4
```

### GET /api/jobs
List all jobs (debugging).

### GET /health
Health check.

## How It Works

1. Server accepts YouTube URL via POST request
2. Runs nbj pipeline in background thread
3. Client polls `/api/status/:id` every 3 seconds
4. When complete, video is available at `/api/download/:id`

## Configuration

Default settings (hardcoded in `app.py`):
- Aggressiveness: 5
- Quality: 1080p
- Video mode: slideshow
- TTS provider: edge (free)
- Voice: Aria (en-US-AriaNeural)
- **Condenser: OpenAI GPT-4o** (more reliable than Claude)

To customize, edit your `.env` file:
- `CONDENSER_SERVICE=openai` (default, uses GPT-4o) or `claude` (uses Claude Sonnet)
- Or edit the `pipeline.run()` call in `process_video()` function for other settings

## Deployment

### Server
- Runs on localhost port 5000 by default
- Exposed via ngrok for remote access
- Static ngrok URL configured: `https://conciser-aurora.ngrok.dev`

### Chrome Extension
- Packaged extension: `../nbj-chrome-extension.zip` (14 KB)
- Smart icon state: colored when usable (on YouTube video), grayed when not
- Ready to distribute or submit to Chrome Web Store
- Server URL hardcoded in `popup.js` (update if using different ngrok URL)

## Notes

- Single-threaded: Only processes one video at a time
- In-memory storage: Jobs lost on server restart
- No authentication: Anyone with ngrok URL can submit videos
- Videos kept in `output/` directory (consider periodic cleanup)
- Chrome extension requires server + ngrok to be running
