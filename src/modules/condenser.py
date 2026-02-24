"""Content condensation module using LLMs."""

import json
from pathlib import Path
from typing import Dict, Any
import logging
from anthropic import Anthropic

from ..utils.prompt_templates import get_condense_prompt

logger = logging.getLogger(__name__)


class ContentCondenser:
    """Condenses transcript using Claude API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        """
        Initialize the condenser.

        Args:
            api_key: Anthropic API key
            model: Claude model to use
        """
        self.client = Anthropic(api_key=api_key)
        self.model = model

    def condense(
        self,
        transcript: str,
        duration_minutes: float,
        aggressiveness: int = 5,
        target_reduction_percentage: int = None
    ) -> Dict[str, Any]:
        """
        Condense transcript to shorter version.

        Args:
            transcript: Full transcript text
            duration_minutes: Original video duration in minutes
            aggressiveness: Condensing aggressiveness (1-10)
            target_reduction_percentage: Optional specific reduction target

        Returns:
            Dictionary with:
                - condensed_script: The condensed script text
                - original_duration_minutes: Original duration
                - estimated_condensed_duration_minutes: Estimated new duration
                - reduction_percentage: Actual reduction achieved
                - key_points_preserved: List of key points kept
                - removed_content_summary: Summary of removed content
                - quality_notes: Notes about the condensation
        """
        try:
            logger.info(f"Starting content condensation (aggressiveness: {aggressiveness}/10)")

            # Generate the prompt
            prompt = get_condense_prompt(
                transcript=transcript,
                duration_minutes=duration_minutes,
                aggressiveness=aggressiveness,
                target_reduction_percentage=target_reduction_percentage
            )

            # Call Claude API
            message = self.client.messages.create(
                model=self.model,
                max_tokens=16000,
                temperature=0.3,  # Lower temperature for more consistent output
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            # Extract the response
            response_text = message.content[0].text

            # Parse JSON response
            # Try to extract JSON if wrapped in markdown code blocks
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()

            result = json.loads(response_text)

            # Ensure original_duration_minutes is in the result (in case LLM omitted it)
            if 'original_duration_minutes' not in result:
                result['original_duration_minutes'] = duration_minutes

            logger.info(
                f"Condensation completed: {result.get('reduction_percentage', 0):.1f}% reduction, "
                f"{result.get('original_duration_minutes', 0):.1f}min -> "
                f"{result.get('estimated_condensed_duration_minutes', 0):.1f}min"
            )

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.error(f"Response was: {response_text[:500]}")
            raise RuntimeError(f"Failed to parse condensed content: {e}")

        except Exception as e:
            from ..utils.audio_utils import extract_api_error_message
            from ..utils.exceptions import ApiError
            from colorama import Fore, Style
            error_msg = extract_api_error_message(e, "Anthropic")
            if error_msg:
                print(f"\n{Fore.RED}{error_msg}{Style.RESET_ALL}\n")
                raise ApiError(error_msg) from None
            else:
                logger.error(f"Content condensation failed: {e}")
                raise RuntimeError(f"Failed to condense content: {e}")

    def save_condensed_script(
        self,
        condensed_result: Dict[str, Any],
        output_path: Path
    ) -> Path:
        """
        Save condensed script to file.

        Args:
            condensed_result: Result from condense()
            output_path: Path to output JSON file

        Returns:
            Path to saved file
        """
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(condensed_result, f, indent=2, ensure_ascii=False)

            logger.info(f"Condensed script saved to: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Failed to save condensed script: {e}")
            raise RuntimeError(f"Failed to save condensed script: {e}")

    def load_condensed_script(self, script_path: Path) -> Dict[str, Any]:
        """
        Load condensed script from file.

        Args:
            script_path: Path to script JSON file

        Returns:
            Condensed script dictionary
        """
        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                script = json.load(f)

            logger.info(f"Condensed script loaded from: {script_path}")
            return script

        except Exception as e:
            logger.error(f"Failed to load condensed script: {e}")
            raise RuntimeError(f"Failed to load condensed script: {e}")

    def validate_condensed_script(self, script: Dict[str, Any]) -> bool:
        """
        Validate that condensed script has required fields.

        Args:
            script: Condensed script dictionary

        Returns:
            True if valid, raises exception otherwise
        """
        required_fields = [
            'condensed_script',
            'original_duration_minutes',
            'estimated_condensed_duration_minutes',
            'reduction_percentage'
        ]

        for field in required_fields:
            if field not in script:
                raise ValueError(f"Missing required field: {field}")

            if field == 'condensed_script' and not script[field].strip():
                raise ValueError("Condensed script is empty")

        return True
