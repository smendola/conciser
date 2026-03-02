#!/bin/bash
# NBJ Condenser - Complete New VM Setup
# Orchestrates all setup steps in the correct order
#
# Usage: ./setup-new-vm.sh

set -e

REMOTE_HOST="${1:-conciser}"

echo "🚀 NBJ Condenser - Complete VM Setup"
echo "====================================="
echo ""
echo "Target: $REMOTE_HOST"
echo ""

# Check SSH connectivity
echo "🔍 Checking SSH connectivity..."
if ! ssh -o ConnectTimeout=5 "$REMOTE_HOST" 'echo "SSH OK"' >/dev/null 2>&1; then
    echo "❌ Error: Cannot connect to $REMOTE_HOST via SSH"
    echo "   Make sure you can run: ssh $REMOTE_HOST"
    exit 1
fi
echo "   ✅ SSH connection OK"
echo ""

# Step 1: Install system dependencies
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 1: Installing system dependencies"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "This will take 3-5 minutes..."
echo ""
ssh "$REMOTE_HOST" 'bash -s' < terraform-vm.sh
echo ""

# Step 2: Deploy application
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 2: Deploying application"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
./deploy.sh
echo ""

# Step 3: Copy environment file
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 3: Copying environment file"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
if [ ! -f ".env" ]; then
    echo "⚠️  Warning: .env file not found in current directory"
    echo "   You'll need to manually create .env on the VM later"
    echo ""
else
    ./deploy-env.sh
    echo ""
fi

# Step 4: Configure firewall (DISABLED - configure Oracle Cloud Security List manually)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 4: Firewall Configuration (SKIPPED)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "⚠️  VM firewall management disabled to prevent SSH lockout."
echo "   Configure Oracle Cloud Security List manually instead."
echo ""

# Step 5: Set up cleanup cron job
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 4: Setting up cleanup cron job"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
ssh "$REMOTE_HOST" 'bash -s' < setup-cron.sh
echo ""

# Final summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Setup Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🎯 Next Steps:"
echo ""
echo "1. ⚠️  Configure Oracle Cloud Security List (REQUIRED)"
echo "   Add Ingress Rule for port 5000 (or 80/443 for production)"
echo "   Oracle Console: Networking → VCN → Security Lists → Add Ingress Rule"
echo ""
echo "2. Test the server:"
echo "   curl http://129.80.134.46:5000/health"
echo ""
echo "3. Access the extension install page:"
echo "   http://129.80.134.46:5000/start"
echo ""
echo "4. For future updates, just run:"
echo "   ./deploy.sh"
echo ""
echo "📝 View logs:"
echo "   ssh $REMOTE_HOST 'tail -f nbj-condenser/server.log'"
echo ""
