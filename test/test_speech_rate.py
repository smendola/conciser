#!/usr/bin/env python3
"""Test Edge TTS speech rate parameter."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from pathlib import Path
from modules.edge_tts import EdgeTTS

def test_speech_rate():
    """Test different speech rates."""
    edge = EdgeTTS()

    test_text = "This is a test of speech rate adjustment."
    output_dir = Path("./temp")
    output_dir.mkdir(exist_ok=True)

    rates = ["-50%", "-25%", "+0%", "+25%", "+50%"]

    print("Testing Edge TTS with different speech rates...\n")

    for rate in rates:
        output_path = output_dir / f"test_rate_{rate.replace('%', 'pct').replace('+', 'plus').replace('-', 'minus')}.mp3"

        try:
            print(f"Generating with rate={rate}...")
            edge.generate_speech(
                text=test_text,
                output_path=output_path,
                voice="en-US-AriaNeural",
                rate=rate
            )

            if output_path.exists():
                size = output_path.stat().st_size
                print(f"  ✓ Success: {output_path.name} ({size:,} bytes)")
            else:
                print(f"  ❌ Failed: File not created")

        except Exception as e:
            print(f"  ❌ Error: {e}")

    print("\nTest complete! Check ./temp for generated audio files.")

if __name__ == "__main__":
    test_speech_rate()
