#!/bin/bash
# NBJ Condenser - VM Infrastructure Setup
# Installs all system-level dependencies on Oracle Linux 9
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

# Update system
echo "📦 [1/6] Updating system packages..."
$SUDO yum update -y -q

# Install EPEL repository (needed for some packages)
echo "📦 [2/6] Installing EPEL repository..."
$SUDO yum install -y -q epel-release

# Install Python 3 and development tools
echo "🐍 [3/6] Installing Python 3 and development tools..."
$SUDO yum install -y -q \
    python3 \
    python3-pip \
    python3-devel \
    gcc \
    gcc-c++ \
    make

# Install Git
echo "📝 [4/6] Installing Git..."
$SUDO yum install -y -q git

# Install ffmpeg and related tools
echo "🎬 [5/6] Installing ffmpeg and media tools..."
$SUDO yum install -y -q \
    ffmpeg \
    ffmpeg-devel

# Install other system utilities
echo "🔧 [6/6] Installing system utilities..."
$SUDO yum install -y -q \
    wget \
    curl \
    cronie \
    firewalld

# Enable and start firewalld and crond
echo "⚙️  Enabling services..."
$SUDO systemctl enable --now firewalld
$SUDO systemctl enable --now crond

# Upgrade pip globally
echo "📦 Upgrading pip..."
$SUDO pip3 install --upgrade pip setuptools wheel

# Install yt-dlp (YouTube downloader) globally
echo "📺 Installing yt-dlp..."
$SUDO pip3 install --upgrade yt-dlp

# Clean up
echo "🧹 Cleaning up..."
$SUDO yum clean all -q

# Verify installations
echo ""
echo "✅ Installation Complete! Verifying..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Python:    $(python3 --version 2>&1)"
echo "Pip:       $(pip3 --version 2>&1 | cut -d' ' -f1-2)"
echo "Git:       $(git --version 2>&1)"
echo "ffmpeg:    $(ffmpeg -version 2>&1 | head -1)"
echo "yt-dlp:    $(yt-dlp --version 2>&1)"
echo "Firewalld: $(systemctl is-active firewalld)"
echo "Crond:     $(systemctl is-active crond)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🎯 System is ready for NBJ Condenser deployment!"
echo ""
echo "Next steps:"
echo "  1. Run: ./deploy.sh            # Deploy application code"
echo "  2. Run: ./deploy-env.sh        # Copy .env file"
echo "  3. Run: ./setup-firewall.sh    # Open port 5000"
echo "  4. Run: ./setup-cron.sh        # Set up cleanup job"
