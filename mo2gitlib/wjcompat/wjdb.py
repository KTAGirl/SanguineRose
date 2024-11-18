import gzip
import sqlite3

import mo2gitlib.wjcompat.binaryreader as binaryreader
from mo2gitlib.common import *
from mo2gitlib.files import File, ArchiveEntry


class _Img:
    w: int
    h: int
    mip : int
    fmt : int
    phash: bytes # len=40

    def __init__(self, br: binaryreader.BinaryReader) -> None:
        #binaryreader.trace_reader('Img:')
        self.w = br.read_uint16()
        self.h = br.read_uint16()
        self.mip = br.read_byte()
        self.fmt = br.read_byte()
        self.phash = br.read_bytes(40)

    def dbg_string(self) -> str:
        return '{ w=' + str(self.w) + ' h=' + str(self.h) + ' mip=' + str(self.mip) + ' fmt=' + str(
            self.fmt) + ' phash=[' + str(len(self.phash)) + ']}'


class _HashedFile:
    path: str
    file_hash: int
    img: _Img|None
    size: int
    children: list["_HashedFile"]

    def __init__(self, br: binaryreader.BinaryReader) -> None:
        #binaryreader.trace_reader('_HashedFile:')
        self.path = br.read_string()
        self.file_hash = br.read_uint64()
        if br.read_boolean():
            self.img = _Img(br)
            # print(self.img.__dict__)
            # br.dbg()
        else:
            self.img = None
        self.size = br.read_int64()
        assert (self.size >= 0)
        n = br.read_int32()
        assert (n >= 0)
        self.children = []
        for i in range(n):
            self.children.append(_HashedFile(br))

    def dbg_string(self) -> str:
        s = '{ path=' + self.path + ' hash=' + str(self.file_hash)
        if self.img:
            s += ' img=' + self.img.dbg_string()
        if len(self.children):
            s += ' children=['
            ci = 0
            for child in self.children:
                if ci:
                    s += ','
                s += child.dbg_string()
                ci += 1
            s += ']'
        s += ' }'
        return s


def _parse_contents(h, contents:bytes, gzipped:bool=True) -> _HashedFile|None:
    if gzipped:
        contents = gzip.decompress(contents)
    # print(contents)
    # print(rowi)
    # print(contents)
    try:
        br = binaryreader.BinaryReader(contents)

        hf = _HashedFile(br)
        assert (br.is_eof())
        # print(br.contents[br.offset:])
        # print(str(hash)+':'+hf.dbg())
        return hf
    except Exception as e:
        print("Parse Exception with hash=" + str(h) + ": " + str(e))
        print(traceback.format_exc())
        print(contents)
        dbgwait()
        return None


def _normalize_hash(h:int) -> int:
    if h < 0:
        return h + (1 << 64)
    else:
        return h


def _archive_entries(paths:list[str], hf:_HashedFile, root_archive_hash:int) -> list[ArchiveEntry]:
    aes = []
    for child in hf.children:
        cp = paths + [child.path]
        aes.append(ArchiveEntry(root_archive_hash, cp, child.size, child.file_hash))
        if len(child.children) > 0:
            aes2 = aes + _archive_entries(cp, child, root_archive_hash)
            aes = aes2
    return aes


def vfs_file_path() -> str:
    home_dir = os.path.expanduser("~")
    return home_dir + '\\AppData\\Local\\Wabbajack\\GlobalVFSCache5.sqlite'


def load_vfs() -> Generator[ArchiveEntry]:
    con = sqlite3.connect(vfs_file_path())
    cur = con.cursor()
    # rowi = -1
    nn = 0
    nx = 0
    for row in cur.execute('SELECT Hash,Contents FROM VFSCache'):
        contents = row[1]

        hf = _parse_contents(row[0], contents)
        nn += 1
        if hf is None:
            nx += 1
            warn('VFS: CANNOT PARSE' + str(contents) + ' FOR hash=' + str(hash) + '\n')
        else:
            aes = _archive_entries([], hf, hf.file_hash)
            for ae in aes:
                yield ae

    con.close()
    info('loadVFS: nn=' + str(nn) + ' nx=' + str(nx))


def _wj_timestamp_to_python_timestamp(wjftime:float) -> float:
    return (wjftime - 116444736000000000) / 10 ** 7


def hc_file_path() -> str:
    home_dir = os.path.expanduser("~")
    return home_dir + '\\AppData\\Local\\Wabbajack\\GlobalHashCache2.sqlite'


def load_hc(dst:Callable[[File],None]) -> None:
    con = sqlite3.connect(hc_file_path())
    cur = con.cursor()
    nn = 0
    nfiltered = 0
    for row in cur.execute('SELECT Path,LastModified,Hash FROM HashCache'):
        h = _normalize_hash(row[2])
        fi = File(h, _wj_timestamp_to_python_timestamp(row[1]), row[0])
        # olda = out[idx].get(hash)
        dst(fi)
    con.close()
    print('loadHC: nn=' + str(nn) + ' filtered out:' + str(nfiltered))
