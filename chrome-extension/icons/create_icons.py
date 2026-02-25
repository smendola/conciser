#!/usr/bin/env python3
"""Create simple placeholder icons for Chrome extension."""

from PIL import Image, ImageDraw, ImageFont

def create_icon(size, output_file):
    """Create a simple blue icon with white 'C'."""
    # Create blue background
    img = Image.new('RGB', (size, size), color='#1a73e8')
    draw = ImageDraw.Draw(img)

    # Draw white 'C' in center
    font_size = int(size * 0.6)
    try:
        # Try to use a nice font
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except:
        # Fallback to default
        font = ImageFont.load_default()

    # Calculate text position (center)
    text = "C"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (size - text_width) // 2
    y = (size - text_height) // 2

    draw.text((x, y), text, fill='white', font=font)

    img.save(output_file)
    print(f"Created {output_file}")

if __name__ == '__main__':
    create_icon(16, 'icon16.png')
    create_icon(48, 'icon48.png')
    create_icon(128, 'icon128.png')
