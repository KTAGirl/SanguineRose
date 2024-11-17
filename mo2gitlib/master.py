import base64
import re
import urllib.parse as urlparse

from cache import Cache
from mo2gitlib.common import *
from mo2gitlib.files import calculate_file_hash


# we have reasons to have our own Json writer:
#  1. major. we need very specific gitdiff-friendly format
#  2. minor. we want to keep these files as small as feasible (while keeping it more or less readable), 
#            hence JSON5 quote-less names, and path and elements "compression". It was seen to save 3.8x (2x for default pcompression=0), for a 50M file it is quite a bit

def _to_json_hash(h:int) -> str:
    assert (isinstance(h, int))
    assert (h >= 0)
    assert (h < 2 ** 64)
    # print(h)
    b = h.to_bytes(8, 'little', signed=False)
    b64 = base64.b64encode(b).decode('ascii')
    # print(b64)
    s = b64.rstrip('=')
    assert (_from_json_hash(s) == h)
    return s


def _from_json_hash(s:str) -> int:
    ntopad = (3 - (len(s) % 3)) % 3
    # print(ntopad)
    s += '=='[:ntopad]
    # print(s)
    b = base64.b64decode(s)
    h = int.from_bytes(b, byteorder='little')
    return h


def _to_json_fpath(fpath:str) -> str:
    return urlparse.quote(fpath, safe=" /+()'&#$[];,!@")


def _from_json_fpath(fpath:str) -> str:
    return urlparse.unquote(fpath)


def _compress_json_path(prevn:Val|None, prevpath:Val|None, path:str, level:int=2):
    assert '/' not in path
    # assert('>' not in path)
    path = path.replace('\\', '/')
    if level == 0:
        path = '"' + _to_json_fpath(path) + '"'
        assert ('"' not in path[1:-1])
        return path

    spl = path.split('/')
    # print(prevpath.val)
    # print(spl)
    nmatch = 0
    for i in range(min(len(prevpath.val), len(spl))):
        if spl[i] == prevpath.val[i]:
            nmatch = i + 1
        else:
            break
    assert nmatch >= 0
    if level == 2 or (level == 1 and prevn.val <= nmatch):
        if nmatch <= 9:
            path = '"' + str(nmatch)
        else:
            assert (nmatch <= 35)
            path = '"' + chr(nmatch - 10 + 65)
        needslash = False
        for i in range(nmatch, len(spl)):
            if needslash:
                path += '/'
            else:
                needslash = True
            path += _to_json_fpath(spl[i])
    else:  # skipping compression because of level restrictions
        path = '"0' + _to_json_fpath(path)
    prevpath.val = spl
    if prevn is not None:
        prevn.val = nmatch
    assert ('"' not in path[1:])
    return path + '"'


def _decompress_json_path(prevpath:Val, path:str, level:int=2):
    path = _from_json_fpath(path)
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


def _append_json_s(prevs:Val, s:int) -> str:
    if prevs.val == s:
        return ''
    prevs.val = s
    return ',s:' + str(s)


def _append_json_a(preva : Val, a:str):
    if preva.val == a:
        return ''
    preva.val = a
    return ',a:"' + a + '"'


class MasterArchiveItem:
    name: str
    item_hash: int
    def __init__(self, name:str, item_hash:int) -> None:
        self.name = name
        self.item_hash = item_hash

    def eq(self, b: "MasterArchiveItem") -> bool:
        if self.name != b.name:
            return False
        if self.item_hash != b.item_hash:
            return False
        return True


class MasterFileItem:
    file_path: str
    file_hash: int|None
    file_size: int|None
    archive_hash: int|None
    intra_path: list[str]|None
    gitpath: str|None
    warning: str|None

    def __init__(self, path:str, file_hash:int|None, file_size:int|None=None, archive_hash:int|None=None,
                intra_path:list[str]|None=None, gitpath:str|None=None, warning:str|None=None) -> None:
        self.file_path = path
        self.file_hash = file_hash
        self.file_size = file_size
        self.archive_hash = archive_hash
        self.intra_path = intra_path
        self.gitpath = gitpath
        self.warning = warning

    def eq(self, b:"MasterFileItem") -> bool:
        if self.file_path != b.file_path:
            return False
        if self.file_hash != b.file_hash:
            return False
        if self.file_size != b.file_size:
            return False
        if self.archive_hash != b.archive_hash:
            return False
        if self.gitpath != b.gitpath:
            return False
        if self.warning != b.warning:
            return False
        return True


class Master:
    archives: list[MasterArchiveItem]
    files: list[MasterFileItem]

    def __init__(self) -> None:
        self.archives = []
        self.files = []

    def construct_from_cache(self, nesx:Val, nwarn:Val, filecache:Cache, allinstallfiles:dict[int,str]) -> None:
        aif = []
        for h, path in allinstallfiles.items():
            fname = os.path.split(path)[1]
            aif.append((fname, h))
        aif.sort(key=lambda f: f[0])
        self.archives = [MasterArchiveItem(item[0], item[1]) for item in aif]

        files = [fi.file_path for fi in filecache.allFiles()]
        files.sort()

        targetdir = 'mo2\\'
        mo2 = filecache.folders.mo2
        mo2len = len(mo2)
        self.files = []
        for fpath0 in files:
            assert (fpath0.islower())
            assert (fpath0.startswith(mo2))
            fpath = fpath0[mo2len:]

            if is_esx(fpath):
                nesx.val += 1

            ae, archive, fi = filecache.findArchiveForFile(fpath0)
            if ae is None:
                processed = False

                srcpath = filecache.folders.github + targetdir + fpath
                if os.path.isfile(srcpath):  # TODO: add github tree to filecache and search/read hash from there
                    h = calculate_file_hash(srcpath)
                    self.files.append(MasterFileItem(fpath, h, gitpath=fpath))
                    processed = True

                if not processed:
                    if fi is not None:
                        self.files.append(MasterFileItem(fpath, fi.calculate_file_hash, warning='NF'))
                    else:
                        self.files.append(MasterFileItem(fpath, None, warning='NF'))
                    nwarn.val += 1
            else:
                if archive is None:
                    assert (ae.file_size == 0)
                    self.files.append(MasterFileItem(fpath, None, file_size=0))
                else:
                    fi = MasterFileItem(fpath, ae.calculate_file_hash, file_size=ae.file_size,
                                        archive_hash=ae.archive_hash, intra_path=[])
                    for path in ae.intra_path:
                        fi.intra_path.append(path)

                    if not allinstallfiles.get(ae.archive_hash):
                        fi.warning = 'NL'
                        nwarn.val += 1
                    self.files.append(fi)

    def all_files(self) -> Generator[MasterFileItem]:
        for fi in self.files:
            yield fi

    def write(self, wfile : typing.TextIO, masterconfig:dict[str,any]) -> None:
        level = masterconfig.get('pcompression', 0) if masterconfig is not None else 0
        assert (isinstance(level, int))

        wfile.write('// This is JSON5 file, to save some space compared to JSON.\n')
        wfile.write('// Still, do not edit it by hand, mo2git parses it itself using regex to save time\n')
        wfile.write('{ config: { pcompression: ' + str(level) + ' },\n')
        wfile.write('  archives: [ // Legend: n means "name", h means "hash"\n')
        na = 0
        for ar in self.archives:
            if na:
                wfile.write(",\n")
            na += 1
            wfile.write('{n:"' + _to_json_fpath(ar.name) + '",h:"' + _to_json_hash(ar.item_hash) + '"}')
        wfile.write('\n], files: [ // Legend: p means "path", h means "hash", s means "size", f means "from",')
        wfile.write('\n            //         a means "archive_hash", i means "intra_path"\n')

        nf = 0
        lastp = Val([])
        lasts = Val(None)
        lasta = Val(None)
        lastf = Val([])
        lasti = [Val(None)] * 2 # increasing it here will need adding more patterns to constructFromFile()
        nlasti = 0
        lastpn = Val(0)
        for fi in self.files:
            if nf:
                wfile.write(",\n")
            nf += 1

            wfile.write('{p:' + _compress_json_path(lastpn, lastp, fi.file_path, level))  # fi.path is mandatory
            if fi.file_hash is not None:
                wfile.write(',h:"' + _to_json_hash(fi.file_hash) + '"')
            else:
                # there is no lasth, but it is a special record (size==0)
                # print(fi.__dict__)
                assert (fi.warning is not None or fi.file_size == 0)

            if fi.file_size is not None:
                wfile.write(_append_json_s(lasts, fi.file_size))
            else:
                lasts.val = None
            if fi.archive_hash is not None:
                wfile.write(_append_json_a(lasta, _to_json_hash(fi.archive_hash)))
            else:
                lasta.val = None
            if fi.intra_path is not None:
                wfile.write(',i:[')
                np = 0
                for path in fi.intra_path:
                    if np:
                        wfile.write(',')
                    if np >= nlasti:
                        lasti[np] = Val([])
                    wfile.write(_compress_json_path(None, lasti[np], path))
                    np += 1
                wfile.write(']')
                nlasti = np
            else:
                nlasti = 0
            if fi.gitpath is not None:
                wfile.write(',g:' + _compress_json_path(None, lastf, fi.gitpath))
            else:
                lastf.val = []
            if fi.warning is not None:
                wfile.write(',warning:"' + fi.warning + '"')
            wfile.write('}')

        wfile.write('\n]}\n')

    def construct_from_file(self, rfile: typing.TextIO) -> None:
        self.archives = []
        self.files = []
        state = 0  # 0 - before archives, 1 - within archives, 2 - within files, 3 - finished

        patphsi = re.compile(r'^{p:"([^"]*)",h:"([^"]*)",s:([0-9]*),i:\["([^"]*)"]}(.)?')
        patphsai = re.compile(r'^{p:"([^"]*)",h:"([^"]*)",s:([0-9]*),a:"([^"]*)",i:\["([^"]*)"]}(.)?')
        patphai = re.compile(r'^{p:"([^"]*)",h:"([^"]*)",a:"([^"]*)",i:\["([^"]*)"]}(.)?')
        patphsii = re.compile(r'^{p:"([^"]*)",h:"([^"]*)",s:([0-9]*),i:\["([^"]*)","([^"]*)"]}(.)?')
        patphsaii = re.compile(r'^{p:"([^"]*)",h:"([^"]*)",s:([0-9]*),a:"([^"]*)",i:\["([^"]*)","([^"]*)"]}(.)?')
        patphi = re.compile(r'^{p:"([^"]*)",h:"([^"]*)",i:\["([^"]*)"]}(.)?')
        patphii = re.compile(r'^{p:"([^"]*)",h:"([^"]*)",i:\["([^"]*)","([^"]*)"]}(.)?')
        patphf = re.compile(r'^{p:"([^"]*)",h:"([^"]*)",g:"([^"]*)"}(.)?')
        patps0 = re.compile(r'^{p:"([^"]*)",s:0}(.)?')
        patphw = re.compile(r'^{p:"([^"]*)",h:"([^"]*)",warning:"([^"]*)"}(.)?')
        patpw = re.compile(r'^{p:"([^"]*)",warning:"([^"]*)"}(.)?')
        patp = re.compile(r'^{p:"([^"]*)"}(.)?')
        patnh = re.compile(r'^{n:"([^"]*)",h:"([^"]*)"}(.)?')
        patcomment = re.compile(r'^\s*//')

        patspecial0 = re.compile(r'^\s*{\s*config\s*:\s*\{\s*pcompression\s*:\s*([0-9]*)\s*}')
        patspecial1 = re.compile(r'^\s*archives\s*:\s*\[\s*//')
        patspecial2 = re.compile(r'^\s*]\s*,\s*files\s*:\s\[\s*//')
        patspecial3 = re.compile(r'^\s*]\s*}')

        lastp = Val([])
        lasts = Val(None)
        lasta = Val(None)
        #lastf = Val([])
        lasti = [Val(None)] * 2
        nlasti = Val(0)
        lastf = Val([])
        lineno = 0
        level = None
        for line in rfile:
            # ordered in rough order of probability to save time
            lineno += 1
            m = patphsi.match(line)
            if m:
                assert (state == 2)
                fi = _read_phsaii(m.group(1), m.group(2), m.group(3), None, m.group(4), None, lastp, lasts, lasta,
                                  nlasti, lasti, level)
                self.files.append(fi)
                lastf.val = []
                continue
            m = patphsai.match(line)
            if m:
                assert (state == 2)
                fi = _read_phsaii(m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), None, lastp, lasts, lasta,
                                  nlasti, lasti, level)
                self.files.append(fi)
                lastf.val = []
                continue
            m = patphi.match(line)
            if m:
                assert (state == 2)
                fi = _read_phsaii(m.group(1), m.group(2), None, None, m.group(3), None, lastp, lasts, lasta, nlasti,
                                  lasti, level)
                self.files.append(fi)
                lastf.val = []
                continue
            m = patphai.match(line)
            if m:
                assert (state == 2)
                fi = _read_phsaii(m.group(1), m.group(2), None, m.group(3), m.group(4), None, lastp, lasts, lasta,
                                  nlasti, lasti, level)
                self.files.append(fi)
                lastf.val = []
                continue
            m = patphsii.match(line)
            if m:
                assert (state == 2)
                fi = _read_phsaii(m.group(1), m.group(2), m.group(3), None, m.group(4), m.group(5), lastp, lasts, lasta,
                                  nlasti, lasti, level)
                self.files.append(fi)
                lastf.val = []
                continue
            m = patphii.match(line)
            if m:
                assert (state == 2)
                fi = _read_phsaii(m.group(1), m.group(2), None, None, m.group(3), m.group(4), lastp, lasts, lasta,
                                  nlasti, lasti, level)
                self.files.append(fi)
                lastf.val = []
                continue
            m = patphsaii.match(line)
            if m:
                assert (state == 2)
                fi = _read_phsaii(m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), m.group(6), lastp, lasts,
                                  lasta, nlasti, lasti, level)
                self.files.append(fi)
                lastf.val = []
                continue
            m = patphf.match(line)
            if m:
                assert (state == 2)
                fi = MasterFileItem(_decompress_json_path(lastp, m.group(1), level), _from_json_hash(m.group(2)))
                ff = _decompress_json_path(lastf, m.group(3))
                fi.gitpath = ff
                self.files.append(fi)
                lasts.val = None
                lasta.val = None
                nlasti.val = 0
                continue
            m = patps0.match(line)
            if m:
                assert (state == 2)
                fi = MasterFileItem(_decompress_json_path(lastp, m.group(1), level), None)
                ss = 0
                fi.file_size = ss
                self.files.append(fi)
                lasts.val = ss
                lasta.val = None
                nlasti.val = 0
                lastf.val = []
                continue
            m = patp.match(line)
            if m:
                assert (state == 2)
                fi = MasterFileItem(_decompress_json_path(lastp, m.group(1), level), None)
                fi.file_size = lasts.val
                self.files.append(fi)
                lasta.val = None
                nlasti.val = 0
                lastf.val = []
                continue
            m = patphw.match(line)
            if m:
                assert (state == 2)
                fi = MasterFileItem(_decompress_json_path(lastp, m.group(1), level), _from_json_hash(m.group(2)))
                fi.warning = m.group(3)
                self.files.append(fi)
                lasts.val = None
                lasta.val = None
                nlasti.val = 0
                lastf.val = []
                continue
            m = patpw.match(line)
            if m:
                assert (state == 2)
                fi = MasterFileItem(_decompress_json_path(lastp, m.group(1), level), None)
                fi.warning = m.group(2)
                self.files.append(fi)
                lasts.val = None
                lasta.val = None
                nlasti.val = 0
                lastf.val = []
                continue
            m = patnh.match(line)
            if m:
                assert (state == 1)
                ar = MasterArchiveItem(_from_json_fpath(m.group(1)), _from_json_hash(m.group(2)))
                self.archives.append(ar)
                continue
            m = patcomment.match(line)
            if m:
                continue
            m = patspecial0.match(line)
            if m:
                assert state == 0
                level = int(m.group(1))
                assert 0 <= level <= 2
                continue
            m = patspecial1.match(line)
            if m:
                assert state == 0
                state = 1
                continue
            m = patspecial2.match(line)
            if m:
                assert state == 1
                state = 2
                continue
            m = patspecial3.match(line)
            if m:
                assert (state == 2)
                state = 3
                continue

            print('unable to parse line #' + str(lineno) + ': ' + line)
            aassert(False)

        assert (state == 3)


def _read_phsaii(p:str, h:str, s:int|None, a:str|None, i1:str|None, i2:str|None, lastp:Val, lasts:Val, lasta:Val, nlasti:Val, lasti:list[Val], level:int|None):
    fi = MasterFileItem(_decompress_json_path(lastp, p, level), _from_json_hash(h) if h is not None else None)

    if s is None:
        fi.file_size = lasts.val
    else:
        ss = int(s)
        fi.file_size = ss
        lasts.val = ss
    if a is None:
        fi.archive_hash = lasta.val
    else:
        aa = _from_json_hash(a)
        fi.archive_hash = aa
        lasta.val = aa
    if i1 is not None:
        if nlasti.val == 0:
            lasti[0] = Val([])
            nlasti.val = 1
        fi.intra_path = [_decompress_json_path(lasti[0], i1)]
    if i2 is not None:
        assert (i1 is not None)
        assert (nlasti.val > 0)
        assert (len(fi.intra_path) == 1)
        if nlasti.val == 1:
            lasti[1] = Val([])
            nlasti.val = 2
        fi.intra_path.append(_decompress_json_path(lasti[1], i2))
    return fi
