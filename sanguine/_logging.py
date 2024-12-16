import logging
import logging.handlers
import time


class _SanguineFormatter(logging.Formatter):
    FORMAT: str = '[%(levelname)s]: %(message)s (%(filename)s:%(lineno)d)'
    FORMATS: dict[int, str] = {
        logging.DEBUG: '\x1b[90m' + FORMAT + '\x1b[0m',
        logging.INFO: '\x1b[32m' + FORMAT + '\x1b[0m',
        logging.WARNING: '\x1b[33m' + FORMAT + '\x1b[0m',
        logging.ERROR: '\x1b[93m' + FORMAT + '\x1b[0m',  # alert()
        logging.CRITICAL: '\x1b[91;1m' + FORMAT + '\x1b[0m'
    }

    def format(self, record) -> str:
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


_FILEFORMAT: str = '[%(levelname)s@%(sanguine_when).2f]:%(sanguine_prefix)s %(message)s (%(filename)s:%(lineno)d)'


def _html_format(color: str, bold: bool = False) -> str:
    return '<div style="margin: -1em -1em; padding: 0.5em 1em; white-space:nowrap; font-size:1.2em; background-color:black; color:' + color + (
        '; font-weight:600' if bold else '') + '; font-family:monospace;">' + _FILEFORMAT + '</div>'


class _SanguineFileFormatter(logging.Formatter):
    FORMATS: dict[int, str] = {
        logging.DEBUG: _html_format('#666666'),
        logging.INFO: _html_format('#008000'),
        logging.WARNING: _html_format('#a47d1f'),
        logging.ERROR: _html_format('#e5bf00'),  # alert()
        logging.CRITICAL: _html_format('#ff0000', True)
    }

    def format(self, record) -> str:
        record.msg = record.msg.replace('\n', '<br>')
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        if not hasattr(record, 'sanguine_when'):
            record.sanguine_when = time.perf_counter() - _started
        if not hasattr(record, 'sanguine_prefix'):
            record.sanguine_prefix = ''
        return formatter.format(record)


logging.addLevelName(logging.ERROR, 'ALERT')
_logger = logging.getLogger()
_logger.setLevel(logging.DEBUG if __debug__ else logging.INFO)

_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.DEBUG)
_console_handler.setFormatter(_SanguineFormatter())

_logger.addHandler(_console_handler)

_logger_file_handler: logging.StreamHandler | None = None

_started: float = time.perf_counter()


def add_file_logging(fpath: str) -> None:
    global _logger, _logger_file_handler
    assert _logger_file_handler is None
    _logger_file_handler = logging.handlers.RotatingFileHandler(fpath, 'w', backupCount=5)
    _logger_file_handler.setLevel(logging.DEBUG if __debug__ else logging.INFO)
    _logger_file_handler.setFormatter(_SanguineFileFormatter())
    _logger.addHandler(_logger_file_handler)


def add_logging_handler(handler: logging.StreamHandler) -> None:
    global _logger
    _logger.addHandler(handler)


def log_to_file_only(record: logging.LogRecord) -> None:
    global _logger_file_handler
    if _logger_file_handler is None:
        return
    _logger_file_handler.emit(record)


def logging_started() -> float:
    global _started
    return _started


# def logging_format_when(dt:float) -> str:
#    return '{:.2f}'.format(dt)

def debug(msg: str) -> None:
    if not __debug__:
        return
    global _logger
    _logger.debug(msg, stacklevel=2)


def info(msg: str) -> None:
    global _logger
    _logger.info(msg, stacklevel=2)


def warn(msg: str) -> None:
    global _logger
    _logger.warning(msg, stacklevel=2)


def alert(msg: str) -> None:
    global _logger
    _logger.error(msg, stacklevel=2)


def critical(msg: str) -> None:
    global _logger
    _logger.critical(msg, stacklevel=2)
