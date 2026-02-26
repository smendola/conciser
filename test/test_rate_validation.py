#!/usr/bin/env python3
"""Test speech rate validation."""

import re

def validate_speech_rate(speech_rate):
    """Test the validation regex."""
    if speech_rate == '+0%':
        return True, "Default rate (no change)"

    if re.match(r'^[+-]\d+%$', speech_rate):
        return True, "Valid format"
    else:
        return False, "Invalid format"

# Test cases
test_cases = [
    ("+0%", True),
    ("+25%", True),
    ("-10%", True),
    ("+100%", True),
    ("-50%", True),
    ("25%", False),      # Missing sign
    ("+25", False),       # Missing %
    ("+-25%", False),     # Double sign
    ("+25.5%", False),    # Decimal
    ("fast", False),      # Invalid
    ("", False),          # Empty
]

print("Testing speech rate validation...\n")

for rate, expected_valid in test_cases:
    is_valid, message = validate_speech_rate(rate)

    if is_valid == expected_valid:
        status = "✓ PASS"
    else:
        status = "❌ FAIL"

    print(f"{status}: '{rate}' -> {is_valid} ({message})")

print("\nValidation tests complete!")
