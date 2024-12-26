import logging
import time
from multiprocessing import Queue as PQueue
from threading import Thread

from sanguine.install.install_logging import (log_record, log_record_skip_console, make_log_record, log_level_name)
from sanguine.tasks._tasks_common import current_proc_num


def create_logging_thread(logq) -> Thread:
    return Thread(target=_logging_thread_func, args=(logq,))


class _ChildProcessLogHandler(logging.StreamHandler):
    logq: PQueue

    def __init__(self, logq: PQueue) -> None:
        super().__init__()
        self.logq = logq

    def emit(self, record: logging.LogRecord) -> None:
        assert current_proc_num() >= 0
        self.logq.put((current_proc_num(), time.perf_counter(), record))


_log_elapsed: float | None = None
_log_waited: float = 0.


def log_elapsed() -> float | None:
    global _log_elapsed
    return _log_elapsed


def log_waited() -> float:
    global _log_waited
    return _log_waited


_CONSOLE_LOG_QUEUE_THRESHOLD: int = 100
_FILE_LOG_QUEUE_THRESHOLD: int = 1000
_FILE_LOG_SKIPPING_UP_TO_LEVEL: int = logging.INFO


def _patch_log_rec(rec: logging.LogRecord, procnum: int, t: float) -> None:
    rec.sanguine_when = t
    if procnum >= 0:
        rec.sanguine_prefix = 'Process #{}: '.format(procnum + 1)


def _read_log_rec(logq: PQueue) -> tuple[float, logging.LogRecord]:
    wt0 = time.perf_counter()
    record = logq.get()
    return time.perf_counter() - wt0, record


def _end_of_log(log_started: float, log_w: float) -> None:
    global _log_elapsed
    global _log_waited
    _log_elapsed = time.perf_counter() - log_started
    _log_waited = log_w


def _logging_thread_func(logq: PQueue) -> None:
    assert current_proc_num() == -1
    log_started = time.perf_counter()
    log_w = 0.
    while True:
        assert current_proc_num() == -1
        qsize = logq.qsize()

        if qsize > _FILE_LOG_QUEUE_THRESHOLD:
            skipped = {}
            for i in range(_FILE_LOG_QUEUE_THRESHOLD):
                wt, record = _read_log_rec(logq)
                log_w += wt
                if record is None:
                    _end_of_log(log_started, log_w)
                    return
                (procnum, t, rec) = record
                assert isinstance(rec, logging.LogRecord)
                levelno = rec.levelno
                if levelno <= _FILE_LOG_SKIPPING_UP_TO_LEVEL:
                    if levelno in skipped:
                        skipped[levelno] += 1
                    else:
                        skipped[levelno] = 1
                else:
                    _patch_log_rec(rec, procnum, t)
                    # rec.msg = 'LOGTHREAD:' + rec.msg  # TODO: remove
                    log_record(rec)

            for levelno in skipped:
                rec = make_log_record(levelno,
                                      'tasks.log: logging thread overloaded, skipped {} [{}] entries, which are lost forever'.format(
                                          skipped[levelno], log_level_name(levelno)))
                log_record(rec)
            continue

        if qsize > _CONSOLE_LOG_QUEUE_THRESHOLD:
            skipped = {}
            for i in range(_CONSOLE_LOG_QUEUE_THRESHOLD):
                wt, record = _read_log_rec(logq)
                if record is None:
                    _end_of_log(log_started, log_w)
                    return
                log_w += wt
                (procnum, t, rec) = record
                assert isinstance(rec, logging.LogRecord)
                levelno = rec.levelno
                if levelno in skipped:
                    skipped[levelno] += 1
                else:
                    skipped[levelno] = 1
                _patch_log_rec(rec, procnum, t)
                # rec.msg = 'LOGTHREAD:' + rec.msg  # TODO: remove
                log_record_skip_console(rec)

            for levelno in skipped:
                rec = make_log_record(levelno,
                                      'tasks.log: logging thread overloaded, skipped {} [{}] entries in console, see log file for full details'.format(
                                          skipped[levelno], log_level_name(levelno)))
                log_record(rec)
            continue

        wt, record = _read_log_rec(logq)
        log_w += wt
        if record is None:
            _end_of_log(log_started, log_w)
            return
        (procnum, t, rec) = record
        _patch_log_rec(rec, procnum, t)
        # rec.msg = 'LOGTHREAD:' + rec.msg # TODO: remove
        log_record(rec)
