import sqlite3
from pathlib import Path
import sys
import time
import signal

import click
from colorama import Fore, Style

from ...config import get_settings


def _suppress_httpx_info_logs() -> None:
    import logging as stdlib_logging
    stdlib_logging.getLogger('httpx').setLevel(stdlib_logging.WARNING)


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
def logs(job_id, limit, stage, follow):
    """View pipeline logs from job processing.

    Examples:
        nbj logs                    # Show recent events
        nbj logs --follow           # Live tail new events
        nbj logs f8ab4b2a           # Show events for specific job
        nbj logs -s TRANSCRIBE      # Show only transcription events
        nbj logs --follow -s ERROR  # Live tail only error events
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
        
        if follow:
            _tail_logs(conn, job_id, stage, limit)
        else:
            _show_logs(conn, job_id, stage, limit)
            
        conn.close()
        
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Interrupted by user{Style.RESET_ALL}")
        sys.exit(130)
    except Exception as e:
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)


def _show_logs(conn, job_id, limit, stage):
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
    _display_events(events)
    
    # Show job info if specific job
    if job_id and events:
        _show_job_details(conn, job_id)


def _tail_logs(conn, job_id, stage, limit):
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
        _display_events(events)
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
                _display_events(new_events)
                if new_events:
                    last_timestamp = new_events[-1]['timestamp']
            
            # Check for database changes
            time.sleep(1)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"{Fore.RED}Error in tail: {e}{Style.RESET_ALL}")
            time.sleep(1)


def _display_events(events):
    """Display events with formatting."""
    if not events:
        return
        
    # Calculate column widths
    job_id_width = max(12, max(len(str(event['job_id'])) for event in events))
    stage_width = max(12, max(len(str(event['stage'])) for event in events))
    
    # Print header (only if not in tail mode)
    if not hasattr(_display_events, 'header_shown'):
        print(f"{Fore.CYAN}{'TIMESTAMP':<20}  {'JOB ID':<{job_id_width}}  {'STAGE':<{stage_width}}  {'MESSAGE'}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'-' * 20}  {'-' * job_id_width}  {'-' * stage_width}  {'-' * 50}{Style.RESET_ALL}")
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
        display_message = message[:47] + "..." if len(message) > 50 else message
        
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
