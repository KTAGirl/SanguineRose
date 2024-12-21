import shutil
import tempfile

from sanguine.common import *
from sanguine.helpers.archives import FileInArchive

if typing.TYPE_CHECKING:
    from sanguine.cache.available_files import AvailableFiles


### generic FileRetriever

class FileRetriever(ABC):  # new dog breed ;-)
    # Provides a base class for retrieving files from already-available data
    file_hash: bytes
    file_size: int
    type _BaseInit = Callable[[FileRetriever], None] | tuple[bytes, int]

    def __init__(self, filehash: bytes, filesize: int) -> None:
        self.file_hash = filehash
        self.file_size = filesize

    @staticmethod
    def _init_from_child(parent, baseinit: _BaseInit) -> None:
        assert type(parent) is FileRetriever
        if isinstance(baseinit, tuple):
            (h, s) = baseinit
            parent.__init__(h, s)
        else:
            baseinit(parent)  # calls super().__init__(...) within

    @abstractmethod
    def fetch(self, available: "AvailableFiles", targetfpath: str):
        pass

    @abstractmethod
    def fetch_for_reading(self, available: "AvailableFiles",
                          tmpdirpath: str) -> str:  # returns file path to work with; can be an existing file, or temporary within tmpdirpath
        pass


class ZeroFileRetriever(FileRetriever):
    ZEROHASH = hashlib.sha256(b"").digest()

    # noinspection PyMissingConstructor
    #              _init_from_child() calls super().__init__()
    def __init__(self, baseinit: FileRetriever._BaseInit) -> None:
        if isinstance(baseinit, tuple):  # we can't use _init_from_child() here
            (h, s) = baseinit
            assert h == self.ZEROHASH
            assert s == 0
        FileRetriever._init_from_child(self, baseinit)

    def fetch(self, available: "AvailableFiles", targetfpath: str):
        assert is_normalized_file_path(targetfpath)
        open(targetfpath, 'wb').close()

    def fetch_for_reading(self, available: "AvailableFiles", tmpdirpath: str) -> str:
        wf, tfname = tempfile.mkstemp(dir=tmpdirpath)
        os.close(wf)  # yep, it is exactly enough to create temp zero file
        return tfname

    @staticmethod
    def make_retriever_if(h: bytes) -> "ZeroFileRetriever|None":
        if h == ZeroFileRetriever.ZEROHASH:
            return ZeroFileRetriever((ZeroFileRetriever.ZEROHASH, 0))
        else:
            return None


class GithubFileRetriever(FileRetriever):
    github_author: str  # '' for 'this project'
    github_project: str  # '' means 'this project'
    from_path: str

    # noinspection PyMissingConstructor
    #              _init_from_child() calls super().__init__()
    def __init__(self, baseinit: FileRetriever._BaseInit,
                 githubauthor: str, githubproject: str, frompath: str) -> None:
        FileRetriever._init_from_child(super(), baseinit)
        self.github_author = githubauthor
        self.github_project = githubproject
        self.from_path = frompath

    def _full_path(self) -> str:
        pass  # TODO!

    def fetch(self, available: "AvailableFiles", targetfpath: str):
        assert is_normalized_file_path(targetfpath)
        shutil.copyfile(self._full_path(), targetfpath)

    def fetch_for_reading(self, available: "AvailableFiles", tmpdirpath: str) -> str:
        return self._full_path()


class ArchiveFileRetrieverHelper(FileRetriever):
    archive_hash: bytes
    archive_size: int
    file_in_archive: FileInArchive

    # noinspection PyMissingConstructor
    #              _init_from_child() calls super().__init__()
    def __init__(self, baseinit: FileRetriever._BaseInit,
                 archive_hash: bytes, archive_size: int, file_in_archive: FileInArchive) -> None:
        FileRetriever._init_from_child(super(), baseinit)
        assert self.file_hash == file_in_archive.file_hash
        assert self.file_size == file_in_archive.file_size
        self.archive_hash = archive_hash
        self.archive_size = archive_size
        self.file_in_archive = file_in_archive

    def fetch(self, available: "AvailableFiles", targetfpath: str) -> None:
        assert False  # should not be called directly, only via archive aggregation

    def fetch_for_reading(self, available: "AvailableFiles", tmpdirpath: str) -> str:
        assert False  # should not be called directly, only via aggregation
        # noinspection PyUnreachableCode
        return ''


class ArchiveFileRetriever(FileRetriever):
    single_archive_retrievers: list[ArchiveFileRetrieverHelper]  # from outermost to innermost

    # noinspection PyMissingConstructor
    #              _init_from_child() calls super().__init__()
    def __init__(self, baseinit: FileRetriever._BaseInit, singles: list[ArchiveFileRetrieverHelper]) -> None:
        FileRetriever._init_from_child(super(), baseinit)
        if __debug__:
            for i in range(len(singles) - 1):
                assert singles[i].file_hash == singles[i + 1].archive_hash
        self.single_archive_retrievers = singles

    def constructor_parameter_appending_child(self, child: ArchiveFileRetrieverHelper) -> list[
        ArchiveFileRetrieverHelper]:
        assert self.single_archive_retrievers[-1].file_hash == child.archive_hash
        return self.single_archive_retrievers + [child]

    def constructor_parameter_prepending_parent(self, parent: ArchiveFileRetrieverHelper) -> list[
        ArchiveFileRetrieverHelper]:
        assert parent.file_hash == self.single_archive_retrievers[0].archive_hash
        return [parent] + self.single_archive_retrievers

    def constructor_parameter_removing_parent(self) -> list[ArchiveFileRetrieverHelper]:
        assert len(self.single_archive_retrievers) > 1
        return self.single_archive_retrievers[1:]

    def archive_hash(self) -> bytes:
        return self.single_archive_retrievers[0].archive_hash

    def fetch(self, available: "AvailableFiles", targetfpath: str) -> None:
        assert False  # should not be called directly, only via archive aggregation

    def fetch_for_reading(self, available: "AvailableFiles", tmpdirpath: str) -> str:
        assert False  # should not be called directly, only via archive aggregation
        # noinspection PyUnreachableCode
        return ''
