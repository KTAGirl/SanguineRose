# common is used by sanguine_install_helpers, so it must not import any installable modules

import base64
import enum
import json
import os
import pickle
import traceback
import typing
# noinspection PyUnresolvedReferences
from abc import ABC, abstractmethod
# noinspection PyUnresolvedReferences
from collections.abc import Callable, Generator, Iterable
# noinspection PyUnresolvedReferences
from types import TracebackType

Type = typing.Type

# noinspection PyUnresolvedReferences
from sanguine._logging import debug, info, warn, alert, critical, add_file_logging


class GameUniverse(enum.Enum):
    Skyrim = 0,
    Fallout = 1


def game_universe() -> GameUniverse:
    return GameUniverse.Skyrim  # TODO: read from project config


class Val:
    val: any

    def __init__(self, initval: any) -> None:
        self.val = initval

    def __str__(self) -> str:
        return str(self.val)


def add_to_dict_of_lists(dicttolook: dict[any, list[any]], key: any, val: any) -> None:
    if key not in dicttolook:
        dicttolook[key] = [val]
    else:
        dicttolook[key].append(val)


### error-handling related

class SanguinicError(Exception):
    pass


def abort_if_not(cond: bool,
                 f: Callable[
                     [], str] = None):  # 'always assert', even if __debug__ is False. f is a lambda printing error message before throwing
    if not cond:
        msg = 'abort_if_not() failed'
        if f is not None:
            msg += ':' + f()
        where = traceback.extract_stack(limit=2)[0]
        critical(msg + ' @line ' + str(where.lineno) + ' of ' + os.path.split(where.filename)[1])
        raise SanguinicError(msg)


### JSON-related

def to_json_hash(h: bytes) -> str:
    b64 = base64.b64encode(h).decode('ascii')
    # print(b64)
    s = b64.rstrip('=')
    # assert from_json_hash(s) == h
    return s


def from_json_hash(s: str) -> bytes:
    ntopad = (3 - (len(s) % 3)) % 3
    s += '=='[:ntopad]
    b = base64.b64decode(s)
    return b


class _JsonEncoder(json.JSONEncoder):
    def encode(self, o: any) -> any:
        return json.JSONEncoder.encode(self, self.default(o))

    def default(self, o: any) -> any:
        if isinstance(o, bytes):
            return base64.b64encode(o).decode('ascii')
        elif isinstance(o, dict):
            return self._adjust_dict(o)
        elif o is None or isinstance(o, str) or isinstance(o, tuple) or isinstance(o, list):
            return o
        elif isinstance(o, object):
            return o.__dict__
        else:
            return o

    def _adjust_dict(self, d: dict[str, any]) -> dict[str, any]:
        out = {}
        for k, v in d.items():
            if isinstance(k, bytes):
                k = base64.b64encode(k).decode('ascii')
            out[k] = self.default(v)
        return out


def as_json(data: any) -> str:
    return _JsonEncoder().encode(data)


### file-related helpers

def open_3rdparty_txt_file(fname: str) -> typing.TextIO:
    return open(fname, 'rt', encoding='cp1252', errors='replace')


def open_3rdparty_txt_file_w(fname) -> typing.TextIO:
    return open(fname, 'wt', encoding='cp1252')


def read_dict_from_pickled_file(fpath: str) -> dict[str, any]:
    try:
        with open(fpath, 'rb') as rfile:
            return pickle.load(rfile)
    except Exception as e:
        warn('error loading ' + fpath + ': ' + str(e) + '. Will continue without it')
        return {}


### normalized stuff

#  all our dir and file names are always in lowercase, and always end with '\\'

def normalize_dir_path(path: str) -> str:
    path = os.path.abspath(path)
    assert '/' not in path
    assert not path.endswith('\\')
    return path.lower() + '\\'


def is_normalized_dir_path(path: str) -> bool:
    return path == os.path.abspath(path).lower() + '\\'


def normalize_file_path(path: str) -> str:
    assert not path.endswith('\\') and not path.endswith('/')
    path = os.path.abspath(path)
    assert '/' not in path
    return path.lower()


def is_normalized_file_path(path: str) -> bool:
    return path == os.path.abspath(path).lower()


def to_short_path(base: str, path: str) -> str:
    assert path.startswith(base)
    return path[len(base):]


def is_short_file_path(fpath: str) -> bool:
    assert not fpath.endswith('\\') and not fpath.endswith('/')
    if not fpath.islower(): return False
    return not os.path.isabs(fpath)


def is_short_dir_path(fpath: str) -> bool:
    return fpath.islower() and fpath.endswith('\\') and not os.path.isabs(fpath)


def is_normalized_file_name(fname: str) -> bool:
    if '/' in fname or '\\' in fname: return False
    return fname.islower()


def normalize_file_name(fname: str) -> str:
    assert '\\' not in fname and '/' not in fname
    return fname.lower()


def normalize_archive_intra_path(fpath: str):
    assert is_short_file_path(fpath.lower())
    return fpath.lower()


##### esx stuff

def is_esl_flagged(filename: str) -> bool:
    with open(filename, 'rb') as f:
        buf = f.read(10)
        return (buf[0x9] & 0x02) == 0x02


def is_esx(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext == '.esl' or ext == '.esp' or ext == '.esm'


'''
### unused, candidates for removal
def escape_json(s: any) -> str:
    return json.dumps(s)

def all_esxs(mod: str, mo2: str) -> list[str]:
    esxs = glob.glob(mo2 + 'mods/' + mod + '/*.esl')
    esxs = esxs + glob.glob(mo2 + 'mods/' + mod + '/*.esp')
    esxs = esxs + glob.glob(mo2 + 'mods/' + mod + '/*.esm')
    return esxs

def read_dict_from_json_file(fpath: str) -> dict[str, any]:
    try:
        with open(fpath, 'rt', encoding='utf-8') as rfile:
            return json.load(rfile)
    except Exception as e:
        warn('error loading ' + fpath + ': ' + str(e) + '. Will continue without it')
        return {}
'''
