import glob
import json
import logging
import os
import traceback
import typing
from collections.abc import Callable as _Callable, Generator as _Generator
from types import TracebackType as _TracebackType
from typing import Type as _Type

# stubs for importing from other modules, while preventing import optimizer from optimizing it out
Callable = _Callable
Generator = _Generator
Type = _Type
TracebackType = _TracebackType


def dbgwait() -> None:
    input("Press Enter to continue.")


def dbgfirst(data: any) -> any:
    if isinstance(data, list):
        print(len(data))
        return data[0]
    elif isinstance(data, dict):
        # print(len(data))
        it = iter(data)
        key = next(it)
        # print(key)
        return data[key]
    else:
        return data


def dbgprint(s) -> None:
    if __debug__:
        print(s)


class Mo2gitError(Exception):
    pass


def aassert(cond: bool,
            f: Callable[
                [], str] = None):  # 'always assert', even if __debug__ is False. f is a lambda printing error message before throwing
    if not cond:
        msg = 'aassert() failed'
        if f is not None:
            msg += ':' + f()
        where = traceback.extract_stack(limit=2)[0]
        critical(msg + ' @line ' + str(where.lineno) + ' of ' + os.path.split(where.filename)[1])
        raise Mo2gitError(msg)


_logger = logging.getLogger('mo2git')
logging.basicConfig(level=logging.DEBUG)


def warn(msg: str) -> None:
    global _logger
    _logger.warning(msg)


def info(msg: str) -> None:
    global _logger
    _logger.info(msg)


def critical(msg: str):
    global _logger
    _logger.critical(msg)


###

class JsonEncoder(json.JSONEncoder):
    def default(self, o: any) -> any:
        if isinstance(o, object):
            return o.__dict__
        else:
            return o


def open_3rdparty_txt_file(fname: str) -> typing.TextIO:
    return open(fname, 'rt', encoding='cp1252', errors='replace')


def open_3rdparty_txt_file_w(fname) -> typing.TextIO:
    return open(fname, 'wt', encoding='cp1252')


def escape_json(s: any) -> str:
    return json.dumps(s)


def is_esl_flagged(filename: str) -> bool:
    with open(filename, 'rb') as f:
        buf = f.read(10)
        return (buf[0x9] & 0x02) == 0x02


def add_to_dict_of_lists(dicttolook: dict[list[any]], key: any, val: any) -> None:
    if key not in dicttolook:
        dicttolook[key] = [val]
    else:
        dicttolook[key].append(val)


def is_esx(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext == '.esl' or ext == '.esp' or ext == '.esm'


def all_esxs(mod: str, mo2: str) -> list[str]:
    esxs = glob.glob(mo2 + 'mods/' + mod + '/*.esl')
    esxs = esxs + glob.glob(mo2 + 'mods/' + mod + '/*.esp')
    esxs = esxs + glob.glob(mo2 + 'mods/' + mod + '/*.esm')
    return esxs


'''
class Elapsed:
    def __init__(self):
        self.t0 = time.perf_counter()
        
    def printAndReset(self,where):
        t1 = time.perf_counter()
        print(where+' took '+str(round(t1-self.t0,2))+'s')
        self.t0 = t1
'''


class Val:
    val: any

    def __init__(self, initval: any) -> None:
        self.val = initval

    def __str__(self) -> str:
        return str(self.val)
