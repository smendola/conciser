#!/usr/bin/env python3
"""Build script for NBJ Chrome Extension.

Creates a production-ready zip package of the chrome extension.
Output: dist/nbj-chrome-extension.zip
"""

import zipfile
from pathlib import Path
import shutil

def build_extension():
    """Package the chrome extension into a zip file."""
    # Paths
    extension_dir = Path(__file__).parent  # chrome-extension/
    project_root = extension_dir.parent    # project root
    dist_dir = project_root / 'dist'
    output_zip = dist_dir / 'nbj-chrome-extension.zip'

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

    # Files/folders to include
    include_patterns = [
        'manifest.json',
        'popup.html',
        'popup.js',
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
