#!/usr/bin/env python3
"""Test script to verify voice shortcut parsing."""

def test_voice_shortcut_parsing():
    """Test the provider/voice shortcut format."""
    test_cases = [
        # (input_voice, input_provider, expected_provider, expected_voice)
        ("edge/ryan", "elevenlabs", "edge", "ryan"),
        ("edge/aria", "elevenlabs", "edge", "aria"),
        ("elevenlabs/George", "edge", "elevenlabs", "George"),
        ("George", "elevenlabs", "elevenlabs", "George"),  # No slash, use default
        ("Ryan", "edge", "edge", "Ryan"),  # No slash, use default
    ]

    for voice_input, provider_input, expected_provider, expected_voice in test_cases:
        # Simulate the parsing logic
        voice = voice_input
        tts_provider = provider_input

        # Parse shortcut format: --voice=provider/voice
        if voice and '/' in voice:
            parts = voice.split('/', 1)
            if len(parts) == 2:
                provider_from_voice, voice_name = parts
                provider_from_voice = provider_from_voice.lower().strip()
                voice_name = voice_name.strip()

                # Validate provider
                if provider_from_voice not in ['elevenlabs', 'edge']:
                    print(f"❌ FAIL: Invalid provider '{provider_from_voice}'")
                    continue

                # Set provider and voice
                tts_provider = provider_from_voice
                voice = voice_name

        # Check results
        if tts_provider == expected_provider and voice == expected_voice:
            print(f"✓ PASS: '{voice_input}' with provider '{provider_input}' -> provider='{tts_provider}', voice='{voice}'")
        else:
            print(f"❌ FAIL: '{voice_input}' with provider '{provider_input}' -> expected provider='{expected_provider}', voice='{expected_voice}', got provider='{tts_provider}', voice='{voice}'")

if __name__ == "__main__":
    print("Testing voice shortcut parsing...\n")
    test_voice_shortcut_parsing()
    print("\nAll tests completed!")
