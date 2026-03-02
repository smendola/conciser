#!/bin/bash
# NBJ Condenser - One-button deploy to Oracle Cloud VM

set -e

# Configuration
REMOTE_USER="opc"
REMOTE_HOST="conciser"
REMOTE_DIR="/home/opc/nbj-condenser"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🚀 Deploying NBJ Condenser to $REMOTE_HOST..."

# 1. Commit and push changes
echo "📝 Committing changes..."
cd "$LOCAL_DIR"
git add -A
if git diff --staged --quiet; then
    echo "   No changes to commit"
else
    git commit -m "Deploy $(date +%Y-%m-%d_%H:%M:%S)" || true
fi

echo "📤 Pushing to GitHub..."
git push origin main || git push origin master

# 2. Deploy to VM
echo "📦 Deploying to VM..."
ssh $REMOTE_USER@$REMOTE_HOST << 'ENDSSH'
cd /home/opc

# Clone or pull repo
if [ -d "nbj-condenser" ]; then
    echo "   Pulling latest changes..."
    cd nbj-condenser
    git pull
else
    echo "   Cloning repository..."
    git clone https://github.com/smendola/conciser nbj-condenser
    cd nbj-condenser
fi

# Set up Python environment
echo "   Setting up Python environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip
pip install -e .

# Copy .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "   ⚠️  No .env file found on VM - you'll need to create one"
fi

# Restart server if running
echo "   Restarting server..."
pkill -f "server/app.py" || true
sleep 2

# Start server in background
nohup venv/bin/python server/app.py > server.log 2>&1 &
echo "   ✅ Server started (PID: $!)"

echo "   📊 Server status:"
sleep 2
curl http://localhost:5000/health || echo "   ⚠️  Server not responding yet"

ENDSSH

echo ""
echo "✅ Deployment complete!"
echo "📍 Server running at: http://129.80.134.46:5000"
echo "📝 View logs: ssh conciser 'tail -f nbj-condenser/server.log'"
