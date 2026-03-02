#!/bin/bash
# NBJ Condenser - SSL/TLS Setup with Let's Encrypt
# Sets up HTTPS on port 443 using certbot
#
# Usage: ssh conciser 'bash -s' < setup-ssl.sh
# 
# Requirements:
# - Domain name pointing to your server's IP
# - Port 80 must be accessible (for Let's Encrypt validation)
# - nginx must already be installed and configured

set -e

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
    SUDO=""
else 
    SUDO="sudo"
fi

# Prompt for domain name
read -p "Enter your domain name (e.g., conciser.example.com): " DOMAIN_NAME

if [ -z "$DOMAIN_NAME" ]; then
    echo "❌ Error: Domain name is required"
    exit 1
fi

read -p "Enter your email address (for Let's Encrypt notifications): " EMAIL

if [ -z "$EMAIL" ]; then
    echo "❌ Error: Email is required"
    exit 1
fi

echo ""
echo "🔐 Setting up SSL/TLS for: $DOMAIN_NAME"
echo ""

# Install certbot
echo "📦 Installing certbot..."
$SUDO yum install -y certbot python3-certbot-nginx

# Obtain SSL certificate
echo "📜 Obtaining SSL certificate from Let's Encrypt..."
echo "   This may take a minute..."
$SUDO certbot --nginx \
    --non-interactive \
    --agree-tos \
    --email "$EMAIL" \
    -d "$DOMAIN_NAME"

# Open port 443 in firewall
echo "🔥 Opening port 443 in firewall..."
$SUDO firewall-cmd --permanent --add-service=https
$SUDO firewall-cmd --reload

# Set up auto-renewal
echo "⏰ Setting up automatic certificate renewal..."
$SUDO systemctl enable --now certbot-renew.timer

echo ""
echo "✅ SSL/TLS setup complete!"
echo ""
echo "📍 Your site is now available at:"
echo "   https://$DOMAIN_NAME"
echo ""
echo "🔒 Certificate auto-renews every 60 days via systemd timer"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⚠️  Oracle Cloud Security List Update Required"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Add Ingress Rule for HTTPS:"
echo ""
echo "1. Go to Oracle Cloud Console"
echo "2. Navigate to: Networking → Virtual Cloud Networks"
echo "3. Click your VCN → Security Lists → Default Security List"
echo "4. Add Ingress Rule:"
echo "   • Source CIDR: 0.0.0.0/0"
echo "   • IP Protocol: TCP"
echo "   • Destination Port Range: 443"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
