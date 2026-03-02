#!/bin/bash
# NBJ Condenser - Initial VM setup script
# Run this ONCE on a fresh Oracle Cloud VM to install all dependencies
#
# Usage: ssh conciser 'bash -s' < setup-vm.sh

set -e

echo "🔧 NBJ Condenser - VM Setup"
echo "=============================="
echo ""

# Update system
echo "📦 Updating system packages..."
sudo yum update -y

# Install Python 3, pip, git
echo "🐍 Installing Python 3, pip, and git..."
sudo yum install -y python3 python3-pip git

# Install ffmpeg (required for video processing)
echo "🎬 Installing ffmpeg..."
sudo yum install -y ffmpeg

# Install yt-dlp (YouTube downloader)
echo "📺 Installing yt-dlp..."
sudo pip3 install yt-dlp

# Verify installations
echo ""
echo "✅ Installation complete! Verifying..."
echo "Python: $(python3 --version)"
echo "Pip: $(pip3 --version)"
echo "Git: $(git --version)"
echo "ffmpeg: $(ffmpeg -version | head -1)"
echo "yt-dlp: $(yt-dlp --version)"

echo ""
echo "🎯 Next steps:"
echo "1. Run ./deploy.sh from your local machine to deploy the app"
echo "2. Run ./deploy-env.sh to copy your .env file to the VM"
echo "3. Configure firewall to allow port 5000 (see DEPLOY.md)"
