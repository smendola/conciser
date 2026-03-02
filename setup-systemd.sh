#!/bin/bash
# NBJ Condenser - Systemd Service Setup
# Creates a systemd service to run the Flask server
#
# Usage: ssh conciser 'bash -s' < setup-systemd.sh

set -e

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
    SUDO=""
else 
    SUDO="sudo"
fi

echo "🔧 Setting up systemd service for NBJ Condenser..."
echo ""

# Create systemd service file
echo "📝 Creating systemd service..."
$SUDO tee /etc/systemd/system/nbj-condenser.service > /dev/null <<'EOF'
[Unit]
Description=NBJ Condenser Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/nbj-condenser
Environment="PATH=/root/nbj-condenser/venv/bin"
ExecStart=/root/nbj-condenser/venv/bin/python /root/nbj-condenser/server/app.py
Restart=always
RestartSec=10
StandardOutput=append:/root/nbj-condenser/server.log
StandardError=append:/root/nbj-condenser/server.log

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
echo "🔄 Reloading systemd..."
$SUDO systemctl daemon-reload

# Enable the service (start on boot)
echo "⚙️  Enabling service..."
$SUDO systemctl enable nbj-condenser

# Start the service
echo "▶️  Starting service..."
$SUDO systemctl start nbj-condenser

# Wait a moment
sleep 3

# Check status
echo ""
echo "📊 Service status:"
$SUDO systemctl status nbj-condenser --no-pager || true

echo ""
echo "✅ Systemd service setup complete!"
echo ""
echo "📝 Useful commands:"
echo "   sudo systemctl status nbj-condenser   # Check status"
echo "   sudo systemctl restart nbj-condenser  # Restart server"
echo "   sudo systemctl stop nbj-condenser     # Stop server"
echo "   sudo systemctl start nbj-condenser    # Start server"
echo "   sudo journalctl -u nbj-condenser -f   # View logs (live)"
echo ""
