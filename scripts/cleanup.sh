#!/bin/bash
# NBJ Condenser - Cleanup old temp and output files
# Run this via cron to prevent disk space issues

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

TEMP_DIR="$PROJECT_DIR/temp"
OUTPUT_DIR="$PROJECT_DIR/output"
SERVER_OUTPUT_DIR="$PROJECT_DIR/server/output"

# Delete files older than 7 days
DAYS_OLD=7

echo "[$(date)] Starting cleanup (files older than $DAYS_OLD days)..."

# Cleanup temp/
if [ -d "$TEMP_DIR" ]; then
    echo "Cleaning $TEMP_DIR..."
    find "$TEMP_DIR" -type f -mtime +$DAYS_OLD -delete
    find "$TEMP_DIR" -type d -empty -delete
    TEMP_SIZE=$(du -sh "$TEMP_DIR" 2>/dev/null | cut -f1)
    echo "  Temp dir size: $TEMP_SIZE"
fi

# Cleanup output/
if [ -d "$OUTPUT_DIR" ]; then
    echo "Cleaning $OUTPUT_DIR..."
    find "$OUTPUT_DIR" -type f -mtime +$DAYS_OLD -delete
    OUTPUT_SIZE=$(du -sh "$OUTPUT_DIR" 2>/dev/null | cut -f1)
    echo "  Output dir size: $OUTPUT_SIZE"
fi

# Cleanup server/output/
if [ -d "$SERVER_OUTPUT_DIR" ]; then
    echo "Cleaning $SERVER_OUTPUT_DIR..."
    find "$SERVER_OUTPUT_DIR" -type f -mtime +$DAYS_OLD -delete
    SERVER_OUTPUT_SIZE=$(du -sh "$SERVER_OUTPUT_DIR" 2>/dev/null | cut -f1)
    echo "  Server output dir size: $SERVER_OUTPUT_SIZE"
fi

# Cleanup old log files (keep last 30 days)
if [ -f "$PROJECT_DIR/nbj.log" ]; then
    find "$PROJECT_DIR" -name "*.log" -type f -mtime +30 -delete
fi

echo "[$(date)] Cleanup complete!"
