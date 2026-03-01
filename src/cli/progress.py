from colorama import Fore, Style
 
from .logging import _PATH_RE, _BLUE, _RESET
 
 
class ProgressDisplay:
    """Display progress updates with colors."""
 
    STAGE_COLORS = {
        'DOWNLOAD': Fore.CYAN,
        'TRANSCRIBE': Fore.BLUE,
        'CONDENSE': Fore.MAGENTA,
        'VOICE_CLONE': Fore.YELLOW,
        'VOICE_GENERATE': Fore.YELLOW,
        'VIDEO_GENERATE': Fore.GREEN,
        'COMPOSE': Fore.GREEN,
        'CLEANUP': Fore.WHITE,
        'COMPLETE': Fore.GREEN,
    }
 
    @staticmethod
    def show(stage: str, message: str):
        """Show progress message."""
        color = ProgressDisplay.STAGE_COLORS.get(stage, Fore.WHITE)
        message = _PATH_RE.sub(lambda m: f"{_BLUE}{m.group()}{_RESET}", message)
        print(f"{color}[{stage}]{Style.RESET_ALL} {message}")
