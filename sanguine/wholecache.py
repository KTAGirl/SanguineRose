import sanguine.tasks as tasks
from sanguine.available import AvailableFiles
from sanguine.common import *
from sanguine.files import FileOnDisk, FileRetriever
from sanguine.foldercache import FolderCache, FolderToCache
from sanguine.projectconfig import ProjectConfig


class WholeCache:
    # WholeCache, once ready_task_name() is reached, contains whole information about the folders, and available files
    #             all the information is in-memory, so it can work incredibly fast
    mo2cache: FolderCache
    available: AvailableFiles
    _SYNCOWNTASKNAME: str = 'sanguine.wholecache.sync'

    def __init__(self, by: str, cfgfolders: ProjectConfig) -> None:
        self.available = AvailableFiles(by, cfgfolders.cache_dir, cfgfolders.tmp_dir, cfgfolders.github_dir,
                                        cfgfolders.download_dirs)
        
        folderstocache: list[FolderToCache] = [FolderToCache(cfgfolders.mo2_dir, [cfgfolders.mo2_mods_dir()])]
        for d in cfgfolders.all_enabled_mo2_mod_dirs():
            folderstocache.append(FolderToCache(d))
        self.mo2cache = FolderCache(cfgfolders.cache_dir, 'mo2', folderstocache)

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

    def all_mo2_files(self) -> Iterable[FileOnDisk]:
        return self.mo2cache.all_files()

    def file_retrievers_by_hash(self, h: bytes) -> list[FileRetriever]:  # resolved as fully as feasible
        return self.available.file_retrievers_by_hash(h)

    def file_retrievers_by_name(self, fname: str) -> list[FileRetriever]:  # resolved as fully as feasible
        return self.available.file_retrievers_by_name(fname)
