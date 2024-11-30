import base64
import hashlib
import stat

from mo2gitlib.common import *

ZEROHASH = hashlib.sha256(b"")


def calculate_file_hash(fpath: str) -> bytes:  # using SHA-256, the fastest crypto-function because of hardware instruction
    st = os.lstat(fpath)
    assert stat.S_ISREG(st.st_mode) and not stat.S_ISLNK(st.st_mode)
    h = hashlib.sha256()
    blocksize = 1048576
    fsize = 0
    with open(fpath, 'rb') as f:
        while True:
            bb = f.read(blocksize)
            h.update(bb)
            lbb = len(bb)
            assert lbb <= blocksize
            fsize += lbb
            if lbb != blocksize:
                break

    # were there any changes while we were working?
    assert st.st_size == fsize
    st2 = os.lstat(fpath)
    assert st2.st_size == st.st_size
    assert st2.st_mtime == st.st_mtime
    return h.digest()


def truncate_file_hash(h: bytes) -> bytes:
    assert len(h) == 32
    return h[:9]


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


class File:
    file_hash: bytes | None
    file_path: str
    file_modified: float
    file_size: int | None

    def __init__(self, file_hash: bytes | None, file_modified: float | None, file_path: str,
                 file_size: int | None):
        assert file_path is not None
        self.file_hash = file_hash
        self.file_modified = file_modified
        self.file_path = file_path
        self.file_size = file_size

    def eq(self, other: "File") -> bool:
        if self.file_hash != other.file_hash:
            return False
        if self.file_modified != other.file_modified:
            return False
        if self.file_path != other.file_path:
            return False
        return True

    def to_json(self) -> str:
        if self.file_hash is None:
            return '{{"file_path":{},"file_hash":null}}'.format(escape_json(self.file_path))
        else:
            return '{{"file_hash":"{}","file_modified":{},"file_path":"{}"}}'.format(to_json_hash(self.file_hash),
                                                                                 self.file_modified, self.file_path)


class ArchiveEntry:
    archive_hash: bytes
    intra_path: list[str]
    file_size: int
    file_hash: bytes

    def __init__(self, archive_hash: bytes, intra_path: list[str], file_size: int, file_hash: bytes) -> None:
        self.archive_hash = archive_hash
        self.intra_path = intra_path
        self.file_size = file_size
        self.file_hash = file_hash

    def to_json(self) -> str:
        return '{{"archive_hash":"{}","intra_path":{},"file_size":{},"file_hash":"{}"}}'.format(
            to_json_hash(self.archive_hash), escape_json(self.intra_path), self.file_size, to_json_hash(self.file_hash))
