# we have reasons to have our own Json writer:
#  1. major. we need very specific gitdiff-friendly format
#  2. minor. we want to keep these files as small as feasible (while keeping it more or less readable),
#            hence JSON5 quote-less names, and path and elements "compression". It was seen to save 3.8x (2x for default pcompression=0), for a 50M file it is quite a bit

import base64
import urllib.parse as urlparse
from abc import ABC, abstractmethod
from enum import Enum

from mo2gitlib.common import *


### compressors

class GitParamCompressor(ABC):
    @abstractmethod
    def compress(self, val: any) -> str:
        pass


class GitParamIntCompressor(GitParamCompressor):
    can_skip: bool
    name: str
    prev: int | None

    def __init__(self, name: str, can_skip: bool) -> None:
        self.can_skip = can_skip
        self.name = name
        self.prev = None

    def compress(self, val: int) -> str:
        assert isinstance(val, int)
        if self.can_skip and self.prev == val:
            return ''
        self.prev = val
        return self.name + ':' + str(val)


class GitParamStrCompressor(GitParamCompressor):
    can_skip: bool
    name: str
    prev: str | None

    def __init__(self, name: str, can_skip: bool) -> None:
        self.can_skip = can_skip
        self.name = name
        self.prev = None

    def compress(self, val: str) -> str:
        assert isinstance(val, str)
        if self.can_skip and self.prev == val:
            return ''
        self.prev = val
        return self.name + ':' + val


class GitParamHashCompressor(GitParamCompressor):
    can_skip: bool
    name: str
    prev: int

    def __init__(self, name: str, can_skip: bool) -> None:
        self.can_skip = can_skip
        self.name = name
        self.prev = 0

    @staticmethod
    def _to_json_hash(h: int) -> str:
        assert h >= 0
        assert h < 2 ** 64
        # print(h)
        b = h.to_bytes(8, 'little', signed=False)
        b64 = base64.b64encode(b).decode('ascii')
        # print(b64)
        s = b64.rstrip('=')
        # assert from_json_hash(s) == h
        return s

    def compress(self, h: int) -> str:
        assert isinstance(h, int)
        if h is None:
            assert self.can_skip
            return ''
        if self.can_skip and self.prev == h:
            return ''
        self.prev = h
        return self.name + ':"' + GitParamHashCompressor._to_json_hash(h) + '"'


class GitParamPathCompressor(GitParamCompressor):
    name: str
    level: int
    prevn: int
    prevpath: list[str]

    def __init__(self, name: str, level=2) -> None:
        self.name = name
        self.prevn = 0
        self.prevpath = []
        self.level = level

    @staticmethod
    def _to_json_fpath(fpath: str) -> str:
        return urlparse.quote(fpath, safe=" /+()'&#$[];,!@")

    @staticmethod
    def _from_json_fpath(fpath: str) -> str:
        return urlparse.unquote(fpath)

    def compress(self, path: str | None) -> str:
        if path is None:
            return ''
        assert isinstance(path, str)
        assert '/' not in path
        # assert('>' not in path)
        path = path.replace('\\', '/')
        if self.level == 0:
            path = self.name + ':"' + GitParamPathCompressor._to_json_fpath(path) + '"'
            assert '"' not in path[1:-1]
            return path

        spl = path.split('/')
        # print(prevpath.val)
        # print(spl)
        nmatch = 0
        for i in range(min(len(self.prevpath), len(spl))):
            if spl[i] == self.prevpath[i]:
                nmatch = i + 1
            else:
                break
        assert nmatch >= 0
        if self.level == 2 or (self.level == 1 and self.prevn <= nmatch):
            if nmatch <= 9:
                path = self.name + ':"' + str(nmatch)
            else:
                assert nmatch <= 35
                path = self.name + ':"' + chr(nmatch - 10 + 65)
            needslash = False
            for i in range(nmatch, len(spl)):
                if needslash:
                    path += '/'
                else:
                    needslash = True
                path += GitParamPathCompressor._to_json_fpath(spl[i])
        else:  # skipping compression because of level restrictions
            path = '"0' + GitParamPathCompressor._to_json_fpath(path)
        self.prevpath = spl
        self.prevn = nmatch
        assert '"' not in path[1:]
        return path


### decompressors

'''
class GitParamDecompressor(ABC):
    @abstractmethod
    def decompress(self, val: any) -> str:
        pass


def from_json_hash(s: str) -> int:
    ntopad = (3 - (len(s) % 3)) % 3
    # print(ntopad)
    s += '=='[:ntopad]
    # print(s)
    b = base64.b64decode(s)
    h = int.from_bytes(b, byteorder='little')
    return h


def decompress_json_path(prevpath: Val, path: str, level: int = 2):
    path = from_json_fpath(path)
    if level == 0:
        return path.replace('/', '\\')

    p0 = path[0]
    if '0' <= p0 <= '9':
        nmatch = int(p0)
    elif 'A' <= p0 <= 'Z':
        nmatch = ord(p0) - 65 + 10
    else:
        assert False
    out = ''

    # print(prevpath)
    # print(nmatch)
    for i in range(nmatch):
        if i > 0:
            out += '/'
        out += prevpath.val[i]
    if out != '':
        out += '/'
    out += path[1:]
    prevpath.val = out.split('/')
    return out.replace('/', '\\')


def int_json_param(name: str, prev: Val, new: int) -> str:
    if prev.val == new:
        return ''
    prev.val = new
    return ',' + name + ':' + str(new)


def str_json_param(name: str, prev: Val, new: str) -> str:
    if prev.val == new:
        return ''
    prev.val = new
    return ',' + name + ':"' + new + '"'
'''


###  params

class GitDataType(Enum):
    Path = 0,
    Hash = 1,
    Int = 2,
    Str = 3


class GitDataParam:
    can_skip: bool
    name: str
    typ: GitDataType
    compress: bool

    def __init__(self, name: str, typ: GitDataType, can_skip: bool = True) -> None:
        self.name = name
        self.typ = typ
        self.can_skip = can_skip


def _compressor(p: GitDataParam) -> any:
    match p.typ:
        case GitDataType.Path:
            return GitParamPathCompressor(p.name, 2 if p.can_skip else 0)
        case GitDataType.Hash:
            return GitParamHashCompressor(p.name, p.can_skip)
        case GitDataType.Int:
            return GitParamIntCompressor(p.name, p.can_skip)
        case GitDataType.Str:
            return GitParamStrCompressor(p.name, p.can_skip)


class GitDataHandler:
    optional: list[GitDataParam]

    def __init__(self, optional: list[GitDataParam]) -> None:
        self.optional = optional


class GitDataList:
    mandatory: list[GitDataParam]
    handlers: list[GitDataHandler]

    def __init__(self, mandatory: list[GitDataParam], handlers: list[GitDataHandler]) -> None:
        if __debug__:
            assert not mandatory[0].can_skip

            if len(handlers) > 1:  # if only one handler, there can be no problems distinguishing handlers, even if the only handler has no parameters whatsoever
                for h in handlers:
                    assert not h.optional[0].can_skip  # otherwise regex parsing may become ambiguous

            # handlers must distinguish by their first param (to avoid regex ambiguity)
            first_param_names = [h.optional[0].name for h in handlers]
            assert len(first_param_names) == len(set(first_param_names))

            # there must be no duplicate names for any handler, including mandatory (to be JSON5-compliant)
            for h in handlers:
                all_param_names = [manda.name for manda in mandatory] + [opt.name for opt in h.optional]
                assert len(all_param_names) == len(set(all_param_names))
        self.mandatory = mandatory
        self.handlers = handlers


### writing

def write_file_header_comment(wfile: typing.TextIO) -> None:
    wfile.write('// This is JSON5 file, to save some space compared to JSON.\n')
    wfile.write('// Still, do not edit it by hand, mo2git parses it itself using regex to save time\n')


class GitDataListWriter:
    df: GitDataList
    wfile: typing.TextIO
    mandatory_compressor: list[GitParamCompressor]
    last_handler: GitDataHandler | None
    last_handler_compressor: list[
        GitParamCompressor]  # we never go beyond last line, so only one (last) per-handler compressor is ever necessary
    line_num: int

    def __init__(self, df: GitDataList, wfile: typing.TextIO) -> None:
        self.df = df
        self.wfile = wfile
        self.mandatory_compressor = [_compressor(manda) for manda in df.mandatory]
        self.last_handler = None
        self.last_handler_compressor = []
        self.line_num = 0

    def write_begin(self) -> None:
        pass

    def write_line(self, handler: GitDataHandler, values: tuple[int | str | None, ...]) -> None:
        assert len(values) == len(self.df.mandatory) + len(handler.optional)
        if self.line_num > 0:
            ln = ',\n{'
        else:
            ln = '{'
        self.line_num += 1
        assert len(self.mandatory_compressor) == len(self.df.mandatory)
        for i in range(len(self.df.mandatory)):
            if i > 0:
                ln += ','
            ln += self.mandatory_compressor[i].compress(values[i])

        shift = len(self.df.mandatory)
        if handler == self.last_handler:
            for i in range(len(handler.optional)):
                ln += self.last_handler_compressor[i].compress(values[shift + i])
        else:
            self.last_handler = handler
            self.last_handler_compressor = [_compressor(opt) for opt in handler.optional]

        ln += '}'
        self.wfile.write(ln)

    def write_end(self) -> None:
        if self.line_num > 0:
            self.wfile.write('\n')
