import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def _resolve_voice(voice: str, api_key: str) -> str:
    """
    Resolve voice name or ID to voice ID.

    Args:
        voice: Voice ID or name (e.g., "George" or "JBFqnCBsd6RMkjVDRZzb")
        api_key: ElevenLabs API key

    Returns:
        Voice ID if found, None otherwise
    """
    # If it looks like a voice ID (20+ alphanumeric chars), return as-is
    if len(voice) > 15 and voice.replace('-', '').isalnum():
        return voice

    # Otherwise, look up by name
    try:
        from ..modules.tts import VoiceCloner
        cloner = VoiceCloner(api_key)
        voices = cloner.list_voices()

        # Case-insensitive search
        voice_lower = voice.lower()
        for v in voices:
            # Check if name matches (partial or full)
            if voice_lower in v['name'].lower() or v['name'].lower().startswith(voice_lower):
                return v['voice_id']

        return None
    except Exception as e:
        logger.error(f"Failed to resolve voice: {e}")
        return None


def _format_script_into_paragraphs(script_text: str, api_key: str) -> str:
    """Format a script into paragraphs using Claude."""
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)

    prompt = f"""Format this script into natural paragraphs for better readability. Add paragraph breaks (using double newlines) at logical topic transitions and natural breaks. Each paragraph should cover a cohesive idea.

Rules:
- Use \\n\\n (double newline) to separate paragraphs
- Keep all the original text - don't summarize or change wording
- Only add paragraph breaks at natural transitions
- Aim for paragraphs of 3-5 sentences each
- Return ONLY the formatted text, no explanations

Script to format:
{script_text}"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            # temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )

        formatted_text = message.content[0].text.strip()
        return formatted_text
    except Exception as e:
        logger.error(f"Failed to format script: {e}")
        return None


def _load_videos_txt(filepath: Path = None) -> list:
    """
    Load (video_id, label_or_None) pairs from videos.txt.

    Format: one entry per line — "<video_id>  [optional label text]"
    Lines starting with # are comments and are ignored.

    Returns list of (video_id, label) tuples; label is None if the line has
    only a video ID with no following text.
    """
    if filepath is None:
        filepath = Path("videos.txt")
    if not filepath.exists():
        return []
    entries = []
    for line in filepath.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split(None, 1)  # split on first whitespace, max 2 parts
        video_id = parts[0]
        label = parts[1].strip() if len(parts) > 1 else None
        entries.append((video_id, label))
    return entries
