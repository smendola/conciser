#!/usr/bin/env python3
"""Test speech rate validation."""

import re
import pytest

def validate_speech_rate(speech_rate):
    """Test the validation regex."""
    if speech_rate == '+0%':
        return True, "Default rate (no change)"

    if re.match(r'^[+-]\d+%$', speech_rate):
        return True, "Valid format"
    else:
        return False, "Invalid format"


@pytest.mark.parametrize(
    "rate,expected_valid",
    [
        ("+0%", True),
        ("+25%", True),
        ("-10%", True),
        ("+100%", True),
        ("-50%", True),
        ("25%", False),
        ("+25", False),
        ("+-25%", False),
        ("+25.5%", False),
        ("fast", False),
        ("", False),
    ],
)
def test_validate_speech_rate(rate, expected_valid):
    is_valid, _message = validate_speech_rate(rate)
    assert is_valid == expected_valid


def test_settings_paths_resolve_from_project_root_regardless_of_cwd(monkeypatch):
    from src.config import get_settings
    from src.utils.project_root import get_project_root

    project_root = get_project_root()
    monkeypatch.chdir(project_root / "server")

    s = get_settings()
    assert s.temp_dir == (project_root / "temp").resolve()
    assert s.output_dir == (project_root / "output").resolve()
