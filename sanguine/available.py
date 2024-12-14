import os.path
import re

import sanguine.archives
import sanguine.git_data_file as gitdatafile
import sanguine.tasks as tasks
from sanguine.archives import Archive, FileInArchive
from sanguine.common import *
from sanguine.file_origin import file_origins_for_file, FileOrigin, GitFileOriginsJson
from sanguine.file_retriever import FileRetriever, FileRetrieverFromSingleArchive, FileRetrieverFromNestedArchives
from sanguine.folder_cache import FolderCache, FolderToCache, calculate_file_hash, truncate_file_hash
from sanguine.git_data_file import GitDataParam, GitDataType, GitDataHandler
from sanguine.pickled_cache import pickled_cache
from sanguine.tmp_path import TmpPath


### GitArchivesJson

class GitArchivesReadHandler(GitDataHandler):
    archives: list[Archive]

    def __init__(self, archives: list[Archive]) -> None:
        super().__init__()
        self.archives = archives

    def decompress(self, common_param: tuple[bytes, str, bytes, int, int, str], specific_param: tuple) -> None:
        assert len(specific_param) == 0
        # warn(repr(param))
        # time.sleep(1)
        (h, i, a, x, s, b) = common_param
        found = None
        if len(self.archives) > 0:
            ar = self.archives[-1]
            if ar.archive_hash == a:
                assert ar.archive_size == x
                found = ar

        if found is None:
            found = Archive(a, x, b)
            self.archives.append(found)

        found.files.append(FileInArchive(h, s, i))


class GitArchivesJson:
    _COMMON_FIELDS: list[GitDataParam] = [
        GitDataParam('h', GitDataType.Hash, False),  # file_hash (truncated)
        GitDataParam('i', GitDataType.Path),  # intra_path
        GitDataParam('a', GitDataType.Hash),  # archive_hash
        GitDataParam('x', GitDataType.Int),  # archive_size
        GitDataParam('s', GitDataType.Int),  # file_size
        GitDataParam('b', GitDataType.Str)
    ]

    def __init__(self) -> None:
        pass

    def write(self, wfile: typing.TextIO, archives0: Iterable[Archive]) -> None:
        archives = sorted(archives0, key=lambda a: a.archive_hash)
        # warn(str(len(archives)))
        gitdatafile.write_git_file_header(wfile)
        wfile.write(
            '  archives: // Legend: i=intra_archive_path, a=archive_hash, x=archive_size, h=file_hash, s=file_size, b=by\n')

        ahandler = GitDataHandler()
        da = gitdatafile.GitDataList(self._COMMON_FIELDS, [ahandler])
        alwriter = gitdatafile.GitDataListWriter(da, wfile)
        alwriter.write_begin()
        # warn('archives: ' + str(len(archives)))
        for ar in archives:
            # warn('files: ' + str(len(ar.files)))
            for fi in sorted(ar.files,
                             key=lambda f: f.intra_path):
                alwriter.write_line(ahandler, (
                    fi.file_hash, fi.intra_path, ar.archive_hash,
                    ar.archive_size, fi.file_size, ar.by))
        alwriter.write_end()
        gitdatafile.write_git_file_footer(wfile)

    def read_from_file(self, rfile: typing.TextIO) -> list[Archive]:
        archives: list[Archive] = []

        # skipping header
        ln, lineno = gitdatafile.skip_git_file_header(rfile)

        # reading archives:  ...
        # info(ln)
        assert re.search(r'^\s*archives\s*:\s*//', ln)

        da = gitdatafile.GitDataList(self._COMMON_FIELDS, [GitArchivesReadHandler(archives)])
        lineno = gitdatafile.read_git_file_list(da, rfile, lineno)

        # skipping footer
        gitdatafile.skip_git_file_footer(rfile, lineno)

        if __debug__:
            assert len(set([ar.archive_hash for ar in archives])) == len(archives)

        # warn(str(len(archives)))
        return archives


##### MasterGitData

### MasterGitData Helpers

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
                  plugin: sanguine.archives.ArchivePluginBase,
                  archivepath: str, arhash: bytes, arsize: int) -> None:
    assert os.path.isdir(tmppath)
    plugin.extract_all(archivepath, tmppath)
    pluginexts = sanguine.archives.all_archive_plugins_extensions()  # for nested archives
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
                nested_plugin = sanguine.archives.archive_plugin_for(fpath)
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


### MasterGitData Tasks

def _load_archives_task_func(param: tuple[str, str, dict[str, any]]) -> tuple[list[Archive], dict[str, any]]:
    (mastergitdir, cachedir, cachedata) = param
    (archives, cacheoverrides) = _read_cached_git_archives(mastergitdir, cachedir, cachedata)
    return archives, cacheoverrides


def _archive_hashing_task_func(param: tuple[str, str, bytes, int, str]) -> tuple[list[Archive]]:
    (by, arpath, arhash, arsize, tmppath) = param
    assert not os.path.isdir(tmppath)
    os.makedirs(tmppath)
    plugin = sanguine.archives.archive_plugin_for(arpath)
    assert plugin is not None
    archives = []
    _hash_archive(archives, by, tmppath, plugin, arpath, arhash, arsize)
    debug('MGA: about to remove temporary tree {}'.format(tmppath))
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


### MasterGitData itself

class MasterGitData:
    master_git_dir: str
    cache_dir: str
    tmp_dir: str
    cache_data: dict[str, any]
    archives_by_hash: dict[bytes, Archive] | None
    archived_files_by_hash: dict[bytes, list[tuple[Archive, FileInArchive]]] | None
    archived_files_by_name: dict[str, list[tuple[Archive, FileInArchive]]] | None
    file_origins_by_hash: dict[bytes, list[FileOrigin]] | None
    nhashes: int  # number of hashes already requested; used to make name of tmp dir
    by: str
    dirtyar: bool
    dirtyfo: bool

    _LOADAROWNTASKNAME = 'sanguine.available.mga.loadarown'
    _LOADFOOWNTASKNAME = 'sanguine.available.mga.loadfoown'

    def __init__(self, by: str, mastergitdir: str, cachedir: str, tmpdir: str, cache_data: dict[str, any]) -> None:
        self.by = by
        self.master_git_dir = mastergitdir
        self.cache_dir = cachedir
        self.tmp_dir = tmpdir
        self.cache_data = cache_data
        self.archives_by_hash = None
        self.archived_files_by_hash = None
        self.archived_files_by_name = None
        self.file_origins_by_hash = None
        self.nhashes = 0
        self.dirtyar = False
        self.dirtyfo = False

    def _append_archive(self, ar: Archive) -> None:
        # warn(str(len(ar.files)))
        assert ar.archive_hash not in self.archives_by_hash
        self.archives_by_hash[ar.archive_hash] = ar
        for fi in ar.files:
            if fi.file_hash not in self.archived_files_by_hash:
                self.archived_files_by_hash[fi.file_hash] = []
            self.archived_files_by_hash[fi.file_hash].append((ar, fi))

            fname = os.path.split(fi.intra_path)[1]
            if fname not in self.archived_files_by_name:
                self.archived_files_by_name[fname] = []
            self.archived_files_by_name[fname].append((ar, fi))

    def _load_archives_own_task_func(self, out: tuple[list[Archive], dict[str, any]]) -> None:
        (archives, cacheoverrides) = out
        assert self.archives_by_hash is None
        assert self.archived_files_by_hash is None
        self.archives_by_hash = {}
        self.archived_files_by_hash = {}
        self.archived_files_by_name = {}
        for ar in archives:
            self._append_archive(ar)
        self.cache_data |= cacheoverrides

    def _archive_hashing_own_task_func(self, out: tuple[list[Archive]]):
        (archives,) = out
        for ar in archives:
            self._append_archive(ar)
        self.dirtyar = True

    def _done_hashing_own_task_func(self, parallel: tasks.Parallel) -> None:
        if self.dirtyar:
            savetaskname = 'sanguine.available.mga.savear'
            savetask = tasks.Task(savetaskname, _save_archives_task_func,
                                  (self.master_git_dir, list(self.archives_by_hash.values())), [])
            parallel.add_task(savetask)

    def _load_file_origins_own_task_func(self, out: tuple[dict[bytes, list[FileOrigin]], dict[str, any]]) -> None:
        (forigins, cacheoverrides) = out
        assert self.file_origins_by_hash is None
        self.file_origins_by_hash = forigins
        self.cache_data |= cacheoverrides

    def start_tasks(self, parallel: tasks.Parallel) -> None:
        loadtaskname = 'sanguine.available.mga.loadar'
        loadtask = tasks.Task(loadtaskname, _load_archives_task_func,
                              (self.master_git_dir, self.cache_dir, self.cache_data), [])
        parallel.add_task(loadtask)
        loadowntaskname = MasterGitData._LOADAROWNTASKNAME
        loadowntask = tasks.OwnTask(loadowntaskname,
                                    lambda _, out: self._load_archives_own_task_func(out), None,
                                    [loadtaskname])
        parallel.add_task(loadowntask)

        load2taskname = 'sanguine.available.mga.loadfo'
        load2task = tasks.Task(load2taskname, _load_file_origins_task_func,
                               (self.master_git_dir, self.cache_dir, self.cache_data), [])
        parallel.add_task(load2task)
        load2owntaskname = MasterGitData._LOADFOOWNTASKNAME
        load2owntask = tasks.OwnTask(load2owntaskname,
                                     lambda _, out: self._load_file_origins_own_task_func(out), None,
                                     [load2taskname])
        parallel.add_task(load2owntask)

    @staticmethod
    def ready_to_start_hashing_task_name() -> str:
        return MasterGitData._LOADAROWNTASKNAME

    @staticmethod
    def ready_to_start_adding_file_origins_task_name() -> str:
        return MasterGitData._LOADFOOWNTASKNAME

    def start_hashing_archive(self, parallel: tasks.Parallel, arpath: str, arhash: bytes, arsize: int) -> None:
        hashingtaskname = 'sanguine.available.mga.hash.' + arpath
        self.nhashes += 1
        tmp_dir = TmpPath.tmp_in_tmp(self.tmp_dir, 'ah.', self.nhashes)
        hashingtask = tasks.Task(hashingtaskname, _archive_hashing_task_func,
                                 (self.by, arpath, arhash, arsize, tmp_dir), [])
        parallel.add_task(hashingtask)
        hashingowntaskname = 'sanguine.available.mga.hashown.' + arpath
        hashingowntask = tasks.OwnTask(hashingowntaskname,
                                       lambda _, out: self._archive_hashing_own_task_func(out), None,
                                       [hashingtaskname])
        parallel.add_task(hashingowntask)

    def add_file_origin(self, h: bytes, fo: FileOrigin) -> None:
        if h in self.file_origins_by_hash:
            for oldfo in self.file_origins_by_hash[h]:
                if fo.eq(oldfo):
                    return

            self.file_origins_by_hash[h].append(fo)
            self.dirtyfo = True
        else:
            self.file_origins_by_hash[h] = [fo]
            self.dirtyfo = True

    def start_done_hashing_task(self,  # should be called only after all start_hashing_archive() calls are done
                                parallel: tasks.Parallel) -> str:
        donehashingowntaskname = 'sanguine.available.mga.donehashing'
        donehashingowntask = tasks.OwnTask(donehashingowntaskname,
                                           lambda _, _1: self._done_hashing_own_task_func(parallel), None,
                                           [MasterGitData._LOADAROWNTASKNAME, 'sanguine.available.mga.hashown.*'])
        parallel.add_task(donehashingowntask)

        return donehashingowntaskname

    def start_done_adding_file_origins_task(self,  # should be called only after all add_file_origin() calls are done
                                            parallel: tasks.Parallel) -> None:
        if self.dirtyfo:
            save2taskname = 'sanguine.available.mga.savefo'
            save2task = tasks.Task(save2taskname, _save_file_origins_task_func,
                                   (self.master_git_dir, self.file_origins_by_hash), [])
            parallel.add_task(save2task)


##### AvailableFiles

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


class AvailableFiles:
    _downloads_cache: FolderCache
    _git_data: MasterGitData
    _READYOWNTASKNAME = 'sanguine.available.readyown'

    def __init__(self, by: str, cachedir: str, tmpdir: str, mastergitdir: str, downloads: list[str]) -> None:
        self._downloads_cache = FolderCache(cachedir, 'downloads', [FolderToCache(d, []) for d in downloads])
        self._git_data = MasterGitData(by, mastergitdir, cachedir, tmpdir, {})

    # public interface

    def start_tasks(self, parallel: tasks.Parallel):
        self._downloads_cache.start_tasks(parallel)
        self._git_data.start_tasks(parallel)

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

    def _single_archive_retrievers(self, h: bytes) -> list[FileRetrieverFromSingleArchive]:
        found = self._git_data.archived_files_by_hash.get(h)
        if found is None:
            return []
        assert len(found) > 0
        return [FileRetrieverFromSingleArchive(self, (h, fi.file_size), ar.archive_hash, fi) for ar, fi in found]

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

    def _archived_file_retrievers_by_name(self, fname: str) -> list[
        FileRetriever]:  # not resolving archive_retrievers
        found = self._git_data.archived_files_by_name.get(fname)
        if not found:
            return []
        assert len(found) > 0
        singles = [FileRetrieverFromSingleArchive(self, (fi.file_hash, fi.file_size), ar.archive_hash, fi) for ar, fi in
                   found]
        out = []
        self._add_nested_to_retrievers(out, singles)
        assert len(out) > 0
        return out

    def file_retrievers_by_hash(self, h: bytes) -> list[FileRetriever]:
        # TODO: add retrievers from ownmods
        return self._archived_file_retrievers_by_hash(h)

    def file_retrievers_by_name(self, fname: str) -> list[FileRetriever]:
        # TODO: add retrievers from ownmods
        return self._archived_file_retrievers_by_name(fname)

    # private functions

    def _start_hashing_own_task_func(self, parallel: tasks.Parallel) -> None:
        for ar in self._downloads_cache.all_files():
            ext = os.path.splitext(ar.file_path)[1]
            if ext == '.meta':
                continue

            if not ar.file_hash in self._git_data.archives_by_hash:
                if ext in sanguine.archives.all_archive_plugins_extensions():
                    self._git_data.start_hashing_archive(parallel, ar.file_path, ar.file_hash, ar.file_size)
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
                self._git_data.add_file_origin(fox[0], fo)
        self._git_data.start_done_adding_file_origins_task(parallel)  # no need to wait for it

        gitarchivesdonehashingtaskname: str = self._git_data.start_done_hashing_task(parallel)
        readyowntaskname = AvailableFiles._READYOWNTASKNAME
        readyowntask = tasks.OwnTask(readyowntaskname,
                                     lambda _, _1: AvailableFiles._sync_only_own_task_func(), None,
                                     [gitarchivesdonehashingtaskname])
        parallel.add_task(readyowntask)

    @staticmethod
    def _sync_only_own_task_func() -> None:
        pass  # do nothing, this task is necessary only as means to synchronize


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
                                        [normalize_dir_path('..\\..\\..\\mo2\\downloads')])
            with tasks.Parallel(None, dbg_serialize=False) as tparallel:
                tavailable.start_tasks(tparallel)
                tparallel.run([])  # all necessary tasks were already added in acache.start_tasks()
