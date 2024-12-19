# we have reasons to have our own Json writer:
#  1. major. we need very specific gitdiff-friendly format
#  2. minor. we want to keep these files as small as feasible (while keeping them more or less readable),
#            hence JSON5 quote-less names, and path and elements "compression". It was seen to save 3.8x (2x for default pcompression=0),
#            for a 50M file, with overall GitHub limit being 100M, it is quite a bit

import re
import urllib.parse as urlparse
from enum import Enum

from sanguine.common import *


### helper

def open_git_data_file_for_writing(fpath: str) -> typing.TextIO:
    return open(fpath, 'wt', encoding='utf-8', newline='\n')


def open_git_data_file_for_reading(fpath: str) -> typing.TextIO:
    return open(fpath, 'rt', encoding='utf-8')


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
    can_skip: bool
    prefix: str
    level: int
    prevn: int
    prevpath: list[str]

    def __init__(self, name: str, can_skip: bool, level: int) -> None:
        self.prefix = name + ':'
        self.prevn = 0
        self.prevpath = []
        self.level = level
        self.can_skip = can_skip

    @staticmethod
    def _to_json_fpath(fpath: str) -> str:
        return urlparse.quote(fpath, safe=" /+()'&#$[];,!@")

    def compress(self, path: str | None) -> str:
        if path is None:
            return ''
        assert isinstance(path, str)
        assert '/' not in path
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
        lspl = len(spl)
        lprev = len(self.prevpath)
        for i in range(min(lprev, lspl)):
            if spl[i] == self.prevpath[i]:
                nmatch = i + 1
            else:
                break

        assert 0 <= nmatch < lspl
        processed = False
        if self.level >= 2 and lprev == lspl and nmatch == lspl - 1:
            # for 'a'-'f' codes explanation, see decompressor
            old = self.prevpath[-1]
            new = spl[-1]
            oldext = os.path.splitext(old)
            newext = os.path.splitext(new)
            if oldext[1] == newext[1]:
                old = oldext[0]
                new = newext[0]
                common = os.path.commonprefix([old, new])
                nleft = len(new) - len(common)
                ncut = len(old) - len(common)
                assert nleft >= 0 and ncut >= 0
                if ncut == 1:
                    if nleft == 1 and '0' <= new[-1] <= '9' and '0' <= old[-1] <= '9' and int(new[-1]) == int(
                            old[-1]) + 1:
                        path = None  # instead of legacy 'c'
                        processed = True
                    elif nleft == 1 and 'a' <= new[-1] <= 'z' and 'a' <= old[-1] <= 'z' and ord(new[-1]) == ord(
                            old[-1]) + 1:
                        path = None  # instead of legacy 'c'
                        processed = True
                    else:
                        if nleft > 0:
                            path = self.prefix + '"b' + new[-nleft:]
                        else:
                            path = self.prefix + '"b'
                        processed = True
                elif ncut <= 35:
                    if ncut == 0:
                        path = self.prefix + '"d'
                    else:
                        path = self.prefix + '"a' + (str(ncut) if (ncut <= 9) else chr(ncut - 10 + 65))
                    if nleft > 0:
                        path += new[-nleft:]
                    processed = True
                if not processed:
                    path = self.prefix + '"f' + newext[0]
                    processed = True
            elif oldext[0] == newext[0]:
                assert newext[1].startswith('.')
                path = self.prefix + '"e' + newext[1][1:]
                processed = True

        if not processed:
            if nmatch <= 9:
                path = self.prefix + '"' + str(nmatch)
            else:
                assert nmatch <= 35
                path = self.prefix + '"' + chr(nmatch - 10 + 65)

            needslash = False
            for i in range(nmatch, lspl):
                if needslash:
                    path += '/'
                else:
                    needslash = True
                path += GitParamPathCompressor._to_json_fpath(spl[i])

        self.prevpath = spl
        self.prevn = nmatch
        if path is None:
            if self.can_skip:
                return ''
            else:
                return self.prefix + '""'
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

    def __init__(self, name: str, level: int) -> None:
        self.name = name
        self.prev = None
        self.level = level

    def regex_part(self) -> str:
        return self.name + r':"([^"]*)"'

    def matched(self, match: str) -> str:
        return self._decompress_json_path(match, self.level)

    def skipped(self) -> str:
        return self._decompress_json_path('', self.level)

    def reset(self) -> None:
        self.prev = None

    @staticmethod
    def _from_json_fpath(fpath: str) -> str:
        return urlparse.unquote(fpath)

    def _decompress_json_path(self, path: str, level: int) -> str:
        path = GitParamPathDecompressor._from_json_fpath(path)
        if level == 0:
            return path.replace('/', '\\')

        if path == '':
            path = 'c'  # pretty ugly, but historical 'c' was replaced by ''
        p0 = path[0]
        if '0' <= p0 <= '9':
            nmatch = int(p0)
        elif 'A' <= p0 <= 'Z':
            nmatch = ord(p0) - 65 + 10
        elif 'a' <= p0 <= 'f':
            nmatch = len(self.prev) - 1
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

        if p0 == 'a':  # aN, cut off N symbols from previous fname, add what follows aN, and previous extension
            fname, ext = os.path.splitext(self.prev[-1])
            p1 = path[1]
            n = (ord(p1) - 65 + 10) if ('A' <= p1 <= 'Z') else int(p1)
            if n == 0:
                out += fname + path[2:] + ext
            else:
                out += fname[:-n] + path[2:] + ext
        elif p0 == 'b':  # === 'a1'
            fname, ext = os.path.splitext(self.prev[-1])
            out += fname[:-1] + path[1:] + ext
        elif p0 == 'c':  # increment last digit of fname, keep previous extension
            fname, ext = os.path.splitext(self.prev[-1])
            if '0' <= fname[-1] <= '9':
                out += fname[:-1] + str(int(fname[-1]) + 1) + ext
            else:
                out += fname[:-1] + chr(ord(fname[-1]) + 1) + ext
        elif p0 == 'd':  # === a0
            fname, ext = os.path.splitext(self.prev[-1])
            out += fname + path[1:] + ext
        elif p0 == 'e':  # keep previous fname, change extension
            fname, ext = os.path.splitext(self.prev[-1])
            out += fname + '.' + path[1:]
        elif p0 == 'f':  # keep previous extension, change fname
            fname, ext = os.path.splitext(self.prev[-1])
            out += path[1:] + ext
        else:
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
            return GitParamPathCompressor(p.name, p.can_skip, p.compress_level)
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
            return GitParamPathDecompressor(p.name, p.compress_level)
        case GitDataType.Hash:
            return GitParamHashDecompressor(p.name)
        case GitDataType.Int:
            return GitParamIntDecompressor(p.name)
        case GitDataType.Str:
            return GitParamStrDecompressor(p.name)
        case _:
            assert False


class GitDataWriteHandler:
    specific_fields: list[GitDataParam]  # fields in the list entry which are specific to handler

    def __init__(self, specific_fields: list[GitDataParam] = None) -> None:
        self.specific_fields = specific_fields if specific_fields is not None else []


class GitDataReadHandler(GitDataWriteHandler):
    @abstractmethod
    def decompress(self, common_param: tuple[str | int | bytes, ...],
                   specific_param: tuple[str | int | bytes, ...]) -> None:
        pass


class GitDataWriteList:
    common_fields: list[GitDataParam]  # fields which are common for all handlers
    handlers: list[GitDataWriteHandler]

    def __init__(self, common_fields: list[GitDataParam], handlers: list[GitDataWriteHandler]) -> None:
        if __debug__:
            assert not common_fields[0].can_skip

            if len(handlers) > 1:  # if there is only one handler, then there can be no problems distinguishing handlers,
                # even if the only handler has no parameters whatsoever
                for h in handlers:
                    assert not h.specific_fields[0].can_skip  # otherwise regex parsing may become ambiguous

                # handlers must distinguish by their first param (to avoid regex ambiguity)
                first_param_names = [(h.specific_fields[0].name if len(h.specific_fields) > 0 else '') for h in
                                     handlers]
                assert len(first_param_names) == len(set(first_param_names))

            # there must be no duplicate names for any handler, including common_fields fields (to be JSON5-compliant)
            for h in handlers:
                all_param_names = [manda.name for manda in common_fields] + [opt.name for opt in h.specific_fields]
                assert len(all_param_names) == len(set(all_param_names))
        self.common_fields = common_fields
        self.handlers = handlers


class GitDataReadList(GitDataWriteList):
    def __init__(self, common_fields: list[GitDataParam], handlers: list[GitDataReadHandler]) -> None:
        super().__init__(common_fields, handlers)

    def read_handlers(self) -> list[GitDataReadHandler]:
        # noinspection PyTypeChecker
        # we do know what we're doing here: it is indeed a list of GitDataReadHanders, as guaranteed by __init__(handlers:list[GitDataReadHandler])
        return self.handlers


### writing

def write_git_file_header(wfile: typing.TextIO) -> None:
    wfile.write('// This is JSON5 file, to save some space compared to JSON.\n')
    wfile.write('// Still, do not edit it by hand, SanguineRose parses it itself using regex to save time\n')
    wfile.write('{\n')


def write_git_file_footer(wfile: typing.TextIO) -> None:
    wfile.write('}\n')


class GitDataListWriter:
    df: GitDataWriteList
    wfile: typing.TextIO
    common_fields_compressors: list[GitParamCompressor]
    last_handler: GitDataWriteHandler | None
    last_handler_compressors: list[
        GitParamCompressor]  # we never go beyond last line, so only one (last) per-handler compressor is ever necessary
    line_num: int

    def __init__(self, df: GitDataWriteList, wfile: typing.TextIO) -> None:
        self.df = df
        self.wfile = wfile
        self.common_fields_compressors = [_compressor(cf) for cf in df.common_fields]
        self.last_handler = None
        self.last_handler_compressors = []
        self.line_num = 0

    def write_begin(self) -> None:
        self.wfile.write('[\n')

    def write_line(self, handler: GitDataWriteHandler, common_values: tuple, specific_values: tuple = ()) -> None:
        assert len(common_values) == len(self.df.common_fields)
        assert len(specific_values) == len(handler.specific_fields)
        if self.line_num > 0:
            ln = ',\n{'
        else:
            ln = '{'
        lnempty = True
        self.line_num += 1
        assert len(self.common_fields_compressors) == len(self.df.common_fields)
        for i in range(len(self.df.common_fields)):
            compressed = self.common_fields_compressors[i].compress(common_values[i])
            if len(compressed):
                if lnempty:
                    lnempty = False
                else:
                    ln += ','
                ln += compressed

        if handler == self.last_handler:
            pass
        else:
            self.last_handler = handler
            self.last_handler_compressors = [_compressor(opt) for opt in handler.specific_fields]

        for i in range(len(handler.specific_fields)):
            compressed = self.last_handler_compressors[i].compress(specific_values[i])
            if len(compressed):
                if lnempty:
                    lnempty = False
                else:
                    ln += ','
                ln += compressed

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
    df: GitDataReadList
    common_fields_decompressor: list[GitParamDecompressor]
    last_handler: GitDataReadHandler | None
    comment_only_line: re.Pattern
    regexps: list[
        tuple[re.Pattern, GitDataReadHandler, list[tuple[int, GitParamDecompressor]], list[
            tuple[int, GitParamDecompressor]]]]  # decompressor lists are matched, skipped

    def __init__(self, df: GitDataReadList) -> None:
        self.df = df
        self.common_fields_decompressor = [_decompressor(cf) for cf in df.common_fields]
        self.last_handler = None
        self.comment_only_line = re.compile(r'^\s*//')
        self.regexps = []

        ncommon = len(self.df.common_fields)
        for h in self.df.read_handlers():
            canskip = []
            for i in range(ncommon):
                if self.df.common_fields[i].can_skip:
                    canskip.append(i)
            for i in range(len(h.specific_fields)):
                if h.specific_fields[i].can_skip:
                    canskip.append(ncommon + i)

            # warn(str(len(canskip)))
            assert len(canskip) <= ncommon + len(h.specific_fields)
            handlerds = [_decompressor(p) for p in h.specific_fields]
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

                    # p = h.specific_fields[i]
                    d = handlerds[i]
                    if skip:
                        dskipped.append((j, d))
                    else:
                        dmatched.append((j, d))
                        if len(rex) != 1:
                            rex += ','
                        rex += d.regex_part()

                rex += '}'  # instrumental for supporting empty h.specific_fields
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
                    # info(repr(h))
                    # info(repr(self.last_handler))
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
                        # info(str(skipped[0]))
                        # info(repr(d))
                        param[skipped[0]] = d.skipped()
                    self.last_handler = h

                ncommon = len(self.df.common_fields)
                h.decompress(tuple(param[:ncommon]), tuple(param[ncommon:]))
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


def read_git_file_list(dlist: GitDataReadList, rfile: typing.TextIO, lineno: int) -> int:
    rda = _GitDataListContentsReader(dlist)

    ln = rfile.readline()
    # info(ln)

    while rda.comment_only_line.match(ln):
        ln = rfile.readline()
    assert re.search(r'^\s*\[\s*$', ln)

    while True:
        ln = rfile.readline()
        lineno += 1
        assert ln
        # warn(ln)
        processed = rda.parse_line(ln)
        if not processed:
            # warn(ln)
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
