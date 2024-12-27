import sanguine.gitdata.git_data_file as gitdatafile
import sanguine.tasks as tasks
from sanguine.cache.pickled_cache import pickled_cache
from sanguine.common import *
from sanguine.gitdata.file_origin import FileOrigin, GitFileOriginsJson
from sanguine.gitdata.master_git_archives import GitArchivesJson
from sanguine.helpers.archives import Archive, FileInArchive
from sanguine.helpers.archives import ArchivePluginBase, all_archive_plugins_extensions, archive_plugin_for
from sanguine.helpers.tmp_path import TmpPath

### AllMasterGitData Helpers

_KNOWN_ARCHIVES_FNAME = 'known-archives.json5'
_KNOWN_FILE_ORIGINS_FNAME = 'known-file-origins.json5'


def _processing_archive_time_estimate(fsize: int):
    return float(fsize) / 1048576. / 10.  # 10 MByte/s


def _read_git_archives(params: tuple[str]) -> list[Archive]:
    (archivesgitfile,) = params
    assert is_normalized_file_path(archivesgitfile)
    with gitdatafile.open_git_data_file_for_reading(archivesgitfile) as rf:
        archives = GitArchivesJson().read_from_file(rf)
    return archives


def _read_cached_git_archives(mastergitdir: str, cachedir: str,
                              cachedata: dict[str, any]) -> tuple[list[Archive], dict[str, any]]:
    assert is_normalized_dir_path(mastergitdir)
    mastergitfile = mastergitdir + _KNOWN_ARCHIVES_FNAME
    return pickled_cache(cachedir, cachedata, 'known_archives', [mastergitfile],
                         _read_git_archives, (mastergitfile,))


def _write_git_archives(mastergitdir: str, archives: list[Archive]) -> None:
    assert is_normalized_dir_path(mastergitdir)
    fpath = mastergitdir + _KNOWN_ARCHIVES_FNAME
    with gitdatafile.open_git_data_file_for_writing(fpath) as wf:
        GitArchivesJson().write(wf, archives)


def _hash_archive(archives: list[Archive], by: str, tmppath: str,  # recursive!
                  plugin: ArchivePluginBase,
                  archivepath: str, arhash: bytes, arsize: int) -> None:
    assert os.path.isdir(tmppath)
    plugin.extract_all(archivepath, tmppath)
    pluginexts = all_archive_plugins_extensions()  # for nested archives
    ar = Archive(arhash, arsize, by)
    archives.append(ar)
    for root, dirs, files in os.walk(tmppath):
        nf = 0
        for f in files:
            nf += 1
            fpath = os.path.join(root, f)
            s, h = calculate_file_hash(fpath)
            assert fpath.startswith(tmppath)
            ar.files.append(
                FileInArchive(truncate_file_hash(h), s, normalize_archive_intra_path(fpath[len(tmppath):])))

            ext = os.path.split(fpath)[1].lower()
            if ext in pluginexts:
                nested_plugin = archive_plugin_for(fpath)
                assert nested_plugin is not None
                newtmppath = TmpPath.tmp_in_tmp(tmppath,
                                                'T3lIzNDx.',  # tmp is not from root,
                                                # so randomly-looking prefix is necessary
                                                nf)
                assert not os.path.isdir(newtmppath)
                os.makedirs(newtmppath)
                _hash_archive(archives, by, newtmppath, nested_plugin, fpath, h, s)


def _read_git_file_origins(params: tuple[str]) -> dict[bytes, list[FileOrigin]]:
    (fogitfile,) = params
    assert is_normalized_file_path(fogitfile)
    with gitdatafile.open_git_data_file_for_reading(fogitfile) as rf:
        forigins = GitFileOriginsJson().read_from_file(rf)
    return forigins


def _read_cached_file_origins(mastergitdir: str, cachedir: str,
                              cachedata: dict[str, any]) -> tuple[dict[bytes, list[FileOrigin]], dict[str, any]]:
    assert is_normalized_dir_path(mastergitdir)
    mastergitfile = mastergitdir + _KNOWN_FILE_ORIGINS_FNAME
    return pickled_cache(cachedir, cachedata, 'known_file_origins', [mastergitfile],
                         _read_git_file_origins, (mastergitfile,))


def _write_git_file_origins(mastergitdir: str, forigins: dict[bytes, list[FileOrigin]]) -> None:
    assert is_normalized_dir_path(mastergitdir)
    fpath = mastergitdir + _KNOWN_FILE_ORIGINS_FNAME
    with gitdatafile.open_git_data_file_for_writing(fpath) as wf:
        GitFileOriginsJson().write(wf, forigins)


### AllMasterGitData Tasks

def _append_archive(archives_by_hash, archived_files_by_hash, archived_files_by_name, ar: Archive) -> None:
    # warn(str(len(ar.files)))
    assert ar.archive_hash not in archives_by_hash
    archives_by_hash[ar.archive_hash] = ar
    for fi in ar.files:
        if fi.file_hash not in archived_files_by_hash:
            archived_files_by_hash[fi.file_hash] = []
        archived_files_by_hash[fi.file_hash].append((ar, fi))

        fname = os.path.split(fi.intra_path)[1]
        if fname not in archived_files_by_name:
            archived_files_by_name[fname] = []
        archived_files_by_name[fname].append((ar, fi))


def _load_archives_task_func(param: tuple[str, str, dict[str, any]]) -> tuple[dict, dict, dict, dict[str, any]]:
    (mastergitdir, cachedir, cachedata) = param
    (archives, cacheoverrides) = _read_cached_git_archives(mastergitdir, cachedir, cachedata)
    archives_by_hash = {}
    archived_files_by_hash = {}
    archived_files_by_name = {}
    for ar in archives:
        _append_archive(archives_by_hash, archived_files_by_hash, archived_files_by_name, ar)
    return archives_by_hash, archived_files_by_hash, archived_files_by_name, cacheoverrides


def _archive_hashing_task_func(param: tuple[str, str, bytes, int, str]) -> tuple[list[Archive]]:
    (by, arpath, arhash, arsize, tmppath) = param
    assert not os.path.isdir(tmppath)
    os.makedirs(tmppath)
    plugin = archive_plugin_for(arpath)
    assert plugin is not None
    archives = []
    _hash_archive(archives, by, tmppath, plugin, arpath, arhash, arsize)
    debug('AllMasterGitData: about to remove temporary tree {}'.format(tmppath))
    TmpPath.rm_tmp_tree(tmppath)
    return (archives,)


def _debug_assert_eq_list(saved_loaded: list, sorted_data: list) -> None:
    assert len(saved_loaded) == len(sorted_data)
    for i in range(len(sorted_data)):
        olda: str = as_json(sorted_data[i])
        newa: str = as_json(saved_loaded[i])
        if olda != newa:
            warn(olda)
            warn(newa)
            warn(os.path.commonprefix([olda, newa]))
            assert False


def _save_archives_task_func(param: tuple[str, list[Archive]]) -> None:
    (mastergitdir, archives) = param
    _write_git_archives(mastergitdir, archives)
    if __debug__:
        saved_loaded = _read_git_archives((mastergitdir + _KNOWN_ARCHIVES_FNAME,))
        # warn(str(len(archives)))
        # warn(str(len(saved_loaded)))
        sorted_archives = sorted([Archive(ar.archive_hash, ar.archive_size, ar.by,
                                          sorted([fi for fi in ar.files], key=lambda f: f.intra_path))
                                  for ar in archives], key=lambda a: a.archive_hash)
        _debug_assert_eq_list(saved_loaded, sorted_archives)


def _load_file_origins_task_func(param: tuple[str, str, dict[str, any]]) -> tuple[
    dict[bytes, list[FileOrigin]], dict[str, any]]:
    (mastergitdir, cachedir, cachedata) = param
    (forigins, cacheoverrides) = _read_cached_file_origins(mastergitdir, cachedir, cachedata)
    return forigins, cacheoverrides


def _save_file_origins_task_func(param: tuple[str, dict[bytes, list[FileOrigin]]]) -> None:
    (mastergitdir, forigins) = param
    # warn(repr(forigins))
    _write_git_file_origins(mastergitdir, forigins)
    if __debug__:
        saved_loaded = list(_read_git_file_origins((mastergitdir + _KNOWN_FILE_ORIGINS_FNAME,)).items())
        # warn(str(len(forigins)))
        # warn(str(len(saved_loaded)))
        sorted_forigins: list[tuple[bytes, list[FileOrigin]]] = sorted(forigins.items())
        for i in range(len(sorted_forigins)):
            fox = sorted_forigins[i]
            sorted_forigins[i] = (fox[0], sorted(fox[1], key=lambda fo2: fo2.tentative_name))
        _debug_assert_eq_list(saved_loaded, sorted_forigins)


### AllMasterGitData itself

class AllMasterGitData:
    _master_git_dir: str
    _cache_dir: str
    _tmp_dir: str
    _cache_data: dict[str, any]
    _archives_by_hash: dict[bytes, Archive] | None
    _archived_files_by_hash: dict[bytes, list[tuple[Archive, FileInArchive]]] | None
    _archived_files_by_name: dict[str, list[tuple[Archive, FileInArchive]]] | None
    _file_origins_by_hash: dict[bytes, list[FileOrigin]] | None
    _nhashes_requested: int  # number of hashes already requested; used to make name of tmp dir
    _new_hashes_by: str
    _dirty_ar: bool
    _dirty_fo: bool
    _ar_is_ready: int  # 0 - not ready, 1 - partially ready, 2 - fully ready
    _fo_is_ready: bool

    _LOADAROWNTASKNAME = 'sanguine.mastergit.ownloadar'
    _LOADFOOWNTASKNAME = 'sanguine.mastergit.ownloadfo'

    def __init__(self, new_hashes_by: str, mastergitdir: str, cachedir: str, tmpdir: str,
                 cache_data: dict[str, any]) -> None:
        self._new_hashes_by = new_hashes_by
        self._master_git_dir = mastergitdir
        self._cache_dir = cachedir
        self._tmp_dir = tmpdir
        self._cache_data = cache_data
        self._archives_by_hash = None
        self._archived_files_by_hash = None
        self._archived_files_by_name = None
        self._file_origins_by_hash = None
        self._nhashes_requested = 0
        self._dirty_ar = False
        self._dirty_fo = False
        self._ar_is_ready = 0
        self._fo_is_ready = False

    def _load_archives_own_task_func(self, out: tuple[dict, dict, dict, dict[str, any]]) -> None:
        (archives_by_hash, archived_files_by_hash, archived_files_by_name, cacheoverrides) = out
        assert self._archives_by_hash is None
        assert self._archived_files_by_hash is None
        self._archives_by_hash = archives_by_hash
        self._archived_files_by_hash = archived_files_by_hash
        self._archived_files_by_name = archived_files_by_name
        self._cache_data |= cacheoverrides
        assert self._ar_is_ready == 0
        self._ar_is_ready = 1

    def _archive_hashing_own_task_func(self, out: tuple[list[Archive]]):
        (archives,) = out
        for ar in archives:
            _append_archive(self._archives_by_hash, self._archived_files_by_hash, self._archived_files_by_name, ar)
        self._dirty_ar = True

    def _done_hashing_own_task_func(self, parallel: tasks.Parallel) -> None:
        if self._dirty_ar:
            savetaskname = 'sanguine.mastergit.savear'
            savetask = tasks.Task(savetaskname, _save_archives_task_func,
                                  (self._master_git_dir, list(self._archives_by_hash.values())), [])
            parallel.add_task(savetask)
        self._ar_is_ready = 2

    def _load_file_origins_own_task_func(self, out: tuple[dict[bytes, list[FileOrigin]], dict[str, any]]) -> None:
        (forigins, cacheoverrides) = out
        assert self._file_origins_by_hash is None
        self._file_origins_by_hash = forigins
        self._cache_data |= cacheoverrides

    def start_tasks(self, parallel: tasks.Parallel) -> None:
        loadtaskname = 'sanguine.mastergit.loadar'
        loadtask = tasks.Task(loadtaskname, _load_archives_task_func,
                              (self._master_git_dir, self._cache_dir, self._cache_data), [])
        parallel.add_task(loadtask)
        loadowntaskname = AllMasterGitData._LOADAROWNTASKNAME
        loadowntask = tasks.OwnTask(loadowntaskname,
                                    lambda _, out: self._load_archives_own_task_func(out), None,
                                    [loadtaskname])
        parallel.add_task(loadowntask)

        load2taskname = 'sanguine.mastergit.loadfo'
        load2task = tasks.Task(load2taskname, _load_file_origins_task_func,
                               (self._master_git_dir, self._cache_dir, self._cache_data), [])
        parallel.add_task(load2task)
        load2owntaskname = AllMasterGitData._LOADFOOWNTASKNAME
        load2owntask = tasks.OwnTask(load2owntaskname,
                                     lambda _, out: self._load_file_origins_own_task_func(out), None,
                                     [load2taskname])
        parallel.add_task(load2owntask)

    @staticmethod
    def ready_to_start_hashing_task_name() -> str:
        return AllMasterGitData._LOADAROWNTASKNAME

    @staticmethod
    def ready_to_start_adding_file_origins_task_name() -> str:
        return AllMasterGitData._LOADFOOWNTASKNAME

    def start_hashing_archive(self, parallel: tasks.Parallel, arpath: str, arhash: bytes, arsize: int) -> None:
        hashingtaskname = 'sanguine.mastergit.hash.' + arpath
        self._nhashes_requested += 1
        tmp_dir = TmpPath.tmp_in_tmp(self._tmp_dir, 'ah.', self._nhashes_requested)
        hashingtask = tasks.Task(hashingtaskname, _archive_hashing_task_func,
                                 (self._new_hashes_by, arpath, arhash, arsize, tmp_dir), [])
        parallel.add_task(hashingtask)
        hashingowntaskname = 'sanguine.mastergit.ownhash.' + arpath
        hashingowntask = tasks.OwnTask(hashingowntaskname,
                                       lambda _, out: self._archive_hashing_own_task_func(out), None,
                                       [hashingtaskname])
        parallel.add_task(hashingowntask)

    def add_file_origin(self, h: bytes, fo: FileOrigin) -> None:
        if h in self._file_origins_by_hash:
            for oldfo in self._file_origins_by_hash[h]:
                if fo.eq(oldfo):
                    return

            self._file_origins_by_hash[h].append(fo)
            self._dirty_fo = True
        else:
            self._file_origins_by_hash[h] = [fo]
            self._dirty_fo = True

    def start_done_hashing_task(self,  # should be called only after all start_hashing_archive() calls are done
                                parallel: tasks.Parallel) -> str:
        donehashingowntaskname = 'sanguine.mastergit.donehashing'
        donehashingowntask = tasks.OwnTask(donehashingowntaskname,
                                           lambda _, _1: self._done_hashing_own_task_func(parallel), None,
                                           [AllMasterGitData._LOADAROWNTASKNAME, 'sanguine.mastergit.hashown.*'])
        parallel.add_task(donehashingowntask)

        return donehashingowntaskname

    def start_done_adding_file_origins_task(self,  # should be called only after all add_file_origin() calls are done
                                            parallel: tasks.Parallel) -> None:
        if self._dirty_fo:
            save2taskname = 'sanguine.mastergit.savefo'
            save2task = tasks.Task(save2taskname, _save_file_origins_task_func,
                                   (self._master_git_dir, self._file_origins_by_hash), [])
            parallel.add_task(save2task)

        self._fo_is_ready = True

    def archived_file_by_hash(self, h: bytes) -> list[tuple[Archive, FileInArchive]] | None:
        assert self._ar_is_ready == 2
        return self._archived_files_by_hash.get(h)

    def archive_by_hash(self, arh: bytes, partialok: bool = False) -> Archive | None:
        assert (self._ar_is_ready >= 1) if partialok else (self._ar_is_ready >= 2)
        return self._archives_by_hash.get(arh)

    def stats_of_interest(self) -> list[str]:
        return ['sanguine.mastergit.savear', 'sanguine.mastergit.loadar',
                'sanguine.mastergit.loadfo', 'sanguine.mastergit.savefo',
                'sanguine.mastergit.ownloadar', 'sanguine.mastergit.ownloadfo',
                'sanguine.mastergit.hash.', 'sanguine.mastergit.ownhash.'
                                            'sanguine.mastergit.donehashing',
                'sanguine.mastergit.']
