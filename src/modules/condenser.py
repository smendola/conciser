"""Content condensation module using LLMs."""

import json
import time
from pathlib import Path
from typing import Dict, Any, Literal
import logging
from anthropic import Anthropic
from openai import OpenAI

from ..utils.prompt_templates import get_condense_prompt

logger = logging.getLogger(__name__)


class ContentCondenser:
    """Condenses transcript using Claude or OpenAI API."""

    def __init__(
        self,
        provider: Literal["claude", "openai"] = "openai",
        api_key: str = None,
        openai_api_key: str = None,
        anthropic_api_key: str = None,
        model: str = None
    ):
        """
        Initialize the condenser.

        Args:
            provider: LLM provider to use ("claude" or "openai")
            api_key: API key (deprecated, use provider-specific keys)
            openai_api_key: OpenAI API key
            anthropic_api_key: Anthropic API key
            model: Model to use (provider-specific defaults if not specified)
        """
        self.provider = provider.lower()

        if self.provider == "claude":
            key = anthropic_api_key or api_key
            if not key:
                raise ValueError("Anthropic API key required for Claude provider")
            self.client = Anthropic(api_key=key)
            self.model = model or "claude-sonnet-4-20250514"

        elif self.provider == "openai":
            key = openai_api_key or api_key
            if not key:
                raise ValueError("OpenAI API key required for OpenAI provider")
            self.client = OpenAI(api_key=key)
            self.model = model or "gpt-4o"

        else:
            raise ValueError(f"Unsupported provider: {provider}. Use 'claude' or 'openai'.")

    def condense(
        self,
        transcript: str,
        duration_minutes: float,
        aggressiveness: int = 5,
        target_reduction_percentage: int = None,
        max_retries: int = 5,
        initial_retry_delay: float = 2.0
    ) -> Dict[str, Any]:
        """
        Condense transcript to shorter version.

        Args:
            transcript: Full transcript text
            duration_minutes: Original video duration in minutes
            aggressiveness: Condensing aggressiveness (1-10)
            target_reduction_percentage: Optional specific reduction target
            max_retries: Maximum number of retry attempts for transient errors
            initial_retry_delay: Initial delay in seconds before first retry (doubles each time)

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
            logger.info(f"Starting content condensation (provider: {self.provider}, model: {self.model}, aggressiveness: {aggressiveness}/10)")

            # Generate the prompt
            prompt = get_condense_prompt(
                transcript=transcript,
                duration_minutes=duration_minutes,
                aggressiveness=aggressiveness,
                target_reduction_percentage=target_reduction_percentage
            )

            # Retry logic for transient errors
            response_text = None
            last_error = None

            for attempt in range(max_retries + 1):
                try:
                    # Call LLM API based on provider
                    if self.provider == "claude":
                        message = self.client.messages.create(
                            model=self.model,
                            max_tokens=16000,
                            temperature=0.3,
                            messages=[
                                {
                                    "role": "user",
                                    "content": prompt
                                }
                            ]
                        )
                        response_text = message.content[0].text

                    elif self.provider == "openai":
                        completion = self.client.chat.completions.create(
                            model=self.model,
                            messages=[
                                {
                                    "role": "system",
                                    "content": "You are an expert content editor skilled at condensing transcripts while preserving key information. Always respond with valid JSON."
                                },
                                {
                                    "role": "user",
                                    "content": prompt
                                }
                            ],
                            temperature=0.3,
                            max_tokens=16000,
                            response_format={"type": "json_object"}
                        )
                        response_text = completion.choices[0].message.content

                    break  # Success! Exit retry loop

                except Exception as api_error:
                    last_error = api_error
                    error_str = str(api_error)

                    # Check if this is a retryable error (529 Overloaded, rate limits, network issues)
                    is_retryable = (
                        "529" in error_str or
                        "overloaded" in error_str.lower() or
                        "rate_limit" in error_str.lower() or
                        "timeout" in error_str.lower() or
                        "connection" in error_str.lower()
                    )

                    if not is_retryable or attempt >= max_retries:
                        # Not retryable or out of retries
                        raise

                    # Calculate exponential backoff delay
                    delay = initial_retry_delay * (2 ** attempt)
                    logger.warning(
                        f"API request failed (attempt {attempt + 1}/{max_retries + 1}): {error_str}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)

            # Safety check
            if response_text is None:
                raise RuntimeError(f"API request failed after {max_retries + 1} attempts. Last error: {last_error}")

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
