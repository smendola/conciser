# Conciser Remote Server

HTTP server for remote video condensation via Chrome extension.

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
ngrok start conciser
```

Server will be available at the static URL: `https://conciser-aurora.ngrok.dev`

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
2. Runs conciser pipeline in background thread
3. Client polls `/api/status/:id` every 3 seconds
4. When complete, video is available at `/api/download/:id`

## Configuration

Default settings (hardcoded in `app.py`):
- Aggressiveness: 5
- Quality: 1080p
- Video mode: slideshow
- TTS provider: edge (free)
- Voice: Aria (en-US-AriaNeural)

To customize, edit the `pipeline.run()` call in `process_video()` function.

## Notes

- Single-threaded: Only processes one video at a time
- In-memory storage: Jobs lost on server restart
- No authentication: Anyone with ngrok URL can submit videos
- Videos kept forever in `output/` directory
