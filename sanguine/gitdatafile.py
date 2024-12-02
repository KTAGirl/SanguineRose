# we have reasons to have our own Json writer:
#  1. major. we need very specific gitdiff-friendly format
#  2. minor. we want to keep these files as small as feasible (while keeping them more or less readable),
#            hence JSON5 quote-less names, and path and elements "compression". It was seen to save 3.8x (2x for default pcompression=0),
#            for a 50M file, with overall GitHub limit being 100M, it is quite a bit

import re
import urllib.parse as urlparse
from abc import ABC, abstractmethod
from enum import Enum

from sanguine.common import *
from sanguine.files import from_json_hash, to_json_hash


### compressors

class GitParamCompressor(ABC):
    @abstractmethod
    def compress(self, val: int | str | None) -> str:
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
    prev: bytes | None

    def __init__(self, name: str, can_skip: bool) -> None:
        self.can_skip = can_skip
        self.name = name
        self.prev = None

    def compress(self, h: bytes) -> str:
        assert isinstance(h, bytes)
        if h is None:
            assert self.can_skip
            return ''
        if self.can_skip and self.prev == h:
            return ''
        self.prev = h
        return self.name + ':"' + to_json_hash(h) + '"'


class GitParamPathCompressor(GitParamCompressor):
    prefix: str
    level: int
    prevn: int
    prevpath: list[str]

    def __init__(self, name: str, level=2) -> None:
        self.prefix = name + ':'
        self.prevn = 0
        self.prevpath = []
        self.level = level

    @staticmethod
    def _to_json_fpath(fpath: str) -> str:
        return urlparse.quote(fpath, safe=" /+()'&#$[];,!@")

    def compress(self, path: str | None) -> str:
        if path is None:
            return ''
        assert isinstance(path, str)
        assert '/' not in path
        # assert('>' not in path)
        path = path.replace('\\', '/')
        if self.level == 0:
            path = self.prefix + '"' + GitParamPathCompressor._to_json_fpath(path) + '"'
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
                path = self.prefix + '"' + str(nmatch)
            else:
                assert nmatch <= 35
                path = self.prefix + '"' + chr(nmatch - 10 + 65)
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

class GitParamDecompressor(ABC):
    @abstractmethod
    def regex_part(self) -> str:
        pass

    @abstractmethod
    def matched(self, _: str) -> str | int:
        pass

    @abstractmethod
    def skipped(self) -> str | int:
        pass

    @abstractmethod
    def reset(self) -> None:
        pass


class GitParamIntDecompressor(GitParamDecompressor):
    name: str
    prev: int | None

    def __init__(self, name: str) -> None:
        self.name = name
        self.prev = None

    def regex_part(self) -> str:
        return self.name + r':([0-9]*)'

    def matched(self, match: str) -> int:
        self.prev = int(match)
        return self.prev

    def skipped(self) -> int:
        assert self.prev is not None
        return self.prev

    def reset(self) -> None:
        self.prev = None


class GitParamStrDecompressor(GitParamDecompressor):
    name: str
    prev: str | None

    def __init__(self, name: str) -> None:
        self.name = name
        self.prev = None

    def regex_part(self) -> str:
        return self.name + r':("([^"]*)"*)'

    def matched(self, match: str) -> str:
        self.prev = match
        return self.prev

    def skipped(self) -> str:
        assert self.prev is not None
        return self.prev

    def reset(self) -> None:
        self.prev = None


class GitParamHashDecompressor(GitParamDecompressor):
    name: str
    prev: bytes | None

    def __init__(self, name: str) -> None:
        self.name = name
        self.prev = None

    def regex_part(self) -> str:
        return self.name + r':("([^"]*)"*)'

    def matched(self, match: str) -> bytes:
        self.prev = from_json_hash(match)
        return self.prev

    def skipped(self) -> bytes:
        assert self.prev is not None
        return self.prev

    def reset(self) -> None:
        self.prev = None


class GitParamPathDecompressor(GitParamDecompressor):
    name: str
    prev: list[str] | None

    def __init__(self, name: str) -> None:
        self.name = name
        self.prev = None

    def regex_part(self) -> str:
        return self.name + r':("([^"]*)"*)'

    def matched(self, match: str) -> str:
        return self._decompress_json_path(match)

    def skipped(self) -> None:
        assert False

    def reset(self) -> None:
        self.prev = None

    @staticmethod
    def _from_json_fpath(fpath: str) -> str:
        return urlparse.unquote(fpath)

    def _decompress_json_path(self, path: str, level: int = 2) -> str:
        path = GitParamPathDecompressor._from_json_fpath(path)
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
            out += self.prev[i]
        if out != '':
            out += '/'
        out += path[1:]
        self.prev = out.split('/')
        return out.replace('/', '\\')


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


def _compressor(p: GitDataParam) -> GitParamCompressor:
    match p.typ:
        case GitDataType.Path:
            return GitParamPathCompressor(p.name, 2 if p.can_skip else 0)
        case GitDataType.Hash:
            return GitParamHashCompressor(p.name, p.can_skip)
        case GitDataType.Int:
            return GitParamIntCompressor(p.name, p.can_skip)
        case GitDataType.Str:
            return GitParamStrCompressor(p.name, p.can_skip)
        case _:
            assert False


def _decompressor(p: GitDataParam) -> GitParamDecompressor:
    match p.typ:
        case GitDataType.Path:
            return GitParamPathDecompressor(p.name)
        case GitDataType.Hash:
            return GitParamHashDecompressor(p.name)
        case GitDataType.Int:
            return GitParamIntDecompressor(p.name)
        case GitDataType.Str:
            return GitParamStrDecompressor(p.name)
        case _:
            assert False


class GitDataHandler(ABC):
    optional: list[GitDataParam]

    def __init__(self, optional: list[GitDataParam]) -> None:
        self.optional = optional

    @abstractmethod
    def decompress(self, param: tuple[str | int, ...]) -> None:
        pass


class GitDataList:
    mandatory: list[GitDataParam]
    handlers: list[GitDataHandler]

    def __init__(self, mandatory: list[GitDataParam], handlers: list[GitDataHandler]) -> None:
        if __debug__:
            assert not mandatory[0].can_skip

            if len(handlers) > 1:  # if there is only one handler, then there can be no problems distinguishing handlers, even if the only handler has no parameters whatsoever
                for h in handlers:
                    assert not h.optional[0].can_skip  # otherwise regex parsing may become ambiguous

            # handlers must distinguish by their first param (to avoid regex ambiguity)
            first_param_names = [h.optional[0].name for h in handlers]
            assert len(first_param_names) == len(set(first_param_names))

            # there must be no duplicate names for any handler, including mandatory fields (to be JSON5-compliant)
            for h in handlers:
                all_param_names = [manda.name for manda in mandatory] + [opt.name for opt in h.optional]
                assert len(all_param_names) == len(set(all_param_names))
        self.mandatory = mandatory
        self.handlers = handlers


### writing

def write_git_file_header(wfile: typing.TextIO) -> None:
    wfile.write('// This is JSON5 file, to save some space compared to JSON.\n')
    wfile.write('// Still, do not edit it by hand, SanguineRose parses it itself using regex to save time\n')
    wfile.write('{\n')


def write_git_file_footer(wfile: typing.TextIO) -> None:
    wfile.write('}\n')


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
        self.wfile.write('[\n')

    def write_line(self, handler: GitDataHandler, values: tuple) -> None:
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
        self.wfile.write(']\n')


### reading

class GitHeaderFooterReader:
    comment_only_line: re.Pattern

    def __init__(self) -> None:
        self.comment_only_line = re.compile(r'^\s*//')

    def parse_line(self, ln: str) -> bool:
        if self.comment_only_line.search(ln):
            return True
        return False


class _GitDataListContentsReader:
    df: GitDataList
    mandatory_decompressor: list[GitParamDecompressor]
    last_handler: GitDataHandler | None
    comment_only_line: re.Pattern
    regexps: list[
        tuple[re.Pattern, GitDataHandler, list[tuple[int, GitParamDecompressor]], list[
            tuple[int, GitParamDecompressor]]]]  # decompressor lists are matched, skipped

    def __init__(self, df: GitDataList) -> None:
        self.df = df
        self.mandatory_decompressor = [_decompressor(manda) for manda in df.mandatory]
        self.last_handler = None
        self.comment_only_line = re.compile(r'^\s*//')

        for h in self.df.handlers:
            canskip = []
            for i in range(len(h.optional)):
                if h.optional[i].can_skip:
                    canskip.append(i)

            for mask in range(2 ** len(canskip)):  # scanning all pf them to get all 2**n possible bit mask patterns
                skip = False
                rex = ''
                dmatched: list[tuple[int, GitParamDecompressor]] = []
                dskipped: list[tuple[int, GitParamDecompressor]] = []
                for i in range(len(h.optional)):
                    if i in canskip:
                        idx = canskip.index(i)
                        if mask & (1 << idx):
                            skip = True

                    p = h.optional[i]
                    d = _decompressor(p)
                    if skip:
                        dskipped.append((i, d))
                    else:
                        dmatched.append((i, d))
                        if len(rex) != 0:
                            rex += ','
                        rex += d.regex_part()

                rexc: re.Pattern = re.compile(rex)
                assert len(dmatched) + len(dskipped) == len(h.optional)
                self.regexps.append((rexc, h, dmatched, dskipped))

    def parse_line(self, ln) -> bool:  # returns False if didn't handle lm
        if self.comment_only_line.search(ln):
            return True
        for rex in self.regexps:
            (pattern, h, dmatched, dskipped) = rex
            m = pattern.match(ln)
            if m:
                assert len(dmatched) + len(dskipped) == len(h.optional)
                param: list[str | int | None] = [None] * len(h.optional)
                i = 1
                if h != self.last_handler:  # duplicating a bit of code to move comparison out of the loop and speed things up a bit
                    for matched in dmatched:
                        d: GitParamDecompressor = matched[1]
                        d.reset()
                        param[matched[0]] = d.matched(m.group(i))
                        i += 1
                    for skipped in dskipped:
                        d: GitParamDecompressor = skipped[1]
                        d.reset()
                        param[skipped[0]] = d.skipped()
                    self.last_handler = h
                else:
                    if h != self.last_handler:
                        for matched in dmatched:
                            d: GitParamDecompressor = matched[1]
                            param[matched[0]] = d.matched(m.group(i))
                            i += 1
                        for skipped in dskipped:
                            d: GitParamDecompressor = skipped[1]
                            param[skipped[0]] = d.skipped()

                h.decompress(tuple(param))
                return True

        return False


def skip_git_file_header(rfile: typing.TextIO) -> tuple[str, int]:
    openbracketfound: bool = False
    openbracket = re.compile(r'^\s*\{\s*$')
    rdh = GitHeaderFooterReader()
    lineno = 0
    while True:
        ln = rfile.readline()
        lineno += 1
        assert ln
        processed = rdh.parse_line(ln)
        if not processed:
            m = openbracket.match(ln)
            if m:
                assert not openbracketfound
                openbracketfound = True
            else:
                assert openbracketfound
                return ln, lineno


def read_git_file_list(dlist: GitDataList, rfile: typing.TextIO, lineno: int) -> int:
    ln = rfile.readline()
    assert re.search(r'^\s*\[\s*//', ln)
    rda = _GitDataListContentsReader(dlist)
    while True:
        ln = rfile.readline()
        lineno += 1
        assert ln
        processed = rda.parse_line(ln)
        if not processed:
            assert re.search(r'^\s*]\s*//', ln)
            return lineno


def skip_git_file_footer(rfile: typing.TextIO, lineno: int) -> None:
    closebracketfound = False
    closebracket = re.compile(r'^\s*}\s*$')
    rdh = GitHeaderFooterReader()
    while True:
        ln = rfile.readline()
        lineno += 1
        if not ln:
            assert closebracketfound
            return
        processed = rdh.parse_line(ln)
        if not processed:
            if closebracket.match(ln):
                assert not closebracketfound
                closebracketfound = True
            else:
                critical('Unrecognized line #' + str(lineno) + ':' + ln)
                abort_if_not(False)  # unknown pattern
