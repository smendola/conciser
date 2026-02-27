#!/usr/bin/env python3
"""
Test driver for condensation prompt testing.

Tests different aggressiveness levels on multiple videos,
outputs condensed text and statistics for manual review.
"""

import sys
import json
import csv
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import click
from colorama import init as colorama_init, Fore, Style

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_settings
from src.modules.downloader import VideoDownloader
from src.modules.condenser import ContentCondenser
from src.pipeline import CondenserPipeline
from src.utils.prompt_templates import get_condense_prompt, TARGET_RETENTION

colorama_init()


def load_videos_txt(filepath: Path = Path("videos.txt")) -> List[str]:
    """Load video IDs from videos.txt file (one ID per line)."""
    if not filepath.exists():
        print(f"{Fore.YELLOW}Warning: {filepath} not found. Creating example file.{Style.RESET_ALL}")
        with open(filepath, 'w') as f:
            f.write("dQw4w9WgXcQ\n")
            f.write("jNQXAC9IVRw\n")
        return ["dQw4w9WgXcQ", "jNQXAC9IVRw"]

    with open(filepath, 'r') as f:
        video_ids = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    return video_ids


def parse_video_spec(spec: str, all_videos: List[str]) -> List[str]:
    """
    Parse video specification which can be:
    - Comma-separated indices (1-based): "1,2,3"
    - Comma-separated video IDs: "dQw4w9WgXcQ,jNQXAC9IVRw"
    - Mix of both: "1,2,dQw4w9WgXcQ"
    """
    parts = [p.strip() for p in spec.split(',')]
    result = []

    for part in parts:
        # Try to parse as integer (1-based index)
        try:
            idx = int(part)
            if 1 <= idx <= len(all_videos):
                result.append(all_videos[idx - 1])
            else:
                print(f"{Fore.YELLOW}Warning: Index {idx} out of range (1-{len(all_videos)}), skipping{Style.RESET_ALL}")
        except ValueError:
            # Not an integer, treat as video ID
            result.append(part)

    return result


def parse_aggr_spec(spec: str) -> List[int]:
    """Parse aggressiveness specification: "1,2,3" -> [1, 2, 3]"""
    parts = [p.strip() for p in spec.split(',')]
    result = []

    for part in parts:
        try:
            aggr = int(part)
            if 1 <= aggr <= 10:
                result.append(aggr)
            else:
                print(f"{Fore.YELLOW}Warning: Aggressiveness {aggr} out of range (1-10), skipping{Style.RESET_ALL}")
        except ValueError:
            print(f"{Fore.YELLOW}Warning: Invalid aggressiveness '{part}', skipping{Style.RESET_ALL}")

    return result


def condense_video_at_level(
    video_id: str,
    aggressiveness: int,
    settings,
    output_dir: Path,
    transcript_cache: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Condense a single video at a single aggressiveness level.

    Args:
        video_id: YouTube video ID
        aggressiveness: Aggressiveness level (1-10)
        settings: App settings
        output_dir: Directory to save outputs
        transcript_cache: Dictionary to cache transcripts (keyed by video_id)

    Returns:
        Dictionary with stats and results
    """
    print(f"\n{Fore.CYAN}Processing: {video_id} at aggressiveness {aggressiveness}/10{Style.RESET_ALL}")

    try:
        # Check if transcript is cached
        if video_id in transcript_cache:
            print(f"  {Fore.GREEN}Using cached transcript{Style.RESET_ALL}")
            transcript = transcript_cache[video_id]['transcript']
            metadata = transcript_cache[video_id]['metadata']
            already_cached = True
        else:
            already_cached = False
            # Look for existing transcript first
            transcript_file = None
            for folder in settings.temp_dir.iterdir():
                if folder.is_dir() and folder.name.startswith(video_id):
                    potential_transcript = folder / "transcript.json"
                    if potential_transcript.exists():
                        transcript_file = potential_transcript
                        break

            if transcript_file and transcript_file.exists():
                print(f"  {Fore.YELLOW}Loading existing transcript from disk...{Style.RESET_ALL}")
                with open(transcript_file, 'r') as f:
                    transcript_data = json.load(f)
                transcript = transcript_data['text']

                # Load metadata if available
                metadata_file = transcript_file.parent / "metadata.json"
                if metadata_file.exists():
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                else:
                    metadata = {'title': video_id, 'duration': 0}

                # Cache it
                transcript_cache[video_id] = {
                    'transcript': transcript,
                    'metadata': metadata
                }
            else:
                # Need to download and transcribe - use pipeline methods to avoid duplication
                print(f"  {Fore.YELLOW}Downloading video...{Style.RESET_ALL}")
                pipeline = CondenserPipeline(settings)

                # Download using pipeline method
                download_result = pipeline._download_video(
                    f"https://youtube.com/watch?v={video_id}",
                    quality="720p"
                )
                video_path = Path(download_result['video_path'])
                video_folder = Path(download_result['video_folder'])
                metadata = download_result['metadata']

                # Transcribe using pipeline method (handles YouTube API + Whisper fallback)
                print(f"  {Fore.YELLOW}Getting transcript...{Style.RESET_ALL}")
                transcript_result = pipeline._transcribe_video(video_path, video_folder, video_id)
                transcript = transcript_result['text']

                # Cache it
                transcript_cache[video_id] = {
                    'transcript': transcript,
                    'metadata': metadata
                }

        # Print input transcript once per video (first time only)
        if not already_cached:
            print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}INPUT TRANSCRIPT (Video: {video_id}){Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Word count: {len(transcript.split()):,}{Style.RESET_ALL}")
            print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

        # Condense at specified aggressiveness level
        print(f"  {Fore.YELLOW}Condensing at level {aggressiveness}/10...{Style.RESET_ALL}")
        condenser = ContentCondenser(
            api_key=settings.openai_api_key,
            model="gpt-5.2"
        )

        duration_minutes = metadata.get('duration', 0) / 60
        condensed_result = condenser.condense(
            transcript=transcript,
            duration_minutes=duration_minutes,
            aggressiveness=aggressiveness
        )

        # Calculate stats
        original_word_count = len(transcript.split())
        condensed_word_count = len(condensed_result['condensed_script'].split())

        # Get target from imported table (single source of truth)
        target_retention_pct = TARGET_RETENTION.get(aggressiveness, 30)
        target_reduction = 100 - target_retention_pct
        target_word_count = int(original_word_count * (target_retention_pct / 100))

        # Calculate actual retention and reduction
        actual_retention = (condensed_word_count / original_word_count) * 100
        actual_reduction = 100 - actual_retention

        # Save condensed text with new filename format: yt_{vid_id}_agg_{agg}.txt
        output_file = output_dir / f"yt_{video_id}_agg_{aggressiveness}.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"Video: {metadata.get('title', video_id)}\n")
            f.write(f"Video ID: {video_id}\n")
            f.write(f"Aggressiveness: {aggressiveness}/10\n")
            f.write(f"Original words: {original_word_count:,}\n")
            f.write(f"Condensed words: {condensed_word_count:,}\n")
            f.write(f"Actual reduction: {actual_reduction:.1f}%\n")
            f.write(f"Target reduction: {target_reduction:.1f}%\n")
            f.write(f"Error: {abs(actual_reduction - target_reduction):.1f}%\n")
            f.write("=" * 80 + "\n\n")
            f.write(condensed_result['condensed_script'])
            f.write("\n\n" + "=" * 80 + "\n")
            f.write("KEY POINTS PRESERVED:\n")
            for i, point in enumerate(condensed_result.get('key_points_preserved', []), 1):
                f.write(f"{i}. {point}\n")
            f.write("\n" + "=" * 80 + "\n")
            f.write(f"REMOVED: {condensed_result.get('removed_content_summary', 'N/A')}\n")
            f.write(f"NOTES: {condensed_result.get('quality_notes', 'N/A')}\n")

        # Save JSON for machine processing
        json_file = output_dir / f"yt_{video_id}_agg_{aggressiveness}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            result_data = {
                'video_id': video_id,
                'title': metadata.get('title', video_id),
                'aggressiveness': aggressiveness,
                'original_word_count': original_word_count,
                'condensed_word_count': condensed_word_count,
                'target_reduction_percentage': target_reduction,
                'actual_reduction_percentage': actual_reduction,
                'error_percentage': abs(actual_reduction - target_reduction),
                'condensed_result': condensed_result,
                'timestamp': datetime.now().isoformat()
            }
            json.dump(result_data, f, indent=2, ensure_ascii=False)

        error = actual_retention - target_retention_pct
        error_color = Fore.GREEN if abs(error) < 5 else Fore.YELLOW if abs(error) < 10 else Fore.RED
        print(f"  {Fore.GREEN}✓ Complete: {condensed_word_count:,} words (target: {target_retention_pct:.1f}%, actual: {actual_retention:.1f}%, error: {error_color}{error:+.1f}%{Style.RESET_ALL}{Fore.GREEN}){Style.RESET_ALL}")
        print(f"  {Fore.GREEN}  Saved to: {output_file}{Style.RESET_ALL}")

        return {
            'video_id': video_id,
            'title': metadata.get('title', video_id),
            'aggressiveness': aggressiveness,
            'original_words': original_word_count,
            'target_words': target_word_count,
            'condensed_words': condensed_word_count,
            'target_retention': target_retention_pct,
            'actual_retention': actual_retention,
            'target_reduction': target_reduction,
            'actual_reduction': actual_reduction,
            'error_pct': error,  # actual - target (positive = over target)
            'success': True,
            'error': None
        }

    except Exception as e:
        print(f"  {Fore.RED}✗ Error: {e}{Style.RESET_ALL}")
        return {
            'video_id': video_id,
            'title': video_id,
            'aggressiveness': aggressiveness,
            'original_words': 0,
            'target_words': 0,
            'condensed_words': 0,
            'target_retention': 0,
            'actual_retention': 0,
            'target_reduction': 0,
            'actual_reduction': 0,
            'error_pct': 0,
            'success': False,
            'error': str(e)
        }


@click.command()
@click.option(
    '--videos',
    '-v',
    default=None,
    help='Video specification: comma-separated 1-based indices or video IDs (e.g., "1,2,3" or "1,dQw4w9WgXcQ")'
)
@click.option(
    '--aggressiveness',
    '-a',
    default=None,
    help='Aggressiveness levels: comma-separated values 1-10 (e.g., "1,5,10")'
)
@click.option(
    '--output-dir',
    '-o',
    type=click.Path(),
    default='test_outputs',
    help='Output directory for test results (default: test_outputs)'
)
@click.option(
    '--re-summarize',
    is_flag=True,
    help='Re-generate summary table from existing JSON outputs without re-running tests'
)
def main(videos, aggressiveness, output_dir, re_summarize):
    """
    Test driver for condensation prompt testing.

    Reads video IDs from videos.txt (one per line).

    Examples:

        # Run all videos at all aggressiveness levels (1-10)
        python test_condense.py

        # Test videos 1, 2, 3 from videos.txt at all aggressiveness levels
        python test_condense.py -v 1,2,3

        # Test all videos at aggressiveness 3 and 4
        python test_condense.py -a 3,4

        # Test videos 2 and 3 at aggressiveness 2 and 3
        python test_condense.py -v 2,3 -a 2,3

        # Mix indices and video IDs
        python test_condense.py -v 1,2,dQw4w9WgXcQ,jNQXAC9IVRw -a 5

        # Test specific video IDs not in videos.txt
        python test_condense.py -v dQw4w9WgXcQ,jNQXAC9IVRw -a 1,5,10
    """
    # Suppress httpx INFO logs
    import logging
    logging.getLogger('httpx').setLevel(logging.WARNING)

    print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Condensation Test Driver{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

    # Handle --re-summarize: read JSONs and print summary without re-running
    if re_summarize:
        output_path = Path(output_dir)
        if not output_path.exists():
            print(f"{Fore.RED}Error: Output directory '{output_dir}' does not exist{Style.RESET_ALL}")
            sys.exit(1)

        # Find all JSON files matching pattern yt_*_agg_*.json
        json_files = sorted(output_path.glob("yt_*_agg_*.json"))
        if not json_files:
            print(f"{Fore.RED}Error: No JSON output files found in '{output_dir}'{Style.RESET_ALL}")
            sys.exit(1)

        print(f"Found {len(json_files)} result files in {output_dir}\n")

        # Read all JSONs and build results
        results = []
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Extract stats from JSON
                original_words = data['original_word_count']
                condensed_words = data['condensed_word_count']
                target_reduction = data['target_reduction_percentage']
                actual_reduction = data['actual_reduction_percentage']

                # Calculate retention percentages
                target_retention = 100 - target_reduction
                actual_retention = 100 - actual_reduction
                target_words = int(original_words * (target_retention / 100))

                # Calculate error (actual - target)
                error_pct = actual_retention - target_retention

                results.append({
                    'video_id': data['video_id'],
                    'title': data['title'],
                    'aggressiveness': data['aggressiveness'],
                    'original_words': original_words,
                    'target_words': target_words,
                    'condensed_words': condensed_words,
                    'target_retention': target_retention,
                    'actual_retention': actual_retention,
                    'target_reduction': target_reduction,
                    'actual_reduction': actual_reduction,
                    'error_pct': error_pct,
                    'success': True,
                    'error': None
                })
            except Exception as e:
                print(f"{Fore.YELLOW}Warning: Failed to read {json_file.name}: {e}{Style.RESET_ALL}")
                continue

        # Sort results by video_id, then by aggressiveness (numerical)
        results.sort(key=lambda r: (r['video_id'], r['aggressiveness']))

        # Print summary table (reuse code below)
        print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Test Summary (from cached results){Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

        print(f"{'Video ID':<15} {'Aggr':<6} {'Original':<10} {'Target':<10} {'Condensed':<10} {'Target%':<8} {'Actual%':<8} {'Error%':<10} {'Status':<10}")
        print("-" * 108)

        for r in results:
            status = f"{Fore.GREEN}✓{Style.RESET_ALL}"
            error_pct = r['error_pct']
            error_color = Fore.GREEN if abs(error_pct) < 5 else Fore.YELLOW if abs(error_pct) < 10 else Fore.RED
            error_num_str = f"{error_pct:+.0f}%"
            error_str = f"{error_color}{error_num_str:<10}{Style.RESET_ALL}"

            print(f"{r['video_id']:<15} {r['aggressiveness']:<6} {r['original_words']:<10,} {r['target_words']:<10,} {r['condensed_words']:<10,} "
                  f"{r['target_retention']:<8.1f} {r['actual_retention']:<8.1f} {error_str} {status:<10}")

        # Calculate average accuracy
        avg_error = sum(abs(r['error_pct']) for r in results) / len(results) if results else 0
        print(f"\n{Fore.CYAN}Results:{Style.RESET_ALL}")
        print(f"  Total results: {len(results)}")
        print(f"\n{Fore.CYAN}Average retention error:{Style.RESET_ALL} {avg_error:.1f}% (distance from target)")
        print()

        return

    # Load videos from videos.txt
    all_videos = load_videos_txt()
    print(f"Loaded {len(all_videos)} videos from videos.txt")

    # Determine which videos to test
    if videos:
        video_ids = parse_video_spec(videos, all_videos)
    else:
        # No -v specified: use all videos from txt file
        video_ids = all_videos

    # Determine aggressiveness levels to test
    if aggressiveness:
        aggr_levels = parse_aggr_spec(aggressiveness)
    else:
        # No -a specified: use all levels 1-10
        aggr_levels = list(range(1, 11))

    if not video_ids:
        print(f"{Fore.RED}Error: No valid videos specified{Style.RESET_ALL}")
        sys.exit(1)

    if not aggr_levels:
        print(f"{Fore.RED}Error: No valid aggressiveness levels specified{Style.RESET_ALL}")
        sys.exit(1)

    print(f"Videos to test ({len(video_ids)}): {Fore.CYAN}{', '.join(video_ids)}{Style.RESET_ALL}")
    print(f"Aggressiveness levels ({len(aggr_levels)}): {Fore.CYAN}{', '.join(map(str, aggr_levels))}{Style.RESET_ALL}")
    print(f"Output directory: {Fore.CYAN}{output_dir}{Style.RESET_ALL}\n")

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Load settings
    settings = get_settings()

    # Check API keys
    if not settings.openai_api_key:
        print(f"{Fore.RED}Error: OPENAI_API_KEY not set in .env{Style.RESET_ALL}")
        sys.exit(1)

    # Transcript cache to avoid re-extracting
    transcript_cache = {}

    # Run tests
    results = []
    total_tests = len(video_ids) * len(aggr_levels)
    completed = 0

    for video_id in video_ids:
        for aggr in aggr_levels:
            completed += 1
            print(f"\n{Fore.CYAN}[{completed}/{total_tests}]{Style.RESET_ALL}")

            result = condense_video_at_level(
                video_id=video_id,
                aggressiveness=aggr,
                settings=settings,
                output_dir=output_path,
                transcript_cache=transcript_cache
            )
            results.append(result)

    # Generate summary report
    print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Test Summary{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

    # Sort results by video_id, then by aggressiveness (numerical)
    results.sort(key=lambda r: (r['video_id'], r['aggressiveness']))

    # Save CSV summary
    csv_file = output_path / f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'video_id', 'title', 'aggressiveness',
            'original_words', 'target_words', 'condensed_words',
            'target_retention', 'actual_retention',
            'target_reduction', 'actual_reduction',
            'error_pct',
            'success', 'error'
        ])
        writer.writeheader()
        writer.writerows(results)

    # Print summary table
    print(f"{'Video ID':<15} {'Aggr':<6} {'Original':<10} {'Target':<10} {'Condensed':<10} {'Target%':<8} {'Actual%':<8} {'Error%':<10} {'Status':<10}")
    print("-" * 108)

    success_count = 0
    for r in results:
        status = f"{Fore.GREEN}✓{Style.RESET_ALL}" if r['success'] else f"{Fore.RED}✗{Style.RESET_ALL}"
        if r['success']:
            success_count += 1
            # Colorize error percentage - pad BEFORE applying color
            error_pct = r['error_pct']
            error_color = Fore.GREEN if abs(error_pct) < 5 else Fore.YELLOW if abs(error_pct) < 10 else Fore.RED
            error_num_str = f"{error_pct:+.0f}%"
            error_str = f"{error_color}{error_num_str:<10}{Style.RESET_ALL}"
        else:
            error_str = "N/A       "  # Pad to match column width

        print(f"{r['video_id']:<15} {r['aggressiveness']:<6} {r['original_words']:<10,} {r['target_words']:<10,} {r['condensed_words']:<10,} "
              f"{r['target_retention']:<8.1f} {r['actual_retention']:<8.1f} {error_str} {status:<10}")

    print(f"\n{Fore.CYAN}Results:{Style.RESET_ALL}")
    print(f"  Total tests: {total_tests}")
    print(f"  Successful: {Fore.GREEN}{success_count}{Style.RESET_ALL}")
    print(f"  Failed: {Fore.RED}{total_tests - success_count}{Style.RESET_ALL}")
    print(f"\n{Fore.CYAN}Output saved to:{Style.RESET_ALL}")
    print(f"  Directory: {output_path}")
    print(f"  Summary CSV: {csv_file}\n")

    # Calculate average accuracy (how close to target retention)
    successful_results = [r for r in results if r['success']]
    if successful_results:
        avg_error = sum(abs(r['actual_retention'] - r['target_retention']) for r in successful_results) / len(successful_results)
        print(f"{Fore.CYAN}Average retention error:{Style.RESET_ALL} {avg_error:.1f}% (distance from target)")
        print()


if __name__ == '__main__':
    main()
