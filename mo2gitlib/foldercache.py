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


def _read_scan_stats(dirpath: str, name: str) -> dict[str, int]:
    assert Folders.is_normalized_dir_path(dirpath)
    fpath = dirpath + name + '.scan-stats.pickle'
    with open(fpath, 'rb') as rf:
        out = pickle.load(rf)
        return out


def _write_scan_stats(dirpath: str, name: str, scan_stats: dict[str, int]) -> None:
    assert Folders.is_normalized_dir_path(dirpath)
    fpath = dirpath + name + '.scan-stats.pickle'
    outstats = scan_stats
    with open(fpath, 'wb') as wf:
        # noinspection PyTypeChecker
        pickle.dump(outstats, wf)

    fpath2 = dirpath + name + '.scan-stats.json'
    with open_3rdparty_txt_file_w(fpath2) as wf2:
        srt = sorted(outstats.items())
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
    # filesbypath: dict[str, File]
    scanned_files: dict[str, File]
    requested_dirs: list[str]
    requested_files: list[tuple[str, float, int]]
    scan_stats: dict[str, int]  # fpath -> nfiles

    def __init__(self) -> None:
        # self.filesbypath = {}
        self.scanned_files = {}
        self.requested_dirs = []
        self.requested_files = []
        self.scan_stats = {}


class FolderScanFilter:
    dir_path_is_ok: tasks.LambdaReplacement
    file_path_is_ok: tasks.LambdaReplacement

    def __init__(self, dir_path_is_ok: tasks.LambdaReplacement, file_path_is_ok: tasks.LambdaReplacement) -> None:
        assert isinstance(file_path_is_ok, tasks.LambdaReplacement) and isinstance(dir_path_is_ok,
                                                                                   tasks.LambdaReplacement)
        self.dir_path_is_ok = dir_path_is_ok
        self.file_path_is_ok = file_path_is_ok


# heuristics to enable splitting/merging tasks

def _should_split_task(t: float) -> bool:
    return t > 0.5


def _scan_task_threshold() -> int:
    sec_threshold = 0.3
    return int(sec_threshold * 20000)  # scans per second


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
        if foldercache.scan_filter.file_path_is_ok.call(key):
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
        if foldercache.scan_filter.file_path_is_ok.call(key):
            foldercache.underlying_files_by_path[key] = val
    foldercache.pub_underlying_files_by_path = tasks.SharedPublication(parallel, foldercache.underlying_files_by_path)


def _scan_folder_task_func(param: tuple[str, list[str], str, FolderScanFilter, tasks.SharedPubParam, dict[str, float]],
                           fromownload: tuple[tasks.SharedPubParam]) -> tuple[
    list[str], _FolderScanStats, _FolderScanDirOut]:
    (taskroot, exdirs, name, scan_filter, pubunderlying, estimates) = param
    (pubfilesbypath,) = fromownload
    sdout = _FolderScanDirOut()
    stats = _FolderScanStats()
    filesbypath = tasks.from_publication(pubfilesbypath)
    underlying = tasks.from_publication(pubunderlying)
    started = time.perf_counter()
    FolderCache._scan_dir(started, sdout, stats, taskroot, filesbypath, underlying, pubunderlying, exdirs, name,
                          scan_filter,
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
    assert len(foldercache.scan_stats.keys() & sdout.scan_stats.keys()) == 0
    foldercache.scan_stats |= sdout.scan_stats

    for f in sdout.requested_files:
        (fpath, tstamp, fsize) = f
        htaskname = _hashing_task_name(foldercache.name, fpath)
        htask = tasks.Task(htaskname, _calc_hash_task_func,
                           (fpath, tstamp, fsize),
                           [])
        howntaskname = _hashing_own_task_name(foldercache.name, fpath)
        howntask = tasks.OwnTask(howntaskname,
                                 lambda _, o: _own_calc_hash_task_func(o, foldercache, scannedfiles),
                                 None, [htaskname])
        parallel.add_late_tasks([htask, howntask])

    # new tasks
    for fpath in sdout.requested_dirs:
        taskname = _scanned_task_name(foldercache.name, fpath)
        task = tasks.Task(taskname, _scan_folder_task_func,
                          (fpath, exdirs, foldercache.name, foldercache.scan_filter,
                           foldercache.pub_underlying_files_by_path, parallel.copy_estimates()),
                          [])
        owntaskname = _scanned_own_task_name(foldercache.name, fpath)
        owntask = tasks.OwnTask(owntaskname,
                                lambda _, o: _scan_folder_own_task_func(o, foldercache, parallel, scannedfiles, stats),
                                None, [taskname])
        parallel.add_late_tasks([task, owntask])


def _own_reconcile_task_func(foldercache: "FolderCache", parallel: tasks.Parallel,
                             scannedfiles: dict[str, File]) -> None:
    info('FolderCache(' + foldercache.root_folder + '): ' + str(len(scannedfiles)) + ' files scanned')
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
                           foldercache.filtered_files, foldercache.scan_stats),
                          [])
    parallel.add_late_task(
        savetask)  # we won't explicitly wait for savetask, it will be waited for in Parallel.__exit__


def _save_files_task_func(param: tuple[str, str, dict[str, File], dict[str, File], dict[str, int]]) -> None:
    (cachedir, name, filesbypath, filteredfiles, scan_stats) = param
    _write_dict_of_files(cachedir, name, filesbypath, filteredfiles)
    _write_scan_stats(cachedir, name, scan_stats)


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

    def fill_tasks(self, alltasks: list[tuple[str, list[str]]]) -> tuple[int, list[str]]:  # recursive
        nf = self.own_nf
        chex = []
        chexmerged = []
        for ch in self.children:
            chf, exdirs = ch.fill_tasks(alltasks)
            nf += chf
            chex.append(exdirs)
            chexmerged += exdirs
        if self.parent is not None and nf < _scan_task_threshold():
            return nf, chexmerged
        else:
            assert (len(chex) == len(self.children))
            outexdirs = []
            for i in range(len(self.children)):
                ch = self.children[i]
                alltasks.append((ch.path, chex[i]))
                outexdirs.append(ch.path)
            return self.own_nf, outexdirs


class FolderCache:  # single (recursive) folder cache
    cache_dir: str
    underlying_files_by_path: dict[str, File]
    name: str
    root_folder: str
    files_by_path: dict[str, File]
    filtered_files: list[File]
    scan_filter: FolderScanFilter
    pub_underlying_files_by_path: tasks.SharedPublication | None
    scan_stats: dict[str, int]  # fpath -> nfiles

    def __init__(self, cachedir: str, name: str, rootfolder: str,
                 scan_filter: FolderScanFilter) -> None:
        assert isinstance(scan_filter, FolderScanFilter)
        self.cache_dir = cachedir
        self.name = name
        self.root_folder = rootfolder
        self.files_by_path = {}
        self.filtered_files = []
        self.scan_filter = scan_filter

        self.underlying_files_by_path = {}
        self.pub_underlying_files_by_path = None
        try:
            self.scan_stats = _read_scan_stats(cachedir, name)
        except Exception as e:
            warn('error loading ' + name + '.scan-stats.pickle: ' + str(e) + '. Will continue w/o scan_stats')
            self.scan_stats = {}

    def start_tasks(self, parallel: tasks.Parallel,
                    underlyingfilesbypath_generator: Generator[tuple[str, File]],
                    task_name_enabling_underlyingfilesbypath_generator) -> None:

        # building tree of known scans
        rootstatnode: _ScanStatsNode | None = None
        curstatnode: _ScanStatsNode | None = None
        for fpath, nf in sorted(self.scan_stats.items()):
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

        alltasks: list[tuple[str, list[str]]] = []
        rootstatnode.fill_tasks(alltasks)

        # merged, starting tasks
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

        for tt in alltasks:
            (path, exdirs) = tt
            assert Folders.is_normalized_dir_path(path)
            taskname = _scanned_task_name(self.name, path)
            task = tasks.Task(taskname, _scan_folder_task_func,
                              (path, exdirs, self.name, self.scan_filter,
                               tasks.make_shared_publication_param(self.pub_underlying_files_by_path),
                               parallel.copy_estimates()),
                              [loadowntaskname, underlyingowntaskname])
            owntaskname = _scanned_own_task_name(self.name, path)
            owntask = tasks.OwnTask(owntaskname,
                                    lambda _, out: _scan_folder_own_task_func(out, self, parallel, scannedfiles, stats),
                                    None, [taskname])

            parallel.add_late_tasks([task, owntask])

        reconciletask = tasks.OwnTask(_reconcile_own_task_name(self.name),
                                      lambda _, _1: _own_reconcile_task_func(self, parallel, scannedfiles),
                                      None, [_scanned_own_task_name(self.name, self.root_folder) + '*',
                                             _hashing_own_task_name(self.name, self.root_folder) + '*'])
        parallel.add_late_task(reconciletask)

    def ready_task_name(self) -> str:
        return _reconcile_own_task_name(self.name)

    @staticmethod
    def _scan_dir(started: float, sdout: _FolderScanDirOut, stats: _FolderScanStats, dirpath: str,
                  filesbypath: dict[str, File], underlying: dict[str, File], pubunderlying: tasks.SharedPubParam,
                  exdirs: list[str], name: str,
                  scanfilter: FolderScanFilter, estimates: dict[str, float]) -> None:  # recursive over dir
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

                # if(not filter.filePathIsOk.call(fpath)):
                #    continue
                assert scanfilter.file_path_is_ok.call(fpath)

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
                if scanfilter.dir_path_is_ok.call(newdir):
                    est = tasks.Parallel.estimated_time_from_estimates(estimates, _scanned_task_name(name, newdir), 1.)
                    elapsed = time.perf_counter() - started
                    if _should_split_task(elapsed + est):
                        sdout.requested_dirs.append(newdir)
                    else:
                        FolderCache._scan_dir(started, sdout, stats, fpath, filesbypath, underlying, pubunderlying,
                                              exdirs, name, scanfilter, estimates)
            else:
                critical(fpath + ' is neither dir or file, aborting')
                abort_if_not(False)
        assert dirpath not in sdout.scan_stats
        sdout.scan_stats[dirpath] = nf
