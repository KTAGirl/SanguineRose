import pickle
import time

import mo2gitlib.pluginhandler as pluginhandler
import mo2gitlib.tasks as tasks
import mo2gitlib.wjcompat.wjdb as wjdb
from mo2gitlib.common import *
from mo2gitlib.files import ArchiveEntry, calculate_file_hash
from mo2gitlib.folders import Folders
from mo2gitlib.pickledcache import pickled_cache


def _read_dict_of_archive_entries(dirpath: str) -> dict[str, ArchiveEntry]:
    assert Folders.is_normalized_dir_path(dirpath)
    fpath = dirpath + 'aentries.pickle'
    # out = {}
    with open(fpath, 'rb') as rfile:
        out = pickle.load(rfile)
        return out


def _write_dict_of_archive_entries(dirpath: str, archiveentries: dict[str, ArchiveEntry]) -> None:
    assert Folders.is_normalized_dir_path(dirpath)
    fpath = dirpath + 'aentries.pickle'
    with open(fpath, 'wb') as wf:
        # noinspection PyTypeChecker
        pickle.dump(archiveentries, wf)

    fpath2 = dirpath + '.njson'
    with open_3rdparty_txt_file_w(fpath2) as wf2:
        srt: list[tuple[str, ArchiveEntry]] = sorted(archiveentries.items())
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
                assert (nested_plugin is not None)
                _archive_to_entries(archive_entries, archive_hash, tmppath + str(nf) + '\\', new_intra_path,
                                    nested_plugin, fpath)


### Tasks

def _load_aentries_task_func(param: tuple[str]) -> tuple[dict[str, ArchiveEntry]]:
    (cachedir,) = param
    try:
        archive_entries = _read_dict_of_archive_entries(cachedir)
    except Exception as e:
        warn('error loading cache aentries.pickle: ' + str(e) + '. Will continue w/o respective cache')
        archive_entries = {}  # just in case

    return (archive_entries,)


def _load_aentries_own_task_func(out: tuple[dict[str, ArchiveEntry]], aecache: "ArchiveEntriesCache",
                                 is_archive_hash_known: Callable[[int], bool], ) -> None:
    (archive_entries,) = out
    assert len(aecache.archive_entries) == 0
    for ae in archive_entries.values():
        ahash = ae.archive_hash
        assert (ahash >= 0)
        if is_archive_hash_known(ahash):
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


def _own_filter_task_func(aecache: "ArchiveEntriesCache", parallel: tasks.Parallel,
                          is_archive_hash_known: Callable[[int], bool],
                          fromloadvfs: tuple[tasks.SharedReturnParam, dict[str, any]]) -> None:
    t0 = time.perf_counter()

    (sharedparam, cachedataoverwrites) = fromloadvfs
    aecache.cache_data |= cachedataoverwrites

    tsh0 = time.perf_counter()
    unfilteredarchiveentries: list[ArchiveEntry] = parallel.received_shared_return(sharedparam)
    tsh = time.perf_counter() - tsh0

    assert (len(aecache.wj_archive_entries) == 0)
    for ae in unfilteredarchiveentries:
        ahash = ae.archive_hash
        assert (ahash >= 0)
        if is_archive_hash_known(ahash):
            aecache.wj_archive_entries[ae.file_hash] = ae
        else:
            aecache.filtered_wj_archive_entries[ae.file_hash] = ae

    tsh0 = time.perf_counter()
    info('Filtering VFS: ' + str(len(aecache.wj_archive_entries)) + ' survived out of ' + str(
        len(unfilteredarchiveentries)))
    tsh += time.perf_counter() - tsh0
    info('Filtering took ' + str(round(time.perf_counter() - t0, 2)) + 's, including ' + str(
        round(tsh, 2)) + 's working with shared memory (pickling/unpickling)')


### class itself

class ArchiveEntriesCache:
    wj_archive_entries: dict[int, ArchiveEntry]
    archive_entries: dict[int, ArchiveEntry]
    filtered_wj_archive_entries: dict[int, ArchiveEntry]
    filtered_archive_entries: dict[int, ArchiveEntry]
    cache_data: dict[str, any]

    def __init__(self, cache_dir, cache_data: dict[str, any]) -> None:
        self.cache_dir = cache_dir
        self.wj_archive_entries = {}
        self.archive_entries = {}
        self.filtered_wj_archive_entries = {}
        self.filtered_archive_entries = {}
        self.cache_data = cache_data

    def start_tasks(self, parallel: tasks.Parallel, is_archive_hash_known: Callable[[int], bool],
                    task_name_enabling_is_archive_hash_known: str) -> None:
        loadtaskname = 'mo2gitlib.aentriescache.load'
        loadtask = tasks.Task(loadtaskname, _load_aentries_task_func,
                              (self.cache_dir,), [])
        parallel.add_late_task(loadtask)
        loadowntaskname = 'mo2gitlib.aentriescache.loadown'
        loadowntask = tasks.Task(loadowntaskname,
                                 lambda _, out: _load_aentries_own_task_func(out, self, is_archive_hash_known), None,
                                 [loadtaskname, task_name_enabling_is_archive_hash_known])
        parallel.add_late_own_task(loadowntask)

        loadvfstaskname = 'mo2gitlib.aentriescache.loadvfs'
        vfstask = tasks.Task(loadvfstaskname, _load_vfs_task_func,
                             (self.cache_dir, self.cache_data), [])
        parallel.add_late_task(vfstask)

        ownfiltertask = tasks.Task('mo2gitlib.aentriescache.ownfilter',
                                   lambda _, fromloadvfs, _2, _3: _own_filter_task_func(self, parallel,
                                                                                        is_archive_hash_known,
                                                                                        fromloadvfs),
                                   None,
                                   [loadvfstaskname, task_name_enabling_is_archive_hash_known, loadowntaskname])
        parallel.add_late_own_task(ownfiltertask)

    def find_entry_by_hash(self, h: int):
        assert h >= 0
        out = self.archive_entries.get(h)
        return out if out is not None else self.wj_archive_entries.get(h)

    def find_filtered_entry_by_hash(self, h: int):
        assert h >= 0
        out = self.filtered_archive_entries.get(h)
        return out if out is not None else self.filtered_wj_archive_entries.get(h)
