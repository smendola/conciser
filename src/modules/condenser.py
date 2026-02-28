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
            self.model = model or "gpt-5.2"

        else:
            raise ValueError(f"Unsupported provider: {provider}. Use 'claude' or 'openai'.")

    def init_chains(self) -> dict:
        """
        Initialize OpenAI Responses API chains for all 10 aggressiveness levels.

        For each level, sends the combined system prompt (level 1 + level 2) with
        a seed "Ready." message and stores the resulting response ID. Subsequent
        condense() calls continue from that chain tip, skipping the system prompt.

        Returns:
            Dict mapping aggressiveness level strings ("1"-"10") to response IDs.
        """
        if self.provider != "openai":
            raise ValueError("Chain initialization is only supported for the OpenAI provider")

        import textwrap
        from ..utils.chain_store import save_chains
        from ..utils.prompt_templates import CONDENSE_SYSTEM_PROMPT, STRATEGY_PROMPTS, RETENTION_RANGES

        chains = {}
        for level in range(1, 11):
            retention_range = RETENTION_RANGES[level]
            strategy_prompt = textwrap.dedent(STRATEGY_PROMPTS[level]).strip().format(retention_range=retention_range)
            system_prompt = CONDENSE_SYSTEM_PROMPT.strip() + "\n\n" + strategy_prompt

            logger.info(f"Initializing chain for aggressiveness {level}/10...")
            response = self.client.responses.create(
                model=self.model,
                instructions=system_prompt,
                input="Ready.",
            )
            chains[str(level)] = response.id
            logger.info(f"  aggressiveness {level} → {response.id}")

        save_chains(self.model, chains)
        return chains

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

            # Generate the prompts (system and user)
            system_prompt, user_prompt = get_condense_prompt(
                transcript=transcript,
                duration_minutes=duration_minutes,
                aggressiveness=aggressiveness,
                target_reduction_percentage=target_reduction_percentage
            )

            # Debug: Output the exact prompts being sent to LLM
            DEBUG_SHOW_PROMPT = False
            if DEBUG_SHOW_PROMPT:
                from colorama import Fore, Style
                print(f"\n{Fore.MAGENTA}{'='*80}")
                print(f"CONDENSER LLM SYSTEM PROMPT:")
                print(f"{'='*80}")
                print(system_prompt)
                print(f"{'='*80}")
                print(f"CONDENSER LLM USER PROMPT:")
                print(f"{'='*80}")
                # Show the actual formatted prompt with word counts, but truncate the transcript
                if len(user_prompt) > 2000:
                    # Find where the transcript starts
                    transcript_marker = "<transcript>"
                    if transcript_marker in user_prompt:
                        prefix = user_prompt[:user_prompt.find(transcript_marker) + len(transcript_marker)]
                        print(prefix)
                        print()
                        print("[TRANSCRIPT TEXT TRUNCATED FOR DISPLAY]")
                        print()
                        print("</transcript>")
                    else:
                        print(user_prompt[:2000])
                        print("\n[PROMPT TRUNCATED FOR DISPLAY]")
                else:
                    print(user_prompt)
                print(f"{'='*80}{Style.RESET_ALL}\n")

            # For OpenAI: resolve chain ID once before entering the retry loop
            openai_chain_id = None
            if self.provider == "openai":
                from ..utils.chain_store import load_chains
                chains = load_chains(self.model)
                if chains is None:
                    logger.info("Chain IDs missing or stale — running init_chains()...")
                    try:
                        chains = self.init_chains()
                    except Exception as e:
                        logger.warning(f"init_chains() failed: {e} — falling back to chat completions")
                if chains is not None:
                    openai_chain_id = chains.get(str(aggressiveness))

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
                            # temperature=0.3,
                            system=system_prompt,
                            messages=[
                                {
                                    "role": "user",
                                    "content": user_prompt
                                }
                            ]
                        )
                        response_text = message.content[0].text

                    elif self.provider == "openai":
                        if openai_chain_id:
                            # Responses API: continue from pre-seeded chain (no system prompt needed)
                            response = self.client.responses.create(
                                model=self.model,
                                previous_response_id=openai_chain_id,
                                input=user_prompt,
                                text={"format": {"type": "json_object"}},
                                max_output_tokens=16000,
                            )
                            response_text = response.output_text
                        else:
                            # Fallback: chat completions with full system prompt
                            api_params = {
                                "model": self.model,
                                "messages": [
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": user_prompt},
                                ],
                                # "temperature": 0.3,
                                "response_format": {"type": "json_object"},
                            }
                            if self.model.startswith("gpt-5") or self.model.startswith("o1"):
                                api_params["max_completion_tokens"] = 16000
                            else:
                                api_params["max_tokens"] = 16000
                            completion = self.client.chat.completions.create(**api_params)
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

            # Add original_duration_minutes
            result['original_duration_minutes'] = duration_minutes

            # Calculate estimated_condensed_duration_minutes based on word count
            # Assume 150 words per minute speaking rate
            condensed_word_count = len(result.get('condensed_script', '').split())
            result['estimated_condensed_duration_minutes'] = condensed_word_count / 150.0

            # Calculate reduction_percentage based on word counts
            original_word_count = len(transcript.split())
            if original_word_count > 0:
                result['reduction_percentage'] = ((original_word_count - condensed_word_count) / original_word_count) * 100
            else:
                result['reduction_percentage'] = 0.0

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
