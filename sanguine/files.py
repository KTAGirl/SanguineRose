import hashlib
import stat
import tempfile
from abc import abstractmethod

from sanguine.common import *

_ZEROHASH = hashlib.sha256(b"")


def calculate_file_hash(
        fpath: str) -> tuple[int, bytes]:  # using SHA-256, the fastest crypto-hash because of hardware instruction
    st = os.lstat(fpath)
    assert stat.S_ISREG(st.st_mode) and not stat.S_ISLNK(st.st_mode)
    h = hashlib.sha256()
    blocksize = 1048576
    fsize = 0
    with open(fpath, 'rb') as f:
        while True:
            bb = f.read(blocksize)
            if not bb:
                break
            h.update(bb)
            lbb = len(bb)
            assert lbb <= blocksize
            fsize += lbb

    # were there any changes while we were working?
    assert st.st_size == fsize
    st2 = os.lstat(fpath)
    assert st2.st_size == st.st_size
    assert st2.st_mtime == st.st_mtime
    return fsize, h.digest()


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


class FileOnDisk:
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


class FileRetriever:  # new dog breed ;-)
    # Provides a base class for retrieving files from already-available data
    rel_path: str

    def __init__(self, rel_path: str) -> None:
        assert is_short_file_path(rel_path)
        self.rel_path = rel_path

    @abstractmethod
    def fetch(self, targetfpath: str):
        pass

    @abstractmethod
    def fetch_for_reading(self,
                          tmpdirpath: str) -> str:  # returns file path to work with; can be an existing file, or temporary within tmpdirpath
        pass


class ZeroFileRetriever(FileRetriever):
    @abstractmethod
    def fetch(self, targetfpath: str):
        open(targetfpath, 'wb').close()

    @abstractmethod
    def fetch_for_reading(self,
                          tmpdirpath: str) -> str:  # returns file path to work with; can be an existing file, or temporary within tmpdirpath
        wf, tfname = tempfile.mkstemp(dir=tmpdirpath)
        os.close(wf)  # yep, it is exactly enough to create temp zero file
        return tfname


def make_zero_retriever_if(mo2dir:str, fi: FileOnDisk) -> ZeroFileRetriever | None:
    assert is_normalized_dir_path(mo2dir)
    if fi.file_hash == _ZEROHASH or fi.file_size == 0:
        assert fi.file_hash == _ZEROHASH and fi.file_size == 0
        return ZeroFileRetriever(to_short_path(mo2dir,fi.file_path))
    else:
        return None


class PlainFileRetriever(FileRetriever):  # only partially specialized, needs further specialization to be usable
    fpath: str

    def __init__(self, fpath: str) -> None:
        super().__init__(fpath)
        self.fpath = fpath

    def fetch(self, targetfpath: str):
        shutil.copyfile(self.fpath, targetfpath)

    @abstractmethod
    def fetch_for_reading(self,
                          tmpdirpath: str) -> str:  # returns file path to work with; can be an existing file, or temporary within tmpdirpath
        return self.fpath


class FileDownloader:  # Provides a base class for downloading files
    pass
