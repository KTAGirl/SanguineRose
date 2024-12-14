import os.path

import sanguine.archives
import sanguine.tasks as tasks
from sanguine.common import *
from sanguine.file_origin import file_origins_for_file, FileOrigin
from sanguine.file_retriever import (FileRetriever, ZeroFileRetriever, GithubFileRetriever,
                                     FileRetrieverFromSingleArchive, FileRetrieverFromNestedArchives)
from sanguine.folder_cache import FolderCache, FolderToCache, FileOnDisk
from sanguine.master_git_data import MasterGitData
from sanguine.tmp_path import TmpPath


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
    _master_data: MasterGitData
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
        self._master_data = MasterGitData(by, mastergitdir, cachedir, tmpdir, {})
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
                                             MasterGitData.ready_to_start_hashing_task_name()])
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
        zero = ZeroFileRetriever.make_retriever_if(self, h)
        if zero is not None:
            return [zero]  # if it is zero file, we won't even try looking elsewhere
        archived = self._archived_file_retrievers_by_hash(h)
        github = self._github_file_retrievers_by_hash(h)
        return archived + github

    ### lists of file retrievers
    def _single_archive_retrievers(self, h: bytes) -> list[FileRetrieverFromSingleArchive]:
        found = self._master_data.archived_file_by_hash(h)
        if found is None:
            return []
        assert len(found) > 0
        return [FileRetrieverFromSingleArchive(self, (h, fi.file_size), ar.archive_hash, ar.archive_size, fi)
                for ar, fi in found]

    def _add_nested_to_retrievers(self, out: list[FileRetrieverFromSingleArchive | FileRetrieverFromNestedArchives],
                                  singles: list[FileRetrieverFromSingleArchive]) -> None:
        # resolving nested archives
        for r in singles:
            out.append(r)
            found2 = self._archived_file_retrievers_by_hash(r.archive_hash)
            for r2 in found2:
                out.append(FileRetrieverFromNestedArchives(self, (r2.file_hash, r2.file_size), r2, r))

    def _archived_file_retrievers_by_hash(self, h: bytes) -> list[
        FileRetrieverFromSingleArchive | FileRetrieverFromNestedArchives]:  # recursive
        singles = self._single_archive_retrievers(h)
        if len(singles) == 0:
            return []
        assert len(singles) > 0

        out = []
        self._add_nested_to_retrievers(out, singles)
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

            out.append(GithubFileRetriever(self, (h, gh.file_size), author, projectname, intrapath))

    '''
    def _archived_file_retrievers_by_name(self, fname: str) -> list[FileRetriever]:
        found = self._master_data._archived_files_by_name.get(fname)
        if not found:
            return []
        assert len(found) > 0
        singles = [
            FileRetrieverFromSingleArchive(self, (fi.file_hash, fi.file_size), ar.archive_hash, ar.archive_size, fi)
            for ar, fi in found]
        out = []
        self._add_nested_to_retrievers(out, singles)
        assert len(out) > 0
        return out

    def file_retrievers_by_name(self, fname: str) -> list[FileRetriever]:
        # TODO: add retrievers from ownmods
        return self._archived_file_retrievers_by_name(fname)
    '''

    # private functions

    def _start_hashing_own_task_func(self, parallel: tasks.Parallel) -> None:
        for ar in self._downloads_cache.all_files():
            ext = os.path.splitext(ar.file_path)[1]
            if ext == '.meta':
                continue

            if not self._master_data.archived_file_by_hash(ar.file_hash):
                if ext in sanguine.archives.all_archive_plugins_extensions():
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
                                        MasterGitData.ready_to_start_adding_file_origins_task_name()])
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


### choose_retrievers()

def _archive_hash(r: FileRetriever) -> bytes | None:
    if isinstance(r, FileRetrieverFromSingleArchive):
        return r.archive_hash
    if isinstance(r, FileRetrieverFromNestedArchives):
        return r.single_archive_retrievers[0].archive_hash
    return None


def _filter_with_used(inlist: list[tuple[bytes, list[FileRetriever]]], out: list[tuple[bytes, FileRetriever | None]],
                      used_archives: dict[bytes, int]) -> list[tuple[bytes, list[FileRetriever]]]:
    filtered: list[tuple[bytes, list[FileRetriever]]] = []
    for x in inlist:
        (h, retrs) = x
        assert len(retrs) >= 2
        done = False
        for r in retrs:
            arh = _archive_hash(r)
            assert arh is not None
            if arh in used_archives:
                out.append((h, r))
                used_archives[arh] += 1
                done = True
                break  # for r

        if not done:
            filtered.append((h, retrs))

    return filtered


def _separate_cluster_step(inlist: list[tuple[bytes, list[FileRetriever]]],
                           cluster: list[tuple[bytes, list[FileRetriever]]],
                           cluster_archives: dict[bytes, int]) -> list[tuple[bytes, list[FileRetriever]]]:
    filtered: list[tuple[bytes, list[FileRetriever]]] = []
    for x in inlist:  # this code is close, but not identical to the one in _filter_with_used()
        (h, retrs) = x
        assert len(retrs) >= 2
        found = False
        for r in retrs:
            arh = _archive_hash(r)
            assert arh is not None
            if arh in cluster_archives:
                cluster_archives[arh] += 1
            else:
                cluster_archives[arh] = 1
            found = True
            # no break here

        if found:
            cluster.append((h, retrs))
        else:
            filtered.append((h, retrs))
    return filtered


def _separate_cluster(inlist: list[tuple[bytes, list[FileRetriever]]],
                      cluster: list[tuple[bytes, list[FileRetriever]]],
                      cluster_archives: dict[bytes, int]) -> list[tuple[bytes, list[FileRetriever]]]:
    prev = inlist
    while True:
        oldclusterlen = len(cluster)
        filtered: list[tuple[bytes, list[FileRetriever]]] = _separate_cluster_step(prev, cluster, cluster_archives)
        assert len(filtered) <= len(prev)
        assert len(prev) - len(filtered) == len(cluster) - oldclusterlen
        if len(filtered) < len(prev):
            prev = filtered
            continue

        return prev


_MAX_EXPONENT_RETRIEVERS = 20  # 2**20 is a million, within reason


def _make_masked_set(cluster_archives: list[bytes], mask: int) -> dict[bytes, int]:
    filtered_archives = {}
    for i in range(len(cluster_archives)):
        if ((1 << i) & mask) != 0:
            h = cluster_archives[i]
            filtered_archives[h] = 1
    return filtered_archives


def _covers_set(cluster: list[tuple[bytes, list[FileRetriever]]], filtered_archives: dict[bytes, int]) -> bool:
    for x in cluster:
        (h, retrs) = x
        for r in retrs:
            arh = _archive_hash(r)
            assert arh is not None
            if arh not in filtered_archives:
                return False
    return True


def _cost_of_set(filtered_archives: dict[bytes, int], archive_weights: dict[bytes, float]) -> float:
    out = 0.
    for arh in filtered_archives:
        out += archive_weights[arh]
    return out


def _full_search_retrievers(out: list[tuple[bytes, FileRetriever | None]],
                            cluster: list[tuple[bytes, list[FileRetriever]]], cluster_archives0: dict[bytes, int],
                            archive_weights: dict[bytes, float]):
    cluster_archives = [h for h in cluster_archives0.keys()]
    assert len(cluster_archives) <= _MAX_EXPONENT_RETRIEVERS
    bestcost = None
    bestset = None
    for mask in range(2 ** len(cluster_archives)):
        filtered_archives = _make_masked_set(cluster_archives, mask)
        if _covers_set(cluster, filtered_archives):
            cost = _cost_of_set(filtered_archives, archive_weights)
            if bestcost is None or cost < bestcost:
                bestcost = cost
                bestset = filtered_archives

    assert bestset is not None
    for x in cluster:
        (h, retrs) = x
        done = False
        for r in retrs:
            arh = _archive_hash(r)
            assert arh is not None
            if arh in bestset:
                out.append((h, r))
                done = True
                break  # for x

        assert done


def _number_covered_by_archive(cluster: list[tuple[bytes, list[FileRetriever]]], h0: bytes) -> int:
    out = 0
    for x in cluster:
        (h, retrs) = x
        for r in retrs:
            arh = _archive_hash(r)
            assert arh is not None
            if arh == h0:
                out += 1
                break  # for r
    return out


def choose_retrievers(inlist: list[tuple[bytes, list[FileRetriever]]], archive_weights: dict[bytes, float]) -> list[
    tuple[bytes, FileRetriever | None]]:
    out: list[tuple[bytes, FileRetriever | None]] = []

    # first pass: choosing unique ones, as well as GitHub ones
    remaining: list[tuple[bytes, list[FileRetriever]]] = []
    used_archives: dict[bytes, int] = {}
    for x in inlist:
        (h, retrs) = x
        if len(retrs) == 0:
            out.append((h, None))
            continue
        elif len(retrs) == 1:
            out.append((h, retrs[0]))
            arh = _archive_hash(retrs[0])
            if arh is not None:
                if arh not in used_archives:
                    used_archives[arh] = 1
                else:
                    used_archives[arh] += 1
            continue

        done = False
        for r in retrs:
            if isinstance(r, GithubFileRetriever):
                out.append((h, r))
                done = True
                break  # for r

        if done:
            continue  # for x

        # cannot do much now, placing it to remaining[]
        if __debug__:
            for r in retrs:
                assert isinstance(r, FileRetrieverFromSingleArchive) or isinstance(r, FileRetrieverFromNestedArchives)
        remaining.append((h, retrs))

    # separate into clusters
    remaining = _filter_with_used(remaining, out, used_archives)
    clusters: list[list[tuple[bytes, list[FileRetriever]]]] = []
    clusters_archives: list[dict[bytes, int]] = []
    while len(remaining) > 0:
        cluster: list[tuple[bytes, list[FileRetriever]]] = [remaining[0]]
        remaining = remaining[1:]
        cluster_archives = {}
        for x in cluster[0]:
            (h, retrs) = x
            arh = _archive_hash(h)
            assert arh is not None
            if arh in cluster_archives:
                cluster_archives[arh] += 1
            else:
                cluster_archives[arh] = 1

        oldremaininglen = len(remaining)
        oldclusterlen = len(cluster)
        remaining = _separate_cluster(remaining, cluster, cluster_archives)
        assert len(remaining) <= oldremaininglen
        assert len(cluster) - oldclusterlen == oldremaininglen - len(remaining)
        clusters.append(cluster)
        clusters_archives.append(cluster_archives)

    assert len(clusters_archives) == len(clusters)
    for i in range(len(clusters)):
        cluster = clusters[i]
        cluster_archives: dict[bytes, int] = clusters_archives[i]

        while len(cluster_archives) > _MAX_EXPONENT_RETRIEVERS:
            # "greedy" reduction of search space
            #           for the time being, we're just taking lowest-cost archives (starting from highest-use within lowest-cost)
            xarchives: list[tuple[bytes, float, int]] = sorted(
                [(arh, archive_weights[arh], _number_covered_by_archive(cluster, arh)) for arh in
                 cluster_archives.keys()],
                key=lambda x2: (x2[1], x2[2]))
            # we should not try cutting all (len(cluster_archives)-_MAX_EXPONENT) at once, as filtering can change
            #               the pattern
            arh = xarchives[0][0]
            assert arh not in cluster_archives
            cluster_archives[arh] = 1
            cluster = _filter_with_used(cluster, out, cluster_archives)

        assert len(cluster_archives) <= _MAX_EXPONENT_RETRIEVERS
        _full_search_retrievers(out, cluster, cluster_archives, archive_weights)

    return out


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        from sanguine.install_checks import check_sanguine_prerequisites

        ttmppath = normalize_dir_path('..\\..\\sanguine.tmp\\')
        add_file_logging(ttmppath + 'sanguine.log.html')

        check_sanguine_prerequisites()

        with TmpPath(ttmppath) as ttmpdir:
            tavailable = AvailableFiles('KTAGirl',
                                        normalize_dir_path('..\\..\\sanguine.cache\\'),
                                        ttmpdir.tmp_dir(),
                                        normalize_dir_path('..\\..\\sanguine-skyrim-root\\'),
                                        [normalize_dir_path('..\\..\\..\\mo2\\downloads')],
                                        [GithubFolder('KTAGirl', 'KTA',
                                                      normalize_dir_path('..\\..\\KTA\\'))])
            with tasks.Parallel(None, dbg_serialize=False) as tparallel:
                tavailable.start_tasks(tparallel)
                tparallel.run([])  # all necessary tasks were already added in acache.start_tasks()
