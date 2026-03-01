import sys

import click
from colorama import Fore, Back, Style

from ...config import get_settings

from ..app import cli


@cli.command()
@click.option(
    '--verbose', '-v',
    is_flag=True,
    default=False,
    help='Show detailed error messages from API servers'
)
def check(verbose):
    """
    Check configuration and API connectivity.
    """
    # Suppress httpx INFO logs
    import logging as stdlib_logging
    stdlib_logging.getLogger('httpx').setLevel(stdlib_logging.WARNING)

    print(f"\n{Fore.CYAN}Checking NBJ Condenser Configuration...{Style.RESET_ALL}\n")

    settings = get_settings()

    # Check directories
    print("Directories:")
    temp_exists = settings.temp_dir.exists()
    output_exists = settings.output_dir.exists()
    print(f"  Temp: {settings.temp_dir} {Style.BRIGHT}{Fore.GREEN}{Back.LIGHTBLACK_EX} ✔ {Style.RESET_ALL}" if temp_exists else f"  Temp: {settings.temp_dir} {Style.BRIGHT}{Fore.RED} ✗ {Style.RESET_ALL}")
    print(f"  Output: {settings.output_dir} {Style.BRIGHT}{Fore.GREEN}{Back.LIGHTBLACK_EX} ✔ {Style.RESET_ALL}" if output_exists else f"  Output: {settings.output_dir} {Style.BRIGHT}{Fore.RED} ✗ {Style.RESET_ALL}")
    print()

    # Check dependencies
    print("Dependencies:")
    import subprocess

    def check_command(cmd, version_flag='--version'):
        try:
            subprocess.run([cmd, version_flag], capture_output=True, check=True)
            return True
        except:
            return False

    # ffmpeg/ffprobe use -version (single dash), not --version
    ffmpeg_found = check_command('ffmpeg', '-version')
    ffprobe_found = check_command('ffprobe', '-version')
    print(f"  ffmpeg: {Style.BRIGHT}{Fore.GREEN}{Back.LIGHTBLACK_EX} ✔ {Style.RESET_ALL}" if ffmpeg_found else f"  ffmpeg: {Style.BRIGHT}{Fore.RED} ✗ {Style.RESET_ALL} Not found")
    print(f"  ffprobe: {Style.BRIGHT}{Fore.GREEN}{Back.LIGHTBLACK_EX} ✔ {Style.RESET_ALL}" if ffprobe_found else f"  ffprobe: {Style.BRIGHT}{Fore.RED} ✗ {Style.RESET_ALL} Not found")
    print()

    # Check API keys with parallel validation
    print("API Keys:")

    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Prepare validation tasks
    tasks = []
    required_services_missing = False
    if settings.openai_api_key:
        tasks.append(('OpenAI', settings.openai_api_key, _validate_openai_key))
    else:
        print(f"  OpenAI: {Style.BRIGHT}{Fore.RED} ✗ {Style.RESET_ALL} Not set")
        required_services_missing = True

    if settings.groq_api_key:
        tasks.append(('Groq', settings.groq_api_key, _validate_groq_key))
    else:
        if settings.transcription_service == 'groq':
            print(f"  Groq: {Style.BRIGHT}{Fore.RED} ✗ {Style.RESET_ALL} Not set (required when transcription_service=groq)")
            required_services_missing = True
        else:
            print(f"  Groq: {Style.BRIGHT}{Fore.RED} ✗ {Style.RESET_ALL} Not set (optional)")

    if settings.anthropic_api_key:
        tasks.append(('Anthropic', settings.anthropic_api_key, _validate_anthropic_key))
    else:
        print(f"  Anthropic: {Style.BRIGHT}{Fore.RED} ✗ {Style.RESET_ALL} Not set")
        required_services_missing = True

    if settings.elevenlabs_api_key:
        tasks.append(('ElevenLabs', settings.elevenlabs_api_key, _validate_elevenlabs_key))
    else:
        print(f"  ElevenLabs: {Style.BRIGHT}{Fore.RED} ✗ {Style.RESET_ALL} Not set")
        required_services_missing = True

    if settings.did_api_key:
        tasks.append(('D-ID', settings.did_api_key, _validate_did_key))
    else:
        print(f"  D-ID: {Style.BRIGHT}{Fore.RED} ✗ {Style.RESET_ALL} Not set (optional - only needed for avatar mode)")

    # Run validations in parallel
    results = {}
    if tasks:
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_service = {
                executor.submit(validate_fn, api_key): service_name
                for service_name, api_key, validate_fn in tasks
            }

            for future in as_completed(future_to_service):
                service_name = future_to_service[future]
                try:
                    status, error = future.result()
                    results[service_name] = (status, error)
                except Exception as e:
                    results[service_name] = (False, str(e))

    # Display results in order
    all_valid = True
    if required_services_missing:
        all_valid = False
    for service_name in ['OpenAI', 'Groq', 'Anthropic', 'ElevenLabs', 'D-ID']:
        if service_name in results:
            status, error = results[service_name]
            if status:
                print(f"  {service_name}: {Style.BRIGHT}{Fore.GREEN}{Back.LIGHTBLACK_EX} ✔ {Style.RESET_ALL} Valid")
            else:
                print(f"  {service_name}: {Style.BRIGHT}{Fore.RED} ✗ {Style.RESET_ALL} Invalid")
                if verbose and error:
                    print(f"    {Fore.RED}Error: {error}{Style.RESET_ALL}")
                if service_name == 'D-ID':
                    pass
                elif service_name == 'Groq' and settings.transcription_service != 'groq':
                    pass
                else:
                    all_valid = False

    print()

    if all_valid:
        print(f"{Style.BRIGHT}{Fore.GREEN}{Back.LIGHTBLACK_EX} ✔ {Style.RESET_ALL} {Fore.GREEN}All required API keys are valid and working{Style.RESET_ALL}\n")
    else:
        print(f"{Fore.YELLOW}⚠ Some API keys are missing or invalid.{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Run 'nbj setup' to configure missing keys.{Style.RESET_ALL}")
        if not verbose:
            print(f"{Fore.YELLOW}Use 'nbj check --verbose' for detailed error messages.{Style.RESET_ALL}")
        print()


def _validate_openai_key(api_key: str) -> tuple[bool, str]:
    """Validate OpenAI API key."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        # Try to list models (lightweight call)
        client.models.list()
        return True, None
    except Exception as e:
        error_msg = str(e)
        # Extract the meaningful part of the error
        if "authentication" in error_msg.lower() or "unauthorized" in error_msg.lower():
            return False, "Invalid API key or authentication failed"
        elif "quota" in error_msg.lower() or "insufficient" in error_msg.lower():
            return False, "Insufficient quota or credits"
        return False, error_msg


def _validate_groq_key(api_key: str) -> tuple[bool, str]:
    """Validate Groq API key (OpenAI-compatible)."""
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        client.models.list()
        return True, None
    except Exception as e:
        error_msg = str(e)
        if "authentication" in error_msg.lower() or "unauthorized" in error_msg.lower() or "invalid" in error_msg.lower():
            return False, "Invalid API key or authentication failed"
        return False, error_msg


def _validate_anthropic_key(api_key: str) -> tuple[bool, str]:
    """Validate Anthropic API key."""
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        # Try a minimal message (very cheap test)
        client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1,
            messages=[{"role": "user", "content": "test"}]
        )
        return True, None
    except Exception as e:
        error_msg = str(e)
        if "authentication" in error_msg.lower() or "invalid" in error_msg.lower():
            return False, "Invalid API key or authentication failed"
        elif "credit" in error_msg.lower() or "insufficient" in error_msg.lower():
            return False, "Insufficient credits"
        return False, error_msg


def _validate_elevenlabs_key(api_key: str) -> tuple[bool, str]:
    """Validate ElevenLabs API key."""
    try:
        from elevenlabs.client import ElevenLabs
        client = ElevenLabs(api_key=api_key)
        # Try to get user info or list voices (lightweight call)
        client.voices.get_all()
        return True, None
    except Exception as e:
        error_msg = str(e)
        if "unauthorized" in error_msg.lower() or "invalid" in error_msg.lower():
            return False, "Invalid API key or authentication failed"
        elif "quota" in error_msg.lower() or "limit" in error_msg.lower():
            return False, "Quota exceeded or limit reached"
        return False, error_msg


def _validate_did_key(api_key: str) -> tuple[bool, str]:
    """Validate D-ID API key."""
    try:
        import requests
        # Try to get credits (lightweight call)
        response = requests.get(
            "https://api.d-id.com/credits",
            headers={"Authorization": f"Basic {api_key}"},
            timeout=10
        )
        if response.status_code == 200:
            return True, None
        elif response.status_code == 401:
            return False, "Invalid API key or authentication failed"
        else:
            return False, f"HTTP {response.status_code}: {response.text}"
    except Exception as e:
        return False, str(e)
