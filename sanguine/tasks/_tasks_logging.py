import logging
import time
from multiprocessing import SimpleQueue as PQueue, shared_memory, Semaphore
from threading import Thread

from sanguine.install.install_logging import (log_record, log_record_skip_console, make_log_record, log_level_name)
from sanguine.tasks._tasks_common import current_proc_num


class _LoggingQueue_nonworking:
    _queue: PQueue
    _queuesz_data: shared_memory.SharedMemory
    _queuesz_lock: Semaphore

    def __init__(self,param:tuple[str,Semaphore]|None):
        self._queue = PQueue()
        if param is None:
            self._queuesz_data = shared_memory.SharedMemory(create=True,size=4)
            self._queuesz_data.buf[:] = int.to_bytes(1, length=4) # adding 1 to account for temporary borrowing
            self._queuesz_lock = Semaphore(1)
        else:
            print(param[0])
            self._queuesz_data = shared_memory.SharedMemory(param[0])
            self._queuesz_lock = param[1]

    def put(self,item:any) -> None:
        # print('_LoggingQueue.put()')
        self._queuesz_lock.acquire()
        print('name='+self._queuesz_data.name+' len=' + str(len(self._queuesz_data.buf)))
        if len(self._queuesz_data.buf) != 4:
            print(self._queuesz_data.name)
            print('len='+str(len(self._queuesz_data.buf)))
            assert False
        print('old='+str(self._queuesz_data.buf.hex()))
        old = int.from_bytes(self._queuesz_data.buf)
        self._queuesz_data.buf[:] = int.to_bytes(old+1,length=4)
        self._queuesz_lock.release()
        self._queue.put(item)

    def get(self) -> any:
        out = self._queue.get()
        self._queuesz_lock.acquire()
        old = int.from_bytes(self._queuesz_data.buf)
        assert old >= 0
        self._queuesz_data.buf[:] = int.to_bytes(old-1,length=4)
        self._queuesz_lock.release()
        return out

    def qsize(self) -> int:
        self._queuesz_lock.acquire()
        out = int.from_bytes(self._queuesz_data.buf) - 1
        self._queuesz_lock.release()
        return out

    def mp_param(self) -> tuple[str,Semaphore]:
        return self._queuesz_data.name,self._queuesz_lock

type _LoggingQueue = PQueue

def create_logging_thread(logq:_LoggingQueue,outlogq:PQueue) -> Thread:
    return Thread(target=_logging_thread_func, args=(logq,outlogq))

class _ChildProcessLogHandler(logging.StreamHandler):
    logq: _LoggingQueue

    def __init__(self, logq: _LoggingQueue) -> None:
        super().__init__()
        self.logq = logq

    def emit(self, record: logging.LogRecord) -> None:
        assert current_proc_num() >= 0
        self.logq.put((current_proc_num(), time.perf_counter(), record))
        print(record.getMessage())


_log_elapsed: float | None = None
_log_waited: float = 0.


def log_elapsed() -> float | None:
    global _log_elapsed
    return _log_elapsed


def log_waited() -> float:
    global _log_waited
    return _log_waited

class EndOfRegularLog:
    pass

### Implementation

_CONSOLE_LOG_QUEUE_THRESHOLD: int = 100
_FILE_LOG_QUEUE_THRESHOLD: int = 1000
_FILE_LOG_SKIPPING_UP_TO_LEVEL: int = logging.INFO


class _LoggingThreadState:
    _state: int
    _log_started: float
    _log_waited: float
    _log_outq: PQueue

    def __init__(self,outlogq:PQueue) -> None:
        self._state = 0
        self._log_started = time.perf_counter()
        self._log_waited = 0.
        self._log_outq = outlogq

    def read_log_rec(self,logq: _LoggingQueue) -> tuple|None|bool:
        assert self._state == 0 or self._state == 1
        wt0 = time.perf_counter()
        record = logq.get()
        self._log_waited += time.perf_counter() - wt0
        if record is None:
            self._state = 2
            global _log_elapsed
            global _log_waited
            _log_elapsed = time.perf_counter() - self._log_started
            _log_waited = self._log_waited
            return None
        if isinstance(record, EndOfRegularLog):
            self._state = 1
            self._log_outq.put(None)
            return False
        assert isinstance(record, tuple)

        (procnum,t,rec) = record
        rec.sanguine_when = t
        if procnum >= 0:
            rec.sanguine_prefix = 'Process #{}: '.format(procnum + 1)

        #rec.sanguine_prefix = '@{}:'.format(self._state) + (rec.sanguine_prefix if hasattr(rec,'sanguine_prefix') and rec.sanguine_prefix is not None else '')
        #rec.msg = 'LOGTHREAD:' + rec.msg  # TODO: remove

        return record



def _logging_thread_func(logq: _LoggingQueue,outlogq:PQueue) -> None:
    assert current_proc_num() == -1
    lstate = _LoggingThreadState(outlogq)
    while True:
        assert current_proc_num() == -1
        '''
        qsize = logq.qsize()

        if qsize > _FILE_LOG_QUEUE_THRESHOLD:
            skipped = {}
            for i in range(_FILE_LOG_QUEUE_THRESHOLD):
                record = lstate.read_log_rec(logq)
                if record is None:
                    return
                if record is False:
                    continue
                (procnum, t, rec) = record
                levelno = rec.levelno
                if levelno <= _FILE_LOG_SKIPPING_UP_TO_LEVEL:
                    if levelno in skipped:
                        skipped[levelno] += 1
                    else:
                        skipped[levelno] = 1
                else:
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
                record = lstate.read_log_rec(logq)
                if record is None:
                    return
                if record is False:
                    continue
                (procnum, t, rec) = record
                levelno = rec.levelno
                if levelno in skipped:
                    skipped[levelno] += 1
                else:
                    skipped[levelno] = 1
                log_record_skip_console(rec)

            for levelno in skipped:
                rec = make_log_record(levelno,
                                      'tasks.log: logging thread overloaded, skipped {} [{}] entries in console, see log file for full details'.format(
                                          skipped[levelno], log_level_name(levelno)))
                log_record(rec)
            continue
        '''

        record = lstate.read_log_rec(logq)
        if record is None:
            return
        if record is False:
            continue
        (procnum, t, rec) = record
        log_record(rec)
