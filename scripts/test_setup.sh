#!/bin/bash
# Test that everything is set up correctly

echo "Testing Conciser Setup"
echo "====================="
echo

# Check Python
echo -n "Python version: "
python3 --version

# Check ffmpeg
echo -n "ffmpeg version: "
ffmpeg -version | head -n1

# Check pip packages
echo
echo "Checking installed packages..."
pip show yt-dlp openai anthropic elevenlabs click > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✓ Core packages installed"
else
    echo "✗ Some packages missing"
fi

# Check directories
echo
echo "Checking directories..."
[ -d "temp" ] && echo "✓ temp/ exists" || echo "✗ temp/ missing"
[ -d "output" ] && echo "✓ output/ exists" || echo "✗ output/ missing"

# Check configuration
echo
echo "Checking configuration..."
[ -f ".env" ] && echo "✓ .env exists" || echo "✗ .env missing (run: conciser setup)"

# Run conciser check
echo
echo "Running conciser diagnostics..."
echo "================================"
conciser check

echo
echo "Test complete!"
