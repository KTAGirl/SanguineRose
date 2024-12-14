import hashlib
import shutil
import tempfile

from sanguine.archives import FileInArchive
from sanguine.common import *
from sanguine.folder_cache import FileOnDisk

if typing.TYPE_CHECKING:
    from sanguine.available import AvailableFiles


### generic FileRetriever

class FileRetriever:  # new dog breed ;-)
    # Provides a base class for retrieving files from already-available data
    available: AvailableFiles
    file_hash: bytes
    file_size: int
    type _BaseInit = Callable[[FileRetriever], None] | tuple[bytes, int]

    def __init__(self, available: AvailableFiles, filehash: bytes, filesize: int) -> None:
        self.available = available
        self.file_hash = filehash
        self.file_size = filesize

    @staticmethod
    def _init_from_child(parent, available: AvailableFiles, baseinit: _BaseInit) -> None:
        assert type(parent) is FileRetriever
        if isinstance(baseinit, tuple):
            (h, s) = baseinit
            parent.__init__(available, h, s)
        else:
            baseinit(parent)  # calls super().__init__(...) within

    @abstractmethod
    def fetch(self, targetfpath: str):
        pass

    @abstractmethod
    def fetch_for_reading(self,
                          tmpdirpath: str) -> str:  # returns file path to work with; can be an existing file, or temporary within tmpdirpath
        pass


class ZeroFileRetriever(FileRetriever):
    ZEROHASH = hashlib.sha256(b"").digest()

    # noinspection PyMissingConstructor
    #              _init_from_child() calls super().__init__()
    def __init__(self, available: AvailableFiles, baseinit: FileRetriever._BaseInit) -> None:
        if isinstance(baseinit, tuple):  # we can't use _init_from_child() here
            (h, s) = baseinit
            assert h == self.ZEROHASH
            assert s == 0
        FileRetriever._init_from_child(self, available, baseinit)

    def fetch(self, targetfpath: str):
        assert is_normalized_file_path(targetfpath)
        open(targetfpath, 'wb').close()

    def fetch_for_reading(self, tmpdirpath: str) -> str:
        wf, tfname = tempfile.mkstemp(dir=tmpdirpath)
        os.close(wf)  # yep, it is exactly enough to create temp zero file
        return tfname

    @staticmethod
    def make_retriever_if(available: AvailableFiles, fi: FileOnDisk) -> "ZeroFileRetriever|None":
        if fi.file_hash == ZeroFileRetriever.ZEROHASH or fi.file_size == 0:
            assert fi.file_hash == ZeroFileRetriever.ZEROHASH and fi.file_size == 0
            return ZeroFileRetriever(available, (ZeroFileRetriever.ZEROHASH, 0))
        else:
            return None


class GithubFileRetriever(FileRetriever):  # only partially specialized, needs further specialization to be usable
    github_author: str  # '' for 'this project'
    github_project: str  # '' means 'this project'
    from_path: str

    # noinspection PyMissingConstructor
    #              _init_from_child() calls super().__init__()
    def __init__(self, available: AvailableFiles, baseinit: FileRetriever._BaseInit,
                 githubauthor: str, githubproject: str, frompath: str) -> None:
        FileRetriever._init_from_child(super(), available, baseinit)
        self.github_author = githubauthor
        self.github_project = githubproject
        self.from_path = frompath

    def _full_path(self) -> str:
        pass  # TODO!

    def fetch(self, targetfpath: str):
        assert is_normalized_file_path(targetfpath)
        shutil.copyfile(self._full_path(), targetfpath)

    def fetch_for_reading(self, tmpdirpath: str) -> str:
        return self._full_path()


class FileRetrieverFromSingleArchive(FileRetriever):
    archive_hash: bytes
    archive_size: int
    file_in_archive: FileInArchive

    # noinspection PyMissingConstructor
    #              _init_from_child() calls super().__init__()
    def __init__(self, available: AvailableFiles, baseinit: FileRetriever._BaseInit,
                 archive_hash: bytes, archive_size: int, file_in_archive: FileInArchive) -> None:
        FileRetriever._init_from_child(super(), available, baseinit)
        self.archive_hash = archive_hash
        self.archive_size = archive_size
        self.file_in_archive = file_in_archive

    def fetch(self, targetfpath: str) -> None:
        pass
        # TODO!

    def fetch_for_reading(self, tmpdirpath: str) -> str:
        pass
        # TODO!


class FileRetrieverFromNestedArchives(FileRetriever):
    single_archive_retrievers: list[FileRetrieverFromSingleArchive]

    # noinspection PyMissingConstructor
    #              _init_from_child() calls super().__init__()
    def __init__(self, available: AvailableFiles, baseinit: FileRetriever._BaseInit,
                 parent: "FileRetrieverFromSingleArchive|FileRetrieverFromNestedArchives",
                 child: FileRetrieverFromSingleArchive) -> None:
        FileRetriever._init_from_child(super(), available, baseinit)
        if isinstance(parent, FileRetrieverFromSingleArchive):
            assert parent.file_in_archive.file_hash == child.archive_hash
            self.single_archive_retrievers = [parent, child]
        else:
            assert isinstance(parent, FileRetrieverFromNestedArchives)
            assert parent.single_archive_retrievers[-1].file_in_archive.file_hash == child.archive_hash
            self.single_archive_retrievers = parent.single_archive_retrievers + [child]

    def fetch(self, targetfpath: str) -> None:
        pass
        # TODO!

    def fetch_for_reading(self, tmpdirpath: str) -> str:
        pass
        # TODO!
