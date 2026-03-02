#!/bin/bash
# NBJ Condenser - VM Infrastructure Setup
# Installs all system-level dependencies on Oracle Linux 9
#
# Usage: ssh conciser 'bash -s' < terraform-vm.sh

set -e

echo "🏗️  NBJ Condenser - Infrastructure Setup"
echo "=========================================="
echo ""
echo "⚠️  NOTE: System package updates (yum update) are SKIPPED."
echo "   Oracle Linux VMs are pre-patched. Running yum update kills SSH"
echo "   without a reboot. Update manually when you're ready to reboot."
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
    SUDO=""
else 
    SUDO="sudo"
fi

# Install EPEL repository (needed for some packages)
echo "📦 [1/5] Installing EPEL repository..."
$SUDO yum install -y epel-release

# Install Python 3 and development tools
echo "🐍 [2/5] Installing Python 3 and development tools..."
$SUDO yum install -y \
    python3 \
    python3-pip \
    python3-devel \
    gcc \
    gcc-c++ \
    make

# Install Git
echo "📝 [3/5] Installing Git..."
$SUDO yum install -y git

# Install ffmpeg and related tools
echo "🎬 [4/5] Installing ffmpeg and media tools..."
$SUDO yum install -y \
    ffmpeg \
    ffmpeg-devel

# Install other system utilities
echo "🔧 [5/5] Installing system utilities..."
$SUDO yum install -y \
    wget \
    curl \
    cronie

# Enable and start crond
echo "⚙️  Enabling services..."
$SUDO systemctl enable --now crond

# Upgrade pip globally
echo "📦 Upgrading pip..."
$SUDO pip3 install --upgrade pip setuptools wheel

# Install yt-dlp (YouTube downloader) globally
echo "📺 Installing yt-dlp..."
$SUDO pip3 install --upgrade yt-dlp

# Clean up
echo "🧹 Cleaning up..."
$SUDO yum clean all

# Verify installations
echo ""
echo "✅ Installation Complete! Verifying..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Python:    $(python3 --version 2>&1)"
echo "Pip:       $(pip3 --version 2>&1 | cut -d' ' -f1-2)"
echo "Git:       $(git --version 2>&1)"
echo "ffmpeg:    $(ffmpeg -version 2>&1 | head -1)"
echo "yt-dlp:    $(yt-dlp --version 2>&1)"
echo "Crond:     $(systemctl is-active crond)"
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
echo "  • Firewall management disabled to avoid SSH lockout"
echo "  • System updates (yum update) SKIPPED to avoid SSH lockout"
echo "  • Configure Oracle Cloud Security List manually for port access"
echo ""
echo "To update system packages later (requires reboot):"
echo "  ssh conciser 'sudo yum update -y && sudo reboot'"
