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
import yaml
from datetime import datetime
from flask import Flask, request, jsonify, send_file, render_template, send_from_directory, redirect, url_for, Response
from urllib.parse import quote_plus
from flask_cors import CORS
import requests

from src.utils.project_root import get_project_root

# Add project root to path to import nbj modules (independent of CWD)
sys.path.insert(0, str(get_project_root()))

# Initialize CLI logging for server output
os.environ.setdefault('NBJ_LOG_STREAM', '0')
from src.cli import logging as _logging  # noqa: F401

logger = _logging.logger

from src.config import get_settings
from src.pipeline import CondenserPipeline
from src.modules.edge_tts import EdgeTTS
from src.utils.prompt_templates import get_strategy_description
from server.job_service import JobService

app = Flask(__name__)
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "X-User-Id"],
        "expose_headers": ["Content-Type"],
        "supports_credentials": False
    }
})  # Allow requests from Chrome extension and other origins

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
        output_path = get_project_root() / output_path
    return output_path


def _youtube_thumbnail_url(youtube_url: str) -> str | None:
    try:
        import re
        # Bare video ID (11 chars, YouTube-legal characters)
        if re.fullmatch(r'[a-zA-Z0-9_-]{11}', youtube_url):
            video_id = youtube_url
        else:
            patterns = [
                r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})',
                r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})',
            ]
            video_id = None
            for pattern in patterns:
                match = re.search(pattern, youtube_url)
                if match:
                    video_id = match.group(1)
                    break
    except Exception:
        return None

    if not video_id:
        return None
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def _cover_path_for_output(output_path: Path) -> Path:
    return output_path.with_suffix('.jpg')


@app.route('/api/yt_thumb/<video_id>')
def youtube_thumbnail(video_id: str):
    """Proxy a YouTube thumbnail image so the player reliably shows a real thumbnail."""
    if not re.fullmatch(r'[a-zA-Z0-9_-]{11}', video_id or ''):
        return jsonify({'error': 'Invalid video id'}), 400

    quality = (request.args.get('q') or 'hq').strip().lower()
    if quality not in {'max', 'hq', 'mq', 'sd', 'default'}:
        quality = 'hq'

    quality_to_file = {
        'max': 'maxresdefault.jpg',
        'hq': 'hqdefault.jpg',
        'mq': 'mqdefault.jpg',
        'sd': 'sddefault.jpg',
        'default': 'default.jpg',
    }

    import urllib.request

    last_err = None
    for q in (quality, 'hq', 'mq', 'default'):
        remote_url = f"https://i.ytimg.com/vi/{video_id}/{quality_to_file[q]}"
        try:
            req = urllib.request.Request(
                remote_url,
                headers={
                    'User-Agent': 'Mozilla/5.0',
                    'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
                },
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                body = resp.read()

            # Some missing thumbnails return HTML or very small placeholder-like responses.
            if not body or len(body) < 200:
                continue
            ct = resp.headers.get('Content-Type', '')
            if ct and not ct.startswith('image/'):
                continue

            return app.response_class(body, mimetype=ct or 'image/jpeg')
        except Exception as e:
            last_err = e
            continue

    return jsonify({'error': f'Failed to fetch thumbnail: {last_err}'}), 502


@app.route('/api/log', methods=['POST'])
def api_log():
    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.get_data(as_text=True)
    logger.info(f"[API_LOG] {payload}")
    return jsonify({'ok': True})


def _job_type_to_type(job_type: str) -> str:
    jt = (job_type or '').strip().lower()
    if jt in {'condense', 'takeaways'}:
        return jt
    return jt


def _artifact_kind_from_suffix(suffix: str) -> str:
    s = (suffix or '').lower()
    if s == '.mp4':
        return 'video'
    if s == '.mp3':
        return 'audio'
    if s in {'.jpg', '.jpeg'}:
        return 'image'
    if s in {'.md', '.txt'}:
        return 'text'
    return 'file'


def _artifact_mime_from_suffix(suffix: str) -> str:
    s = (suffix or '').lower()
    if s == '.mp4':
        return 'video/mp4'
    if s == '.mp3':
        return 'audio/mpeg'
    if s in {'.jpg', '.jpeg'}:
        return 'image/jpeg'
    if s == '.md':
        return 'text/markdown'
    if s == '.txt':
        return 'text/plain'
    return 'application/octet-stream'


def _expected_artifacts_for_job(job: dict) -> list:
    """Return ordered list of (artifact_name, ext) tuples the job should have produced.

    Files are named {job_id}_{artifact_name}.{ext} on disk.
    The first entry is the primary artifact (the one stored in output_file).
    """
    jt = _job_type_to_type(job.get('job_type'))
    params = job.get('params') or {}

    if jt == 'takeaways':
        format_type = (params.get('format_type') or 'text').strip().lower()
        if format_type == 'audio':
            return [('takeaways', 'mp3')]
        return [('takeaways', 'md')]

    # condense
    video_mode = (params.get('video_mode') or 'slideshow').strip().lower()
    if video_mode == 'text':
        return [('condensed_script', 'md')]
    if video_mode == 'audio_only':
        return [('audio', 'mp3'), ('condensed_script', 'md')]
    # slideshow (and any other video mode)
    return [('slideshow', 'mp4'), ('audio', 'mp3'), ('condensed_script', 'md')]


def _primary_artifact_for_job(job: dict) -> tuple:
    """Return (artifact_name, ext) for the primary artifact."""
    return _expected_artifacts_for_job(job)[0]


def _artifact_ext_for_output_path(output_path: Path) -> str:
    return (output_path.suffix or '').lstrip('.').lower()


def _artifact_render_ext_for_output_path(output_path: Path) -> str:
    """Render URLs always end in .html for now."""
    return 'html'


def _job_repr(job: dict) -> dict:
    params = job.get('params') or {}
    rep = {
        'id': job.get('id'),
        'type': _job_type_to_type(job.get('job_type')),
        'url': job.get('url'),
        'title': job.get('title'),
        'status': job.get('status'),
        'progress': job.get('progress') or None,
        'params': params,
        'error': job.get('error') or None,
        'created_at': job.get('created_at'),
        'completed_at': job.get('completed_at') or None,
    }
    if rep['status'] == 'queued':
        pos = job_service.get_queue_position(job.get('id'))
        if pos is not None:
            rep['queue_position'] = pos
    return rep


def _artifact_repr(job: dict, artifact_name: str, artifact_path: Path) -> dict:
    raw_ext = _artifact_ext_for_output_path(artifact_path)
    render_ext = _artifact_render_ext_for_output_path(artifact_path)

    return {
        'name': artifact_name,
        'ext': raw_ext,
        'kind': _artifact_kind_from_suffix(artifact_path.suffix),
        'mime': _artifact_mime_from_suffix(artifact_path.suffix),
        'filename': artifact_path.name,
        'raw_url': url_for('raw_artifact', job_id=job.get('id'), artifact_name=artifact_name, ext=raw_ext, cid=job.get('client_id')),
        'render_url': url_for('render_artifact', job_id=job.get('id'), artifact_name=artifact_name, ext=render_ext, cid=job.get('client_id')),
    }


def _thumbnail_artifact_repr(job: dict) -> dict:
    return {
        'name': 'thumbnail',
        'ext': 'jpg',
        'kind': 'image',
        'mime': 'image/jpeg',
        'filename': 'thumbnail.jpg',
        'raw_url': url_for('raw_thumbnail', job_id=job.get('id'), cid=job.get('client_id')),
        'render_url': None,
    }


def _render_markdown_output(job_id, client_id, output_path, youtube_url=None, channel_name=None, template='takeaways.html'):
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
        template,
        job_id=job_id,
        page_title=page_title,
        html_content=html_content,
        client_id=client_id,
        youtube_url=youtube_url,
        channel_name=channel_name,
    )


@app.route('/api/jobs', methods=['POST'])
def api_create_job():
    client_id, error_response = _client_id_response()
    if error_response:
        return error_response

    active = job_service.get_active_job_for_client(client_id)
    if active:
        return jsonify({
            'error': 'Client already has an active job. Please wait for it to finish or cancel it before submitting a new one.',
            'active_job': {
                'id': active.get('id'),
                'status': active.get('status'),
                'type': _job_type_to_type(active.get('job_type')),
                'created_at': active.get('created_at'),
            },
        }), 429

    data = request.get_json(force=True, silent=True) or {}
    job_type = (data.get('type') or '').strip().lower()
    youtube_url = data.get('url')
    params = data.get('params') or {}

    if job_type not in {'condense', 'takeaways'}:
        return jsonify({'error': 'Invalid type'}), 400
    if not youtube_url:
        return jsonify({'error': 'Missing url parameter'}), 400

    title = fetch_video_title(youtube_url)
    channel_name = fetch_channel_name(youtube_url)

    job_id = job_service.create_job(
        url=youtube_url,
        job_type=job_type,
        title=title,
        channel_name=channel_name,
        client_id=client_id,
        params=params,
    )

    resp = jsonify({'id': job_id, 'status': 'queued', 'type': job_type, 'created_at': datetime.utcnow().isoformat() + 'Z'})
    resp.status_code = 201
    resp.headers['Location'] = f"/api/jobs/{job_id}"
    return resp


@app.route('/api/jobs', methods=['GET'])
def api_list_jobs():
    client_id, error_response = _client_id_response()
    if error_response:
        return error_response

    status = request.args.get('status')
    job_type = request.args.get('type')
    limit = request.args.get('limit')
    limit_int = None
    if limit:
        try:
            limit_int = int(limit)
        except Exception:
            return jsonify({'error': 'Invalid limit'}), 400

    jobs = job_service.list_jobs(client_id=client_id, status=status, limit=limit_int)
    if job_type:
        jt = job_type.strip().lower()
        jobs = [j for j in jobs if _job_type_to_type(j.get('job_type')) == jt]

    return jsonify({'jobs': [_job_repr(j) for j in jobs]})


@app.route('/api/jobs/<job_id>', methods=['GET'])
def api_get_job(job_id: str):
    client_id, error_response = _client_id_response()
    if error_response:
        return error_response

    job = job_service.get_job(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    if job.get('client_id') and job.get('client_id') != client_id:
        return jsonify({'error': 'Job not found'}), 404

    return jsonify(_job_repr(job))


@app.route('/api/jobs/<job_id>/stream', methods=['GET'])
def api_stream_job(job_id: str):
    """Server-Sent Events endpoint for real-time job status updates."""
    client_id, error_response = _client_id_response()
    if error_response:
        return error_response

    job = job_service.get_job(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    if job.get('client_id') and job.get('client_id') != client_id:
        return jsonify({'error': 'Job not found'}), 404

    def generate():
        import time
        import json

        # Send initial status immediately
        job_data = job_service.get_job(job_id)
        if job_data:
            yield f"data: {json.dumps(_job_repr(job_data))}\n\n"

        # Poll for updates until job is completed or errored
        while True:
            time.sleep(1)  # Check every second

            job_data = job_service.get_job(job_id)
            if not job_data:
                # Job was deleted
                yield f"data: {json.dumps({'status': 'error', 'error': 'Job not found'})}\n\n"
                break

            status = job_data.get('status')
            yield f"data: {json.dumps(_job_repr(job_data))}\n\n"

            # Stop streaming when job reaches terminal state
            if status in ('completed', 'error'):
                break

    return Response(generate(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no'  # Disable nginx buffering
    })


@app.route('/api/jobs/<job_id>', methods=['DELETE'])
def api_delete_job(job_id: str):
    client_id, error_response = _client_id_response()
    if error_response:
        return error_response

    job = job_service.get_job(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    if job.get('client_id') and job.get('client_id') != client_id:
        return jsonify({'error': 'Job not found'}), 404

    ok = job_service.store.mark_deleted(job_id)
    if not ok:
        return jsonify({'error': 'Job not found'}), 404

    return ('', 204)


@app.route('/api/jobs/<job_id>/artifacts', methods=['GET'])
def api_list_artifacts(job_id: str):
    client_id, error_response = _client_id_response()
    if error_response:
        return error_response

    job = job_service.get_job(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    if job.get('client_id') and job.get('client_id') != client_id:
        return jsonify({'error': 'Job not found'}), 404

    if job.get('status') != 'completed' or not job.get('output_file'):
        return jsonify({'error': 'Job not ready'}), 409

    primary_path = _resolve_output_path(job['output_file'])
    if not primary_path.exists():
        return jsonify({'error': 'Output file not found'}), 404

    jobs_dir = primary_path.parent
    job_id = job.get('id')
    expected = _expected_artifacts_for_job(job)

    artifacts = []
    for artifact_name, ext in expected:
        artifact_path = jobs_dir / f"{job_id}_{artifact_name}.{ext}"
        if artifact_path.exists():
            artifacts.append(_artifact_repr(job, artifact_name, artifact_path))

    # Expose a stable thumbnail artifact if we can derive a YouTube thumbnail.
    yt_thumb = _youtube_thumbnail_url(job.get('url') or '')
    if yt_thumb:
        artifacts.append(_thumbnail_artifact_repr(job))

    return jsonify({'artifacts': artifacts})


@app.route('/raw/<job_id>/<artifact_name>.<ext>', methods=['GET'])
def raw_artifact(job_id: str, artifact_name: str, ext: str):
    client_id, error_response = _client_id_response()
    if error_response:
        return error_response

    job, job_error = _get_authorized_completed_job(job_id, client_id)
    if job_error:
        status_code = 409 if job_error[1] == 400 else 404
        error_message = 'Job not ready' if status_code == 409 else 'Job not found'
        return jsonify({'error': error_message}), status_code

    primary_path = _resolve_output_path(job['output_file'])
    jobs_dir = primary_path.parent
    expected = _expected_artifacts_for_job(job)
    expected_names = {name for name, _ in expected}
    if artifact_name not in expected_names:
        return jsonify({'error': 'Artifact not found'}), 404

    artifact_path = jobs_dir / f"{job_id}_{artifact_name}.{ext.lower()}"
    if not artifact_path.exists():
        return jsonify({'error': 'Artifact not found'}), 404

    return send_file(artifact_path, as_attachment=True, download_name=artifact_path.name)


@app.route('/raw/<job_id>/thumbnail.jpg', methods=['GET'])
def raw_thumbnail(job_id: str):
    client_id, error_response = _client_id_response()
    if error_response:
        return error_response

    job, job_error = _get_authorized_completed_job(job_id, client_id)
    if job_error:
        status_code = 409 if job_error[1] == 400 else 404
        error_message = 'Job not ready' if status_code == 409 else 'Job not found'
        return jsonify({'error': error_message}), status_code

    thumb_url = _youtube_thumbnail_url(job.get('url') or '')
    if not thumb_url:
        return jsonify({'error': 'Thumbnail not available'}), 404

    r = requests.get(thumb_url, timeout=10)
    if r.status_code != 200:
        return jsonify({'error': 'Thumbnail fetch failed'}), 502

    return Response(r.content, mimetype='image/jpeg')


@app.route('/render/<job_id>/<artifact_name>.<ext>', methods=['GET'])
def render_artifact(job_id: str, artifact_name: str, ext: str):
    client_id, error_response = _client_id_response()
    if error_response:
        return error_response

    job, job_error = _get_authorized_completed_job(job_id, client_id)
    if job_error:
        status_code = 409 if job_error[1] == 400 else 404
        error_message = 'Job not ready' if status_code == 409 else 'Job not found'
        return jsonify({'error': error_message}), status_code

    primary_path = _resolve_output_path(job['output_file'])
    jobs_dir = primary_path.parent
    expected = _expected_artifacts_for_job(job)
    expected_names = {name for name, _ in expected}
    if artifact_name not in expected_names:
        return jsonify({'error': 'Artifact not found'}), 404

    # We only support HTML render endpoints.
    if ext.lower() != 'html':
        return jsonify({'error': 'Unsupported render format'}), 400

    # Find the artifact file on disk
    matching = [(n, e) for n, e in expected if n == artifact_name]
    artifact_path = jobs_dir / f"{job_id}_{artifact_name}.{matching[0][1]}"
    if not artifact_path.exists():
        return jsonify({'error': 'Artifact not found'}), 404

    suffix = artifact_path.suffix.lower()

    if suffix == '.md':
        template = 'condensed_script.html' if artifact_name == 'condensed_script' else 'takeaways.html'
        try:
            return _render_markdown_output(
                job_id,
                client_id,
                artifact_path,
                youtube_url=job.get('url'),
                channel_name=job.get('channel_name'),
                template=template,
            )
        except Exception as e:
            return jsonify({'error': f'Failed to render markdown: {str(e)}'}), 500

    if suffix not in {'.mp3', '.mp4'}:
        return jsonify({'error': f'Unsupported file type for render: {suffix or "unknown"}'}), 400

    media_kind = 'audio' if suffix == '.mp3' else 'video'
    media_url = url_for('render_artifact_content', job_id=job_id, artifact_name=artifact_name, cid=client_id)
    raw_url = url_for('raw_artifact', job_id=job_id, artifact_name=artifact_name, ext=matching[0][1], cid=client_id)

    params = job.get('params') or {}
    aggressiveness = params.get('aggressiveness')
    voice = params.get('voice')
    thumbnail_url = None
    if media_kind == 'audio':
        cover_path = _cover_path_for_output(artifact_path)
        if cover_path.exists():
            thumbnail_url = url_for('render_artifact_cover', job_id=job_id, cid=client_id, v=str(uuid.uuid4())[:8])
        else:
            # Use our own proxied thumbnail endpoint to avoid hotlink/CORS issues.
            if _youtube_thumbnail_url(job.get('url') or ''):
                thumbnail_url = url_for('raw_thumbnail', job_id=job_id, cid=client_id)

    return render_template(
        'media_player.html',
        job_id=job_id,
        video_title=job.get('title') or None,
        channel_name=job.get('channel_name') or None,
        aggressiveness=aggressiveness,
        voice=voice,
        thumbnail_url=thumbnail_url,
        media_kind=media_kind,
        media_url=media_url,
        download_url=raw_url,
        file_name=artifact_path.name,
        youtube_url=job.get('url') or None,
    )


@app.route('/render/<job_id>/cover.jpg', methods=['GET'])
def render_artifact_cover(job_id: str):
    client_id, error_response = _client_id_response()
    if error_response:
        return error_response

    job, job_error = _get_authorized_completed_job(job_id, client_id)
    if job_error:
        status_code = 409 if job_error[1] == 400 else 404
        error_message = 'Job not ready' if status_code == 409 else 'Job not found'
        return jsonify({'error': error_message}), status_code

    primary_path = _resolve_output_path(job['output_file'])
    if primary_path.suffix.lower() != '.mp3':
        return jsonify({'error': 'Cover art is only available for MP3 outputs'}), 400

    cover_path = _cover_path_for_output(primary_path)
    if not cover_path.exists():
        return jsonify({'error': 'Cover image not found'}), 404

    return send_file(cover_path, as_attachment=False, mimetype='image/jpeg', download_name=cover_path.name)


@app.route('/render/<job_id>/content/<artifact_name>', methods=['GET'])
def render_artifact_content(job_id: str, artifact_name: str):
    client_id, error_response = _client_id_response()
    if error_response:
        return error_response

    job, job_error = _get_authorized_completed_job(job_id, client_id)
    if job_error:
        status_code = 409 if job_error[1] == 400 else 404
        error_message = 'Job not ready' if status_code == 409 else 'Job not found'
        return jsonify({'error': error_message}), status_code

    primary_path = _resolve_output_path(job['output_file'])
    jobs_dir = primary_path.parent
    expected = _expected_artifacts_for_job(job)
    matching = [(n, e) for n, e in expected if n == artifact_name]
    if not matching:
        return jsonify({'error': 'Artifact not found'}), 404

    artifact_path = jobs_dir / f"{job_id}_{artifact_name}.{matching[0][1]}"
    if not artifact_path.exists():
        return jsonify({'error': 'Artifact not found'}), 404

    suffix = artifact_path.suffix.lower()
    if suffix not in {'.mp3', '.mp4'}:
        return jsonify({'error': f'Unsupported file type for content: {suffix or "unknown"}'}), 400

    mimetype = 'audio/mpeg' if suffix == '.mp3' else 'video/mp4'
    return send_file(artifact_path, as_attachment=False, mimetype=mimetype, download_name=artifact_path.name)


@app.route('/api/health', methods=['GET'])
def api_health():
    running_jobs = job_service.get_running_jobs()
    return jsonify({
        'status': 'ok',
        'busy': len(running_jobs) > 0,
        'running_jobs': len(running_jobs),
        'max_workers': job_service.max_workers
    })


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
    dist_dir = get_project_root() / 'dist'
    files = list(dist_dir.glob('nbj-chrome-extension-*.zip'))

    unversioned = dist_dir / 'nbj-chrome-extension.zip'
    if unversioned.exists():
        files.append(unversioned)

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
    dist_dir = get_project_root() / 'dist'
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


def _load_voice_whitelist() -> dict:
    """Load voice_whitelist.yaml at call time so edits take effect without restart."""
    path = Path(__file__).parent / 'voice_whitelist.yaml'
    try:
        with open(path, 'r') as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning(f"voice_whitelist.yaml not found at {path} — no whitelist applied")
        return {}


def _apply_voice_whitelist_per_voice(voices: list, provider: str) -> list:
    """For each voice apply the whitelist for its specific locale; if no whitelist exists for that locale, pass through."""
    whitelist = _load_voice_whitelist()
    provider_wl = whitelist.get(provider, {})
    result = []
    for v in voices:
        locale = v.get('locale', '')
        allowed = provider_wl.get(locale)
        if not allowed:
            result.append(v)
        else:
            prefix = locale + '-'
            if any(v['name'].startswith(prefix + entry) for entry in allowed):
                result.append(v)
    return result


@app.route('/api/voices', methods=['GET'])
def get_voices():
    """Get available TTS voices filtered by lang (required).
    lang=xx-YY  exact locale, whitelist applied if defined for that locale.
    lang=xx     all locales under that language, per-locale whitelists applied.
    """
    lang = request.args.get('locale')
    if not lang:
        return jsonify({'error': 'locale parameter is required (e.g. ?locale=en or ?locale=en-US)'}), 400
    exact_locale = '-' in lang
    settings = get_settings()

    def _friendly_voice_name(voice_name: str) -> str:
        return (
            voice_name.split('-', 2)[-1]
            .replace('Multilingual', '')
            .replace('Expressive', '')
            .replace('Turbo', '')
            .replace('Neural', '')
            .strip()
        )

    def _is_voice_name_allowed(friendly_name: str) -> bool:
        if not friendly_name:
            return False

        if 'AI' in friendly_name:
            return False

        if ':' in friendly_name:
            return False

        if any(ch.isdigit() for ch in friendly_name):
            return False

        return True

    def _to_voice_repr(v: dict) -> dict:
        friendly_name = _friendly_voice_name(v['name'])
        return {
            'name': v['name'],
            'gender': v.get('gender', 'Unknown'),
            'locale': v.get('locale', 'Unknown'),
            'friendly_name': friendly_name,
        }

    def _to_elevenlabs_voice_repr(v: dict) -> dict:
        name = v.get('name') or ''
        return {
            'name': v.get('voice_id') or name,
            'gender': 'Unknown',
            'locale': 'Unknown',
            'friendly_name': name,
        }

    try:
        match settings.tts_provider:
            case 'elevenlabs':
                if not settings.elevenlabs_api_key:
                    return jsonify({'voices': []})

                from src.modules.tts import VoiceCloner
                cloner = VoiceCloner(settings.elevenlabs_api_key)
                all_voices = cloner.list_voices()
                filtered_voices = sorted(
                    [_to_elevenlabs_voice_repr(v) for v in all_voices],
                    key=lambda x: (x.get('friendly_name') or x['name'])
                )

            case 'azure':
                if not settings.azure_speech_key or not settings.azure_speech_region:
                    return jsonify({
                        'error': 'Azure TTS not configured (missing AZURE_SPEECH_KEY or AZURE_SPEECH_REGION)',
                        'voices': []
                    }), 400

                from src.modules.azure_tts import AzureTTS
                azure = AzureTTS(settings.azure_speech_key, settings.azure_speech_region)
                all_voices = azure.list_voices(locale_filter=lang)
                locale_match = (lambda v: v['locale'] == lang) if exact_locale else (lambda v: v['locale'].startswith(lang + '-'))
                filtered_voices = sorted(
                    [
                        _to_voice_repr(v)
                        for v in all_voices
                        if locale_match(v)
                        if _is_voice_name_allowed(_friendly_voice_name(v['name']))
                    ],
                    key=lambda x: x['name']
                )
                filtered_voices = _apply_voice_whitelist_per_voice(filtered_voices, 'azure')
                # Deduplicate by friendly_name — multiple variants (Neural, MultilingualNeural)
                # look identical to clients; keep the first seen after name sort.
                seen: set = set()
                deduped = []
                for v in filtered_voices:
                    key = v['friendly_name']
                    if key not in seen:
                        seen.add(key)
                        deduped.append(v)
                filtered_voices = deduped

            case 'edge' | _:
                edge_tts = EdgeTTS()
                all_voices = edge_tts.list_voices()
                locale_match = (lambda v: v['locale'] == lang) if exact_locale else (lambda v: v['locale'].startswith(lang + '-'))
                filtered_voices = sorted(
                    [
                        _to_voice_repr(v)
                        for v in all_voices
                        if locale_match(v)
                        if _is_voice_name_allowed(_friendly_voice_name(v['name']))
                    ],
                    key=lambda x: x['name']
                )
                filtered_voices = _apply_voice_whitelist_per_voice(filtered_voices, 'edge')
                seen: set = set()
                deduped = []
                for v in filtered_voices:
                    if v['friendly_name'] not in seen:
                        seen.add(v['friendly_name'])
                        deduped.append(v)
                filtered_voices = deduped
        return jsonify({'voices': filtered_voices})
    except Exception as e:
        logger.error(f"Failed to fetch voices: {e}")
        return jsonify({'error': 'Failed to fetch voices'}), 500


def _print_startup_banner():
    print("=" * 60)
    print("NBJ Condenser Server")
    print("=" * 60)
    print("\nServer starting on http://127.0.0.1:5000")
    try:
        settings_path = get_project_root() / 'build-settings.json'
        settings = json.loads(settings_path.read_text(encoding='utf-8')) if settings_path.exists() else {}
        preset_servers = settings.get('preset_servers', [])
        default_server_index = settings.get('default_server_index', 0)
        public_url = preset_servers[default_server_index]['url'] if preset_servers else None
    except Exception:
        public_url = None
    if public_url:
        print(f"\nPublic URL: {public_url}")
    print("\nEndpoints:")
    print("  GET    /                         - Redirect to /start")
    print("  GET    /start                    - Extension download & installation guide")
    print("  GET    /extension.zip            - Download Chrome extension bundle")
    print("  GET    /android.apk              - Download Android APK")
    print("")
    print("  GET    /api/health               - Health check")
    print("  GET    /api/voices               - Get TTS voices (?locale=)")
    print("  GET    /api/strategies           - Get aggressiveness strategies")
    print("  GET    /api/yt_thumb/<video_id>  - Proxy YouTube thumbnail")
    print("  POST   /api/log                  - Client-side log forwarding")
    print("")
    print("  POST   /api/jobs                 - Create a job (condense/takeaways)")
    print("  GET    /api/jobs                 - List jobs")
    print("  GET    /api/jobs/<id>            - Get job")
    print("  GET    /api/jobs/<id>/stream     - SSE stream for job updates")
    print("  GET    /api/jobs/<id>/artifacts  - List artifacts")
    print("  DELETE /api/jobs/<id>            - Delete job")
    print("")
    print("  GET    /raw/<job_id>/<artifact>.<ext>   - Download raw artifact")
    print("  GET    /raw/<job_id>/thumbnail.jpg      - Proxied YouTube thumbnail for job")
    print("  GET    /render/<job_id>/<artifact>.html - Render artifact (HTML player/markdown)")
    print("  GET    /render/<job_id>/cover.jpg       - Cover art for audio job")
    print("  GET    /render/<job_id>/content         - Raw media stream for player")
    if public_url:
        print(f"\n👉 Share this link: {public_url.rstrip('/')}/start")
    print("\n" + "=" * 60 + "\n")


if __name__ == '__main__':
    use_reloader = os.environ.get('NBJ_NO_RELOADER') not in {'1', 'true', 'yes'}

    # With the Werkzeug reloader, the parent process should NOT perform one-time startup.
    # Only the reloader child (WERKZEUG_RUN_MAIN=true) should start workers and print banners.
    is_reloader_child = (not use_reloader) or (os.environ.get("WERKZEUG_RUN_MAIN") == "true")

    if is_reloader_child:
        # Fail fast on invalid configuration before starting workers / serving requests.
        get_settings()

        _print_startup_banner()

        # Start job service worker loop
        job_service.start()
        import threading
        worker_thread = threading.Thread(target=job_service.start_worker_loop, daemon=True)
        worker_thread.start()
        print("Concurrent mode enabled with JobService")

    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=use_reloader)
