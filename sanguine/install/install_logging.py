import logging
# import logging.handlers
import time
from collections.abc import Callable


def _sanguine_patch_record(record: logging.LogRecord) -> None:
    if not hasattr(record, 'sanguine_when'):
        record.sanguine_when = time.perf_counter()
    if not hasattr(record, 'sanguine_prefix'):
        record.sanguine_prefix = ''
    record.sanguine_from_start = record.sanguine_when - logging_started()


_PERFWARN_LEVEL_NUM = 25

'''
def log_level_name(levelno: int) -> str:
    match levelno:
        case logging.DEBUG:
            return 'DEBUG'
        case logging.INFO:
            return 'INFO'
        case 25:  # _PERFWARN_LEVEL_NUM, no idea why PyCharm complains if I put its name here
            return 'PERFWARN'
        case logging.WARNING:
            return 'WARNING'
        case logging.ERROR:
            return 'ALERT'
        case logging.CRITICAL:
            return 'CRITICAL'
        case _:
            return 'LEVEL={}'.format(levelno)
'''

_FORMAT: str = '[%(levelname)s@%(sanguine_from_start).2f]:%(sanguine_prefix)s %(message)s (%(filename)s:%(lineno)d)'


class _SanguineFormatter(logging.Formatter):
    FORMATS: dict[int, str] = {
        logging.DEBUG: '\x1b[90m' + _FORMAT + '\x1b[0m',
        logging.INFO: '\x1b[32m' + _FORMAT + '\x1b[0m',
        _PERFWARN_LEVEL_NUM: '\x1b[34m' + _FORMAT + '\x1b[0m',
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
        _PERFWARN_LEVEL_NUM: '<div class="perf_warn">' + _FORMAT + '</div>',
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


logging.addLevelName(_PERFWARN_LEVEL_NUM, "PERFWARN")


def _perfwarn(self, message, *args, **kws):
    if self.isEnabledFor(_PERFWARN_LEVEL_NUM):
        # Yes, logger takes its '*args' as 'args'.
        self._log(_PERFWARN_LEVEL_NUM, message, args, **kws)


logging.Logger.perf_warn = _perfwarn

logging.addLevelName(logging.ERROR, 'ALERT')
_logger = logging.getLogger()
_logger.setLevel(logging.DEBUG if __debug__ else logging.INFO)

_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.DEBUG)
_console_handler.setFormatter(_SanguineFormatter())

_logger.addHandler(_console_handler)

_logger_file_handler: logging.StreamHandler | None = None

_started: float = time.perf_counter()


class _HtmlFileHandler(logging.FileHandler):
    def __init__(self, fpath) -> None:
        super().__init__(fpath, 'w', encoding='utf-8')
        bodystyle = 'body{ background-color:black; white-space:nowrap; font-size:1.2em; font-family:monospace; }\n'
        debugstyle = '.debug{color:#666666;}\n'
        infostyle = '.info{color:#008000;}\n'
        perfwarnstyle = '.perf_warn{color:#0492c2;}\n'
        warnstyle = '.warn{color:#a28a08;}\n'
        alertstyle = '.alert{color:#e5bf00; font-weight:600;}\n'
        criticalstyle = '.critical{color:#ff0000; font-weight:600;}\n'
        self.stream.write(
            '<html><head><style>\n' + bodystyle + debugstyle + infostyle + perfwarnstyle + warnstyle + alertstyle + criticalstyle + '</style></head>\n' +
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


_logging_hook: Callable[[logging.LogRecord], None] | None = None


def set_logging_hook(newhook: Callable[[logging.LogRecord], None] | None) -> Callable[[logging.LogRecord], None] | None:
    global _logging_hook
    oldhook = _logging_hook
    _logging_hook = newhook
    return oldhook


def log_record(record: logging.LogRecord) -> None:
    global _console_handler, _logger_file_handler
    _console_handler.emit(record)
    if _logger_file_handler is None:
        return
    _logger_file_handler.emit(record)


def log_record_skip_console(record: logging.LogRecord) -> None:
    global _logger_file_handler
    if _logger_file_handler is None:
        return
    _logger_file_handler.emit(record)


def _make_log_record(level, msg: str) -> logging.LogRecord:
    global _logger
    fn, lno, func, sinfo = _logger.findCaller(False, stacklevel=3)
    rec = _logger.makeRecord(_logger.name, level, fn, lno, msg, (), None, func, None, sinfo)
    rec.sanguine_when = time.perf_counter()
    rec.sanguine_prefix = ''
    return rec


def make_log_record(level, msg: str) -> logging.LogRecord:  # different stacklevel than _make_log_record
    global _logger
    fn, lno, func, sinfo = _logger.findCaller(False, stacklevel=2)
    rec = _logger.makeRecord(_logger.name, level, fn, lno, msg, (), None, func, None, sinfo)
    rec.sanguine_when = time.perf_counter()
    rec.sanguine_prefix = ''
    return rec


def logging_started() -> float:
    global _started
    return _started


def log_with_level(level: int, msg: str) -> None:
    if not __debug__ and level <= logging.DEBUG:
        return
    global _logging_hook
    if _logging_hook is not None:
        _logging_hook(_make_log_record(level, msg))
        return
    global _logger
    _logger.log(level, msg, stacklevel=2)


def debug(msg: str) -> None:
    if not __debug__:
        return
    global _logging_hook
    if _logging_hook is not None:
        _logging_hook(_make_log_record(logging.DEBUG, msg))
        return
    global _logger
    _logger.debug(msg, stacklevel=2)


def info(msg: str) -> None:
    global _logger
    global _logging_hook
    if _logging_hook is not None:
        _logging_hook(_make_log_record(logging.INFO, msg))
        return
    _logger.info(msg, stacklevel=2)


def perf_warn(msg: str) -> None:
    global _logger
    global _logging_hook
    if _logging_hook is not None:
        _logging_hook(_make_log_record(_PERFWARN_LEVEL_NUM, msg))
        return
    # noinspection PyUnresolvedReferences
    _logger.perf_warn(msg, stacklevel=2)


def warn(msg: str) -> None:
    global _logging_hook
    if _logging_hook is not None:
        _logging_hook(_make_log_record(logging.WARN, msg))
        return
    global _logger
    _logger.warning(msg, stacklevel=2)


def alert(msg: str) -> None:
    global _logging_hook
    if _logging_hook is not None:
        _logging_hook(_make_log_record(logging.ERROR, msg))
        return
    global _logger
    _logger.error(msg, stacklevel=2)


def critical(msg: str) -> None:
    global _logging_hook
    if _logging_hook is not None:
        _logging_hook(_make_log_record(logging.CRITICAL, msg))
        return
    global _logger
    _logger.critical(msg, stacklevel=2)


def info_or_perf_warn(pwarn: bool, msg: str) -> None:
    if pwarn:
        perf_warn(msg)
    else:
        info(msg)
