#!/bin/bash
# Installation script for NBJ Condenser

set -e

echo "================================"
echo "NBJ Condenser Installation Script"
echo "================================"
echo

# Check Python version
python_version=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
required_version="3.10"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "Error: Python 3.10 or higher is required (found: $python_version)"
    exit 1
fi

echo "✓ Python $python_version found"

# Check for ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "✗ ffmpeg not found"
    echo
    echo "Please install ffmpeg:"
    echo "  Ubuntu/Debian: sudo apt install ffmpeg"
    echo "  macOS: brew install ffmpeg"
    echo "  Windows: Download from https://ffmpeg.org"
    exit 1
fi

echo "✓ ffmpeg found"

# Create virtual environment
echo
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Install NBJ Condenser
echo "Installing NBJ Condenser..."
pip install -e .

# Create directories
echo "Creating directories..."
mkdir -p temp output

# Check if .env exists
if [ ! -f .env ]; then
    echo
    echo "No .env file found. Running setup wizard..."
    echo
    nbj setup
else
    echo "✓ .env file exists"
fi

echo
echo "================================"
echo "Installation complete!"
echo "================================"
echo
echo "Next steps:"
echo "  1. Activate virtual environment: source venv/bin/activate"
echo "  2. Run configuration check: nbj check"
echo "  3. Try condensing a video: nbj condense <youtube_url>"
echo
echo "For help: nbj --help"
echo "Quick start guide: cat QUICKSTART.md"
echo
