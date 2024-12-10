import sanguine.tasks as tasks
from sanguine.available import AvailableFiles, FileRetriever, FileRetrieverFromArchive
from sanguine.common import *
from sanguine.files import File
from sanguine.foldercache import FolderCache


class WholeCache:
    # WholeCache, once ready_task_name() is reached, contains whole information about the folders, and available files
    #             all the information is in-memory, so it can work incredibly fast
    mo2cache: FolderCache
    available: AvailableFiles
    _SYNCOWNTASKNAME: str = 'sanguine.wholecache.sync'

    def __init__(self, by: str, cachedir: str, tmpdir: str, mastergitdir: str, mo2dir, downloads: list[str]) -> None:
        self.available = AvailableFiles(by, cachedir, tmpdir, mastergitdir, downloads)
        self.mo2cache = FolderCache(cachedir, 'mo2', mo2dir)

    def start_tasks(self, parallel: tasks.Parallel) -> None:
        self.mo2cache.start_tasks(parallel)
        self.available.start_tasks(parallel)

        syncowntask = tasks.OwnTask(WholeCache._SYNCOWNTASKNAME,
                                    lambda _, _1, _2: self._start_sync_own_task_func(), None,
                                    [self.mo2cache.ready_task_name(),
                                     self.available.ready_task_name()])
        parallel.add_task(syncowntask)

    def _start_sync_own_task_func(self) -> None:
        pass  # do nothing, this task is necessary only to synchronize

    @staticmethod
    def ready_task_name() -> str:
        return WholeCache._SYNCOWNTASKNAME

    def all_mo2_files(self) -> Iterable[File]:
        return self.mo2cache.all_files()

    def find_available_file_by_hash(self, h: bytes) -> list[FileRetriever]:  # resolved as fully as feasible
        found = self.available.find_archived_file_by_hash(h)
        for r in found:
            self._resolve_archive_retrievers(r)
        return found

    def find_available_file_by_name(self, fname: str) -> list[FileRetriever]:  # resolved as fully as feasible
        # used for looking for patch candidates
        found = self.available.find_archived_file_by_name(fname)
        for r in found:
            self._resolve_archive_retrievers(r)
        return found

    # private functions

    def _resolve_archive_retrievers(self, r: FileRetriever) -> None:
        if isinstance(r, FileRetrieverFromArchive):
            assert len(r.archive_retrievers) == 0
            r.archive_retrievers = self.available.find_file_origin(r.archive_hash)
            for rr in r.archive_retrievers:
                self._resolve_archive_retrievers(rr)
