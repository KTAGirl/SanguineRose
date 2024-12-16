import hashlib
import os.path
import stat
import time

import sanguine.tasks as tasks
from sanguine.common import *


### *_file_hash() and FileOnDisk

def calculate_file_hash(
        fpath: str) -> tuple[int, bytes]:  # using SHA-256, the fastest crypto-hash because of hardware instruction
    st = os.lstat(fpath)
    assert stat.S_ISREG(st.st_mode) and not stat.S_ISLNK(st.st_mode)
    h = hashlib.sha256()
    blocksize = 1048576
    fsize = 0
    with open(fpath, 'rb') as f:
        while True:
            bb = f.read(blocksize)
            if not bb:
                break
            h.update(bb)
            lbb = len(bb)
            assert lbb <= blocksize
            fsize += lbb

    # were there any changes while we were working?
    assert st.st_size == fsize
    st2 = os.lstat(fpath)
    assert st2.st_size == st.st_size
    assert st2.st_mtime == st.st_mtime
    return fsize, h.digest()


def truncate_file_hash(h: bytes) -> bytes:
    assert len(h) == 32
    return h[:9]


class FileOnDisk:
    file_hash: bytes | None
    file_path: str
    file_modified: float
    file_size: int | None

    def __init__(self, file_hash: bytes | None, file_modified: float | None, file_path: str,
                 file_size: int | None):
        assert file_path is not None
        self.file_hash = file_hash
        self.file_modified = file_modified
        self.file_path = file_path
        self.file_size = file_size


### helpers

def _get_file_timestamp(fname: str) -> float:
    return os.lstat(fname).st_mtime


def _get_file_timestamp_from_st(st: os.stat_result) -> float:
    return st.st_mtime


def _read_dict_of_files(dirpath: str, name: str) -> dict[str, FileOnDisk]:
    assert is_normalized_dir_path(dirpath)
    fpath = dirpath + 'foldercache.' + name + '.pickle'
    return read_dict_from_pickled_file(fpath)


def _write_dict_of_files(dirpath: str, name: str, files: dict[str, FileOnDisk],
                         filteredfiles: dict[str, FileOnDisk]) -> None:
    assert is_normalized_dir_path(dirpath)
    fpath = dirpath + 'foldercache.' + name + '.pickle'
    outfiles: dict[str, FileOnDisk] = files | filteredfiles
    with open(fpath, 'wb') as wf:
        # noinspection PyTypeChecker
        pickle.dump(outfiles, wf)

    fpath2 = dirpath + 'foldercache.' + name + '.njson'
    with open_3rdparty_txt_file_w(fpath2) as wf2:
        srt: list[tuple[str, FileOnDisk]] = sorted(outfiles.items())
        for item in srt:
            wf2.write(as_json(item[1]) + '\n')


def _read_all_scan_stats(dirpath: str, name: str) -> dict[str, dict[str, int]]:
    assert is_normalized_dir_path(dirpath)
    fpath = dirpath + 'foldercache.' + name + '.scan-stats.pickle'
    return read_dict_from_pickled_file(fpath)


def _write_all_scan_stats(dirpath: str, name: str, all_scan_stats: dict[str, dict[str, int]]) -> None:
    assert is_normalized_dir_path(dirpath)
    fpath = dirpath + 'foldercache.' + name + '.scan-stats.pickle'
    with open(fpath, 'wb') as wf:
        # noinspection PyTypeChecker
        pickle.dump(all_scan_stats, wf)

    fpath2 = dirpath + 'foldercache.' + name + '.scan-stats.json'
    srt = sorted(all_scan_stats.items())
    with open_3rdparty_txt_file_w(fpath2) as wf2:
        # noinspection PyTypeChecker
        json.dump(srt, wf2, indent=2)


class _FolderScanStats:
    nmodified: int
    nscanned: int
    ndel: 0

    def __init__(self) -> None:
        self.nmodified = 0
        self.nscanned = 0
        self.ndel = 0

    def add(self, stats2: "_FolderScanStats") -> None:
        self.nmodified += stats2.nmodified
        self.nscanned += stats2.nscanned


class _FolderScanDirOut:
    root: str
    scanned_files: dict[str, FileOnDisk]
    requested_dirs: list[str]
    requested_files: list[tuple[str, float, int]]
    scan_stats: dict[str, int]  # fpath -> nfiles

    def __init__(self, root: str) -> None:
        self.root = root
        self.scanned_files = {}
        self.requested_dirs = []
        self.requested_files = []
        self.scan_stats = {}


class FolderToCache:
    folder: str
    exdirs: list[str]

    def __init__(self, folder: str, exdirs: list[str] = None) -> None:
        self.folder = folder
        self.exdirs = [] if exdirs is None else exdirs


type FolderListToCache = list[FolderToCache]


def filter_ex_dirs(exdirs: list[str], fpath) -> list[str]:
    return [xd for xd in exdirs if xd.startswith(fpath)]


# heuristics to enable splitting tasks

def _time_to_split_task(t: float) -> bool:
    return t > 0.5


def _scan_task_nf_threshold_heuristics() -> int:
    sec_threshold = 0.3
    return int(sec_threshold * 20000)  # scans per second


def _scan_task_time_estimate(nf: int) -> float:
    return float(nf) / 20000.


def _hashing_file_time_estimate(fsize: int) -> float:
    return float(fsize) / 1048576. / 30.


### Tasks

def _load_files_task_func(param: tuple[str, str]) -> tuple[dict[str, FileOnDisk]]:
    (cachedir, name) = param
    # filesbypath = {}
    filesbypath = _read_dict_of_files(cachedir, name)

    return (filesbypath,)


def _scan_folder_task_func(
        param: tuple[str, str, list[str], str],
        fromownload: tuple[tasks.SharedPubParam]) -> tuple[
    list[str], _FolderScanStats, _FolderScanDirOut]:
    (rootpath, taskroot, exdirs, name) = param
    (pubfilesbypath,) = fromownload
    sdout = _FolderScanDirOut(rootpath)
    stats = _FolderScanStats()
    filesbypath = tasks.from_publication(pubfilesbypath)
    started = time.perf_counter()
    lfilesbypath = len(filesbypath)
    FolderCache.scan_dir(started, sdout, stats, rootpath, taskroot, filesbypath, pubfilesbypath, exdirs, name)
    debug('{}FolderCache._scan_folder_task_func(): requested_files/requested_dirs/scanned_files={}/{}/{}'.format(
        tasks.log_process_prefix(), len(sdout.requested_files), len(sdout.requested_dirs), len(sdout.scanned_files)))
    assert len(filesbypath) == lfilesbypath
    return exdirs, stats, sdout


def _calc_hash_task_func(param: tuple[str, float, int]) -> tuple[FileOnDisk]:
    (fpath, tstamp, fsize) = param
    s, h = calculate_file_hash(fpath)
    assert s == fsize
    return (FileOnDisk(h, tstamp, fpath, fsize),)


def _save_files_task_func(
        param: tuple[str, str, dict[str, FileOnDisk], dict[str, FileOnDisk], dict[str, dict[str, int]]]) -> None:
    (cachedir, name, filesbypath, filteredfiles, scan_stats) = param
    _write_dict_of_files(cachedir, name, filesbypath, filteredfiles)
    _write_all_scan_stats(cachedir, name, scan_stats)


class _ScanStatsNode:
    parent: "_ScanStatsNode|None"
    path: str
    own_nf: int
    children: list["_ScanStatsNode"]

    def __init__(self, parent: "_ScanStatsNode|None", path: str, nf: int) -> None:
        self.parent = parent
        self.path = path
        self.own_nf = nf
        self.children = []

    @staticmethod
    def _read_tree_from_stats(scan_stats: dict[str, int] | None) -> "_ScanStatsNode":
        rootstatnode: _ScanStatsNode | None = None
        curstatnode: _ScanStatsNode | None = None
        for fpath, nf in sorted(scan_stats.items()):
            assert is_normalized_dir_path(fpath)
            if curstatnode is None:
                assert rootstatnode is None
                rootstatnode = _ScanStatsNode(None, fpath, nf)
                curstatnode = rootstatnode
                continue

            assert rootstatnode is not None
            if fpath.startswith(curstatnode.path):
                curstatnode = _ScanStatsNode(curstatnode, fpath, nf)
            else:
                ok = False
                while curstatnode.parent is not None:
                    if fpath.startswith(curstatnode.parent.path):
                        curstatnode = _ScanStatsNode(curstatnode, fpath, nf)
                        ok = True
                        break  # while
                    else:
                        curstatnode = curstatnode.parent
                assert ok
        return rootstatnode

    @staticmethod
    def _append_task(alltasks: list[tuple[str, str, int, list[str]]], root: str, path: str, nf: int, exdirs: list[str],
                     extexdirs: list[str]) -> None:
        assert len(filter_ex_dirs(exdirs, path)) == len(exdirs)
        mergedexdirs = exdirs + filter_ex_dirs(extexdirs, path)
        alltasks.append((root, path, nf, mergedexdirs))

    def _is_filtered_out(self, exdirs: list[str]) -> bool:
        for exdir in exdirs:
            if self.path.startswith(exdir):
                return True
        return False

    def _filter_tree(self, exdirs: list[str]) -> None:  # recursive
        assert not self._is_filtered_out(exdirs)
        self.children = [ch for ch in self.children if not ch._is_filtered_out(exdirs)]

    @staticmethod
    def make_tree(scan_stats: dict[str, int] | None, rootfolder: str, exdirs: list[str]):
        if scan_stats is None:
            rootstatnode = _ScanStatsNode(None, rootfolder, 10000)  # a LOT
        else:
            rootstatnode = _ScanStatsNode._read_tree_from_stats(scan_stats)
            assert rootstatnode.path == rootfolder
            rootstatnode._filter_tree(exdirs)
        return rootstatnode

    def fill_tasks(self, alltasks: list[tuple[str, str, int, list[str]]], root: str, extexdirs: list[str]) -> tuple[int,
    list[
        str]] | None:  # recursive
        nf = self.own_nf
        chex = []
        chexmerged = []
        chnfs = []
        for ch in self.children:
            chnf, exdirs = ch.fill_tasks(alltasks, root, extexdirs)
            nf += chnf
            chnfs.append(chnf)
            chex.append(exdirs)
            chexmerged += exdirs
        if self.parent is None:
            _ScanStatsNode._append_task(alltasks, root, self.path, nf, chexmerged, extexdirs)
            return None
        if nf < _scan_task_nf_threshold_heuristics():
            return nf, chexmerged
        else:
            assert len(chex) == len(self.children)
            assert len(chnfs) == len(self.children)
            outexdirs = []
            for i in range(len(self.children)):
                ch = self.children[i]
                _ScanStatsNode._append_task(alltasks, root, ch.path, chnfs[i], chex[i], extexdirs)
                outexdirs.append(ch.path)
            return self.own_nf, outexdirs


class FolderCache:  # folder cache; can handle multiple folders, each folder with its own set of exclusions
    _cache_dir: str
    name: str
    _folder_list: FolderListToCache
    _files_by_path: dict[str, FileOnDisk] | None
    _filtered_files: list[FileOnDisk]
    _all_scan_stats: dict[str, dict[str, int]]  # rootfolder -> {fpath -> nfiles}
    _is_ready: bool

    def __init__(self, cachedir: str, name: str, folder_list: FolderListToCache) -> None:
        assert not FolderCache._folder_list_self_overlaps(folder_list)
        self._cache_dir = cachedir
        self.name = name
        self._folder_list = folder_list
        self._files_by_path = None
        self._filtered_files = []
        self._all_scan_stats = _read_all_scan_stats(cachedir, name)
        self._is_ready = False

    def start_tasks(self, parallel: tasks.Parallel) -> None:
        return self._start_tasks(parallel)

    def ready_task_name(self) -> str:
        return self._reconcile_own_task_name()

    def all_files(self) -> Iterable[FileOnDisk]:
        assert self._is_ready
        return self._files_by_path.values()

    # private functions

    @staticmethod
    def _two_folders_overlap(a: str, aex: list[str], b: str, bex: list[str]) -> bool:
        if a == b:
            return False
        ok = True
        if a.startswith(b):  # b contains a
            ok = False
            for x in bex:
                if a.startswith(x):
                    ok = True
                    break
        elif b.startswith(a):  # a contains b
            ok = False
            for x in aex:
                if b.startswith(x):
                    ok = True
                    break
        return ok

    @staticmethod
    def _folder_list_self_overlaps(l: FolderListToCache) -> bool:
        for aidx in range(len(l)):
            for bidx in range(len(l)):
                if aidx == bidx:
                    continue
                if FolderCache._two_folders_overlap(l[aidx].folder, l[aidx].exdirs, l[bidx].folder, l[bidx].exdirs):
                    return True
        return False

    @staticmethod
    def folder_lists_overlap(al: FolderListToCache, bl: FolderListToCache) -> bool:
        for a in al:
            for b in bl:
                if FolderCache._two_folders_overlap(a.folder, a.exdirs, b.folder, b.exdirs):
                    return True
        return False

    def _start_tasks(self, parallel: tasks.Parallel) -> None:

        # building tree of known scans
        allscantasks: list[tuple[str, str, int, list[str]]] = []  # [(root,path,nf,exdirs)]

        for folderplus in self._folder_list:
            scan_stats = self._all_scan_stats.get(folderplus.folder)
            rootstatnode = _ScanStatsNode.make_tree(scan_stats, folderplus.folder, folderplus.exdirs)
            rootstatnode.fill_tasks(allscantasks, folderplus.folder, folderplus.exdirs)

        # ready to start tasks
        scannedfiles = {}
        stats = _FolderScanStats()

        loadtaskname = 'sanguine.foldercache.load.' + self.name
        loadtask = tasks.Task(loadtaskname, _load_files_task_func, (self._cache_dir, self.name), [])
        parallel.add_task(loadtask)

        loadowntaskname = 'sanguine.foldercache.loadown.' + self.name
        loadowntask = tasks.OwnTask(loadowntaskname, lambda _, out: self._load_files_own_task_func(out, parallel),
                                    None,
                                    [loadtaskname])
        parallel.add_task(loadowntask)

        for tt in allscantasks:
            (root, path, nf, exdirs) = tt
            assert is_normalized_dir_path(path)
            taskname = self._scanned_task_name(path)
            task = tasks.Task(taskname, _scan_folder_task_func,
                              (root, path, exdirs, self.name),
                              [loadowntaskname], _scan_task_time_estimate(nf))
            owntaskname = self._scanned_own_task_name(path)
            owntask = tasks.OwnTask(owntaskname,
                                    lambda _, out: self._scan_folder_own_task_func(out, parallel, scannedfiles, stats),
                                    None, [taskname])

            parallel.add_tasks([task, owntask])

        scanningdeps = [self._scanned_own_task_name(folderplus.folder) + '*' for folderplus in self._folder_list]
        hashingdeps = [self._hashing_own_wildcard_task_name(folderplus.folder) for folderplus in self._folder_list]
        reconciletask = tasks.OwnTask(self._reconcile_own_task_name(),
                                      lambda _: self._own_reconcile_task_func(parallel, scannedfiles),
                                      None, scanningdeps + hashingdeps)
        parallel.add_task(reconciletask)

    @staticmethod
    def _file_path_is_ok_simple(path: str, root: str, exdirs: list[str]) -> bool:
        if not path.startswith(root):
            return False
        for exdir in exdirs:
            if path.startswith(exdir):
                return False
        return True

    @staticmethod
    def _file_path_is_ok(fpath: str, folder_list: FolderListToCache) -> bool:
        for folderplus in folder_list:
            if FolderCache._file_path_is_ok_simple(fpath, folderplus.folder, folderplus.exdirs):
                return True
        return False

    @staticmethod
    def scan_dir(started: float, sdout: _FolderScanDirOut, stats: _FolderScanStats, root: str, dirpath: str,
                 const_filesbypath: dict[str, FileOnDisk], pubfilesbypath: tasks.SharedPubParam,
                 const_exdirs: list[str], name: str) -> None:  # recursive over dir
        assert is_normalized_dir_path(dirpath)
        # recursive implementation: able to skip subtrees, but more calls (lots of os.listdir() instead of single os.walk())
        # still, after recent performance fix seems to win like 1.5x over os.walk-based one
        nf = 0
        for f in os.listdir(dirpath):
            fpath = dirpath + normalize_file_name(f)
            st = os.lstat(fpath)
            fmode = st.st_mode
            if stat.S_ISREG(fmode):
                assert not stat.S_ISLNK(fmode)
                assert is_normalized_file_path(fpath)

                assert FolderCache._file_path_is_ok_simple(fpath, root, const_exdirs)

                stats.nscanned += 1
                nf += 1
                tstamp = _get_file_timestamp_from_st(st)
                found = const_filesbypath.get(fpath)
                matched = False
                if found is not None:
                    # debug('FolderCache: found {}'.format(fpath))
                    sdout.scanned_files[fpath] = found
                    if found.file_hash is None:  # file in cache marked as deleted, re-adding
                        pass
                    else:
                        tstamp2 = found.file_modified
                        if tstamp == tstamp2:
                            matched = True
                            if found.file_size != st.st_size:
                                warn(
                                    'FolderCache: file size changed while timestamp did not for file {}, re-hashing it'.format(
                                        fpath))
                                matched = False
                else:
                    debug('FolderCache: not found {}'.format(fpath))
                if not matched:
                    sdout.requested_files.append((fpath, tstamp, st.st_size))
            elif stat.S_ISDIR(fmode):
                newdir = fpath + '\\'
                assert is_normalized_dir_path(newdir)
                if newdir in const_exdirs:
                    continue
                elapsed = time.perf_counter() - started
                if _time_to_split_task(elapsed):  # an ad-hoc split
                    sdout.requested_dirs.append(newdir)
                else:
                    FolderCache.scan_dir(started, sdout, stats, root, newdir, const_filesbypath, pubfilesbypath,
                                         filter_ex_dirs(const_exdirs, newdir), name)
            else:
                critical('FolderCache: {} is neither dir or file, aborting'.format(fpath))
                abort_if_not(False)
        assert dirpath not in sdout.scan_stats
        sdout.scan_stats[dirpath] = nf

    # Task Names
    def _scanned_task_name(self, dirpath: str) -> str:
        assert is_normalized_dir_path(dirpath)
        return 'sanguine.foldercache.' + self.name + '.' + dirpath

    def _scanned_own_task_name(self, dirpath: str) -> str:
        assert is_normalized_dir_path(dirpath)
        return 'sanguine.foldercache.own.' + self.name + '.' + dirpath

    def _reconcile_own_task_name(self) -> str:
        return 'sanguine.foldercache.reconcile.' + self.name

    def _hashing_task_name(self, fpath: str) -> str:
        assert is_normalized_file_path(fpath)
        return 'sanguine.foldercache.hash.' + self.name + '.' + fpath

    def _hashing_own_task_name(self, fpath: str) -> str:
        assert is_normalized_file_path(fpath)
        return 'sanguine.foldercache.hash.own.' + self.name + '.' + fpath

    def _hashing_own_wildcard_task_name(self, dirpath: str) -> str:
        assert is_normalized_dir_path(dirpath)
        return 'sanguine.foldercache.hash.own.' + self.name + '.' + dirpath + '*'

    ### Own Task Funcs

    def _load_files_own_task_func(self, out: tuple[dict[str, FileOnDisk]], parallel: tasks.Parallel) -> \
            tuple[tasks.SharedPubParam]:
        (filesbypath,) = out
        self._files_by_path = {}
        self._filtered_files = []
        for p, f in filesbypath.items():
            assert p == f.file_path
            if FolderCache._file_path_is_ok(p, self._folder_list):
                self._files_by_path[p] = f
            else:
                self._filtered_files.append(f)

        self.pub_files_by_path = tasks.SharedPublication(parallel, self._files_by_path)
        pubparam = tasks.make_shared_publication_param(self.pub_files_by_path)
        return (pubparam,)

    def _own_calc_hash_task_func(self, out: tuple[FileOnDisk], scannedfiles: dict[str, FileOnDisk]) -> None:
        (f,) = out
        scannedfiles[f.file_path] = f
        self._files_by_path[f.file_path] = f

    def _own_reconcile_task_func(self, parallel: tasks.Parallel,
                                 scannedfiles: dict[str, FileOnDisk]) -> None:
        info('FolderCache({}):{} files scanned'.format(self.name, len(scannedfiles)))
        ndel = 0
        for file in self._files_by_path.values():
            fpath = file.file_path
            assert is_normalized_file_path(fpath)
            if scannedfiles.get(fpath) is None:
                inhere = self._files_by_path.get(fpath)
                if inhere is not None and inhere.file_hash is None:  # special record is already present
                    continue
                info('FolderCache: {} was deleted'.format(fpath))
                # dbgWait()
                self._files_by_path[fpath] = FileOnDisk(None, None, fpath, None)
                ndel += 1
        info('FolderCache reconcile: {} files were deleted'.format(ndel))

        savetaskname = 'sanguine.foldercache.save.' + self.name
        savetask = tasks.Task(savetaskname, _save_files_task_func,
                              (self._cache_dir, self.name, self._files_by_path,
                               self._filtered_files, self._all_scan_stats),
                              [])
        parallel.add_task(
            savetask)  # we won't explicitly wait for savetask, it will be waited for in Parallel.__exit__

        self._is_ready = True

    def _scan_folder_own_task_func(self, out: tuple[list[str], _FolderScanStats, _FolderScanDirOut],
                                   parallel: tasks.Parallel, scannedfiles: dict[str, FileOnDisk],
                                   stats: _FolderScanStats) -> None:
        (exdirs, gotstats, sdout) = out
        stats.add(gotstats)
        assert len(scannedfiles.keys() & sdout.scanned_files.keys()) == 0
        scannedfiles |= sdout.scanned_files
        # if sdout.root in foldercache.all_scan_stats:
        #    assert len(foldercache.all_scan_stats[sdout.root].keys() & sdout.scan_stats.keys()) == 0
        #    foldercache.all_scan_stats[sdout.root] |= sdout.scan_stats
        # else:
        #    foldercache.all_scan_stats[sdout.root] = sdout.scan_stats
        self._all_scan_stats[sdout.root] = sdout.scan_stats  # always overwriting scan_stats

        for f in sdout.requested_files:
            (fpath, tstamp, fsize) = f
            debug(fpath)  # RM
            htaskname = self._hashing_task_name(fpath)
            htask = tasks.Task(htaskname, _calc_hash_task_func,
                               (fpath, tstamp, fsize),
                               [], _hashing_file_time_estimate(fsize))
            howntaskname = self._hashing_own_task_name(fpath)
            howntask = tasks.OwnTask(howntaskname,
                                     lambda _, o: self._own_calc_hash_task_func(o, scannedfiles),
                                     None, [htaskname], 0.001)  # expected to take negligible time
            parallel.add_tasks([htask, howntask])

        # new tasks
        for fpath in sdout.requested_dirs:
            assert is_normalized_dir_path(fpath)
            taskname = self._scanned_task_name(fpath)
            task = tasks.Task(taskname, _scan_folder_task_func,
                              (sdout.root, fpath, filter_ex_dirs(exdirs, fpath), self.name),
                              [], 1.0)  # this is an ad-hoc split, we don't want tasks to cache w, and we have no idea
            owntaskname = self._scanned_own_task_name(fpath)
            owntask = tasks.OwnTask(owntaskname,
                                    lambda _, o: self._scan_folder_own_task_func(o, parallel, scannedfiles, stats),
                                    None, [taskname], 0.01)  # should not take too long
            parallel.add_tasks([task, owntask])


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        tfoldercache = FolderCache(normalize_dir_path('..\\..\\sanguine.cache\\'),
                                   'downloads',
                                   [FolderToCache(normalize_dir_path('..\\..\\..\\mo2\\downloads'), [])])
        with tasks.Parallel(None) as tparallel:
            tfoldercache.start_tasks(tparallel)
            tparallel.run([])  # all necessary tasks were already added in acache.start_tasks()
