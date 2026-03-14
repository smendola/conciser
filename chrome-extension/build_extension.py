#!/usr/bin/env python3
"""Build script for NBJ Chrome Extension.

Creates a production-ready zip package of the chrome extension.
Output: dist/nbj-chrome-extension.zip
"""

import zipfile
import json
from pathlib import Path
import shutil
from datetime import datetime


def _find_project_root(start: Path) -> Path:
    start = start.resolve()
    for candidate in [start, *start.parents]:
        if (candidate / '.project-root').exists():
            return candidate
    raise FileNotFoundError(
        f"Could not locate project root: missing `.project-root` when searching upward from {start}"
    )


def _read_json_file(path: Path) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _write_json_file(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding='utf-8')


def _read_int_file(path: Path, default: int = 0) -> int:
    if not path.exists():
        return default
    try:
        return int(path.read_text(encoding='utf-8').strip())
    except Exception:
        return default


def _write_int_file(path: Path, value: int) -> None:
    path.write_text(str(value) + "\n", encoding='utf-8')


def _bump_chrome_build_number(extension_dir: Path) -> int:
    build_number_file = extension_dir / '.build_number'
    current = _read_int_file(build_number_file, default=0)
    next_value = current + 1
    _write_int_file(build_number_file, next_value)
    print(f"Incremented Chrome build number: {current} -> {next_value}")
    return next_value


def _generate_manifest(extension_dir: Path, version: str) -> None:
    template_path = extension_dir / 'manifest.template.json'
    if not template_path.exists():
        raise FileNotFoundError(f"Missing manifest template: {template_path}")

    manifest = _read_json_file(template_path)
    manifest['version'] = version

    key_path = extension_dir / 'manifest.key.json'
    if key_path.exists():
        key_data = _read_json_file(key_path)
        if isinstance(key_data, dict) and 'key' in key_data and key_data['key']:
            manifest['key'] = key_data['key']

    manifest_path = extension_dir / 'manifest.json'
    _write_json_file(manifest_path, manifest)

def build_extension():
    """Package the chrome extension into a zip file."""
    # Paths
    extension_dir = Path(__file__).parent  # chrome-extension/
    project_root = _find_project_root(extension_dir)
    dist_dir = project_root / 'dist'

    build_number = _bump_chrome_build_number(extension_dir)
    version = f"1.1.{build_number}"
    _generate_manifest(extension_dir, version)

    output_zip = dist_dir / f'nbj-chrome-extension-{version}.zip'

    # Validate extension directory exists
    if not extension_dir.exists():
        print(f"Error: Extension directory not found: {extension_dir}")
        return False

    # Create dist directory if it doesn't exist
    dist_dir.mkdir(exist_ok=True)

    # Remove old zip if it exists
    if output_zip.exists():
        output_zip.unlink()
        print(f"Removed old build: {output_zip}")

    # Read build settings
    build_settings_file = project_root / 'build-settings.json'
    with open(build_settings_file, 'r') as f:
        build_settings = json.load(f)
    default_server_url = build_settings['default_server_url']
    preset_servers = build_settings.get('preset_servers', [])
    preset_urls_js = '[' + ', '.join(f'"{s["url"]}"' for s in preset_servers) + ']'
    preset_names_js = '[' + ', '.join(f'"{s["name"]}"' for s in preset_servers) + ']'

    # Generate build info file
    build_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    build_info_file = extension_dir / 'build-info.js'
    build_info_file.write_text(
        f'const BUILD_VERSION = "{version}";\n'
        f'const DEFAULT_SERVER_URL = "{default_server_url}";\n'
        f'const PRESET_URLS = {preset_urls_js};\n'
        f'const PRESET_NAMES = {preset_names_js};\n'
    )
    print(f"Generated build-info.js: version={version} timestamp={build_timestamp} server={default_server_url} presets={len(preset_servers)}")

    # Files/folders to include
    include_patterns = [
        'manifest.json',
        'popup.html',
        'popup.js',
        'build-info.js',
        'background.js',
        'README.md',
        'icons/*.png'
    ]

    # Files/folders to exclude
    exclude_patterns = [
        'temp',
        'output',
        '*.log',
        '__pycache__',
        '.DS_Store',
        'build_extension.py'
    ]

    print(f"Building extension from: {extension_dir}")
    print(f"Output: {output_zip}")

    # Create zip file
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for item in extension_dir.rglob('*'):
            # Skip directories
            if item.is_dir():
                continue

            # Check if should be excluded
            relative_path = item.relative_to(extension_dir)
            should_exclude = any(
                relative_path.match(pattern) for pattern in exclude_patterns
            )

            if should_exclude:
                continue

            # Add to zip
            zipf.write(item, relative_path)
            print(f"  Added: {relative_path}")

    # Get file size
    size_kb = output_zip.stat().st_size / 1024
    print(f"\n✓ Built successfully: {output_zip} ({size_kb:.1f} KB)")

    return True

if __name__ == '__main__':
    success = build_extension()
    exit(0 if success else 1)
