import os.path
import pickle
import stat
import time

import mo2gitlib.tasks as tasks
from mo2gitlib.common import *
from mo2gitlib.files import File, calculate_file_hash, compare_timestamp_with_wj
from mo2gitlib.folders import Folders


def _get_file_timestamp(fname: str) -> float:
    return os.lstat(fname).st_mtime


def _get_file_timestamp_from_st(st: os.stat_result) -> float:
    return st.st_mtime


def _get_from_one_of_dicts(dicttolook: dict[any, any], dicttolook2: dict[any, any], key: any) -> any:
    found = dicttolook.get(key)
    if found is not None:
        return found
    return dicttolook2.get(key)


def _all_values_in_both_dicts(dicttoscan: dict[any, any], dicttoscan2: dict[any, any]) -> Generator[any]:
    for key, val in dicttoscan.items():
        yield val
    for key, val in dicttoscan2.items():
        yield val


def _read_dict_of_files(dirpath: str, name: str) -> dict[str, File]:
    assert Folders.is_normalized_dir_path(dirpath)
    fpath = dirpath + name + '.pickle'
    with open(fpath, 'rb') as rf:
        out = pickle.load(rf)
        return out


def _write_dict_of_files(dirpath: str, name: str, files: dict[str, File], filteredfiles: dict[str, File]) -> None:
    assert Folders.is_normalized_dir_path(dirpath)
    fpath = dirpath + name + '.pickle'
    outfiles: dict[str, File] = files | filteredfiles
    with open(fpath, 'wb') as wf:
        # noinspection PyTypeChecker
        pickle.dump(outfiles, wf)

    fpath2 = dirpath + name + '.njson'
    with open_3rdparty_txt_file_w(fpath2) as wf2:
        srt: list[tuple[str, File]] = sorted(outfiles.items())
        for item in srt:
            wf2.write(item[1].to_json() + '\n')


def _read_all_scan_stats(dirpath: str, name: str) -> dict[str, dict[str, int]]:
    assert Folders.is_normalized_dir_path(dirpath)
    fpath = dirpath + name + '.scan-stats.pickle'
    with open(fpath, 'rb') as rf:
        out = pickle.load(rf)
        return out


def _write_all_scan_stats(dirpath: str, name: str, all_scan_stats: dict[str, dict[str, int]]) -> None:
    assert Folders.is_normalized_dir_path(dirpath)
    fpath = dirpath + name + '.scan-stats.pickle'
    with open(fpath, 'wb') as wf:
        # noinspection PyTypeChecker
        pickle.dump(all_scan_stats, wf)

    fpath2 = dirpath + name + '.scan-stats.json'
    srt = sorted(all_scan_stats.items())
    with open_3rdparty_txt_file_w(fpath2) as wf2:
        # noinspection PyTypeChecker
        json.dump(srt, wf2)


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
    scanned_files: dict[str, File]
    requested_dirs: list[str]
    requested_files: list[tuple[str, float, int]]
    scan_stats: dict[str, int]  # fpath -> nfiles

    def __init__(self, root: str) -> None:
        self.root = root
        self.scanned_files = {}
        self.requested_dirs = []
        self.requested_files = []
        self.scan_stats = {}


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


# task names

def _scanned_task_name(cachename: str, dirpath: str) -> str:
    assert Folders.is_normalized_dir_path(dirpath)
    return 'mo2gitlib.foldercache.' + cachename + '.' + dirpath


def _scanned_own_task_name(cachename: str, dirpath: str) -> str:
    assert Folders.is_normalized_dir_path(dirpath)
    return 'mo2gitlib.foldercache.own.' + cachename + '.' + dirpath


def _reconcile_own_task_name(name: str) -> str:
    return 'mo2gitlib.foldercache.reconcile.' + name


def _hashing_task_name(cachename: str, dirpath: str) -> str:
    assert Folders.is_normalized_dir_path(dirpath)
    return 'mo2gitlib.foldercache.hash.' + cachename + '.' + dirpath


def _hashing_own_task_name(cachename: str, dirpath: str) -> str:
    assert Folders.is_normalized_dir_path(dirpath)
    return 'mo2gitlib.foldercache.hash.own.' + cachename + '.' + dirpath


### Tasks

def _load_files_task_func(param: tuple[str, str]) -> tuple[dict[str, File]]:
    (cachedir, name) = param
    # filesbypath = {}
    try:
        filesbypath = _read_dict_of_files(cachedir, name)
    except Exception as e:
        warn('error loading cache ' + name + '.pickle: ' + str(e) + '. Will continue w/o respective cache')
        filesbypath = {}  # just in case

    return (filesbypath,)


def _load_files_own_task_func(out, foldercache: "FolderCache", parallel: tasks.Parallel) -> tuple[tasks.SharedPubParam]:
    (filesbypath,) = out
    foldercache.files_by_path = {}
    foldercache.filtered_files = {}
    for key, val in filesbypath.items():
        assert key == val.file_path
        if foldercache.file_path_is_ok(key):
            foldercache.files_by_path[key] = val
        else:
            foldercache.filtered_files[key] = val

    foldercache.pub_underlying_files_by_path = tasks.SharedPublication(parallel, foldercache.underlying_files_by_path)
    pubparam = tasks.make_shared_publication_param(foldercache.pub_underlying_files_by_path)
    return (pubparam,)


def _underlying_own_task_func(foldercache: "FolderCache", parallel: tasks.Parallel,
                              underlyingfilesbypath_generator: Generator[tuple[str, File]]) -> None:
    assert len(foldercache.underlying_files_by_path) == 0
    for key, val in underlyingfilesbypath_generator:
        assert val.file_path == key
        if foldercache.file_path_is_ok(key):
            foldercache.underlying_files_by_path[key] = val
    foldercache.pub_underlying_files_by_path = tasks.SharedPublication(parallel, foldercache.underlying_files_by_path)


def _scan_folder_task_func(
        param: tuple[str, str, list[str], str, tasks.SharedPubParam, dict[str, float]],
        fromownload: tuple[tasks.SharedPubParam]) -> tuple[
    list[str], _FolderScanStats, _FolderScanDirOut]:
    (rootpath, taskroot, exdirs, name, pubunderlying, estimates) = param
    (pubfilesbypath,) = fromownload
    sdout = _FolderScanDirOut(rootpath)
    stats = _FolderScanStats()
    filesbypath = tasks.from_publication(pubfilesbypath)
    underlying = tasks.from_publication(pubunderlying)
    started = time.perf_counter()
    FolderCache._scan_dir(started, sdout, stats, rootpath, taskroot, filesbypath, underlying, pubunderlying, exdirs,
                          name,
                          estimates)
    return exdirs, stats, sdout


def _calc_hash_task_func(param: tuple[str, float, int]) -> tuple[File]:
    (fpath, tstamp, fsize) = param
    h = calculate_file_hash(fpath)
    return (File(h, tstamp, fpath, fsize),)


def _own_calc_hash_task_func(out: tuple[File], foldercache: "FolderCache", scannedfiles: dict[str, File]) -> None:
    (f,) = out
    scannedfiles[f.file_path] = f
    foldercache.files_by_path[f.file_path] = f


def _scan_folder_own_task_func(out: tuple[list[str], _FolderScanStats, _FolderScanDirOut],
                               foldercache: "FolderCache", parallel: tasks.Parallel, scannedfiles: dict[str, File],
                               stats: _FolderScanStats) -> None:
    (exdirs, gotstats, sdout) = out
    stats.add(gotstats)
    assert len(scannedfiles.keys() & sdout.scanned_files.keys()) == 0
    scannedfiles |= sdout.scanned_files
    # foldercache.files_by_path |= sdout.filesbypath
    assert len(foldercache.all_scan_stats[sdout.root].keys() & sdout.scan_stats.keys()) == 0
    foldercache.all_scan_stats[sdout.root] |= sdout.scan_stats

    for f in sdout.requested_files:
        (fpath, tstamp, fsize) = f
        htaskname = _hashing_task_name(foldercache.name, fpath)
        htask = tasks.Task(htaskname, _calc_hash_task_func,
                           (fpath, tstamp, fsize),
                           [], _hashing_file_time_estimate(fsize))
        howntaskname = _hashing_own_task_name(foldercache.name, fpath)
        howntask = tasks.OwnTask(howntaskname,
                                 lambda _, o: _own_calc_hash_task_func(o, foldercache, scannedfiles),
                                 None, [htaskname], 0.001)  # expected to take negligible time
        parallel.add_late_tasks([htask, howntask])

    # new tasks
    for fpath in sdout.requested_dirs:
        assert Folders.is_normalized_dir_path(fpath)
        taskname = _scanned_task_name(foldercache.name, fpath)
        task = tasks.Task(taskname, _scan_folder_task_func,
                          (sdout.root, fpath, filter_ex_dirs(exdirs, fpath), foldercache.name,
                           foldercache.pub_underlying_files_by_path, parallel.copy_estimates()),
                          [], 1.0)  # this is an ad-hoc split, we don't want tasks to cache w, and we have no idea
        owntaskname = _scanned_own_task_name(foldercache.name, fpath)
        owntask = tasks.OwnTask(owntaskname,
                                lambda _, o: _scan_folder_own_task_func(o, foldercache, parallel, scannedfiles, stats),
                                None, [taskname], 0.01)  # should not take too long
        parallel.add_late_tasks([task, owntask])


def _own_reconcile_task_func(foldercache: "FolderCache", parallel: tasks.Parallel,
                             scannedfiles: dict[str, File]) -> None:
    info('FolderCache(' + foldercache.name + '): ' + str(len(scannedfiles)) + ' files scanned')
    ndel = 0
    for file in _all_values_in_both_dicts(foldercache.files_by_path, foldercache.underlying_files_by_path):
        fpath = file.file_path
        assert Folders.is_normalized_file_path(fpath)
        if scannedfiles.get(fpath) is None:
            inhere = foldercache.files_by_path.get(fpath)
            if inhere is not None and inhere.file_hash is None:  # special record is already present
                continue
            info(fpath + ' was deleted')
            # dbgWait()
            foldercache.files_by_path[fpath] = File(None, None, fpath)
            ndel += 1
    info('FolderCache reconcile: ' + str(ndel) + ' files were deleted')
    # dbgWait()

    savetaskname = 'mo2git.foldercache.save.' + foldercache.name
    savetask = tasks.Task(savetaskname, _save_files_task_func,
                          (foldercache.cache_dir, foldercache.name, foldercache.files_by_path,
                           foldercache.filtered_files, foldercache.all_scan_stats),
                          [])
    parallel.add_late_task(
        savetask)  # we won't explicitly wait for savetask, it will be waited for in Parallel.__exit__


def _save_files_task_func(param: tuple[str, str, dict[str, File], dict[str, File], dict[str, dict[str, int]]]) -> None:
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
            assert Folders.is_normalized_dir_path(fpath)
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
    cache_dir: str
    underlying_files_by_path: dict[str, File]
    name: str
    folder_list: list[tuple[str, list[str]]]
    files_by_path: dict[str, File]
    filtered_files: list[File]
    pub_underlying_files_by_path: tasks.SharedPublication | None
    all_scan_stats: dict[str, dict[str, int]]  # rootfolder -> {fpath -> nfiles}

    def __init__(self, cachedir: str, name: str, folder_list: list[tuple[str, list[str]]]) -> None:
        self.cache_dir = cachedir
        self.name = name
        self.folder_list = folder_list
        self.files_by_path = {}
        self.filtered_files = []

        self.underlying_files_by_path = {}
        self.pub_underlying_files_by_path = None
        try:
            self.all_scan_stats = _read_all_scan_stats(cachedir, name)
        except Exception as e:
            warn('error loading ' + name + '.scan-stats.pickle: ' + str(e) + '. Will continue w/o scan_stats')
            self.all_scan_stats = {}

    def start_tasks(self, parallel: tasks.Parallel,
                    underlyingfilesbypath_generator: Generator[tuple[str, File]],
                    task_name_enabling_underlyingfilesbypath_generator) -> None:

        # building tree of known scans
        allscantasks: list[tuple[str, str, int, list[str]]] = []  # [(root,path,nf,exdirs)]

        for folderplus in self.folder_list:
            (rootpath, extexdirs) = folderplus
            scan_stats = self.all_scan_stats.get(rootpath)
            rootstatnode = _ScanStatsNode.make_tree(scan_stats, rootpath, extexdirs)
            rootstatnode.fill_tasks(allscantasks, rootpath, extexdirs)

        # ready to start tasks
        scannedfiles = {}
        stats = _FolderScanStats()

        loadtaskname = 'mo2git.foldercache.load.' + self.name
        loadtask = tasks.Task(loadtaskname, _load_files_task_func, (self.cache_dir, self.name), [])
        parallel.add_late_task(loadtask)

        loadowntaskname = 'mo2git.foldercache.loadown.' + self.name
        loadowntask = tasks.OwnTask(loadowntaskname, lambda _, out: _load_files_own_task_func(out, self, parallel),
                                    None,
                                    [loadtaskname])
        parallel.add_late_task(loadowntask)

        underlyingowntaskname = 'mo2git.foldercache.underlyingown.' + self.name
        underlyingowntask = tasks.OwnTask(underlyingowntaskname, lambda _, _1: _underlying_own_task_func(self, parallel,
                                                                                                         underlyingfilesbypath_generator),
                                          None,
                                          [task_name_enabling_underlyingfilesbypath_generator])
        parallel.add_late_task(underlyingowntask)

        for tt in allscantasks:
            (root, path, nf, exdirs) = tt
            assert Folders.is_normalized_dir_path(path)
            taskname = _scanned_task_name(self.name, path)
            task = tasks.Task(taskname, _scan_folder_task_func,
                              (root, path, exdirs, self.name,
                               tasks.make_shared_publication_param(self.pub_underlying_files_by_path),
                               parallel.copy_estimates()),
                              [loadowntaskname, underlyingowntaskname], _scan_task_time_estimate(nf))
            owntaskname = _scanned_own_task_name(self.name, path)
            owntask = tasks.OwnTask(owntaskname,
                                    lambda _, out: _scan_folder_own_task_func(out, self, parallel, scannedfiles, stats),
                                    None, [taskname])

            parallel.add_late_tasks([task, owntask])

        scanningdeps = [_scanned_own_task_name(self.name, folderplus[0]) + '*' for folderplus in self.folder_list]
        hashingdeps = [_hashing_own_task_name(self.name, folderplus[0]) + '*' for folderplus in self.folder_list]
        reconciletask = tasks.OwnTask(_reconcile_own_task_name(self.name),
                                      lambda _, _1: _own_reconcile_task_func(self, parallel, scannedfiles),
                                      None, scanningdeps + hashingdeps)
        parallel.add_late_task(reconciletask)

    def ready_task_name(self) -> str:
        return _reconcile_own_task_name(self.name)

    @staticmethod
    def file_path_is_ok_ex(path: str, exdirs: list[str]) -> bool:
        for exdir in exdirs:
            if path.startswith(exdir):
                return False
        return True

    def file_path_is_ok(self, fpath: str) -> bool:
        for folderplus in self.folder_list:
            if fpath.startswith(folderplus[0]) and FolderCache.file_path_is_ok_ex(fpath, folderplus[1]):
                return True
        return False

    @staticmethod
    def _scan_dir(started: float, sdout: _FolderScanDirOut, stats: _FolderScanStats, rootpath: str, dirpath: str,
                  filesbypath: dict[str, File], underlying: dict[str, File], pubunderlying: tasks.SharedPubParam,
                  exdirs: list[str], name: str, estimates: dict[str, float]) -> None:  # recursive over dir
        assert Folders.is_normalized_dir_path(dirpath)
        # recursive implementation: able to skip subtrees, but more calls (lots of os.listdir() instead of single os.walk())
        # still, after recent performance fix seems to win like 1.5x over os.walk-based one
        nf = 0
        for f in os.listdir(dirpath):
            fpath = dirpath + Folders.normalize_file_name(f)
            st = os.lstat(fpath)
            fmode = st.st_mode
            if stat.S_ISREG(fmode):
                assert not stat.S_ISLNK(fmode)
                assert Folders.is_normalized_file_path(fpath)

                assert FolderCache.file_path_is_ok_ex(fpath, exdirs)

                stats.nscanned += 1
                nf += 1
                tstamp = _get_file_timestamp_from_st(st)
                # print(fpath)
                found = _get_from_one_of_dicts(filesbypath, underlying, fpath)
                matched = False
                if found is not None:
                    assert found.file_hash == fpath
                    sdout.scanned_files[fpath] = found
                    if found.file_hash is not None:  # file in cache marked as deleted, re-adding
                        tstamp2 = found.file_modified
                        if compare_timestamp_with_wj(tstamp, tstamp2) == 0:
                            matched = True
                if not matched:
                    sdout.requested_files.append((fpath, tstamp, st.st_size))
            elif stat.S_ISDIR(fmode):
                newdir = fpath + '\\'
                assert Folders.is_normalized_dir_path(newdir)
                if newdir in exdirs:
                    continue
                est = tasks.Parallel.estimated_time_from_estimates(estimates, _scanned_task_name(name, newdir), 1.)
                elapsed = time.perf_counter() - started
                if _time_to_split_task(elapsed + est):  # an ad-hoc split
                    sdout.requested_dirs.append(newdir)
                else:
                    FolderCache._scan_dir(started, sdout, stats, rootpath, newdir, filesbypath, underlying,
                                          pubunderlying,
                                          filter_ex_dirs(exdirs, newdir), name, estimates)
            else:
                critical(fpath + ' is neither dir or file, aborting')
                abort_if_not(False)
        assert dirpath not in sdout.scan_stats
        sdout.scan_stats[dirpath] = nf
