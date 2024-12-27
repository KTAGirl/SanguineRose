import sanguine.tasks as tasks
from sanguine.cache.available_files import FileRetriever, AvailableFiles
from sanguine.cache.folder_cache import FileOnDisk, FolderCache
from sanguine.common import *
from sanguine.helpers.project_config import ProjectConfig


class WholeCache:
    # WholeCache, once ready_task_name() is reached, contains whole information about the folders, and available files
    #             all the information is in-memory, so it can work incredibly fast
    cache_data_fname: str
    cache_data: dict[str, any]
    vfscache: FolderCache
    available: AvailableFiles
    _SYNCOWNTASKNAME: str = 'sanguine.wholecache.sync'

    def __init__(self, by: str, projectcfg: ProjectConfig) -> None:
        self.cache_data_fname = projectcfg.cache_dir + 'wholecache.cachedata.json'
        try:
            with open(self.cache_data_fname, 'r') as f:
                self.cache_data = json.load(f)
        except Exception as e:
            warn('WholeCache: cannot load cachedata from {}: {}'.format(self.cache_data_fname, e))
            self.cache_data = {}
        self.available = AvailableFiles(by, projectcfg.cache_dir, projectcfg.tmp_dir, projectcfg.github_root,
                                        projectcfg.download_dirs, projectcfg.github_folders, self.cache_data)

        folderstocache: FolderListToCache = projectcfg.active_vfs_folders()
        self.vfscache = FolderCache(projectcfg.cache_dir, 'vfs', folderstocache)

    def start_tasks(self, parallel: tasks.Parallel) -> None:
        self.vfscache.start_tasks(parallel)
        self.available.start_tasks(parallel)

        syncowntask = tasks.OwnTask(WholeCache._SYNCOWNTASKNAME,
                                    lambda _, _1, _2: self._start_sync_own_task_func(), None,
                                    [self.vfscache.ready_task_name(),
                                     self.available.ready_task_name()])
        parallel.add_task(syncowntask)

    def _start_sync_own_task_func(self) -> None:
        pass  # do nothing, this task is necessary only to synchronize

    @staticmethod
    def ready_task_name() -> str:
        return WholeCache._SYNCOWNTASKNAME

    def all_vfs_files(self) -> Iterable[FileOnDisk]:
        return self.vfscache.all_files()

    def file_retrievers_by_hash(self, h: bytes) -> list[FileRetriever]:  # resolved as fully as feasible
        return self.available.file_retrievers_by_hash(h)

    '''
    def file_retrievers_by_name(self, fname: str) -> list[FileRetriever]:  # resolved as fully as feasible
        return self.available.file_retrievers_by_name(fname)
    '''

    def stats_of_interest(self) -> list[str]:
        return (self.available.stats_of_interest() + self.vfscache.stats_of_interest()
                + ['sanguine.wholecache.'])

    def done(self) -> None:
        with open(self.cache_data_fname, 'w') as f:
            # noinspection PyTypeChecker
            json.dump(self.cache_data, f, indent=4)


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        ttmppath = normalize_dir_path('../../../sanguine.tmp\\')
        add_file_logging(ttmppath + 'sanguine.log.html')
        check_sanguine_prerequisites()

        cfgfname = normalize_file_path('../../../KTA\\KTA.json5')
        cfg = ProjectConfig(cfgfname)

        wcache = WholeCache('KTAGirl', cfg)
        with tasks.Parallel(None, taskstatsofinterest=wcache.stats_of_interest(), dbg_serialize=False) as tparallel:
            wcache.start_tasks(tparallel)
            tparallel.run([])
        wcache.done()

        info('whole_cache.py test finished ok')
