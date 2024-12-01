import base64
import hashlib
import stat

ZEROHASH = hashlib.sha256(b"")


def calculate_file_hash(
        fpath: str) -> bytes:  # using SHA-256, the fastest crypto-function because of hardware instruction
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


#####

from mo2gitlib.gitdatafile import *


class FileInArchive:
    file_hash: bytes
    intra_path: list[str]
    file_size: int

    def __init__(self, file_hash: bytes, file_size: int, intra_path: list[str]) -> None:
        self.file_hash = file_hash
        self.file_size = file_size
        self.intra_path = intra_path


class Archive:
    archive_hash: bytes
    archive_size: int
    files: list[FileInArchive]

    def __init__(self, archive_hash: bytes, archive_size: int, files: list[FileInArchive]) -> None:
        self.archive_hash = archive_hash
        self.archive_size = archive_size
        self.files = sorted(files, key=lambda f: f.intra_path[0] + (f.intra_path[1] if len(f.intra_path) > 1 else ''))


### GitCommonArchive

class GitMasterArchiveHandler(GitDataHandler):
    archives: list[Archive]
    optional: list[GitDataParam] = []

    def __init__(self, archives: list[Archive]) -> None:
        super().__init__(self.optional)
        self.archives = archives

    def decompress(self, param: tuple[str, str, bytes, int, bytes, int]) -> None:
        (i, i2, a, x, h, s) = param
        found = None
        if len(self.archives) > 0:
            ar = self.archives[-1]
            if ar.archive_hash == a:
                assert ar.archive_size == x
                found = ar

        if found is None:
            found = Archive(a, x, [])

        found.files.append(FileInArchive(h, s, [i] if i2 is None else [i, i2]))


class GitMasterArchiveFile:
    _aentry_mandatory: list[GitDataParam] = [
        GitDataParam('i', GitDataType.Path, False),
        GitDataParam('i2', GitDataType.Path),
        GitDataParam('a', GitDataType.Hash),  # archive hash
        GitDataParam('x', GitDataType.Int),  # archive size
        GitDataParam('h', GitDataType.Hash, False),  # file hash (truncated)
        GitDataParam('s', GitDataType.Int)  # file size
    ]

    archives: list[Archive]

    def __init__(self) -> None:
        self.archives = []

    def write(self, wfile: typing.TextIO) -> None:
        write_file_header_comment(wfile)
        wfile.write(
            '  archives: [ // Legend: i=intra_archive_path, i2=intra_archive_path2, a=archive_hash, x=archive_size, h=file_hash, s=file_size\n')

        ahandler = GitDataHandler(GitMasterArchiveHandler.optional)
        da = GitDataList(self._aentry_mandatory, [ahandler])
        writera = GitDataListWriter(da, wfile)
        writera.write_begin()
        for ar in self.archives:
            for fi in ar.files:
                writera.write_line(ahandler, (
                    fi.intra_path[0], fi.intra_path[1] if len(fi.intra_path) > 1 else None, ar.archive_hash,
                    ar.archive_size, truncate_file_hash(fi.file_hash), fi.file_size))
        writera.write_end()
        wfile.write('\n]}\n')

    def construct_from_file(self, rfile: typing.TextIO) -> None:
        assert len(self.archives) == 0

        # skipping header
        archivestart = re.compile(r'^\s*archives\s*:\s*\[\s*//')
        lineno = skip_git_file_header(rfile, archivestart)

        # reading archives: [ ...
        filesend = re.compile(r'^\s*]\s*}')
        da = GitDataList(self._aentry_mandatory, [GitMasterArchiveHandler(self.archives)])
        lineno = read_git_file_section(da, rfile, lineno, filesend)

        # skipping footer
        skip_git_file_footer(rfile, lineno)
