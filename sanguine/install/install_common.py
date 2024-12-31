# part of common.py which can be used in install scripts too

# noinspection PyUnresolvedReferences
import enum
import os
import traceback
import typing
# noinspection PyUnresolvedReferences
from abc import ABC, abstractmethod
# noinspection PyUnresolvedReferences
from collections.abc import Callable, Generator, Iterable
# noinspection PyUnresolvedReferences
from types import TracebackType

Type = typing.Type

# noinspection PyUnresolvedReferences, PyProtectedMember
from sanguine.install.install_logging import (debug, info, perf_warn, warn, alert, critical,
                                              info_or_perf_warn, log_with_level, add_file_logging)
# noinspection PyUnresolvedReferences, PyProtectedMember
from sanguine.install._install_checks import check_sanguine_prerequisites


### error-handling related

class SanguinicError(Exception):
    pass


def abort_if_not(cond: bool, msg: Callable[[], str] | str | None = None):
    # 'always assert', even if __debug__ is False.
    # msg is a string or lambda which returns error message
    if not cond:
        msg1 = 'abort_if_not() failed'
        if msg is not None:
            if callable(msg):
                msg1 += ': ' + msg()
            elif isinstance(msg, str):
                msg1 += ': ' + msg
            else:
                assert False
        where = traceback.extract_stack(limit=2)[0]
        critical(msg1 + ' @line ' + str(where.lineno) + ' of ' + os.path.split(where.filename)[1])
        raise SanguinicError(msg1)
