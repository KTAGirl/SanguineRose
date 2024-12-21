import os.path

import sanguine.tasks as tasks
from sanguine.cache.all_master_git_data import AllMasterGitData
from sanguine.cache.folder_cache import FolderCache, FileOnDisk
from sanguine.common import *
from sanguine.gitdata.file_origin import file_origins_for_file, FileOrigin
from sanguine.helpers.archives import all_archive_plugins_extensions
from sanguine.helpers.file_retriever import (FileRetriever, ZeroFileRetriever, GithubFileRetriever,
                                             ArchiveFileRetriever, ArchiveFileRetrieverHelper)
from sanguine.helpers.tmp_path import TmpPath


def _file_origins_task_func(param: tuple[list[bytes, str]]) -> tuple[list[tuple[bytes, list[FileOrigin]]]]:
    (filtered_downloads,) = param
    allorigins: list[tuple[bytes, list[FileOrigin]]] = []
    for fhash, fpath in filtered_downloads:
        # TODO: multi-picklecache for file origins
        origins = file_origins_for_file(fpath)
        if origins is None:
            warn('Available: file without known origin {}'.format(fpath))
        else:
            allorigins.append((fhash, origins))
    return (allorigins,)


class GithubFolder:
    author: str
    project_name: str
    local_folder: str

    def __init__(self, author: str, project_name: str, local_folder: str) -> None:
        self.author = author
        self.project_name = project_name
        self.local_folder = local_folder


class AvailableFiles:
    _github_cache: FolderCache
    _github_cache_by_hash: dict[bytes, list[FileOnDisk]] | None
    _downloads_cache: FolderCache
    _master_data: AllMasterGitData
    _github_folders: list[GithubFolder]
    _READYOWNTASKNAME = 'sanguine.available.readyown'
    _is_ready: bool

    def __init__(self, by: str, cachedir: str, tmpdir: str, mastergitdir: str, downloads: list[str],
                 github_folders: list[GithubFolder]) -> None:
        self._downloads_cache = FolderCache(cachedir, 'downloads', [FolderToCache(d, []) for d in downloads])
        self._github_cache = FolderCache(cachedir, 'github',
                                         [FolderToCache(g.local_folder, []) for g in github_folders])
        self._github_cache_by_hash = None
        self._github_folders = github_folders
        self._master_data = AllMasterGitData(by, mastergitdir, cachedir, tmpdir, {})
        self._is_ready = False

    # public interface

    def start_tasks(self, parallel: tasks.Parallel):
        self._downloads_cache.start_tasks(parallel)
        self._github_cache.start_tasks(parallel)
        self._master_data.start_tasks(parallel)

        starthashingowntaskname = 'sanguine.available.starthashing'
        starthashingowntask = tasks.OwnTask(starthashingowntaskname,
                                            lambda _, _1, _2: self._start_hashing_own_task_func(parallel), None,
                                            [self._downloads_cache.ready_task_name(),
                                             AllMasterGitData.ready_to_start_hashing_task_name()])
        parallel.add_task(starthashingowntask)

        startoriginsowntaskname = 'sanguine.available.startfileorigins'
        startoriginsowntask = tasks.OwnTask(startoriginsowntaskname,
                                            lambda _, _1: self._start_origins_own_task_func(parallel), None,
                                            [self._downloads_cache.ready_task_name()])
        parallel.add_task(startoriginsowntask)

    @staticmethod
    def ready_task_name() -> str:
        return AvailableFiles._READYOWNTASKNAME

    def file_retrievers_by_hash(self, h: bytes) -> list[FileRetriever]:
        zero = ZeroFileRetriever.make_retriever_if(h)
        if zero is not None:
            return [zero]  # if it is zero file, we won't even try looking elsewhere
        archived = self._archived_file_retrievers_by_hash(h)
        github = self._github_file_retrievers_by_hash(h)
        return archived + github

    ### lists of file retrievers
    def _single_archive_retrievers(self, h: bytes) -> list[ArchiveFileRetrieverHelper]:
        found = self._master_data.archived_file_by_hash(h)
        if found is None:
            return []
        assert len(found) > 0
        return [ArchiveFileRetrieverHelper((h, fi.file_size), ar.archive_hash, ar.archive_size, fi)
                for ar, fi in found]

    def _add_nested_archives(self, out: list[ArchiveFileRetriever],
                             singles: list[ArchiveFileRetrieverHelper]) -> None:
        # resolving nested archives
        for r in singles:
            out.append(ArchiveFileRetriever((r.file_hash, r.file_size), [r]))
            found2 = self._archived_file_retrievers_by_hash(r.archive_hash)
            for r2 in found2:
                out.append(
                    ArchiveFileRetriever((r2.file_hash, r2.file_size), r2.constructor_parameter_appending_child(r)))

    def _archived_file_retrievers_by_hash(self, h: bytes) -> list[ArchiveFileRetriever]:  # recursive
        singles = self._single_archive_retrievers(h)
        if len(singles) == 0:
            return []
        assert len(singles) > 0

        out = []
        self._add_nested_archives(out, singles)
        assert len(out) > 0
        return out

    def _github_file_retrievers_by_hash(self, h: bytes) -> list[GithubFileRetriever]:
        ghlist = self._github_cache_by_hash.get(h)
        if ghlist is None:
            return []

        out = []
        for gh in ghlist:
            fpath = gh.file_path
            author = None
            projectname = None
            intrapath = None
            for d in self._github_folders:
                if fpath.startswith(d.local_folder):
                    assert author is None
                    assert projectname is None
                    assert intrapath is None
                    author = d.author
                    projectname = d.project_name
                    intrapath = fpath[len(d.local_folder):]
                    if not __debug__:
                        break

            assert author is not None
            assert projectname is not None
            assert intrapath is not None

            out.append(GithubFileRetriever((h, gh.file_size), author, projectname, intrapath))

    # private functions

    def _start_hashing_own_task_func(self, parallel: tasks.Parallel) -> None:
        for ar in self._downloads_cache.all_files():
            ext = os.path.splitext(ar.file_path)[1]
            if ext == '.meta':
                continue

            if not self._master_data.archive_by_hash(ar.file_hash, partialok=True):
                if ext in all_archive_plugins_extensions():
                    self._master_data.start_hashing_archive(parallel, ar.file_path, ar.file_hash, ar.file_size)
                else:
                    warn('Available: file with unknown extension {}, ignored'.format(ar.file_path))

    def _start_origins_own_task_func(self, parallel: tasks.Parallel) -> None:
        filtered_downloads: list[tuple[bytes, str]] = []
        for ar in self._downloads_cache.all_files():
            ext = os.path.splitext(ar.file_path)[1]
            if ext == '.meta':
                continue

            filtered_downloads.append((ar.file_hash, ar.file_path))

        originstaskname = 'sanguine.available.fileorigins'
        originstask = tasks.Task(originstaskname, _file_origins_task_func,
                                 (filtered_downloads,), [])
        parallel.add_task(originstask)
        startoriginsowntaskname = 'sanguine.available.ownfileorigins'
        originsowntask = tasks.OwnTask(startoriginsowntaskname,
                                       lambda _, out, _1: self._file_origins_own_task_func(parallel, out), None,
                                       [originstaskname,
                                        AllMasterGitData.ready_to_start_adding_file_origins_task_name()])
        parallel.add_task(originsowntask)

    def _file_origins_own_task_func(self, parallel: tasks.Parallel,
                                    out: tuple[list[tuple[bytes, list[FileOrigin]]]]) -> None:
        (origins,) = out
        for fox in origins:
            for fo in fox[1]:
                self._master_data.add_file_origin(fox[0], fo)
        self._master_data.start_done_adding_file_origins_task(parallel)  # no need to wait for it

        gitarchivesdonehashingtaskname: str = self._master_data.start_done_hashing_task(parallel)
        readyowntaskname = AvailableFiles._READYOWNTASKNAME
        readyowntask = tasks.OwnTask(readyowntaskname,
                                     lambda _, _1, _2: self._ready_own_task_func(), None,
                                     [gitarchivesdonehashingtaskname, self._github_cache.ready_task_name()])
        parallel.add_task(readyowntask)

    def _ready_own_task_func(self) -> None:
        assert self._github_cache_by_hash is None
        self._github_cache_by_hash = {}
        for f in self._github_cache.all_files():
            add_to_dict_of_lists(self._github_cache_by_hash, f.file_hash, f)
        self._is_ready = True


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        from sanguine.install.install_checks import check_sanguine_prerequisites

        ttmppath = normalize_dir_path('../../../sanguine.tmp\\')
        add_file_logging(ttmppath + 'sanguine.log.html')
        # alert('Test alert')
        # critical('Test critical')

        check_sanguine_prerequisites()

        with TmpPath(ttmppath) as ttmpdir:
            tavailable = AvailableFiles('KTAGirl',
                                        normalize_dir_path('../../../sanguine.cache\\'),
                                        ttmpdir.tmp_dir(),
                                        normalize_dir_path('../../../sanguine-skyrim-root\\'),
                                        [normalize_dir_path('../../../../MO2/downloads')],
                                        [GithubFolder('KTAGirl', 'KTA',
                                                      normalize_dir_path('../../../KTA\\'))])
            with tasks.Parallel(None, dbg_serialize=False) as tparallel:
                tavailable.start_tasks(tparallel)
                tparallel.run([])  # all necessary tasks were already added in acache.start_tasks()

        info('available_files.py test finished ok')
