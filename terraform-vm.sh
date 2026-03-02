#!/bin/bash
# NBJ Condenser - VM Infrastructure Setup
# Installs all system-level dependencies on Ubuntu/Debian
#
# Usage: ssh conciser 'bash -s' < terraform-vm.sh

set -e

echo "🏗️  NBJ Condenser - Infrastructure Setup"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
    SUDO=""
else 
    SUDO="sudo"
fi

# Update package lists
echo "📦 [1/5] Updating package lists..."
$SUDO apt-get update

# Install Python 3 and development tools
echo "🐍 [2/5] Installing Python 3 and development tools..."
$SUDO apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    python3-venv \
    build-essential

# Install Git
echo "📝 [3/5] Installing Git..."
$SUDO apt-get install -y git

# Install ffmpeg and related tools
echo "🎬 [4/5] Installing ffmpeg and media tools..."
$SUDO apt-get install -y \
    ffmpeg

# Install other system utilities
echo "🔧 [5/5] Installing system utilities..."
$SUDO apt-get install -y \
    wget \
    curl \
    cron

# Enable and start cron
echo "⚙️  Enabling services..."
$SUDO systemctl enable --now cron 2>/dev/null || true

# Upgrade pip globally
echo "📦 Upgrading pip..."
$SUDO pip3 install --upgrade pip setuptools wheel

# Install yt-dlp (YouTube downloader) globally
echo "📺 Installing yt-dlp..."
$SUDO pip3 install --upgrade yt-dlp

# Clean up
echo "🧹 Cleaning up..."
$SUDO apt-get clean

# Verify installations
echo ""
echo "✅ Installation Complete! Verifying..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Python:    $(python3 --version 2>&1)"
echo "Pip:       $(pip3 --version 2>&1 | cut -d' ' -f1-2)"
echo "Git:       $(git --version 2>&1)"
echo "ffmpeg:    $(ffmpeg -version 2>&1 | head -1)"
echo "yt-dlp:    $(yt-dlp --version 2>&1)"
echo "Cron:      $(systemctl is-active cron 2>/dev/null || echo 'running')"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🎯 System is ready for NBJ Condenser deployment!"
echo ""
echo "Next steps:"
echo "  1. Run: ./deploy.sh            # Deploy application code"
echo "  2. Run: ./deploy-env.sh        # Copy .env file"
echo "  3. Run: ./setup-cron.sh        # Set up cleanup job"
echo ""
echo "⚠️  IMPORTANT NOTES:"
echo "  • Firewall management disabled to avoid conflicts"
echo "  • Configure Hetzner Cloud Firewall for port access if needed"
