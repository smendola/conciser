"""
NBJ Condenser Server

Simple HTTP server that accepts YouTube URLs and processes them with nbj.
"""

import os
import re
import sys
import uuid
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, send_file, render_template, send_from_directory, redirect, url_for
from urllib.parse import quote_plus
from flask_cors import CORS

# Add parent directory to path to import nbj modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings
from src.pipeline import CondenserPipeline
from src.modules.edge_tts import EdgeTTS
from src.utils.prompt_templates import get_strategy_description

app = Flask(__name__)
CORS(app)  # Allow requests from Chrome extension

# In-memory job storage (restored from disk on startup)
jobs = {}
current_job_lock = threading.Lock()
currently_processing = None

MOBILE_USER_AGENT_PATTERN = re.compile(r"(android|iphone|ipad|ipod|blackberry|iemobile|opera mini)", re.IGNORECASE)


def restore_jobs_from_disk():
    """Restore completed jobs from output/jobs/ directory on server startup."""
    settings = get_settings()
    jobs_dir = settings.output_dir / 'jobs'

    if not jobs_dir.exists():
        print("No jobs directory found, starting fresh")
        return

    restored_count = 0
    for file_path in jobs_dir.glob('*'):
        if file_path.is_file():
            job_id = file_path.stem
            ext = file_path.suffix.lower()

            # Determine job type from extension
            if ext == '.md':
                job_type = 'takeaways'
            elif ext in ['.mp4', '.mp3']:
                job_type = 'condense'
            else:
                continue  # Skip unknown file types

            # Create a completed job entry
            youtube_url = '[restored]'
            title = None
            video_id_match = re.search(r"(?:^|_)vid-([a-zA-Z0-9_-]{11})(?:_|$)", file_path.stem)
            if video_id_match:
                video_id = video_id_match.group(1)
                youtube_url = f"https://www.youtube.com/watch?v={video_id}"
                title = fetch_video_title(youtube_url)

            job = Job(job_id, youtube_url=youtube_url, job_type=job_type, title=title)
            job.status = 'completed'
            job.output_file = str(file_path)
            job.created_at = datetime.fromtimestamp(file_path.stat().st_mtime)
            job.completed_at = job.created_at

            jobs[job_id] = job
            restored_count += 1

    print(f"Restored {restored_count} completed jobs from disk")


class Job:
    def __init__(self, job_id, youtube_url, job_type='condense', title=None, client_id=None):
        self.id = job_id
        self.url = youtube_url
        self.title = title  # Video title
        self.job_type = job_type  # 'condense' or 'takeaways'
        self.status = "queued"  # queued, processing, completed, error
        self.progress = ""
        self.output_file = None
        self.error = None
        self.created_at = datetime.now()
        self.completed_at = None
        self.client_id = client_id


def _extract_client_id():
    client_id = request.args.get('cid')
    if client_id:
        return client_id.strip()

    header_value = request.headers.get('X-User-Id') or request.headers.get('x-user-id')
    if header_value:
        return header_value.strip()

    return None


def _client_id_response(optional=False):
    client_id = _extract_client_id()
    if client_id:
        return client_id, None
    if optional:
        return None, None
    return None, (jsonify({'error': 'Missing client identifier'}), 401)


def fetch_video_title(youtube_url):
    """Fetch video title from YouTube oEmbed API."""
    try:
        import urllib.request
        import urllib.parse
        import json

        oembed_url = f"https://www.youtube.com/oembed?url={urllib.parse.quote(youtube_url)}&format=json"
        with urllib.request.urlopen(oembed_url, timeout=5) as response:
            data = json.loads(response.read().decode())
            return data.get('title')
    except Exception as e:
        print(f"Failed to fetch video title: {e}")
        return None


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
                'resume': False
            }
            print(f"\033[35mpipeline.run({params})\033[0m")

        # Run with job parameters (use stored values or defaults)
        video_mode = getattr(job, 'video_mode', 'slideshow')

        # Output to: output/jobs/{job_id}.{ext}
        jobs_dir = settings.output_dir / 'jobs'
        jobs_dir.mkdir(parents=True, exist_ok=True)

        # Determine output file extension
        output_ext = 'mp3' if video_mode == 'audio_only' else 'mp4'
        video_id = None
        try:
            from src.pipeline import CondenserPipeline as _CP
            video_id = _CP._extract_video_id(job.url)  # type: ignore[attr-defined]
        except Exception:
            video_id = None

        suffix = f"_vid-{video_id}" if video_id else ""
        output_path = jobs_dir / f"{job_id}{suffix}.{output_ext}"

        result = pipeline.run(
            video_url=job.url,
            aggressiveness=getattr(job, 'aggressiveness', 5),
            output_path=output_path,
            quality="1080p",
            video_gen_mode=video_mode,
            tts_provider="edge",
            voice_id=getattr(job, 'voice', 'en-GB-RyanNeural'),
            tts_rate=getattr(job, 'speech_rate', '+0%'),
            skip_voice_clone=True,
            progress_callback=progress_callback,
            resume=False,
            prepend_intro=getattr(job, 'prepend_intro', False)
        )

        job.output_file = str(output_path)
        job.status = "completed"
        job.completed_at = datetime.now()
        print(f"[{job_id}] Completed: {job.output_file}")

    except Exception as e:
        job = jobs[job_id]
        job.status = "error"
        job.error = str(e)
        job.progress = ""
        job.completed_at = datetime.now()
        print(f"[{job_id}] Error: {e}")

    finally:
        with current_job_lock:
            currently_processing = None


# Restore jobs on startup (after Job class is defined)
restore_jobs_from_disk()


def is_mobile_user_agent(user_agent: str) -> bool:
    """Simple user-agent check to differentiate mobile visitors."""
    if not user_agent:
        return False
    return bool(MOBILE_USER_AGENT_PATTERN.search(user_agent))


@app.route('/start')
def start_page():
    """Landing page for extension (desktop) or Android app (mobile)."""
    user_agent = request.headers.get('User-Agent', '')
    template = 'start_mobile.html' if is_mobile_user_agent(user_agent) else 'start.html'
    return render_template(template)


@app.route('/')
def root_redirect():
    """Alias root URL to the start page."""
    return redirect(url_for('start_page'))


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


@app.route('/android.apk')
def download_android_apk():
    """Serve the latest Android APK for side-loading."""
    apk_path = Path(__file__).parent.parent / 'dist' / 'nbj-condenser.apk'

    if not apk_path.exists():
        return jsonify({'error': 'Android APK not found. Please download from desktop instead.'}), 404

    return send_file(
        apk_path,
        mimetype='application/vnd.android.package-archive',
        as_attachment=True,
        download_name='nbj-condenser.apk'
    )


@app.route('/api/condense', methods=['POST'])
def condense():
    """Submit a YouTube URL for processing."""
    global currently_processing

    client_id, error_response = _client_id_response()
    if error_response:
        return error_response

    data = request.json
    youtube_url = data.get('url')

    if not youtube_url:
        return jsonify({'error': 'Missing url parameter'}), 400

    # Get optional parameters (with defaults)
    aggressiveness = data.get('aggressiveness', 5)
    voice = data.get('voice', 'en-GB-RyanNeural')
    speech_rate = data.get('speech_rate', '+0%')  # Default to 1.0x
    video_mode = data.get('video_mode', 'slideshow')  # slideshow, static, audio_only
    prepend_intro = bool(data.get('prepend_intro', False))

    # Log all received parameters
    print(f"\n{'='*60}")
    print(f"NEW CONDENSE REQUEST")
    print(f"{'='*60}")
    print(f"URL: {youtube_url}")
    print(f"Aggressiveness: {aggressiveness}/10")
    print(f"Voice: {voice}")
    print(f"Speech Rate: {speech_rate}")
    print(f"Video Mode: {video_mode}")
    print(f"Prepend Intro: {prepend_intro}")
    print(f"{'='*60}\n")

    # Validate aggressiveness
    if not isinstance(aggressiveness, int) or aggressiveness < 1 or aggressiveness > 10:
        return jsonify({'error': 'aggressiveness must be between 1 and 10'}), 400

    # Check if already processing
    with current_job_lock:
        if currently_processing:
            return jsonify({
                'error': 'Server is busy processing another video',
                'current_job': currently_processing
            }), 429

        # Create job and store parameters
        job_id = str(uuid.uuid4())[:8]
        title = fetch_video_title(youtube_url)
        job = Job(job_id, youtube_url, job_type='condense', title=title, client_id=client_id)
        job.aggressiveness = aggressiveness
        job.voice = voice
        job.speech_rate = speech_rate
        job.video_mode = video_mode
        job.prepend_intro = prepend_intro
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


@app.route('/api/takeaways', methods=['POST'])
def takeaways():
    """Extract takeaways from a YouTube video."""
    global currently_processing

    client_id, error_response = _client_id_response()
    if error_response:
        return error_response

    data = request.json
    youtube_url = data.get('url')

    if not youtube_url:
        return jsonify({'error': 'Missing url parameter'}), 400

    # Get optional parameters
    top = data.get('top')  # None for auto, or int (3, 5, 10, etc.)
    format_type = data.get('format', 'text')  # text or audio
    voice = data.get('voice', 'en-GB-RyanNeural') if format_type == 'audio' else None

    # Log all received parameters
    print(f"\n{'='*60}")
    print(f"NEW TAKEAWAYS REQUEST")
    print(f"{'='*60}")
    print(f"URL: {youtube_url}")
    print(f"Top: {top if top else 'auto'}")
    print(f"Format: {format_type}")
    if voice:
        print(f"Voice: {voice}")
    print(f"{'='*60}\n")

    # Check if already processing (takeaways can run concurrently with condense in the CLI,
    # but for simplicity in the server, we'll use the same lock)
    with current_job_lock:
        if currently_processing:
            return jsonify({
                'error': 'Server is busy processing another job',
                'current_job': currently_processing
            }), 429

        # Create job
        job_id = str(uuid.uuid4())[:8]
        title = fetch_video_title(youtube_url)
        job = Job(job_id, youtube_url, job_type='takeaways', title=title, client_id=client_id)
        job.top = top
        job.format_type = format_type
        job.voice = voice
        job.progress = "[init] Queued takeaways extraction"
        jobs[job_id] = job
        currently_processing = job_id

    # Start processing in background
    thread = threading.Thread(target=process_takeaways, args=(job_id,))
    thread.daemon = True
    thread.start()

    return jsonify({
        'job_id': job_id,
        'status': 'queued',
        'message': 'Takeaways extraction started'
    })


def process_takeaways(job_id):
    """Process takeaways extraction in background thread."""
    global currently_processing

    try:
        job = jobs[job_id]
        job.status = "processing"
        job.progress = "[setup] Preparing takeaways job"

        # Use takeaways CLI command via subprocess
        from pathlib import Path

        settings = get_settings()
        temp_dir = settings.temp_dir

        # Build command (use nbj command directly instead of python -m)
        # Output to: output/jobs/{job_id}.{ext}
        settings = get_settings()
        jobs_dir = settings.output_dir / 'jobs'
        jobs_dir.mkdir(parents=True, exist_ok=True)

        # Determine output file extension
        output_ext = 'mp3' if job.format_type == 'audio' else 'md'
        video_id = None
        try:
            from src.pipeline import CondenserPipeline as _CP
            video_id = _CP._extract_video_id(job.url)  # type: ignore[attr-defined]
        except Exception:
            video_id = None

        suffix = f"_vid-{video_id}" if video_id else ""
        output_path = jobs_dir / f"{job_id}{suffix}.{output_ext}"

        cmd = [
            'nbj',
            'takeaways', job.url,
            '--format', job.format_type,
            '--output', str(output_path.with_suffix(''))  # nbj adds extension
        ]

        if job.top:
            cmd.extend(['--top', str(job.top)])

        if job.voice:
            cmd.extend(['--voice', job.voice])

        # Run command (stream output so progress updates are visible while running)
        job.progress = "[FETCH] Starting takeaways job"
        print(f"[{job_id}] Running: {' '.join(cmd)}")

        stage_line_re = re.compile(r"^\[(?P<stage>[A-Z_]+)\]\s*(?P<message>.*)$")
        stderr_lines = []

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=Path(__file__).parent.parent,
        )

        assert proc.stdout is not None
        assert proc.stderr is not None

        def _drain_stderr():
            for line in proc.stderr:
                line = line.rstrip("\n")
                if line:
                    stderr_lines.append(line)
                    print(f"[{job_id}] STDERR: {line}")

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        for raw_line in proc.stdout:
            line = raw_line.rstrip("\n")
            if not line:
                continue

            print(f"[{job_id}] STDOUT: {line}")
            m = stage_line_re.match(line)
            if m:
                progress_callback(m.group('stage'), m.group('message'))

        return_code = proc.wait()
        stderr_thread.join(timeout=1)

        if return_code != 0:
            stderr_text = "\n".join(stderr_lines).strip()
            raise RuntimeError(
                f"Takeaways extraction failed (exit={return_code}): {stderr_text or 'No stderr'}"
            )

        # Output file should be at the path we specified: output/jobs/{job_id}.{ext}
        if not output_path.exists():
            raise RuntimeError(f"Takeaways file not found at expected location: {output_path}")

        job.output_file = str(output_path)
        job.progress = "[FINALIZE] Takeaways ready"

        job.status = "completed"
        job.completed_at = datetime.now()
        print(f"[{job_id}] Completed: {job.output_file}")

    except Exception as e:
        job = jobs[job_id]
        job.status = "error"
        job.error = str(e)
        job.progress = ""
        job.completed_at = datetime.now()
        print(f"[{job_id}] Error: {e}")

    finally:
        with current_job_lock:
            currently_processing = None


@app.route('/api/status/<job_id>', methods=['GET'])
def status(job_id):
    """Get status of a processing job."""
    client_id, error_response = _client_id_response()
    if error_response:
        return error_response

    job = jobs.get(job_id)

    if not job:
        return jsonify({'error': 'Job not found'}), 404

    if job.client_id and job.client_id != client_id:
        return jsonify({'error': 'Job not found'}), 404

    response = {
        'job_id': job.id,
        'status': job.status,
        'progress': job.progress or None,
        'created_at': job.created_at.isoformat(),
    }

    if job.completed_at:
        response['completed_at'] = job.completed_at.isoformat()

    if job.status == 'completed':
        download_url = f"/api/download/{job.id}"
        if job.client_id:
            download_url += f"?cid={quote_plus(job.client_id)}"
        response['download_url'] = download_url

    if job.error:
        response['error'] = job.error

    return jsonify(response)


@app.route('/api/download/<job_id>', methods=['GET'])
def download(job_id):
    """Download the processed output file."""
    client_id, error_response = _client_id_response()
    if error_response:
        return error_response

    job = jobs.get(job_id)

    if not job:
        return jsonify({'error': 'Job not found'}), 404

    if job.status != 'completed':
        return jsonify({'error': 'File not ready yet'}), 400

    if job.client_id and job.client_id != client_id:
        return jsonify({'error': 'Job not found'}), 404

    if not job.output_file or not Path(job.output_file).exists():
        return jsonify({'error': 'Output file not found'}), 404

    # Detect file type and set appropriate MIME type
    # Convert to absolute path to ensure Flask resolves it correctly
    file_path = Path(job.output_file)
    if not file_path.is_absolute():
        # If somehow stored as relative, make it absolute from project root
        file_path = Path(__file__).parent.parent / file_path

    # For markdown files, render as HTML
    if file_path.suffix.lower() == '.md':
        import markdown
        import re

        # Read markdown content
        md_content = file_path.read_text(encoding='utf-8')

        # Extract first H1 heading for page title (e.g., "# Key Takeaways: Video Title")
        # Then remove it from the content to avoid duplication
        page_title = "🎯 Key Takeaways"
        title_match = re.match(r'^#\s+(.+?)$', md_content, re.MULTILINE)
        if title_match:
            page_title = "🎯 " + title_match.group(1)
            # Remove the first H1 from content
            md_content = re.sub(r'^#\s+.+?$', '', md_content, count=1, flags=re.MULTILINE).lstrip()

        # Convert to HTML
        html_content = markdown.markdown(md_content, extensions=['extra', 'nl2br'])
        return render_template(
            'takeaways.html',
            page_title=page_title,
            job_id=job_id,
            html_content=html_content,
        )

    # For audio/video files, send directly
    elif file_path.suffix.lower() == '.mp3':
        mimetype = 'audio/mpeg'
    else:
        mimetype = 'video/mp4'

    return send_file(
        str(file_path.absolute()),
        mimetype=mimetype,
        as_attachment=False
    )


@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """List all jobs (for debugging)."""
    client_id, error_response = _client_id_response()
    if error_response:
        return error_response

    jobs_list = []
    for job in jobs.values():
        if job.client_id and job.client_id != client_id:
            continue

        # Check if output file exists
        file_exists = False
        if job.output_file:
            file_path = Path(job.output_file)
            if not file_path.is_absolute():
                file_path = Path(__file__).parent.parent / file_path
            file_exists = file_path.exists()

        # Best-effort title fill-in (helps Chrome extension recent jobs list)
        if not getattr(job, 'title', None):
            derived_url = None

            if getattr(job, 'url', None) and job.url != '[restored]':
                derived_url = job.url
            else:
                output_file = getattr(job, 'output_file', None)
                if output_file:
                    stem = Path(output_file).stem
                    video_id_match = re.search(r"(?:^|_)vid-([a-zA-Z0-9_-]{11})(?:_|$)", stem)
                    if video_id_match:
                        derived_url = f"https://www.youtube.com/watch?v={video_id_match.group(1)}"
                        job.url = derived_url

            if derived_url:
                title = fetch_video_title(derived_url)
                if title:
                    job.title = title

        jobs_list.append({
            'job_id': job.id,
            'url': job.url,
            'title': getattr(job, 'title', None),
            'status': job.status,
            'job_type': job.job_type,
            'file_exists': file_exists,
            'created_at': job.created_at.isoformat()
        })

    return jsonify({
        'jobs': jobs_list,
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


@app.route('/api/strategies', methods=['GET'])
def get_strategies():
    """Get condensation aggressiveness strategies."""
    strategies = []
    for level in range(1, 11):
        description = get_strategy_description(level)
        strategies.append({
            'level': level,
            'description': description
        })

    return jsonify({'strategies': strategies})


@app.route('/api/voices', methods=['GET'])
def get_voices():
    """Get available Edge TTS voices filtered by user locale."""
    locale = request.args.get('locale', 'en-US')

    try:
        edge_tts = EdgeTTS()
        all_voices = edge_tts.list_voices()

        # Filter voices by locale prefix (e.g., 'en' matches 'en-US', 'en-GB', etc.)
        filtered_voices = sorted(
            [
                {
                    'name': v['name'],
                    'gender': v['gender'],
                    'locale': v['locale'],
                    'friendly_name': v['name'].split('-', 2)[-1]
                                              .replace(r"Multilingual", "")
                                              .replace(r"Expressive", "")
                                              .replace(r"Neural", '')
                }
                for v in all_voices
                if v['locale'].startswith(locale)
            ],
            key=lambda x: x['name']
        )
        return jsonify({'voices': filtered_voices})
    except Exception as e:
        logger.error(f"Failed to fetch voices: {e}")
        return jsonify({'error': 'Failed to fetch voices', 'voices': []}), 500


def _print_startup_banner():
    print("=" * 60)
    print("NBJ Condenser Server")
    print("=" * 60)
    print("\nServer starting on http://127.0.0.1:5000")
    # print("\nPublic URL: http://conciser.603apps.net")
    print("\nEndpoints:")
    print("  GET    /start            - Extension download & installation guide")
    print("  GET    /extension.zip    - Download Chrome extension bundle")
    print("  GET    /android.apk      - Download Android APK")
    print("  POST   /api/condense     - Submit YouTube URL for condensation")
    print("  POST   /api/takeaways    - Extract key takeaways from video")
    print("  GET    /api/status/<id>  - Check job status")
    print("  GET    /api/download/<id>- Download output file")
    print("  GET    /api/strategies   - Get aggressiveness strategies")
    print("  GET    /api/voices       - Get Edge TTS voices")
    print("  GET    /api/jobs         - List all jobs")
    print("  GET    /health           - Health check")
    # print("\n👉 Share this link: http://conciser.603apps.net/start")
    print("\n" + "=" * 60 + "\n")


if __name__ == '__main__':
    # Avoid printing twice when Werkzeug reloads the dev server
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        _print_startup_banner()

    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=True)
