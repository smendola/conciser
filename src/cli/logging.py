import logging
import os
 
_LOG_FMT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
_BLUE  = '\033[94m'   # bright blue
_RESET = '\033[0m'
_PATH_RE = __import__('re').compile(
    r'(?:'
    r'[\w./\\-]+/[\w./\\-]+'
    r'|'
    r'\w[\w._-]*\.(?:json|xml|mp3|mp4|wav|txt|webm|mkv|log|py|zip|jpg|jpeg|png)'
    r')'
)
 
 
class _ColorStreamFormatter(logging.Formatter):
    """Stream formatter that renders file paths in bright blue."""
    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        return _PATH_RE.sub(lambda m: f"{_BLUE}{m.group()}{_RESET}", msg)


_FILE_HANDLER_NAME = 'nbj_file'
_STREAM_HANDLER_NAME = 'nbj_stream'


def _find_handler_by_name(root_logger: logging.Logger, name: str) -> logging.Handler | None:
    for h in root_logger.handlers:
        if getattr(h, 'name', None) == name:
            return h
    return None


def configure_logging() -> None:
    """Configure nbj logging.

    Environment flags:
      - NBJ_LOG_STREAM=0 disables stream handler installation.
      - NBJ_LOG_COLORIZE_FILE=1 applies ANSI colorization to file logs.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    file_handler = _find_handler_by_name(root_logger, _FILE_HANDLER_NAME)
    if file_handler is None:
        file_handler = logging.FileHandler('nbj.log')
        file_handler.name = _FILE_HANDLER_NAME
        root_logger.addHandler(file_handler)
    file_handler.setLevel(logging.DEBUG)

    if os.environ.get('NBJ_LOG_COLORIZE_FILE') in {'1', 'true', 'yes'}:
        file_handler.setFormatter(_ColorStreamFormatter(_LOG_FMT))
    else:
        file_handler.setFormatter(logging.Formatter(_LOG_FMT))

    want_stream = os.environ.get('NBJ_LOG_STREAM', '1') not in {'0', 'false', 'no'}
    if want_stream:
        stream_handler = _find_handler_by_name(root_logger, _STREAM_HANDLER_NAME)
        if stream_handler is None:
            stream_handler = logging.StreamHandler()
            stream_handler.name = _STREAM_HANDLER_NAME
            root_logger.addHandler(stream_handler)
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(_ColorStreamFormatter(_LOG_FMT))
    else:
        existing_stream = _find_handler_by_name(root_logger, _STREAM_HANDLER_NAME)
        if existing_stream is not None:
            root_logger.removeHandler(existing_stream)

logger = logging.getLogger(__name__)


configure_logging()
