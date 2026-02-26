#!/usr/bin/env python3
"""Test condensation with a transcript.json file."""

import sys
import json
from pathlib import Path
from colorama import Fore, Style, init as colorama_init

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_settings
from src.modules.condenser import ContentCondenser

colorama_init()


def main():
    if len(sys.argv) < 2:
        print(f"{Fore.YELLOW}Usage: python test_condense.py <path_to_transcript.json> [aggressiveness]{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Example: python test_condense.py temp/VIDEO_ID/transcript.json 5{Style.RESET_ALL}")
        sys.exit(1)

    transcript_path = Path(sys.argv[1])
    aggressiveness = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    if not transcript_path.exists():
        print(f"{Fore.RED}Error: Transcript file not found: {transcript_path}{Style.RESET_ALL}")
        sys.exit(1)

    # Load transcript
    print(f"\n{Fore.CYAN}Loading transcript...{Style.RESET_ALL}")
    with open(transcript_path, 'r') as f:
        transcript_data = json.load(f)

    transcript_text = transcript_data.get('text', '')
    duration_minutes = transcript_data.get('duration', 0) / 60

    if not transcript_text:
        print(f"{Fore.RED}Error: No transcript text found in file{Style.RESET_ALL}")
        sys.exit(1)

    # Get settings
    settings = get_settings()

    # Initialize condenser (using Claude by default)
    print(f"{Fore.CYAN}Initializing condenser...{Style.RESET_ALL}")
    condenser = ContentCondenser(
        provider="claude",
        anthropic_api_key=settings.anthropic_api_key,
        model="claude-sonnet-4-20250514"
    )

    # Calculate word counts
    original_word_count = len(transcript_text.split())

    print(f"\n{Fore.GREEN}{'='*80}{Style.RESET_ALL}")
    print(f"{Fore.GREEN}Condensation Test{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{'='*80}{Style.RESET_ALL}")
    print(f"Transcript: {transcript_path}")
    print(f"Duration: {duration_minutes:.1f} minutes")
    print(f"Original word count: {original_word_count:,} words")
    print(f"Aggressiveness: {aggressiveness}/10")

    # Calculate target
    target_reduction_percentage = 20 + (aggressiveness * 5.5)
    retention_percentage = 100 - target_reduction_percentage
    target_word_count = int(original_word_count * (retention_percentage / 100))

    print(f"Target reduction: {target_reduction_percentage:.1f}%")
    print(f"Target word count: {target_word_count:,} words")
    print(f"{Fore.GREEN}{'='*80}{Style.RESET_ALL}\n")

    # Condense
    print(f"{Fore.CYAN}Condensing transcript...{Style.RESET_ALL}\n")
    result = condenser.condense(
        transcript=transcript_text,
        duration_minutes=duration_minutes,
        aggressiveness=aggressiveness
    )

    # Analyze results
    condensed_script = result.get('condensed_script', '')
    condensed_word_count = len(condensed_script.split())
    actual_reduction = ((original_word_count - condensed_word_count) / original_word_count) * 100
    actual_retention = 100 - actual_reduction

    # Display results
    print(f"\n{Fore.GREEN}{'='*80}{Style.RESET_ALL}")
    print(f"{Fore.GREEN}Results{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{'='*80}{Style.RESET_ALL}")
    print(f"Original word count:  {original_word_count:,} words")
    print(f"Condensed word count: {condensed_word_count:,} words")
    print(f"Target word count:    {target_word_count:,} words")
    print()
    print(f"Target reduction:     {target_reduction_percentage:.1f}%")
    print(f"Actual reduction:     {actual_reduction:.1f}%")
    print()
    print(f"Target retention:     {retention_percentage:.1f}%")
    print(f"Actual retention:     {actual_retention:.1f}%")
    print()

    # Check accuracy
    tolerance = 10  # Within 10 percentage points
    if abs(actual_reduction - target_reduction_percentage) <= tolerance:
        print(f"{Fore.GREEN}✓ Condensation accuracy: GOOD (within {tolerance}%){Style.RESET_ALL}")
    else:
        diff = abs(actual_reduction - target_reduction_percentage)
        if actual_reduction > target_reduction_percentage:
            print(f"{Fore.RED}✗ Over-condensed by {diff:.1f} percentage points{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}✗ Under-condensed by {diff:.1f} percentage points{Style.RESET_ALL}")

    print(f"{Fore.GREEN}{'='*80}{Style.RESET_ALL}\n")

    # Show key points preserved
    if 'key_points_preserved' in result:
        print(f"{Fore.CYAN}Key Points Preserved:{Style.RESET_ALL}")
        for i, point in enumerate(result['key_points_preserved'], 1):
            print(f"  {i}. {point}")
        print()

    # Show removed content summary
    if 'removed_content_summary' in result:
        print(f"{Fore.CYAN}Removed Content:{Style.RESET_ALL}")
        print(f"  {result['removed_content_summary']}")
        print()

    # Show quality notes
    if 'quality_notes' in result:
        print(f"{Fore.CYAN}Quality Notes:{Style.RESET_ALL}")
        print(f"  {result['quality_notes']}")
        print()

    # Show first 500 chars of condensed script
    print(f"{Fore.CYAN}Condensed Script Preview:{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'─'*80}{Style.RESET_ALL}")
    preview_length = 500
    preview = condensed_script[:preview_length]
    if len(condensed_script) > preview_length:
        preview += "..."
    print(preview)
    print(f"{Fore.CYAN}{'─'*80}{Style.RESET_ALL}\n")


if __name__ == "__main__":
    main()
