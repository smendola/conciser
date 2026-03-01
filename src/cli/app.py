import click
from colorama import init as colorama_init

from . import logging as _logging  # noqa: F401

# Initialize colorama for cross-platform colored output
colorama_init()


@click.group()
@click.version_option(version='0.1.0')
def cli():
    """
    NBJ Condenser - AI-Powered Video Condensation Tool

    Condense videos by removing filler content while preserving key insights,
    using AI voice cloning and video generation.
    """
    pass


from .commands import check as _check  # noqa: E402,F401
from .commands import condense as _condense  # noqa: E402,F401
from .commands import info as _info  # noqa: E402,F401
from .commands import init as _init  # noqa: E402,F401
from .commands import setup as _setup  # noqa: E402,F401
from .commands import show_script as _show_script  # noqa: E402,F401
from .commands import tts as _tts  # noqa: E402,F401
from .commands import tts_samples as _tts_samples  # noqa: E402,F401
from .commands import voices as _voices  # noqa: E402,F401
