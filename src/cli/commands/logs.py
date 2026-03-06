import sqlite3
from pathlib import Path
import sys
import time
import signal
import os
import shutil

import click
from colorama import Fore, Style

from ...config import get_settings


def _suppress_httpx_info_logs() -> None:
    import logging as stdlib_logging
    stdlib_logging.getLogger('httpx').setLevel(stdlib_logging.WARNING)


def _get_terminal_width() -> int:
    """Get terminal width, fallback to 80 if unavailable."""
    try:
        return shutil.get_terminal_size().columns
    except:
        return 80


def _calculate_message_width(total_width: int, job_id_width: int, stage_width: int) -> int:
    """Calculate appropriate message width based on terminal width."""
    # Account for timestamps (20), job_id, stage, and separators (3*4 spaces)
    used_width = 20 + job_id_width + stage_width + 12  # 3*4 spaces between columns
    message_width = total_width - used_width
    return max(20, min(message_width, 200))  # Min 20, Max 200 chars


from ..app import cli  # noqa: E402


@cli.command()
@click.argument('job_id', required=False)
@click.option(
    '--limit', '-l',
    type=int,
    default=50,
    help='Maximum number of events to show (default: 50)'
)
@click.option(
    '--stage', '-s',
    help='Filter by stage (e.g., FETCH, TRANSCRIBE, CONDENSE, etc.)'
)
@click.option(
    '--follow', '-f',
    is_flag=True,
    default=False,
    help='Live tail - follow new events as they arrive'
)
@click.option(
    '--width', '-w',
    type=int,
    help='Width of message column (auto-detected from terminal if not specified)'
)
def logs(job_id, limit, stage, follow, width):
    """View pipeline logs from job processing.

    Examples:
        nbj logs                    # Show recent events
        nbj logs --follow           # Live tail new events
        nbj logs f8ab4b2a           # Show events for specific job
        nbj logs -s TRANSCRIBE      # Show only transcription events
        nbj logs --follow -s ERROR  # Live tail only error events
        nbj logs -w 120             # Set message column width to 120 chars
    """
    _suppress_httpx_info_logs()

    try:
        settings = get_settings()
        db_path = settings.output_dir / "jobs.db"
        
        if not db_path.exists():
            print(f"{Fore.YELLOW}No jobs database found at: {db_path}{Style.RESET_ALL}")
            return

        # Connect to database
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # Determine message width
        if width is None:
            terminal_width = _get_terminal_width()
            width = terminal_width
        else:
            terminal_width = width
        
        if follow:
            _tail_logs(conn, job_id, stage, limit, terminal_width)
        else:
            _show_logs(conn, job_id, stage, limit, terminal_width)
            
        conn.close()
        
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Interrupted by user{Style.RESET_ALL}")
        sys.exit(130)
    except Exception as e:
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


def _show_logs(conn, job_id, stage, limit, terminal_width):
    """Show static logs."""
    # Build query
    query = """
        SELECT job_id, stage, message, timestamp 
        FROM job_events 
        WHERE 1=1
    """
    args = []
    
    if job_id:
        query += " AND job_id = ?"
        args.append(job_id)
        
    if stage:
        query += " AND stage = ?"
        args.append(stage.upper())
        
    query += " ORDER BY timestamp DESC LIMIT ?"
    args.append(limit)
    
    # Execute query
    cursor = conn.execute(query, args)
    events = cursor.fetchall()
    
    if not events:
        print(f"{Fore.YELLOW}No events found matching criteria.{Style.RESET_ALL}")
        return
    
    # Display events (newest first, but we'll reverse for chronological display)
    events.reverse()
    _display_events(events, terminal_width)
    
    # Show job info if specific job
    if job_id and events:
        _show_job_details(conn, job_id)


def _tail_logs(conn, job_id, stage, limit, terminal_width):
    """Live tail new events."""
    print(f"{Fore.CYAN}Starting live tail...{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Press Ctrl+C to stop{Style.RESET_ALL}\n")
    
    # Get initial events
    query = """
        SELECT job_id, stage, message, timestamp 
        FROM job_events 
        WHERE 1=1
    """
    args = []
    
    if job_id:
        query += " AND job_id = ?"
        args.append(job_id)
        
    if stage:
        query += " AND stage = ?"
        args.append(stage.upper())
        
    query += " ORDER BY timestamp DESC LIMIT ?"
    args.append(limit)
    
    cursor = conn.execute(query, args)
    events = cursor.fetchall()
    
    # Show initial events (chronological order)
    if events:
        events.reverse()
        _display_events(events, terminal_width)
        print(f"{Fore.CYAN}--- Initial events loaded ---{Style.RESET_ALL}\n")
    
    # Track last timestamp
    last_timestamp = events[-1]['timestamp'] if events else None
    
    # Tail new events
    while True:
        try:
            # Query for newer events
            query = """
                SELECT job_id, stage, message, timestamp 
                FROM job_events 
                WHERE 1=1
            """
            args = []
            
            if job_id:
                query += " AND job_id = ?"
                args.append(job_id)
                
            if stage:
                query += " AND stage = ?"
                args.append(stage.upper())
                
            if last_timestamp:
                query += " AND timestamp > ?"
                args.append(last_timestamp)
                
            query += " ORDER BY timestamp ASC"
            
            cursor = conn.execute(query, args)
            new_events = cursor.fetchall()
            
            if new_events:
                _display_events(new_events, terminal_width)
                if new_events:
                    last_timestamp = new_events[-1]['timestamp']
            
            # Check for database changes
            time.sleep(1)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"{Fore.RED}Error in tail: {e}{Style.RESET_ALL}")
            time.sleep(1)


def _display_events(events, terminal_width):
    """Display events with formatting."""
    if not events:
        return
        
    # Calculate column widths
    job_id_width = max(12, max(len(str(event['job_id'])) for event in events))
    stage_width = max(12, max(len(str(event['stage'])) for event in events))
    message_width = _calculate_message_width(terminal_width, job_id_width, stage_width)
    
    # Print header (only if not in tail mode)
    if not hasattr(_display_events, 'header_shown'):
        header_message = "MESSAGE"
        header_display = header_message[:message_width].ljust(message_width)
        print(f"{Fore.CYAN}{'TIMESTAMP':<20}  {'JOB ID':<{job_id_width}}  {'STAGE':<{stage_width}}  {header_display}{Style.RESET_ALL}")
        separator = "-" * message_width
        print(f"{Fore.CYAN}{'-' * 20}  {'-' * job_id_width}  {'-' * stage_width}  {separator}{Style.RESET_ALL}")
        _display_events.header_shown = True
    
    # Print events
    for event in events:
        timestamp = str(event['timestamp'])
        job_id_str = str(event['job_id'])
        stage_str = str(event['stage'])
        message = str(event['message'])
        
        # Color code stages
        stage_color = {
            'FETCH': Fore.CYAN,
            'TRANSCRIBE': Fore.BLUE,
            'CONDENSE': Fore.MAGENTA,
            'VOICE_CLONE': Fore.GREEN,
            'VOICE_GENERATE': Fore.YELLOW,
            'VIDEO_GENERATE': Fore.RED,
            'COMPOSE': Fore.WHITE,
            'COMPLETE': Fore.GREEN,
            'ERROR': Fore.RED
        }.get(stage_str.upper(), '')
        
        # Truncate long messages
        display_message = message[:message_width-3] + "..." if len(message) > message_width else message
        display_message = display_message.ljust(message_width)
        
        print(f"{timestamp:<20}  {job_id_str:<{job_id_width}}  {stage_color}{stage_str:<{stage_width}}{Style.RESET_ALL}  {display_message}")


def _show_job_details(conn, job_id):
    """Show job details."""
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    
    if job:
        print(f"\n{Fore.CYAN}Job Details:{Style.RESET_ALL}")
        print(f"  URL: {job['url']}")
        print(f"  Title: {job['title'] or 'N/A'}")
        print(f"  Type: {job['job_type']}")
        print(f"  Status: {job['status']}")
        print(f"  Created: {job['created_at']}")
        if job['completed_at']:
            print(f"  Completed: {job['completed_at']}")
