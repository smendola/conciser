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

def build_extension():
    """Package the chrome extension into a zip file."""
    # Paths
    extension_dir = Path(__file__).parent  # chrome-extension/
    project_root = extension_dir.parent    # project root
    dist_dir = project_root / 'dist'
    with open(extension_dir / 'manifest.json', 'r') as f:
        manifest = json.load(f)
        version = manifest.get('version', '0.0.0')

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

    # Generate build info file
    build_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    build_info_file = extension_dir / 'build-info.js'
    build_info_file.write_text(
        f'const BUILD_VERSION = "{version}";\n'
        f'const DEFAULT_SERVER_URL = "{default_server_url}";\n'
    )
    print(f"Generated build-info.js: version={version} timestamp={build_timestamp} server={default_server_url}")

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
