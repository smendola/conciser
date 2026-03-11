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

# Initialize CLI logging for server output
from src.cli import logging as _logging  # noqa: F401

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


def fetch_channel_name(youtube_url):
    """Fetch channel name (author_name) from YouTube oEmbed API."""
    try:
        import urllib.request
        import urllib.parse
        import json

        oembed_url = f"https://www.youtube.com/oembed?url={urllib.parse.quote(youtube_url)}&format=json"
        with urllib.request.urlopen(oembed_url, timeout=5) as response:
            data = json.loads(response.read().decode())
            return data.get('author_name')
    except Exception as e:
        print(f"Failed to fetch channel name: {e}")
        return None


def is_mobile_user_agent(user_agent: str) -> bool:
    """Simple user-agent check to differentiate mobile visitors."""
    if not user_agent:
        return False
    return bool(MOBILE_USER_AGENT_PATTERN.search(user_agent))


def _get_authorized_completed_job(job_id, client_id):
    job = job_service.get_job(job_id)
    if not job:
        return None, (jsonify({'error': 'Job not found'}), 404)

    if job['client_id'] and job['client_id'] != client_id:
        return None, (jsonify({'error': 'Job not found'}), 404)

    if job['status'] != 'completed' or not job['output_file']:
        return None, (jsonify({'error': 'Job not ready'}), 400)

    return job, None


def _resolve_output_path(output_file):
    output_path = Path(output_file)
    if not output_path.is_absolute():
        output_path = Path(__file__).parent.parent / output_path
    return output_path


@app.route('/api/log', methods=['POST'])
def api_log():
    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.get_data(as_text=True)
    print(f"[API LOG] {payload}", flush=True)
    return jsonify({'ok': True})


def _render_markdown_output(job_id, client_id, output_path):
    import markdown

    md_content = output_path.read_text(encoding='utf-8')

    page_title = "Takeaways"
    lines = md_content.strip().split('\n')
    for line in lines:
        if line.startswith('# '):
            page_title = line[2:].strip()
            break

    md_content = md_content.strip()
    if md_content.startswith('# '):
        first_newline = md_content.find('\n')
        if first_newline != -1:
            md_content = md_content[first_newline + 1:].strip()
        else:
            md_content = ""

    html_content = markdown.markdown(md_content, extensions=['extra', 'codehilite'])

    return render_template(
        'takeaways.html',
        job_id=job_id,
        page_title=page_title,
        html_content=html_content,
        client_id=client_id,
    )


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
    channel_name = fetch_channel_name(youtube_url)
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
        channel_name=channel_name,
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
    channel_name = fetch_channel_name(youtube_url)
    params = {
        'top': top,
        'format_type': format_type,
        'voice': voice,
    }
    job_id = job_service.create_job(
        url=youtube_url,
        job_type='takeaways',
        title=title,
        channel_name=channel_name,
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
        open_url = f"/api/open/{job['id']}"
        if job['client_id']:
            download_url += f"?cid={quote_plus(job['client_id'])}"
            open_url += f"?cid={quote_plus(job['client_id'])}"
        response['download_url'] = download_url
        response['open_url'] = open_url

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

    job, job_error = _get_authorized_completed_job(job_id, client_id)
    if job_error:
        status_code = 400 if job_error[1] == 400 else 404
        error_message = 'Job not ready for download' if status_code == 400 else 'Job not found'
        return jsonify({'error': error_message}), status_code

    output_path = _resolve_output_path(job['output_file'])
    if not output_path.exists():
        return jsonify({'error': 'Output file not found'}), 404

    return send_file(
        output_path,
        as_attachment=True,
        download_name=output_path.name
    )


@app.route('/api/open/<job_id>', methods=['GET'])
def open_output(job_id):
    """Open the processed output in a browser-friendly viewer."""
    client_id, error_response = _client_id_response()
    if error_response:
        return error_response

    job, job_error = _get_authorized_completed_job(job_id, client_id)
    if job_error:
        status_code = 400 if job_error[1] == 400 else 404
        error_message = 'Job not ready to open' if status_code == 400 else 'Job not found'
        return jsonify({'error': error_message}), status_code

    output_path = _resolve_output_path(job['output_file'])
    if not output_path.exists():
        return jsonify({'error': 'Output file not found'}), 404

    suffix = output_path.suffix.lower()

    if suffix == '.md':
        try:
            return _render_markdown_output(job_id, client_id, output_path)
        except Exception as e:
            return jsonify({'error': f'Failed to render markdown: {str(e)}'}), 500

    if suffix not in {'.mp3', '.mp4'}:
        return jsonify({'error': f'Unsupported file type for open: {suffix or "unknown"}'}), 400

    media_kind = 'audio' if suffix == '.mp3' else 'video'
    media_url = url_for('open_output_content', job_id=job_id, cid=client_id)
    download_url = url_for('download', job_id=job_id, cid=client_id)

    return render_template(
        'media_player.html',
        job_id=job_id,
        media_kind=media_kind,
        media_url=media_url,
        download_url=download_url,
        file_name=output_path.name,
    )


@app.route('/api/open/<job_id>/content', methods=['GET'])
def open_output_content(job_id):
    """Serve processed media inline for the browser player."""
    client_id, error_response = _client_id_response()
    if error_response:
        return error_response

    job, job_error = _get_authorized_completed_job(job_id, client_id)
    if job_error:
        status_code = 400 if job_error[1] == 400 else 404
        error_message = 'Job not ready to open' if status_code == 400 else 'Job not found'
        return jsonify({'error': error_message}), status_code

    output_path = _resolve_output_path(job['output_file'])
    if not output_path.exists():
        return jsonify({'error': 'Output file not found'}), 404

    suffix = output_path.suffix.lower()
    if suffix not in {'.mp3', '.mp4'}:
        return jsonify({'error': f'Unsupported file type for open: {suffix or "unknown"}'}), 400

    mimetype = 'audio/mpeg' if suffix == '.mp3' else 'video/mp4'
    return send_file(output_path, as_attachment=False, mimetype=mimetype, download_name=output_path.name)

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
        output_format = None
        if job['output_file']:
            file_path = Path(job['output_file'])
            if not file_path.is_absolute():
                file_path = Path(__file__).parent.parent / file_path
            file_exists = file_path.exists()
            suffix = file_path.suffix.lower()
            if suffix == '.mp3':
                output_format = 'mp3'
            elif suffix == '.mp4':
                output_format = 'mp4'
            elif suffix in {'.md', '.txt'}:
                output_format = 'txt'

        jobs_list.append({
            'job_id': job['id'],
            'url': job['url'],
            'title': job.get('title'),
            'status': job['status'],
            'job_type': job['job_type'],
            'file_exists': file_exists,
            'created_at': job['created_at'],
            'output_format': output_format,
        })

    running_jobs = job_service.get_running_jobs()
    return jsonify({
        'jobs': jobs_list,
        'currently_processing': running_jobs
    })


@app.route('/api/jobs/<job_id>', methods=['DELETE'])
def delete_job(job_id):
    """Soft-delete a job. This does not delete any files."""
    client_id, error_response = _client_id_response()
    if error_response:
        return error_response

    job = job_service.get_job(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404

    if job['client_id'] and job['client_id'] != client_id:
        return jsonify({'error': 'Job not found'}), 404

    ok = job_service.store.mark_deleted(job_id)
    if not ok:
        return jsonify({'error': 'Job not found'}), 404

    return jsonify({'ok': True, 'job_id': job_id, 'status': 'deleted'})


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
    """Get available TTS voices filtered by locale, using the configured voice service."""
    locale = request.args.get('locale', 'en-US')
    settings = get_settings()

    try:
        if settings.tts_provider == 'azure' and settings.azure_speech_key and settings.azure_speech_region:
            from src.modules.azure_tts import AzureTTS
            azure = AzureTTS(settings.azure_speech_key, settings.azure_speech_region)
            all_voices = azure.list_voices(locale_filter=locale)
            filtered_voices = sorted(
                [
                    {
                        'name': v['name'],
                        'gender': v['gender'],
                        'locale': v['locale'],
                        'friendly_name': v['name'].split('-', 2)[-1]
                                                  .replace('Multilingual', '')
                                                  .replace('Expressive', '')
                                                  .replace('Turbo', '')
                                                  .replace('Neural', '')
                    }
                    for v in all_voices
                ],
                key=lambda x: x['name']
            )
        else:
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
                                                  .replace('Multilingual', '')
                                                  .replace('Expressive', '')
                                                  .replace('Neural', '')
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
    print("  GET    /api/open/<id>    - Open output in browser")
    print("  GET    /api/strategies   - Get aggressiveness strategies")
    print("  GET    /api/voices       - Get Edge TTS voices")
    print("  GET    /api/jobs         - List all jobs")
    print("  DELETE /api/jobs/<id>    - Soft-delete a job (no file deletion)")
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
