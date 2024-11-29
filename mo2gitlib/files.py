import xxhash

from mo2gitlib.common import *

ZEROHASH = 17241709254077376921  # xxhash for 0 size


def calculate_file_hash(fpath: str) -> int:  # our file hash function, compatible with WJ
    h = xxhash.xxh64()
    blocksize = 1048576
    with open(fpath, 'rb') as f:
        while True:
            bb = f.read(blocksize)
            h.update(bb)
            assert (len(bb) <= blocksize)
            if len(bb) != blocksize:
                return h.intdigest()


class File:
    file_hash: int
    file_path: str
    file_modified: float
    file_size: int | None

    def __init__(self, file_hash: int | None, file_modified: float | None, file_path: str,
                 file_size: int | None):
        assert (file_path is not None)
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
        # works both for ar=Archive, and ar=SimpleNamespace
        # for SimpleNamespace cannot use return json.dumps(self,default=lambda o: o.__dict__)
        if self.file_hash is None:
            return '{"file_path": ' + escape_json(self.file_path) + ', "file_hash":null}'
        else:
            return '{"file_hash":' + str(self.file_hash) + ', "file_modified": ' + str(
                self.file_modified) + ', "file_path": ' + escape_json(self.file_path) + '}'


class ArchiveEntry:
    archive_hash: int
    intra_path: list[str]
    file_size: int
    file_hash: int

    def __init__(self, archive_hash: int, intra_path: list[str], file_size: int, file_hash: int) -> None:
        self.archive_hash = archive_hash
        self.intra_path = intra_path
        self.file_size = file_size
        self.file_hash = file_hash

    def to_json(self) -> str:
        # works both for ar=ArchiveEntry, and ar=SimpleNamespace
        # for SimpleNamespace cannot use return json.dumps(self,default=lambda o: o.__dict__)
        return '{"archive_hash":' + str(self.archive_hash) + ', "intra_path": ' + escape_json(
            self.intra_path) + ', "file_size": ' + str(self.file_size) + ', "file_hash": ' + str(self.file_hash) + '}'
