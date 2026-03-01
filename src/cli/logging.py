import logging
 
_LOG_FMT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
_BLUE  = '\033[94m'   # bright blue
_RESET = '\033[0m'
_PATH_RE = __import__('re').compile(
    r'(?:'
    r'[\w./\\-]+/[\w./\\-]+'
    r'|'
    r'\w[\w._-]*\.(?:json|mp3|mp4|wav|txt|webm|mkv|log|py|zip|jpg|jpeg|png)'
    r')'
)
 
 
class _ColorStreamFormatter(logging.Formatter):
    """Stream formatter that renders file paths in bright blue."""
    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        return _PATH_RE.sub(lambda m: f"{_BLUE}{m.group()}{_RESET}", msg)
 
 
_file_handler = logging.FileHandler('nbj.log')
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter(_LOG_FMT))
 
_stream_handler = logging.StreamHandler()
_stream_handler.setLevel(logging.INFO)
_stream_handler.setFormatter(_ColorStreamFormatter(_LOG_FMT))
 
_root_logger = logging.getLogger()
_root_logger.setLevel(logging.DEBUG)
_root_logger.addHandler(_file_handler)
_root_logger.addHandler(_stream_handler)
 
logger = logging.getLogger(__name__)
