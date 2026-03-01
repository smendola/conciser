from __future__ import annotations


def get_condense_output_json_schema() -> dict:
    return {
        "name": "condensed_transcript",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "condensed_script": {"type": "string", "minLength": 1},
                "key_points_preserved": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "removed_content_summary": {"type": "string"},
                "quality_notes": {"type": "string"},
            },
            "required": [
                "condensed_script",
                "key_points_preserved",
                "removed_content_summary",
                "quality_notes",
            ],
            "additionalProperties": False,
        },
    }
