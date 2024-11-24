# noinspection PyUnresolvedReferences
import pickle
import time

import mo2gitlib.pluginhandler as pluginhandler
import mo2gitlib.tasks as tasks
import mo2gitlib.wjcompat.wjdb as wjdb
from mo2gitlib.common import *
from mo2gitlib.files import ArchiveEntry, calculate_file_hash
from mo2gitlib.folders import Folders
from mo2gitlib.pickledcache import pickled_cache


def _processing_archive_time_estimate(fsize: int):
    return float(fsize) / 1048576. / 10.  # 10 MByte/s


def _read_dict_of_archive_entries(cachedir: str) -> dict[str, ArchiveEntry]:
    assert Folders.is_normalized_dir_path(cachedir)
    return read_dict_from_pickled_file(cachedir + 'aentries.pickle')


def _write_dict_of_archive_entries(dirpath: str, archiveentries: dict[str, ArchiveEntry],
                                   filtered_archive_entries: dict[str, ArchiveEntry]) -> None:
    assert Folders.is_normalized_dir_path(dirpath)
    fpath = dirpath + 'aentries.pickle'
    outaentries: dict[str, ArchiveEntry] = archiveentries | filtered_archive_entries
    with open(fpath, 'wb') as wf:
        # noinspection PyTypeChecker
        pickle.dump(outaentries, wf)

    fpath2 = dirpath + '.njson'
    with open_3rdparty_txt_file_w(fpath2) as wf2:
        srt: list[tuple[str, ArchiveEntry]] = sorted(outaentries.items())
        for ae in srt:
            wf2.write(ae[1].to_json() + '\n')


def _archive_to_entries(archive_entries: dict[int, ArchiveEntry], archive_hash: int, tmppath: str,
                        cur_intra_path: list[str],
                        plugin: pluginhandler.ArchivePluginBase, archivepath: str):  # recursive
    if not os.path.isdir(tmppath):
        os.makedirs(tmppath)
    plugin.extract_all(archivepath, tmppath)
    pluginexts = pluginhandler.all_archive_plugins_extensions()  # for nested archives
    for root, dirs, files in os.walk(tmppath):
        nf = 0
        for f in files:
            nf += 1
            fpath = os.path.join(root, f)
            assert os.path.isfile(fpath)
            # print(fpath)
            h = calculate_file_hash(fpath)
            assert fpath.startswith(tmppath)
            new_intra_path = cur_intra_path.copy()
            new_intra_path.append(Folders.normalize_archive_intra_path(fpath[len(tmppath):]))
            ae = ArchiveEntry(archive_hash, new_intra_path, os.path.getsize(fpath), h)
            # print(ae.__dict__)
            archive_entries[ae.file_hash] = ae

            ext = os.path.split(fpath)[1].lower()
            if ext in pluginexts:
                nested_plugin = pluginhandler.archive_plugin_for(fpath)
                assert nested_plugin is not None
                _archive_to_entries(archive_entries, archive_hash, tmppath + str(nf) + '\\', new_intra_path,
                                    nested_plugin, fpath)


### Tasks

def _load_aentries_task_func(param: tuple[str]) -> tuple[dict[str, ArchiveEntry]]:
    (cachedir,) = param
    archive_entries = _read_dict_of_archive_entries(cachedir)
    return (archive_entries,)


def _load_aentries_own_task_func(out: tuple[dict[str, ArchiveEntry]], aecache: "ArchiveEntriesCache",
                                 all_used_archives: Iterable[tuple[str, int, int]]) -> None:
    (archive_entries,) = out
    assert aecache.archive_entries is None
    aecache.archive_entries = {}

    allarchives: dict[int, bool] = {}  # have to do it here, cannot fill it before task_func is called
    for a in all_used_archives:
        allarchives[a[1]] = False  # allarchives here is actually a set, value doesn't matter

    for ae in archive_entries.values():
        ahash = ae.archive_hash
        assert ahash >= 0
        if ahash in allarchives:
            aecache.archive_entries[ae.file_hash] = ae
        else:
            aecache.filtered_archive_entries[ae.file_hash] = ae
    info('Filtering aentries: ' + str(len(aecache.archive_entries)) + ' survived out of ' + str(
        len(archive_entries)))


def _load_vfs() -> list[ArchiveEntry]:
    unfilteredarchiveentries = []
    for ae in wjdb.load_vfs():
        unfilteredarchiveentries.append(ae)
    return unfilteredarchiveentries


def _load_vfs_task_func(param: tuple[str, dict[str, any]]) -> tuple[tasks.SharedReturnParam, dict[str, any]]:
    (cachedir, cachedata) = param
    (unfilteredarchiveentries, cachedataoverwrites) = pickled_cache(cachedir, cachedata, 'wjdb.vfsfile',
                                                                    [wjdb.vfs_file_path()],
                                                                    lambda _: _load_vfs())

    shared = tasks.SharedReturn(unfilteredarchiveentries)
    return tasks.make_shared_return_param(shared), cachedataoverwrites


def _archive_hashing_task_func(param: tuple[str, int, str]) -> tuple[dict[int, ArchiveEntry]]:
    (arpath, arhash, tmppath,) = param
    archive_entries: dict[int, ArchiveEntry] = {}
    plugin = pluginhandler.archive_plugin_for(arpath)
    assert plugin is not None
    _archive_to_entries(archive_entries, arhash, tmppath, [], plugin, arpath)
    return (archive_entries,)


def _archive_hashing_own_task_func(out: tuple[dict[int, ArchiveEntry]], aecache: "ArchiveEntriesCache"):
    (archive_entries,) = out
    aecache.archive_entries |= archive_entries
    for ae in archive_entries.values():
        if ae.file_hash in aecache.archive_entries:
            warn('file_hash ' + str(ae.file_hash) + ' already present in archive_entries')
            # do nothing here, will still overwrite it below
        if ae.file_hash in aecache.filtered_archive_entries:
            warn('file_hash ' + str(ae.file_hash) + ' already present in filtered_archive_entries')
            del aecache.filtered_archive_entries[ae.file_hash]
        # we probably do not care too much about collisions with WJ, will simply overwrite them
        aecache.archive_entries[ae.file_hash] = ae


def _own_filter_task_func(aecache: "ArchiveEntriesCache", parallel: tasks.Parallel,
                          all_used_archives: Iterable[tuple[str, int, int]],
                          fromloadvfs: tuple[tasks.SharedReturnParam, dict[str, any]]) -> None:
    t0 = time.perf_counter()

    (sharedparam, cachedataoverwrites) = fromloadvfs
    aecache.cache_data |= cachedataoverwrites

    tsh0 = time.perf_counter()
    unfilteredarchiveentries: list[ArchiveEntry] = parallel.received_shared_return(sharedparam)
    tsh = time.perf_counter() - tsh0

    allarchives: dict[int, tuple[str, int, Val]] = {}  # fpath, size, Val(hashed);
    # have to do it here, cannot fill it before task_func is called
    for a in all_used_archives:
        allarchives[a[1]] = (a[0], a[2], Val(False))  # False means 'not found yet'

    assert len(aecache.wj_archive_entries) == 0
    for ae in unfilteredarchiveentries:
        ahash = ae.archive_hash
        assert ahash >= 0
        if ahash in allarchives:
            aecache.wj_archive_entries[ae.file_hash] = ae
            allarchives[ahash][
                2].val = True  # if we see at least one aentry for archive - we assume that the whole archive has been hashed
        else:
            aecache.filtered_wj_archive_entries[ae.file_hash] = ae

    tsh0 = time.perf_counter()
    info('Filtering VFS: ' + str(len(aecache.wj_archive_entries)) + ' survived out of ' + str(
        len(unfilteredarchiveentries)))
    tsh += time.perf_counter() - tsh0
    info('Filtering took ' + str(round(time.perf_counter() - t0, 2)) + 's, including ' + str(
        round(tsh, 2)) + 's working with shared memory (pickling/unpickling)')

    # Reconciling
    # allarchives[ahash] is already set to True for wj_archive_entries
    assert aecache.archive_entries is not None
    for ae in aecache.archive_entries.values():
        ahash = ae.archive_hash
        assert ahash >= 0
        if ahash in allarchives:
            allarchives[ahash][
                2].val = True  # if we see at least one aentry for archive - we assume that the whole archive has been hashed
    # now, we marked allarchives[ahash] as used for all the hashed archives
    numhashing = 0
    for arhash, ar in allarchives.items():
        if not ar[2].val:
            # found unhashed archive
            info('need to hash ' + ar[0] + ', scheduling archive hashing task')
            numhashing += 1
            hashingtaskname = 'mo2gitlib.aentriescache.hash.' + ar[0]
            hashingtask = tasks.Task(hashingtaskname, _archive_hashing_task_func,
                                     (ar[0], arhash, aecache.tmp_dir + str(numhashing) + '\\'), [],
                                     _processing_archive_time_estimate(ar[1]))
            hashingowntaskname = 'mo2gitlib.aentriescache.hashingown.' + ar[0]
            hashingowntask = tasks.OwnTask(hashingowntaskname,
                                           lambda _, out: _archive_hashing_own_task_func(out, aecache), None,
                                           [hashingtaskname], 0.001)  # should take negligible time
            parallel.add_late_tasks([hashingtask, hashingowntask])

    savetaskname = 'mo2git.aentriescache.save'
    savetask = tasks.Task(savetaskname, _save_aentries_task_func,
                          (aecache.cache_dir, aecache.archive_entries, aecache.filtered_archive_entries),
                          [])
    parallel.add_late_task(
        savetask)  # we won't explicitly wait for savetask, it will be waited for in Parallel.__exit__


def _save_aentries_task_func(param: tuple[str, dict[str, ArchiveEntry], dict[str, ArchiveEntry]]) -> None:
    (cachedir, archive_entries, filtered_archive_entries) = param
    _write_dict_of_archive_entries(cachedir, archive_entries, filtered_archive_entries)


### class itself

class ArchiveEntriesCache:
    cache_dir: str
    tmp_dir: str
    wj_archive_entries: dict[int, ArchiveEntry]
    archive_entries: dict[int, ArchiveEntry] | None
    filtered_wj_archive_entries: dict[int, ArchiveEntry]
    filtered_archive_entries: dict[int, ArchiveEntry]
    cache_data: dict[str, any]

    def __init__(self, cache_dir, base_tmp_dir, cache_data: dict[str, any]) -> None:
        self.cache_dir = cache_dir
        self.tmp_dir = base_tmp_dir + 'aecache\\'
        self.wj_archive_entries = {}
        self.archive_entries = None
        self.filtered_wj_archive_entries = {}
        self.filtered_archive_entries = {}
        self.cache_data = cache_data

    def start_tasks(self, parallel: tasks.Parallel,
                    all_used_archives: Iterable[tuple[str, int, int]],  # fpath, hash, size
                    task_name_enabling_all_used_archives: str) -> None:
        loadtaskname = 'mo2gitlib.aentriescache.load'
        loadtask = tasks.Task(loadtaskname, _load_aentries_task_func,
                              (self.cache_dir,), [])
        parallel.add_late_task(loadtask)
        loadowntaskname = 'mo2gitlib.aentriescache.loadown'
        loadowntask = tasks.OwnTask(loadowntaskname,
                                    lambda _, out, _1: _load_aentries_own_task_func(out, self, all_used_archives), None,
                                    [loadtaskname, task_name_enabling_all_used_archives])
        parallel.add_late_task(loadowntask)

        loadvfstaskname = 'mo2gitlib.aentriescache.loadvfs'
        vfstask = tasks.Task(loadvfstaskname, _load_vfs_task_func,
                             (self.cache_dir, self.cache_data), [])
        parallel.add_late_task(vfstask)

        ownfiltertask = tasks.OwnTask('mo2gitlib.aentriescache.ownfilter',
                                      lambda _, fromloadvfs, _2, _3: _own_filter_task_func(self, parallel,
                                                                                           all_used_archives,
                                                                                           fromloadvfs),
                                      None,
                                      [loadvfstaskname, task_name_enabling_all_used_archives, loadowntaskname])
        parallel.add_late_task(ownfiltertask)

    def find_entry_by_hash(self, h: int):
        assert h >= 0
        out = self.archive_entries.get(h)
        return out if out is not None else self.wj_archive_entries.get(h)

    def find_filtered_entry_by_hash(self, h: int):
        assert h >= 0
        out = self.filtered_archive_entries.get(h)
        return out if out is not None else self.filtered_wj_archive_entries.get(h)
