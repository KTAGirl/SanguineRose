import win32file

from mo2gitlib.common import *


class LockMO2Error(Exception):
    pass


class LockMO2:
    mo2: str
    interface_log: int | None

    def __init__(self, mo2: str) -> None:
        self.mo2 = mo2

    def __enter__(self) -> "LockMO2":
        try:
            self.interface_log = win32file.CreateFile(self.mo2 + 'logs\\mo_interface.log', win32file.GENERIC_READ, 0,
                                                      None, win32file.OPEN_EXISTING, 0, 0)
            # dbgWait()
            return self
        except Exception as e:
            print(e)
            self.interface_log = None
            raise LockMO2Error('Unable to lock mo_interface.log; make sure to close MO2 before running mo2git')

    def __exit__(self, exceptiontype: Type[BaseException], exceptionval: BaseException,
                 exceptiontraceback: TracebackType) -> None:
        if self.interface_log is not None:
            win32file.CloseHandle(self.interface_log)
