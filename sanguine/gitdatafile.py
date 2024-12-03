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
        return self.name + ':"' + val + '"'


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
            p0 = GitParamPathCompressor._to_json_fpath(path)
            assert '"' not in p0
            path = self.prefix + '"' + p0 + '"'
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
        assert path.startswith(self.prefix + '"')
        assert '"' not in path[len(self.prefix) + 1:]
        return path + '"'


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
        return self.name + r':"([^"]*)"'

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
        return self.name + r':"([^"]*)"'

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
        return self.name + r':"([^"]*)"'

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

        # warn(path)
        # warn(str(nmatch))
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
    compress_level: int

    def __init__(self, name: str, typ: GitDataType, can_skip: bool = True, compress_level=2) -> None:
        self.name = name
        self.typ = typ
        self.can_skip = can_skip
        self.compress_level = compress_level


def _compressor(p: GitDataParam) -> GitParamCompressor:
    match p.typ:
        case GitDataType.Path:
            return GitParamPathCompressor(p.name, p.compress_level)
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
    specific_fields: list[GitDataParam]  # fields in the list entry which are specific to handler

    def __init__(self, specific_fields: list[GitDataParam] = None) -> None:
        self.specific_fields = specific_fields if specific_fields is not None else []

    def decompress(self, param: tuple[str | int, ...]) -> None:  # we want to instantiate GitDataHandler,
        # but for such instantiations we don't need decompress()
        assert False


class GitDataList:
    common_fields: list[GitDataParam]  # fields which are common for all handlers
    handlers: list[GitDataHandler]

    def __init__(self, common_fields: list[GitDataParam], handlers: list[GitDataHandler]) -> None:
        if __debug__:
            assert not common_fields[0].can_skip

            if len(handlers) > 1:  # if there is only one handler, then there can be no problems distinguishing handlers,
                # even if the only handler has no parameters whatsoever
                for h in handlers:
                    assert not h.specific_fields[0].can_skip  # otherwise regex parsing may become ambiguous

                # handlers must distinguish by their first param (to avoid regex ambiguity)
                first_param_names = [h.specific_fields[0].name for h in handlers]
                assert len(first_param_names) == len(set(first_param_names))

            # there must be no duplicate names for any handler, including common_fields fields (to be JSON5-compliant)
            for h in handlers:
                all_param_names = [manda.name for manda in common_fields] + [opt.name for opt in h.specific_fields]
                assert len(all_param_names) == len(set(all_param_names))
        self.common_fields = common_fields
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
    common_fields_compressor: list[GitParamCompressor]
    last_handler: GitDataHandler | None
    last_handler_compressor: list[
        GitParamCompressor]  # we never go beyond last line, so only one (last) per-handler compressor is ever necessary
    line_num: int

    def __init__(self, df: GitDataList, wfile: typing.TextIO) -> None:
        self.df = df
        self.wfile = wfile
        self.common_fields_compressor = [_compressor(manda) for manda in df.common_fields]
        self.last_handler = None
        self.last_handler_compressor = []
        self.line_num = 0

    def write_begin(self) -> None:
        self.wfile.write('[\n')

    def write_line(self, handler: GitDataHandler, values: tuple) -> None:
        assert len(values) == len(self.df.common_fields) + len(handler.specific_fields)
        if self.line_num > 0:
            ln = ',\n{'
        else:
            ln = '{'
        lnempty = True
        self.line_num += 1
        assert len(self.common_fields_compressor) == len(self.df.common_fields)
        for i in range(len(self.df.common_fields)):
            compressed = self.common_fields_compressor[i].compress(values[i])
            if len(compressed):
                if lnempty:
                    lnempty = False
                else:
                    ln += ','
                ln += compressed

        shift = len(self.df.common_fields)
        if handler == self.last_handler:
            for i in range(len(handler.specific_fields)):
                ln += self.last_handler_compressor[i].compress(values[shift + i])
        else:
            self.last_handler = handler
            self.last_handler_compressor = [_compressor(opt) for opt in handler.specific_fields]

        ln += '}'
        self.wfile.write(ln)

    def write_end(self) -> None:
        if self.line_num > 0:
            self.wfile.write('\n')
        self.wfile.write(']\n')


### reading

class _GitHeaderFooterReader:
    comment_only_line: re.Pattern
    empty_line: re.Pattern

    def __init__(self) -> None:
        self.comment_only_line = re.compile(r'^\s*//')
        self.empty_line = re.compile(r'^\s*$')

    def parse_line(self, ln: str) -> bool:
        if self.comment_only_line.search(ln) or self.empty_line.search(ln):
            return True
        return False


class _GitDataListContentsReader:
    df: GitDataList
    common_fields_decompressor: list[GitParamDecompressor]
    last_handler: GitDataHandler | None
    comment_only_line: re.Pattern
    regexps: list[
        tuple[re.Pattern, GitDataHandler, list[tuple[int, GitParamDecompressor]], list[
            tuple[int, GitParamDecompressor]]]]  # decompressor lists are matched, skipped

    def __init__(self, df: GitDataList) -> None:
        self.df = df
        self.common_fields_decompressor = [_decompressor(cf) for cf in df.common_fields]
        self.last_handler = None
        self.comment_only_line = re.compile(r'^\s*//')
        self.regexps = []

        ncommon = len(self.df.common_fields)
        for h in self.df.handlers:
            canskip = []
            for i in range(ncommon):
                if self.df.common_fields[i].can_skip:
                    canskip.append(i)
            for i in range(len(h.specific_fields)):
                if h.specific_fields[i].can_skip:
                    canskip.append(ncommon + i)

            # warn(str(len(canskip)))
            assert len(canskip) <= ncommon + len(h.specific_fields)
            for mask in range(2 ** len(canskip)):  # scanning all pf them to get all 2**n possible bit mask patterns
                rex = '{'
                dmatched: list[tuple[int, GitParamDecompressor]] = []
                dskipped: list[tuple[int, GitParamDecompressor]] = []

                assert len(self.common_fields_decompressor) == len(df.common_fields) == ncommon
                for i in range(ncommon):
                    skip = False
                    if i in canskip:
                        idx = canskip.index(i)
                        assert idx >= 0
                        # warn('i='+str(i)+' idx='+str(idx))
                        if mask & (1 << idx):
                            skip = True
                            # warn('skip')

                    d = self.common_fields_decompressor[i]
                    if skip:
                        dskipped.append((i, d))
                    else:
                        dmatched.append((i, d))
                        if len(rex) != 1:
                            rex += ','
                        rex += d.regex_part()

                for i in range(len(h.specific_fields)):
                    j = ncommon + i
                    skip = False
                    if j in canskip:
                        idx = canskip.index(j)
                        if mask & (1 << idx):
                            skip = True

                    p = h.specific_fields[i]
                    d = _decompressor(p)
                    if skip:
                        dskipped.append((j, d))
                    else:
                        dmatched.append((j, d))
                        if len(rex) != 1:
                            rex += ','
                        rex += d.regex_part()

                rex += '}'
                # warn(rex)
                rexc: re.Pattern = re.compile(rex)
                assert len(dmatched) + len(dskipped) == ncommon + len(h.specific_fields)
                # warn(rex)
                # warn(repr(dmatched))
                # warn(repr(dskipped))
                self.regexps.append((rexc, h, dmatched, dskipped))

    def parse_line(self, ln) -> bool:  # returns False if didn't handle lm
        if self.comment_only_line.search(ln):
            return True
        for rex in self.regexps:
            (pattern, h, dmatched, dskipped) = rex
            # warn(pattern.pattern)
            m = pattern.match(ln)
            if m:
                assert len(dmatched) + len(dskipped) == len(self.df.common_fields) + len(h.specific_fields)
                param: list[str | int | None] = [None] * (len(self.df.common_fields) + len(h.specific_fields))

                if h != self.last_handler:  # duplicating a bit of code to move comparison out of the loop and speed things up a bit
                    for i in range(len(dmatched)):
                        matched = dmatched[i]
                        # warn(repr(pattern.pattern))
                        # warn('i='+str(i)+': '+repr(matched))
                        # warn(repr(m.group(i+1)))
                        d: GitParamDecompressor = matched[1]
                        d.reset()
                        param[matched[0]] = d.matched(m.group(i + 1))
                    for skipped in dskipped:
                        d: GitParamDecompressor = skipped[1]
                        d.reset()
                        param[skipped[0]] = d.skipped()
                    self.last_handler = h
                else:
                    for i in range(len(dmatched)):
                        matched = dmatched[i]
                        d: GitParamDecompressor = matched[1]
                        param[matched[0]] = d.matched(m.group(i + 1))
                    for skipped in dskipped:
                        d: GitParamDecompressor = skipped[1]
                        param[skipped[0]] = d.skipped()
                    self.last_handler = h

                h.decompress(tuple(param))
                return True

        return False


def skip_git_file_header(rfile: typing.TextIO) -> tuple[str, int]:
    openbracketfound: bool = False
    openbracket = re.compile(r'^\s*\{\s*$')
    rdh = _GitHeaderFooterReader()
    lineno = 1
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
    # info(ln)
    assert re.search(r'^\s*\[\s*$', ln)
    rda = _GitDataListContentsReader(dlist)
    while True:
        ln = rfile.readline()
        lineno += 1
        assert ln
        processed = rda.parse_line(ln)
        if not processed:
            warn(ln)
            assert re.search(r'^\s*]\s*$', ln)
            return lineno


def skip_git_file_footer(rfile: typing.TextIO, lineno: int) -> None:
    closebracketfound = False
    closebracket = re.compile(r'^\s*}\s*$')
    rdh = _GitHeaderFooterReader()
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
