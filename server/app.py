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
from server.job_service import JobService

app = Flask(__name__)
CORS(app)  # Allow requests from Chrome extension

# Job service for concurrent processing
job_service = JobService(max_workers=3)

MOBILE_USER_AGENT_PATTERN = re.compile(r"(android|iphone|ipad|ipod|blackberry|iemobile|opera mini)", re.IGNORECASE)


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
    """Download the latest packaged Chrome extension."""
    dist_dir = Path(__file__).parent.parent / 'dist'
    files = list(dist_dir.glob('nbj-chrome-extension-*.zip'))
    if not files:
        return jsonify({'error': 'Extension package not found'}), 404

    latest_file = max(files, key=lambda p: p.stat().st_mtime)

    return send_file(
        latest_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=latest_file.name
    )


@app.route('/android.apk')
def download_android_apk():
    """Serve the latest Android APK for side-loading."""
    dist_dir = Path(__file__).parent.parent / 'dist'
    files = list(dist_dir.glob('nbj-condenser-*.apk'))
    if not files:
        return jsonify({'error': 'Android APK not found. Please download from desktop instead.'}), 404

    latest_file = max(files, key=lambda p: p.stat().st_mtime)

    return send_file(
        latest_file,
        mimetype='application/vnd.android.package-archive',
        as_attachment=True,
        download_name=latest_file.name
    )


@app.route('/api/condense', methods=['POST'])
def condense():
    """Submit a YouTube URL for processing."""
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

    # Submit to JobService
    title = fetch_video_title(youtube_url)
    params = {
        'aggressiveness': aggressiveness,
        'voice': voice,
        'speech_rate': speech_rate,
        'video_mode': video_mode,
        'prepend_intro': prepend_intro,
    }
    job_id = job_service.create_job(
        url=youtube_url,
        job_type='condense',
        title=title,
        client_id=client_id,
        params=params,
    )
    return jsonify({
        'job_id': job_id,
        'status': 'queued',
        'message': 'Processing started'
    })


@app.route('/api/takeaways', methods=['POST'])
def takeaways():
    """Extract takeaways from a YouTube video."""
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

    # Submit to JobService
    title = fetch_video_title(youtube_url)
    params = {
        'top': top,
        'format_type': format_type,
        'voice': voice,
    }
    job_id = job_service.create_job(
        url=youtube_url,
        job_type='takeaways',
        title=title,
        client_id=client_id,
        params=params,
    )
    return jsonify({
        'job_id': job_id,
        'status': 'queued',
        'message': 'Takeaways extraction started'
    })


@app.route('/api/status/<job_id>', methods=['GET'])
def status(job_id):
    """Get status of a processing job."""
    client_id, error_response = _client_id_response()
    if error_response:
        return error_response

    # Query JobService
    job = job_service.get_job(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404

    if job['client_id'] and job['client_id'] != client_id:
        return jsonify({'error': 'Job not found'}), 404

    response = {
        'job_id': job['id'],
        'status': job['status'],
        'progress': job.get('progress') or None,
        'created_at': job['created_at'],
    }

    if job['completed_at']:
        response['completed_at'] = job['completed_at']

    if job['status'] == 'completed' and job['output_file']:
        download_url = f"/api/download/{job['id']}"
        if job['client_id']:
            download_url += f"?cid={quote_plus(job['client_id'])}"
        response['download_url'] = download_url

    if job['error']:
        response['error'] = job['error']

    # Add queue position if queued
    if job['status'] == 'queued':
        position = job_service.get_queue_position(job_id)
        if position is not None:
            response['queue_position'] = position

    return jsonify(response)


@app.route('/api/download/<job_id>', methods=['GET'])
def download(job_id):
    """Download the processed output file."""
    client_id, error_response = _client_id_response()
    if error_response:
        return error_response

    # Query JobService
    job = job_service.get_job(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404

    if job['client_id'] and job['client_id'] != client_id:
        return jsonify({'error': 'Job not found'}), 404

    if job['status'] != 'completed' or not job['output_file']:
        return jsonify({'error': 'Job not ready for download'}), 400

    output_path = Path(job['output_file'])
    if not output_path.is_absolute():
        output_path = Path(__file__).parent.parent / output_path
    
    if not output_path.exists():
        return jsonify({'error': 'Output file not found'}), 404

    # Check if download is forced (for markdown files)
    force_download = request.args.get('download') == '1'
    
    # If it's a markdown file and not forcing download, render as HTML
    if output_path.suffix == '.md' and not force_download:
        try:
            import markdown
            
            # Read the markdown content
            md_content = output_path.read_text(encoding='utf-8')
            
            # Extract title from markdown content
            page_title = "Takeaways"
            lines = md_content.strip().split('\n')
            for line in lines:
                if line.startswith('# '):
                    page_title = line[2:].strip()
                    break
            
            # Remove the title line from markdown content to prevent duplicate
            md_content = md_content.strip()
            if md_content.startswith('# '):
                first_newline = md_content.find('\n')
                if first_newline != -1:
                    md_content = md_content[first_newline + 1:].strip()
                else:
                    md_content = ""  # Only title was in the file
            
            # Convert to HTML
            html_content = markdown.markdown(md_content, extensions=['extra', 'codehilite'])
            
            # Render using the existing template
            return render_template('takeaways.html', 
                                 job_id=job_id, 
                                 page_title=page_title,
                                 html_content=html_content,
                                 client_id=client_id)
            
        except Exception as e:
            return jsonify({'error': f'Failed to render markdown: {str(e)}'}), 500
    
    # For non-markdown files (audio, video), serve as attachment
    return send_file(
        output_path,
        as_attachment=True,
        download_name=output_path.name
    )

@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """List all jobs (for debugging)."""
    client_id, error_response = _client_id_response()
    if error_response:
        return error_response

    jobs_list = []
    for job in job_service.list_jobs(client_id=client_id):
        # Check if output file exists
        file_exists = False
        if job['output_file']:
            file_path = Path(job['output_file'])
            if not file_path.is_absolute():
                file_path = Path(__file__).parent.parent / file_path
            file_exists = file_path.exists()

        jobs_list.append({
            'job_id': job['id'],
            'url': job['url'],
            'title': job.get('title'),
            'status': job['status'],
            'job_type': job['job_type'],
            'file_exists': file_exists,
            'created_at': job['created_at']
        })

    running_jobs = job_service.get_running_jobs()
    return jsonify({
        'jobs': jobs_list,
        'currently_processing': running_jobs
    })


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    running_jobs = job_service.get_running_jobs()
    return jsonify({
        'status': 'ok',
        'busy': len(running_jobs) > 0,
        'running_jobs': len(running_jobs),
        'max_workers': job_service.max_workers
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

    # Start job service worker loop
    job_service.start()
    import threading
    worker_thread = threading.Thread(target=job_service.start_worker_loop, daemon=True)
    worker_thread.start()
    print("Concurrent mode enabled with JobService")

    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=True)
