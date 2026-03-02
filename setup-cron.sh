#!/bin/bash
# NBJ Condenser - Set up cron job for cleanup
# Run this on the VM after initial deployment
#
# Usage: ssh conciser 'bash -s' < setup-cron.sh

set -e

PROJECT_DIR="/home/opc/nbj-condenser"
CRON_SCRIPT="$PROJECT_DIR/scripts/cleanup.sh"

echo "⏰ Setting up cleanup cron job..."

# Ensure cleanup script exists
if [ ! -f "$CRON_SCRIPT" ]; then
    echo "❌ Error: cleanup.sh not found at $CRON_SCRIPT"
    echo "   Run ./deploy.sh first to deploy the project"
    exit 1
fi

# Make cleanup script executable
chmod +x "$CRON_SCRIPT"

# Add cron job (runs daily at 3 AM)
CRON_LINE="0 3 * * * $CRON_SCRIPT >> $PROJECT_DIR/cleanup.log 2>&1"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "$CRON_SCRIPT"; then
    echo "   Cron job already exists, skipping..."
else
    # Add to crontab
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
    echo "   ✅ Cron job added: Daily cleanup at 3 AM"
fi

# Show current crontab
echo ""
echo "Current crontab:"
crontab -l

echo ""
echo "✅ Cron setup complete!"
echo "📝 Cleanup logs will be written to: $PROJECT_DIR/cleanup.log"
echo ""
echo "To test the cleanup script manually:"
echo "  ssh conciser '$CRON_SCRIPT'"
