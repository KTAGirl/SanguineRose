import logging
import logging.handlers
import time


def _sanguine_patch_record(record: logging.LogRecord) -> None:
    if not hasattr(record, 'sanguine_when'):
        record.sanguine_when = time.perf_counter() - _started
    if not hasattr(record, 'sanguine_prefix'):
        record.sanguine_prefix = ''


_FORMAT: str = '[%(levelname)s@%(sanguine_when).2f]:%(sanguine_prefix)s %(message)s (%(filename)s:%(lineno)d)'


class _SanguineFormatter(logging.Formatter):
    FORMATS: dict[int, str] = {
        logging.DEBUG: '\x1b[90m' + _FORMAT + '\x1b[0m',
        logging.INFO: '\x1b[32m' + _FORMAT + '\x1b[0m',
        logging.WARNING: '\x1b[33m' + _FORMAT + '\x1b[0m',
        logging.ERROR: '\x1b[93m' + _FORMAT + '\x1b[0m',  # alert()
        logging.CRITICAL: '\x1b[91;1m' + _FORMAT + '\x1b[0m'
    }

    def format(self, record) -> str:
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        _sanguine_patch_record(record)
        return formatter.format(record)


class _SanguineHtmlFileFormatter(logging.Formatter):
    FORMATS: dict[int, str] = {
        logging.DEBUG: '<div class="debug">' + _FORMAT + '</div>',
        logging.INFO: '<div class="info">' + _FORMAT + '</div>',
        logging.WARNING: '<div class="warn">' + _FORMAT + '</div>',
        logging.ERROR: '<div class="alert">' + _FORMAT + '</div>',
        logging.CRITICAL: '<div class="critical">' + _FORMAT + '</div>',
    }

    def format(self, record) -> str:
        record.msg = record.msg.replace('\n', '<br>')
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        _sanguine_patch_record(record)
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


class _HtmlFileHandler(logging.handlers.RotatingFileHandler):
    def __init__(self, fpath) -> None:
        super().__init__(fpath, 'w', encoding='utf-8', backupCount=5)
        bodystyle = 'body{ background-color:black; white-space:nowrap; font-size:1.2em; font-family:monospace; }\n'
        debugstyle = '.debug{color:#666666;}\n'
        infostyle = '.info{color:#008000;}\n'
        warnstyle = '.warn{color:#a28a08;}\n'
        alertstyle = '.alert{color:#e5bf00; font-weight:600;}\n'
        criticalstyle = '.critical{color:#ff0000; font-weight:600;}\n'
        self.stream.write(
            '<html><head><style>\n' + bodystyle + debugstyle + infostyle + warnstyle + alertstyle + criticalstyle + '</style></head>\n' +
            '<body>\n')
        self.stream.write('<div class="info">[STARTING LOGGING]: {}</div>\n'.format(time.asctime()))


def add_file_logging(fpath: str) -> None:
    global _logger, _logger_file_handler
    assert _logger_file_handler is None
    _logger_file_handler = _HtmlFileHandler(fpath)
    _logger_file_handler.setLevel(logging.DEBUG if __debug__ else logging.INFO)
    _logger_file_handler.setFormatter(_SanguineHtmlFileFormatter())
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
