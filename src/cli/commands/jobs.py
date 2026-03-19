import sqlite3
from pathlib import Path
import sys
from typing import Optional

import click
from colorama import Fore, Style

from ...config import get_settings


def _suppress_httpx_info_logs() -> None:
    import logging as stdlib_logging
    stdlib_logging.getLogger('httpx').setLevel(stdlib_logging.WARNING)


from ..app import cli  # noqa: E402


def _truncate_title(title: str, max_length: int = 80, partial_last_word=True) -> str:
    """Truncate title at first punctuation or parenthesis, or after max_length chars.

    partial_last_word:
      True (default) - truncate mid-word at max_length
      'elide'        - remove the partial last word (and preceding space)
      'complete'     - include the full last word, slightly exceeding max_length
    """
    if not title:
        return ""

    # Look for punctuation or parenthesis within the limit
    for i, char in enumerate(title):
        if char in ['.', '?', '!', '(', ')', '[', ']'] and i < max_length:
            return title[:i].strip() + "..."

    # If no punctuation found within limit, truncate at max_length
    if len(title) > max_length:
        if partial_last_word == 'elide':
            truncated = title[:max_length]
            if title[max_length] != ' ':
                last_space = truncated.rfind(' ')
                truncated = truncated[:last_space] if last_space != -1 else truncated
        elif partial_last_word == 'complete':
            truncated = title[:max_length]
            if title[max_length] != ' ':
                next_space = title.find(' ', max_length)
                if next_space == -1:
                    return title.strip()
                truncated = title[:next_space]
        else:
            truncated = title[:max_length]
        return truncated.strip() + "..."

    return title.strip()


def _extract_video_id(url: str) -> str:
    """Extract YouTube video ID from URL."""
    import re
    
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    # If no YouTube ID found, return last part of URL path
    return url.split('/')[-1][:11] if url else "unknown"


@cli.command()
@click.option(
    '--status', '-s',
    help='Filter by job status (comma-separated: queued,processing,completed,error)'
)
@click.option(
    '--client-id', '-c',
    help='Filter by client ID'
)
@click.option(
    '--limit', '-l',
    type=int,
    default=50,
    help='Maximum number of jobs to show (default: 50)'
)
@click.argument('status_shortcut', required=False)
def jobs(status, client_id, limit, status_shortcut: Optional[str]):
    """List active jobs from the SQLite database."""
    _suppress_httpx_info_logs()

    if status_shortcut is not None:
        status_shortcut = status_shortcut.strip().lower()
        if status_shortcut == 'rn':
            status = status or 'processing'
        else:
            raise click.UsageError(f"Unknown jobs argument: {status_shortcut}")

    try:
        settings = get_settings()
        db_path = settings.data_dir / "jobs.db"
        
        if not db_path.exists():
            print(f"{Fore.YELLOW}No jobs database found at: {db_path}{Style.RESET_ALL}")
            return

        # Connect to database
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # Build query
        query = """
            SELECT client_id || ':' || id as job_id, job_type, status, url, title, created_at
            FROM jobs 
            WHERE 1=1
        """
        args = []
        
        if status:
            # Parse comma-separated status values
            status_list = [s.strip().lower() for s in status.split(',')]
            # Filter valid status values
            valid_statuses = ['queued', 'processing', 'completed', 'error']
            status_list = [s for s in status_list if s in valid_statuses]
            
            if status_list:
                placeholders = ",".join(["?"] * len(status_list))
                query += f" AND status IN ({placeholders})"
                args.extend(status_list)
            
        if client_id:
            query += " AND client_id LIKE ?"
            args.append(f"{client_id}%")
            
        query += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        
        # Execute query
        cursor = conn.execute(query, args)
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            print(f"{Fore.YELLOW}No jobs found matching criteria.{Style.RESET_ALL}")
            return
        
        # Calculate column widths
        # Calculate display width based on truncated client IDs
        display_widths = []
        for row in rows:
            job_id_str = str(row['job_id'])
            if ':' in job_id_str:
                client_id, actual_job_id = job_id_str.split(':', 1)
                client_id = client_id[:12]  # Truncate client ID to 12 chars
                display_job_id = f"{client_id}:{actual_job_id}"
            else:
                display_job_id = job_id_str
            display_widths.append(len(display_job_id))
        
        job_id_width = max(20, max(display_widths) if display_widths else 20)
        job_id_width = min(job_id_width, 35)  # Cap at reasonable width
        
        type_width = max(8, max(len(str(row['job_type'])) for row in rows))
        status_width = max(10, max(len(str(row['status'])) for row in rows))
        video_id_width = 12  # Fixed width for video ID
        title_width = 80  # Fixed width for title
        
        # Print header
        print(f"{Fore.CYAN}{'CLIENT ID : JOB ID':<{job_id_width}}  {'TYPE':<{type_width}}  {'STATUS':<{status_width}}  {'VIDEO ID':<{video_id_width}}  {'TITLE'}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'-' * job_id_width}  {'-' * type_width}  {'-' * status_width}  {'-' * video_id_width}  {'-' * title_width}{Style.RESET_ALL}")
        
        # Print rows
        for row in rows:
            job_id = str(row['job_id'])
            job_type = str(row['job_type']).upper()
            job_status = str(row['status']).upper()
            title = _truncate_title(str(row['title'] or ''))
            url = str(row['url'])
            video_id = _extract_video_id(url)
            
            # Split job_id and truncate client_id
            if ':' in job_id:
                client_id, actual_job_id = job_id.split(':', 1)
                client_id = client_id[:12]  # Truncate client ID to 12 chars
                display_job_id = f"{client_id}:{actual_job_id}"
            else:
                display_job_id = job_id
            
            # Color code status
            status_color = {
                'QUEUED': Fore.YELLOW,
                'PROCESSING': Fore.BLUE,
                'COMPLETED': Fore.GREEN,
                'ERROR': Fore.RED
            }.get(job_status, '')
            
            print(f"{display_job_id:<{job_id_width}}  {job_type:<{type_width}}  {status_color}{job_status:<{status_width}}{Style.RESET_ALL}  {video_id:<{video_id_width}}  {title}")
        
        print(f"\n{Fore.CYAN}Showing {len(rows)} job(s){Style.RESET_ALL}")
        
    except Exception as e:
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        sys.exit(1)
