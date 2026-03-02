#!/bin/bash
# NBJ Condenser - Nginx Reverse Proxy Setup
# Sets up nginx to proxy port 80 -> Flask on port 5000
#
# ⚠️  NOTE: This script modifies firewalld settings.
#     Firewall changes disabled in terraform-vm.sh to prevent SSH lockout.
#     You MUST configure Oracle Cloud Security List for ports 80/443.
#
# Usage: ssh conciser 'bash -s' < setup-nginx.sh

set -e

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
    SUDO=""
else 
    SUDO="sudo"
fi

echo "🌐 Setting up Nginx reverse proxy..."
echo ""

# Install nginx
echo "📦 Installing nginx..."
$SUDO yum install -y nginx

# Enable and start nginx
echo "⚙️  Enabling nginx service..."
$SUDO systemctl enable nginx
$SUDO systemctl start nginx

# Create nginx config for NBJ Condenser
echo "📝 Creating nginx configuration..."
$SUDO tee /etc/nginx/conf.d/nbj-condenser.conf <<'EOF'
# NBJ Condenser - Nginx Reverse Proxy Configuration

server {
    listen 80;
    server_name _;  # Accept any hostname
    
    client_max_body_size 500M;  # Allow large video uploads/downloads
    
    # Proxy to Flask app
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts for long-running requests
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
        proxy_read_timeout 300;
        send_timeout 300;
    }
    
    # Serve static files directly (if needed)
    location /static/ {
        alias /home/opc/nbj-condenser/server/static/;
    }
}
EOF

# Test nginx configuration
echo "🔍 Testing nginx configuration..."
$SUDO nginx -t

# Reload nginx
echo "🔄 Reloading nginx..."
$SUDO systemctl reload nginx

# Open port 80 in firewall
echo "🔥 Opening port 80 in firewall..."
$SUDO firewall-cmd --permanent --add-service=http
$SUDO firewall-cmd --reload

echo ""
echo "✅ Nginx setup complete!"
echo ""
echo "📍 Server is now accessible at:"
echo "   http://129.80.134.46"
echo ""
echo "🔧 Nginx is proxying port 80 → Flask on port 5000"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⚠️  Oracle Cloud Security List Update Required"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Update your existing Ingress Rule:"
echo ""
echo "1. Go to Oracle Cloud Console"
echo "2. Navigate to: Networking → Virtual Cloud Networks"
echo "3. Click your VCN → Security Lists → Default Security List"
echo "4. Find the rule for port 5000 and delete it (or keep for testing)"
echo "5. Add new Ingress Rule:"
echo "   • Source CIDR: 0.0.0.0/0"
echo "   • IP Protocol: TCP"
echo "   • Destination Port Range: 80"
echo ""
echo "For HTTPS (port 443), run: ./setup-ssl.sh (coming soon)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
