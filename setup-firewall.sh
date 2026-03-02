#!/bin/bash
# NBJ Condenser - Configure Oracle Cloud firewall
# Run this on the VM to allow HTTP traffic on port 5000
#
# Usage: ssh conciser 'bash -s' < setup-firewall.sh

set -e

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
    SUDO=""
else 
    SUDO="sudo"
fi

echo "🔥 Configuring firewall for port 5000..."

# Ensure firewalld is running
if ! $SUDO systemctl is-active --quiet firewalld; then
    echo "   ⚠️  Starting firewalld..."
    $SUDO systemctl start firewalld
    $SUDO systemctl enable firewalld
fi

# Add firewall rule for port 5000
echo "   Opening port 5000/tcp..."
$SUDO firewall-cmd --permanent --add-port=5000/tcp
$SUDO firewall-cmd --reload

# Verify rule was added
echo "   Verifying firewall rules..."
if $SUDO firewall-cmd --list-ports | grep -q "5000/tcp"; then
    echo "   ✅ Port 5000 is open in firewall!"
else
    echo "   ❌ Failed to open port 5000"
    exit 1
fi

echo ""
echo "✅ Firewall configured successfully!"
echo ""
echo "📍 Server will be accessible at: http://129.80.134.46:5000"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⚠️  IMPORTANT: Oracle Cloud Security List Configuration Required"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "The VM firewall is now open, but you MUST also configure the"
echo "Oracle Cloud Security List to allow inbound traffic:"
echo ""
echo "1. Go to Oracle Cloud Console"
echo "2. Navigate to: Networking → Virtual Cloud Networks"
echo "3. Click your VCN → Security Lists → Default Security List"
echo "4. Click 'Add Ingress Rules'"
echo "5. Configure:"
echo "   • Source Type: CIDR"
echo "   • Source CIDR: 0.0.0.0/0"
echo "   • IP Protocol: TCP"
echo "   • Destination Port Range: 5000"
echo "6. Click 'Add Ingress Rules'"
echo ""
echo "Without this step, external traffic will be blocked!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
