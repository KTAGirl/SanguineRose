from sanguine.helpers.file_retriever import FileRetriever, FileRetrieverFromSingleArchive, FileRetrieverFromNestedArchives

class ArchiveRetrieverAggregator:
    archives: dict[bytes,list[FileRetrieverFromSingleArchive|FileRetrieverFromNestedArchives]]

    def __init__(self) -> None:
        self.archives = {}

    @staticmethod
    def is_my_retriever(fr: FileRetriever) -> bool:
        return isinstance(fr, FileRetrieverFromSingleArchive) or isinstance(fr, FileRetrieverFromNestedArchives)

    def add_retriever(self,fr: FileRetriever):
        assert ArchiveRetrieverAggregator.is_my_retriever(fr)
        if isinstance(fr, FileRetrieverFromNestedArchives):
            arh = fr.single_archive_retrievers[0].archive_hash
        else:
            assert isinstance(fr, FileRetrieverFromSingleArchive)
            arh = fr.archive_hash
        if arh not in self.archives:
            self.archives[arh] = []
        self.archives[arh].append(fr)

    def all_archives_needed(self) -> list[tuple[bytes,list[FileRetrieverFromSingleArchive|FileRetrieverFromNestedArchives]]]:
        return list(self.archives.items())

    @staticmethod
    def process_archive(arh:bytes,files: list[FileRetrieverFromSingleArchive|FileRetrieverFromNestedArchives]) -> list[str]:
        pass # TODO!
