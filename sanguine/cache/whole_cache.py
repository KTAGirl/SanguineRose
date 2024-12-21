import sanguine.tasks as tasks
from sanguine.cache.available_files import FileRetriever, AvailableFiles, GithubFolder
from sanguine.cache.folder_cache import FileOnDisk, FolderCache
from sanguine.common import *
from sanguine.helpers.project_config import ProjectConfig


class WholeCache:
    # WholeCache, once ready_task_name() is reached, contains whole information about the folders, and available files
    #             all the information is in-memory, so it can work incredibly fast
    vfscache: FolderCache
    available: AvailableFiles
    _SYNCOWNTASKNAME: str = 'sanguine.wholecache.sync'

    def __init__(self, by: str, projectcfg: ProjectConfig, githubfolders: list[GithubFolder]) -> None:
        self.available = AvailableFiles(by, projectcfg.cache_dir, projectcfg.tmp_dir, projectcfg.github_dir,
                                        projectcfg.download_dirs, githubfolders)

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


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        from sanguine.install.install_checks import check_sanguine_prerequisites

        ttmppath = normalize_dir_path('../../../sanguine.tmp\\')
        add_file_logging(ttmppath + 'sanguine.log.html')

        check_sanguine_prerequisites()
        import json5

        cfgfname = normalize_file_path('../../../KTA\\KTA.json5')
        with open_3rdparty_txt_file(cfgfname) as f:
            jsoncfg = json5.loads(f.read())
            cfg = ProjectConfig(cfgfname, jsoncfg)
            pass
