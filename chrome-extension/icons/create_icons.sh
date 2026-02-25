#!/bin/bash
# Simple script to create placeholder icons using ImageMagick
# Run: bash create_icons.sh

convert -size 16x16 xc:#1a73e8 -pointsize 12 -fill white -gravity center -draw "text 0,0 'C'" icon16.png
convert -size 48x48 xc:#1a73e8 -pointsize 36 -fill white -gravity center -draw "text 0,0 'C'" icon48.png
convert -size 128x128 xc:#1a73e8 -pointsize 96 -fill white -gravity center -draw "text 0,0 'C'" icon128.png

echo "Icons created!"
