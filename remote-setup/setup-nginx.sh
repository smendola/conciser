#!/bin/bash
# NBJ Condenser - Nginx Reverse Proxy Setup
# Sets up nginx to proxy port 80 -> Flask on port 5000
#
# ⚠️  NOTE: No OS-level firewall management on Ubuntu.
#     Configure Hetzner Cloud Firewall for ports 80/443 if needed.
#
# Usage: ssh conciser 'bash -s' < setup-nginx.sh

set -e

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
    SUDO=""
else 
    SUDO="sudo"
fi

# Detect public IP (fallback to hostname -I)
PUBLIC_IP="$($SUDO curl -s https://ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')"
STATIC_SRC="/root/nbj-condenser/server/static"
STATIC_DEST="/var/www/nbj-condenser-static"
NGINX_SITE="/etc/nginx/sites-available/nbj-condenser"

echo "🌐 Setting up Nginx reverse proxy..."
echo "📍 Public IP detected: ${PUBLIC_IP:-unknown}"
echo ""

# Install nginx
echo "📦 Installing nginx..."
$SUDO apt-get update
$SUDO apt-get install -y nginx rsync

# Enable and start nginx
echo "⚙️  Enabling nginx service..."
$SUDO systemctl enable nginx
$SUDO systemctl start nginx

# Sync static assets if they exist
if [ -d "$STATIC_SRC" ]; then
    echo "🗂️  Syncing static assets to $STATIC_DEST..."
    $SUDO mkdir -p "$STATIC_DEST"
    $SUDO rsync -a --delete "$STATIC_SRC/" "$STATIC_DEST/"
    $SUDO chown -R www-data:www-data "$STATIC_DEST"
else
    echo "⚠️  Warning: Static source directory $STATIC_SRC not found."
    echo "    CSS/JS may not load until this path exists."
fi

# Create nginx config for NBJ Condenser
echo "📝 Creating nginx configuration..."
$SUDO tee "$NGINX_SITE" <<EOF
# NBJ Condenser - Nginx Reverse Proxy Configuration

server {
    listen 80;
    server_name _;  # Accept any hostname
    
    client_max_body_size 500M;  # Allow large video uploads/downloads
    
    # Proxy to Flask app
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # Timeouts for long-running requests
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
        proxy_read_timeout 300;
        send_timeout 300;
    }
    
    # Serve static files directly
    location /static/ {
        alias $STATIC_DEST/;
        access_log off;
        expires 30d;
    }
}
EOF

# Enable the site
echo "🔗 Enabling site..."
$SUDO rm -f /etc/nginx/sites-enabled/default
$SUDO ln -sf "$NGINX_SITE" /etc/nginx/sites-enabled/

# Test nginx configuration
echo "🔍 Testing nginx configuration..."
$SUDO nginx -t

# Reload nginx
echo "🔄 Reloading nginx..."
$SUDO systemctl reload nginx

echo ""
echo "✅ Nginx setup complete!"
echo ""
echo "📍 Server is now accessible at:"
echo "   http://${PUBLIC_IP:-<server-ip>}"
echo ""
echo "🔧 Nginx is proxying port 80 → Flask on port 5000"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⚠️  Hetzner Cloud Firewall (Optional)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Hetzner Cloud servers are open by default (no cloud firewall)."
echo "Ports 80 and 443 should work immediately."
echo ""
echo "To add a Hetzner Cloud Firewall (optional):"
echo "1. Go to Hetzner Cloud Console"
echo "2. Navigate to: Firewalls → Create Firewall"
echo "3. Add Inbound Rules:"
echo "   • TCP port 22 (SSH)"
echo "   • TCP port 80 (HTTP)"
echo "   • TCP port 443 (HTTPS)"
echo "4. Apply firewall to your server"
echo ""
echo "For HTTPS (port 443), run: ./setup-ssl.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
