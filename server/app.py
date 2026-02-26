"""
NBJ Condenser Remote Server

Simple HTTP server that accepts YouTube URLs and processes them with nbj.
Designed to run behind ngrok for remote access.
"""

import os
import sys
import uuid
import threading
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, send_file, render_template_string, send_from_directory
from flask_cors import CORS

# Add parent directory to path to import nbj modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings
from src.pipeline import CondenserPipeline

app = Flask(__name__)
CORS(app)  # Allow requests from Chrome extension

# In-memory job storage (simple, no persistence)
jobs = {}
current_job_lock = threading.Lock()
currently_processing = None


class Job:
    def __init__(self, job_id, youtube_url):
        self.id = job_id
        self.url = youtube_url
        self.status = "queued"  # queued, processing, completed, error
        self.progress = ""
        self.output_file = None
        self.error = None
        self.created_at = datetime.now()
        self.completed_at = None


def progress_callback(stage: str, message: str):
    """Called by pipeline to update progress."""
    global currently_processing
    if currently_processing:
        job = jobs.get(currently_processing)
        if job:
            job.progress = f"[{stage}] {message}"
            print(f"[{job.id}] {job.progress}")


def process_video(job_id):
    """Process video in background thread."""
    global currently_processing

    try:
        job = jobs[job_id]
        job.status = "processing"

        # Initialize pipeline
        settings = get_settings()
        pipeline = CondenserPipeline(settings)

        # Debug: Print actual Python API call in magenta
        DEBUG_SHOW_PROMPT = False
        if DEBUG_SHOW_PROMPT:
            params = {
                'video_url': job.url,
                'aggressiveness': 5,
                'quality': '1080p',
                'video_gen_mode': 'slideshow',
                'tts_provider': 'edge',
                'voice_id': 'en-GB-RyanNeural',
                'skip_voice_clone': True,
                'progress_callback': 'progress_callback',
                'resume': True
            }
            print(f"\033[35mpipeline.run({params})\033[0m")

        # Run with defaults (--voice implies skip_voice_clone=True)
        result = pipeline.run(
            video_url=job.url,
            aggressiveness=5,
            quality="1080p",
            video_gen_mode="slideshow",
            tts_provider="edge",
            voice_id="en-GB-RyanNeural",
            skip_voice_clone=True,
            progress_callback=progress_callback,
            resume=True
        )

        job.output_file = str(result['output_video'])
        job.status = "completed"
        job.completed_at = datetime.now()
        print(f"[{job_id}] Completed: {job.output_file}")

    except Exception as e:
        job = jobs[job_id]
        job.status = "error"
        job.error = str(e)
        job.completed_at = datetime.now()
        print(f"[{job_id}] Error: {e}")

    finally:
        with current_job_lock:
            currently_processing = None


@app.route('/start')
def start_page():
    """Landing page with extension download and installation instructions."""
    html = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NBJ Condenser Remote - Get Started</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
        }

        .container {
            max-width: 900px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, #1a73e8 0%, #1557b0 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }

        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }

        .header p {
            font-size: 1.2em;
            opacity: 0.9;
        }

        .content {
            padding: 40px;
        }

        .download-section {
            background: #f0f7ff;
            border: 2px solid #1a73e8;
            border-radius: 8px;
            padding: 30px;
            margin-bottom: 40px;
            text-align: center;
        }

        .download-btn {
            display: inline-block;
            background: #1a73e8;
            color: white;
            padding: 15px 40px;
            border-radius: 6px;
            text-decoration: none;
            font-size: 1.2em;
            font-weight: 600;
            transition: background 0.3s;
            margin-top: 15px;
        }

        .download-btn:hover {
            background: #1557b0;
        }

        .extensions-btn {
            display: inline-block;
            background: #28a745;
            color: white;
            padding: 12px 30px;
            border-radius: 6px;
            text-decoration: none;
            font-size: 1.1em;
            font-weight: 600;
            border: none;
            cursor: pointer;
            transition: all 0.3s;
            margin: 10px 0;
        }

        .extensions-btn:hover {
            background: #218838;
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }

        .extensions-btn:active {
            transform: translateY(0);
        }

        .extensions-btn.copied {
            background: #007bff;
            animation: pulse 0.3s;
        }

        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }

        .section {
            margin-bottom: 40px;
        }

        .section h2 {
            color: #1a73e8;
            font-size: 1.8em;
            margin-bottom: 20px;
            border-bottom: 2px solid #e0e0e0;
            padding-bottom: 10px;
        }

        .section h3 {
            color: #333;
            font-size: 1.3em;
            margin-top: 25px;
            margin-bottom: 15px;
        }

        .step {
            background: #f8f9fa;
            border-left: 4px solid #1a73e8;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 4px;
        }

        .step-number {
            display: inline-block;
            background: #1a73e8;
            color: white;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            text-align: center;
            line-height: 30px;
            font-weight: bold;
            margin-right: 10px;
        }

        .step-title {
            font-weight: 600;
            font-size: 1.1em;
            margin-bottom: 10px;
        }

        .step-detail {
            margin-left: 40px;
            color: #555;
        }

        code {
            background: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            color: #e83e8c;
        }

        .important {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
        }

        .tip {
            background: #d4edda;
            border-left: 4px solid #28a745;
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
        }

        details {
            margin: 20px 0;
        }

        details summary {
            padding: 10px;
            background: #f8f9fa;
            border-radius: 4px;
        }

        ul {
            margin-left: 40px;
            margin-top: 10px;
            margin-bottom: 10px;
        }

        li {
            margin-bottom: 8px;
        }

        .footer {
            background: #f8f9fa;
            padding: 20px 40px;
            text-align: center;
            color: #666;
            border-top: 1px solid #e0e0e0;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎬 NBJ Condenser Remote</h1>
            <p>AI-Powered YouTube Video Condensation</p>
            <p style="font-size: 0.9em; margin-top: 10px;">Get the <span id="browser-name">browser</span> extension</p>
        </div>

        <div class="content">
            <div class="download-section">
                <h2 style="margin: 0 0 10px 0; color: #1a73e8;">📦 Step 1: Download Extension</h2>
                <p>Click the button below to download the NBJ Condenser extension</p>
                <a href="/extension.zip" class="download-btn" download>⬇ Download Extension</a>
                <p style="margin-top: 15px; font-size: 0.9em; color: #666;">
                    File: <code>nbj-chrome-extension.zip</code> (14 KB)<br>
                    <em>Icon changes color when you're on a YouTube video page!</em>
                </p>
            </div>

            <div class="section">
                <h2>🔧 Step 2: Install in <span id="browser-name-install">Chrome</span></h2>

                <div class="step">
                    <div class="step-title">
                        <span class="step-number">1</span>
                        Open Extensions page
                    </div>
                    <div class="step-detail">
                        Click to copy the URL, then paste it into your browser's address bar:<br>
                        <button class="extensions-btn" id="copy-url-btn" onclick="copyExtensionsURL()">
                            📋 Copy <code id="extensions-url" style="background: transparent; color: white;">chrome://extensions/</code>
                        </button>
                        <div id="copy-feedback" style="display: none; color: #28a745; font-weight: 600; margin-top: 10px;">
                            ✅ Copied! Paste it in a new tab's address bar and press Enter
                        </div>
                        <p style="margin-top: 10px; font-size: 0.85em; color: #888;">
                            <em>Note: For security reasons, this page can't open the extensions page automatically</em>
                        </p>
                    </div>
                </div>

                <div class="step">
                    <div class="step-title">
                        <span class="step-number">2</span>
                        Drag and drop the ZIP file
                    </div>
                    <div class="step-detail">
                        Find <code>nbj-chrome-extension.zip</code> in your Downloads folder<br>
                        <strong>Drag it directly onto the extensions page</strong><br>
                        Chrome will automatically install it - no extraction or developer mode needed!
                        <p style="margin-top: 12px; padding: 10px; background: #e8f4f8; border-radius: 4px; border-left: 3px solid #1a73e8;">
                            <strong>💡 Pro Tip:</strong> You can drag directly from Chrome's <strong>Recent download history</strong> widget (top-right of browser)
                            without opening your file explorer!
                        </p>
                    </div>
                </div>

                <div class="tip">
                    <strong>✨ That's it!</strong> The extension should now appear in your extensions list with a blue "C" icon.
                    Chrome may show a "not from Chrome Web Store" warning - this is normal, just click "OK" or dismiss it.
                </div>

                <details style="margin-top: 20px;">
                    <summary style="cursor: pointer; font-weight: 600; color: #1a73e8;">
                        Alternative: Manual Installation (if drag-and-drop doesn't work)
                    </summary>
                    <div style="margin-top: 15px; padding: 15px; background: #f8f9fa; border-radius: 4px;">
                        <ol style="margin-left: 20px;">
                            <li>Extract the ZIP file to a folder on your computer</li>
                            <li>Enable "Developer mode" toggle (top-right corner)</li>
                            <li>Click "Load unpacked"</li>
                            <li>Select the extracted folder</li>
                        </ol>
                    </div>
                </details>
            </div>

            <div class="section">
                <h2>📌 Step 3: Pin the Extension</h2>

                <div class="step">
                    <div class="step-title">
                        <span class="step-number">1</span>
                        Click the puzzle piece icon (🧩)
                    </div>
                    <div class="step-detail">
                        Look in your browser toolbar (top-right corner, next to the address bar)
                    </div>
                </div>

                <div class="step">
                    <div class="step-title">
                        <span class="step-number">2</span>
                        Pin "NBJ Condenser Remote"
                    </div>
                    <div class="step-detail">
                        Find "NBJ Condenser Remote" in the dropdown<br>
                        Click the <strong>pin icon (📌)</strong> next to it<br>
                        The blue "C" icon will now appear in your toolbar for easy access
                    </div>
                </div>
            </div>

            <div class="section">
                <h2>🎯 Step 4: Using the Extension</h2>

                <div class="important" style="background: #e3f2fd; border-left-color: #1a73e8;">
                    <strong>💡 Smart Icon Feature:</strong> The extension icon changes color to show when it's ready to use!
                    <ul style="margin-top: 10px;">
                        <li><strong>🔵 Blue/Colored Icon:</strong> You're on a YouTube video page - click to condense!</li>
                        <li><strong>⚫ Gray Icon:</strong> Not on a YouTube video page - navigate to a video first</li>
                    </ul>
                    <p style="margin-top: 10px; margin-bottom: 0;">
                        The icon automatically updates as you browse, so you always know when you can use it.
                    </p>
                </div>

                <div class="step">
                    <div class="step-title">
                        <span class="step-number">1</span>
                        Go to YouTube
                    </div>
                    <div class="step-detail">
                        Open <code>youtube.com</code> in your browser<br>
                        Navigate to <strong>any video page</strong> (must be a video, not the homepage or search results)<br>
                        <em>Watch the icon turn blue when you're on a video page!</em>
                    </div>
                </div>

                <div class="step">
                    <div class="step-title">
                        <span class="step-number">2</span>
                        Click the NBJ Condenser icon
                    </div>
                    <div class="step-detail">
                        Click the blue "C" icon in your toolbar (or the puzzle piece icon if you didn't pin it)<br>
                        <em>The icon will only be blue/active when you're on a YouTube video page</em><br>
                        A popup will appear showing the current video
                    </div>
                </div>

                <div class="step">
                    <div class="step-title">
                        <span class="step-number">3</span>
                        Start condensing
                    </div>
                    <div class="step-detail">
                        Click the <strong>"Condense Video"</strong> button<br>
                        The extension will submit the video to the NBJ Condenser server for processing
                    </div>
                </div>

                <div class="step">
                    <div class="step-title">
                        <span class="step-number">4</span>
                        Wait for processing
                    </div>
                    <div class="step-detail">
                        The popup will show real-time progress updates every 3 seconds<br>
                        You'll see stages like "Downloading", "Transcribing", "Condensing", "Generating video"<br>
                        <strong>Processing typically takes 5-15 minutes</strong> depending on video length<br>
                        <strong>💡 Pro tip:</strong> You can close the popup and come back later - the extension remembers your job and will resume tracking when you reopen it!
                    </div>
                </div>

                <div class="step">
                    <div class="step-title">
                        <span class="step-number">5</span>
                        Watch your condensed video
                    </div>
                    <div class="step-detail">
                        When processing completes, you'll see a green "✅ Video ready!" message<br>
                        Click the <strong>"Watch Video"</strong> button<br>
                        The condensed video will open in a new tab and play automatically
                    </div>
                </div>

                <div class="important">
                    <strong>⚠️ Server Limitations:</strong>
                    <ul>
                        <li>The server processes <strong>one video at a time</strong></li>
                        <li>If someone else is using it, you'll see "Server is busy" - just wait and try again</li>
                        <li>Regular YouTube videos work best - some Shorts or restricted videos may not work</li>
                    </ul>
                </div>
            </div>

            <div class="section">
                <h2>🎨 What Does NBJ Condenser Do?</h2>

                <div class="step">
                    <div class="step-title" style="border: none;">
                        AI-Powered Condensation
                    </div>
                    <div class="step-detail">
                        NBJ Condenser uses AI to intelligently condense YouTube videos:
                        <ul>
                            <li><strong>Extracts the script</strong> from the video using speech recognition</li>
                            <li><strong>Analyzes and condenses</strong> the content using Claude AI (aggressiveness: 5/10)</li>
                            <li><strong>Generates new audio</strong> with natural text-to-speech voice</li>
                            <li><strong>Creates a slideshow</strong> using key frames from the original video</li>
                            <li><strong>Produces a final video</strong> that's typically 30-60% shorter</li>
                        </ul>
                    </div>
                </div>

                <div class="tip">
                    <strong>💡 Best for:</strong> Educational videos, tutorials, documentaries, podcasts, and long-form content.
                    Perfect for when you want the key information without watching the entire video!
                </div>
            </div>

            <div class="section">
                <h2>❓ Troubleshooting</h2>

                <h3>"Not a YouTube video page"</h3>
                <div class="step-detail">
                    Make sure you're on a <code>youtube.com/watch?v=...</code> page<br>
                    The extension only works on actual video pages, not the homepage, search results, or channel pages
                </div>

                <h3>"Connection error"</h3>
                <div class="step-detail">
                    The server may be offline or unreachable<br>
                    Contact your administrator to ensure the server and ngrok are running
                </div>

                <h3>"Server is busy"</h3>
                <div class="step-detail">
                    Another video is currently being processed<br>
                    Wait a few minutes and try again when the current job finishes
                </div>

                <h3>"Processing failed"</h3>
                <div class="step-detail">
                    Some videos can't be downloaded (age-restricted, private, removed)<br>
                    Try a different video - standard public YouTube videos work best
                </div>

                <h3>Extension didn't install</h3>
                <div class="step-detail">
                    Try the alternative manual installation method (see Step 2 for details)<br>
                    Make sure you're using Chrome or Edge (other browsers may not be compatible)<br>
                    Check that the ZIP file downloaded completely (should be 14 KB)
                </div>
            </div>
        </div>

        <div class="footer">
            <p><strong>NBJ Condenser Remote Server</strong> • Powered by Claude AI</p>
            <p style="margin-top: 10px; font-size: 0.9em;">
                Need help? Check the server logs or contact your administrator
            </p>
        </div>
    </div>

    <script>
        // Detect mobile device
        const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);

        if (isMobile) {
            // Replace entire page content with message
            document.querySelector('.container').innerHTML = `
                <div class="header">
                    <h1>🎬 NBJ Condenser Remote</h1>
                </div>
                <div class="content" style="text-align: center; padding: 60px 40px;">
                    <h2 style="font-size: 2em; color: #d32f2f; margin-bottom: 20px;">
                        Desktop Only
                    </h2>
                    <p style="font-size: 1.2em; color: #666; margin-top: 30px;">
                        This Chrome extension only works on desktop browsers (Chrome or Edge).<br>
                        Please visit this page on your computer to install.
                    </p>
                </div>
            `;
        } else {
            // Detect browser for display
            const isEdge = navigator.userAgent.indexOf('Edg') !== -1;
            const browserName = isEdge ? 'Edge' : 'Chrome';
            const extensionsURL = isEdge ? 'edge://extensions/' : 'chrome://extensions/';

            // Update browser name in page
            document.querySelectorAll('#browser-name, #browser-name-install').forEach(el => {
                el.textContent = browserName;
            });

            // Update extensions URL display
            const urlElement = document.getElementById('extensions-url');
            if (urlElement) {
                urlElement.textContent = extensionsURL;
            }
        }

        // Copy extensions URL to clipboard
        function copyExtensionsURL() {
            const isEdge = navigator.userAgent.indexOf('Edg') !== -1;
            const extensionsURL = isEdge ? 'edge://extensions/' : 'chrome://extensions/';

            navigator.clipboard.writeText(extensionsURL).then(() => {
                const feedback = document.getElementById('copy-feedback');
                const btn = document.getElementById('copy-url-btn');

                feedback.style.display = 'block';
                btn.classList.add('copied');
                btn.innerHTML = '✅ Copied to Clipboard!';

                setTimeout(() => {
                    feedback.style.display = 'none';
                    btn.classList.remove('copied');
                    btn.innerHTML = '📋 Click to Copy: <code id="extensions-url" style="background: transparent; color: white;">' + extensionsURL + '</code>';
                }, 3000);
            }).catch(err => {
                alert('Copy failed. Please manually copy this URL:\\n\\n' + extensionsURL);
            });
        }
    </script>
</body>
</html>
    '''
    return render_template_string(html)


@app.route('/extension.zip')
def download_extension():
    """Download the packaged Chrome extension."""
    # Serve the pre-packaged extension from dist/
    extension_zip = Path(__file__).parent.parent / 'dist' / 'nbj-chrome-extension.zip'

    if not extension_zip.exists():
        return jsonify({'error': 'Extension package not found'}), 404

    return send_file(
        extension_zip,
        mimetype='application/zip',
        as_attachment=True,
        download_name='nbj-chrome-extension.zip'
    )


@app.route('/api/condense', methods=['POST'])
def condense():
    """Submit a YouTube URL for processing."""
    global currently_processing

    data = request.json
    youtube_url = data.get('url')

    if not youtube_url:
        return jsonify({'error': 'Missing url parameter'}), 400

    # Check if already processing
    with current_job_lock:
        if currently_processing:
            return jsonify({
                'error': 'Server is busy processing another video',
                'current_job': currently_processing
            }), 429

        # Create job
        job_id = str(uuid.uuid4())[:8]
        job = Job(job_id, youtube_url)
        jobs[job_id] = job
        currently_processing = job_id

    # Start processing in background
    thread = threading.Thread(target=process_video, args=(job_id,))
    thread.daemon = True
    thread.start()

    return jsonify({
        'job_id': job_id,
        'status': 'queued',
        'message': 'Processing started'
    })


@app.route('/api/status/<job_id>', methods=['GET'])
def status(job_id):
    """Get status of a processing job."""
    job = jobs.get(job_id)

    if not job:
        return jsonify({'error': 'Job not found'}), 404

    response = {
        'job_id': job.id,
        'status': job.status,
        'progress': job.progress,
        'created_at': job.created_at.isoformat(),
    }

    if job.completed_at:
        response['completed_at'] = job.completed_at.isoformat()

    if job.status == 'completed':
        response['download_url'] = f"/api/download/{job.id}"

    if job.error:
        response['error'] = job.error

    return jsonify(response)


@app.route('/api/download/<job_id>', methods=['GET'])
def download(job_id):
    """Download the processed video."""
    job = jobs.get(job_id)

    if not job:
        return jsonify({'error': 'Job not found'}), 404

    if job.status != 'completed':
        return jsonify({'error': 'Video not ready yet'}), 400

    if not job.output_file or not Path(job.output_file).exists():
        return jsonify({'error': 'Output file not found'}), 404

    return send_file(
        job.output_file,
        mimetype='video/mp4',
        as_attachment=False
    )


@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """List all jobs (for debugging)."""
    return jsonify({
        'jobs': [
            {
                'job_id': job.id,
                'url': job.url,
                'status': job.status,
                'created_at': job.created_at.isoformat()
            }
            for job in jobs.values()
        ],
        'currently_processing': currently_processing
    })


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'busy': currently_processing is not None,
        'total_jobs': len(jobs)
    })


if __name__ == '__main__':
    print("=" * 60)
    print("NBJ Condenser Remote Server")
    print("=" * 60)
    print("\nServer starting on http://127.0.0.1:5000")
    print("Expose with: ngrok start nbj")
    print("\nPublic URL: https://conciser-aurora.ngrok.dev")
    print("\nEndpoints:")
    print("  GET    /start - Extension download & installation guide")
    print("  POST   /api/condense  - Submit YouTube URL")
    print("  GET    /api/status/:id - Check job status")
    print("  GET    /api/download/:id - Download video")
    print("  GET    /api/jobs - List all jobs")
    print("  GET    /health - Health check")
    print("\n👉 Share this link: https://conciser-aurora.ngrok.dev/start")
    print("\n" + "=" * 60 + "\n")

    app.run(host='0.0.0.0', port=5000, debug=False)
