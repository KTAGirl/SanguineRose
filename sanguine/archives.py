from files import FileRetriever


class FileInArchive:
    file_hash: bytes
    intra_path: str
    file_size: int

    def __init__(self, file_hash: bytes, file_size: int, intra_path: str) -> None:
        self.file_hash = file_hash
        self.file_size = file_size
        self.intra_path = intra_path


class Archive:
    archive_hash: bytes
    archive_size: int
    files: list[FileInArchive]
    by: str

    def __init__(self, archive_hash: bytes, archive_size: int, by: str,
                 files: list[FileInArchive] | None = None) -> None:
        self.archive_hash = archive_hash
        self.archive_size = archive_size
        self.files = files if files is not None else []
        self.by = by


### FileRetriever


class FileRetrieverFromSingleArchive(FileRetriever):
    archive_hash: bytes
    file_in_archive: FileInArchive

    def __init__(self, archive_hash: bytes, file_in_archive: FileInArchive) -> None:
        self.archive_hash = archive_hash
        self.file_in_archive = file_in_archive

    def fetch(self, targetfpath: str) -> None:
        pass
        # TODO!

    def fetch_for_reading(self, tmpdirpath: str) -> str:
        pass
        # TODO!


class FileRetrieverFromNestedArchives(FileRetriever):
    single_archive_retrievers: list[FileRetrieverFromSingleArchive]

    def __init__(self, parent: FileRetrieverFromSingleArchive | FileRetrieverFromSingleArchive,
                 child: FileRetrieverFromSingleArchive) -> None:
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
