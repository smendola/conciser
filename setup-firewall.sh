#!/bin/bash
# NBJ Condenser - Configure Oracle Cloud firewall
# Run this on the VM to allow HTTP traffic on port 5000
#
# Usage: ssh conciser 'bash -s' < setup-firewall.sh

set -e

echo "🔥 Configuring firewall for port 5000..."

# Add firewall rule for port 5000
echo "   Opening port 5000..."
sudo firewall-cmd --permanent --add-port=5000/tcp
sudo firewall-cmd --reload

echo "   ✅ Firewall configured!"
echo ""
echo "📍 Server will be accessible at: http://129.80.134.46:5000"
echo ""
echo "⚠️  Oracle Cloud Security List:"
echo "   You also need to add an Ingress Rule in Oracle Cloud Console:"
echo "   1. Go to: Networking > Virtual Cloud Networks > your VCN > Security Lists"
echo "   2. Add Ingress Rule:"
echo "      - Source CIDR: 0.0.0.0/0"
echo "      - IP Protocol: TCP"
echo "      - Destination Port Range: 5000"
echo ""
echo "   Without this, the firewall rule won't be enough!"
