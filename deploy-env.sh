#!/bin/bash
# Copy .env file to VM (one-time setup)

set -e

REMOTE_USER="opc"
REMOTE_HOST="conciser"
REMOTE_DIR="/home/opc/nbj-condenser"

echo "📋 Copying .env to $REMOTE_HOST..."

if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found in current directory"
    exit 1
fi

scp .env $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/.env

echo "✅ .env copied successfully!"
