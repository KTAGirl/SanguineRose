import sanguine.pluginhandler as pluginhandler
import sanguine.tasks as tasks
from sanguine.files import calculate_file_hash, truncate_file_hash
from sanguine.foldercache import FolderCache
from sanguine.folders import Folders
from sanguine.gitdatafile import *
from sanguine.meta import file_origin, GameUniverse, FileOrigin, NexusFileOrigin
from sanguine.pickledcache import pickled_cache


class FileInArchive:
    file_hash: bytes
    intra_path: str
    file_size: int

    def __init__(self, file_hash: bytes, file_size: int, intra_path: str) -> None:
        self.file_hash = file_hash
        self.file_size = file_size
        self.intra_path = intra_path


class Archive:
    archive_hash: bytes
    archive_size: int
    files: list[FileInArchive]
    by: str

    def __init__(self, archive_hash: bytes, archive_size: int, by: str,
                 files: list[FileInArchive] | None = None) -> None:
        self.archive_hash = archive_hash
        self.archive_size = archive_size
        self.files = files if files is not None else []
        self.by = by


### GitArchivesJson

class GitArchivesHandler(GitDataHandler):
    archives: list[Archive]

    def __init__(self, archives: list[Archive]) -> None:
        super().__init__()
        self.archives = archives

    def decompress(self, param: tuple[str, bytes, int, bytes, int, str]) -> None:
        # warn(repr(param))
        # time.sleep(1)
        (i, a, x, h, s, b) = param
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
        GitDataParam('i', GitDataType.Path, False),  # intra_path
        GitDataParam('a', GitDataType.Hash),  # archive_hash
        GitDataParam('x', GitDataType.Int),  # archive_size
        GitDataParam('h', GitDataType.Hash, False),  # file_hash (truncated)
        GitDataParam('s', GitDataType.Int),  # file_size
        GitDataParam('b', GitDataType.Str)
    ]

    def __init__(self) -> None:
        pass

    def write(self, wfile: typing.TextIO, archives0: Iterable[Archive]) -> None:
        archives = sorted(archives0, key=lambda a: a.archive_hash)
        # warn(str(len(archives)))
        write_git_file_header(wfile)
        wfile.write(
            '  archives: // Legend: i=intra_archive_path, a=archive_hash, x=archive_size, h=file_hash, s=file_size, b=by\n')

        ahandler = GitDataHandler()
        da = GitDataList(self._COMMON_FIELDS, [ahandler])
        alwriter = GitDataListWriter(da, wfile)
        alwriter.write_begin()
        # warn('archives: ' + str(len(archives)))
        for ar in archives:
            # warn('files: ' + str(len(ar.files)))
            for fi in sorted(ar.files,
                             key=lambda f: f.intra_path):
                alwriter.write_line(ahandler, (
                    fi.intra_path, ar.archive_hash,
                    ar.archive_size, fi.file_hash, fi.file_size, ar.by))
        alwriter.write_end()
        write_git_file_footer(wfile)

    def read_from_file(self, rfile: typing.TextIO) -> list[Archive]:
        archives: list[Archive] = []

        # skipping header
        ln, lineno = skip_git_file_header(rfile)

        # reading archives:  ...
        # info(ln)
        assert re.search(r'^\s*archives\s*:\s*//', ln)

        da = GitDataList(self._COMMON_FIELDS, [GitArchivesHandler(archives)])
        lineno = read_git_file_list(da, rfile, lineno)

        # skipping footer
        skip_git_file_footer(rfile, lineno)

        if __debug__:
            assert len(set([ar.archive_hash for ar in archives])) == len(archives)

        # warn(str(len(archives)))
        return archives


# GitFileOriginsJson

class GitFileOriginsHandler(GitDataHandler):
    file_origins: dict[bytes, FileOrigin]
    COMMON_FIELDS: list[GitDataParam] = [
        GitDataParam('h', GitDataType.Hash, False),
        GitDataParam('n', GitDataType.Str)
    ]

    def __init__(self, file_origins: dict[bytes, FileOrigin]) -> None:
        super().__init__()
        self.file_origins = file_origins


class GitNexusFileOriginsHandler(GitFileOriginsHandler):
    SPECIFIC_FIELDS: list[GitDataParam] = [
        GitDataParam('f', GitDataType.Int, False),
        GitDataParam('m', GitDataType.Int),
    ]

    def decompress(self, param: tuple[bytes, str, int, int]) -> None:
        (h, n, f, m) = param

        assert h not in self.file_origins
        self.file_origins[h] = NexusFileOrigin(n, f, m)


class GitFileOriginsJson:
    def __init__(self) -> None:
        pass

    def write(self, wfile: typing.TextIO, forigins0: dict[bytes, FileOrigin]) -> None:
        forigins: list[tuple[bytes, FileOrigin]] = sorted(forigins0.items())
        write_git_file_header(wfile)
        wfile.write(
            '  file_origins: // Legend: h=hash, n=tentative_name, \n')
        wfile.write(
            '                // [f=nexus_fileid, m=nexus_modid if Nexus]\n')

        nexus_handler = GitDataHandler(GitNexusFileOriginsHandler.SPECIFIC_FIELDS)
        da = GitDataList(GitFileOriginsHandler.COMMON_FIELDS, [nexus_handler])
        writer = GitDataListWriter(da, wfile)
        writer.write_begin()
        for fox in forigins:
            (h, fo) = fox
            if isinstance(fo, NexusFileOrigin):
                writer.write_line(nexus_handler, (h, fo.tentative_name, fo.fileid, fo.modid))
            else:
                assert False
        writer.write_end()
        write_git_file_footer(wfile)

    def read_from_file(self, rfile: typing.TextIO) -> dict[bytes, FileOrigin]:
        file_origins: dict[bytes, FileOrigin] = {}

        # skipping header
        ln, lineno = skip_git_file_header(rfile)

        # reading archives:  ...
        # info(ln)
        assert re.search(r'^\s*file_origins\s*:\s*//', ln)

        da = GitDataList(GitFileOriginsHandler.COMMON_FIELDS, [GitNexusFileOriginsHandler(file_origins)])
        lineno = read_git_file_list(da, rfile, lineno)

        # skipping footer
        skip_git_file_footer(rfile, lineno)

        if __debug__:
            assert len(set([h for h in file_origins])) == len(file_origins)

        # warn(str(len(archives)))
        return file_origins


##### Helpers

def _processing_archive_time_estimate(fsize: int):
    return float(fsize) / 1048576. / 10.  # 10 MByte/s


def _read_git_archives(params: tuple[str]) -> list[Archive]:
    (archivesgitfile,) = params
    assert Folders.is_normalized_file_path(archivesgitfile)
    with open(archivesgitfile, 'rt', encoding='utf-8') as rf:
        archives = GitArchivesJson().read_from_file(rf)
    return archives


def _read_cached_git_archives(mastergitdir: str, cachedir: str,
                              cachedata: dict[str, any]) -> tuple[list[Archive], dict[str, any]]:
    assert Folders.is_normalized_dir_path(mastergitdir)
    mastergitfile = mastergitdir + 'known-archives.json5'
    return pickled_cache(cachedir, cachedata, 'archivesdata', [mastergitfile],
                         _read_git_archives, (mastergitfile,))


def _write_git_archives(mastergitdir: str, archives: list[Archive]) -> None:
    assert Folders.is_normalized_dir_path(mastergitdir)
    fpath = mastergitdir + 'known-archives.json5'
    with open(fpath, 'wt', encoding='utf-8') as wf:
        GitArchivesJson().write(wf, archives)


def _hash_archive(archives: list[Archive], by: str, tmppath: str,  # recursive!
                  plugin: pluginhandler.ArchivePluginBase,
                  archivepath: str, arhash: bytes, arsize: int) -> None:
    assert os.path.isdir(tmppath)
    plugin.extract_all(archivepath, tmppath)
    pluginexts = pluginhandler.all_archive_plugins_extensions()  # for nested archives
    ar = Archive(arhash, arsize, by)
    archives.append(ar)
    for root, dirs, files in os.walk(tmppath):
        nf = 0
        for f in files:
            nf += 1
            fpath = os.path.join(root, f)
            # if not os.path.isfile(fpath):
            #    critical('_hash_archive(): not path.isfile({})'.format(fpath))
            #    abort_if_not(False)
            # print(fpath)
            s, h = calculate_file_hash(fpath)
            assert fpath.startswith(tmppath)
            ar.files.append(
                FileInArchive(truncate_file_hash(h), s, Folders.normalize_archive_intra_path(fpath[len(tmppath):])))

            ext = os.path.split(fpath)[1].lower()
            if ext in pluginexts:
                nested_plugin = pluginhandler.archive_plugin_for(fpath)
                assert nested_plugin is not None
                newtmppath = TmpPath.tmp_in_tmp(tmppath,
                                                'T3lIzNDx.',  # tmp is not from root,
                                                # so randomly-looking prefix is necessary
                                                nf)
                assert not os.path.isdir(newtmppath)
                os.makedirs(newtmppath)
                _hash_archive(archives, by, newtmppath, nested_plugin, fpath, h, s)


##### Tasks

def _load_archives_task_func(param: tuple[str, str, dict[str, any]]) -> tuple[list[Archive], dict[str, any]]:
    (mastergitdir, cachedir, cachedata) = param
    (archives, cacheoverrides) = _read_cached_git_archives(mastergitdir, cachedir, cachedata)
    return archives, cacheoverrides


def _archive_hashing_task_func(param: tuple[str, str, bytes, int, str]) -> tuple[list[Archive]]:
    (by, arpath, arhash, arsize, tmppath) = param
    assert not os.path.isdir(tmppath)
    os.makedirs(tmppath)
    plugin = pluginhandler.archive_plugin_for(arpath)
    assert plugin is not None
    archives = []
    _hash_archive(archives, by, tmppath, plugin, arpath, arhash, arsize)
    debug('MGA: about to remove temporary tree {}'.format(tmppath))
    TmpPath.rm_tmp_tree(tmppath)
    return (archives,)


def _save_archives_task_func(param: tuple[str, list[Archive]]) -> None:
    (mastergitdir, archives) = param
    _write_git_archives(mastergitdir, archives)
    if __debug__:
        saved_loaded = _read_git_archives((mastergitdir + 'known-archives.json5',))
        # warn(str(len(archives)))
        # warn(str(len(saved_loaded)))
        sorted_archives = sorted([Archive(ar.archive_hash, ar.archive_size, ar.by,
                                          sorted([fi for fi in ar.files], key=lambda f: f.intra_path))
                                  for ar in archives], key=lambda a: a.archive_hash)
        assert len(saved_loaded) == len(archives)
        for i in range(len(archives)):
            olda = JsonEncoder().encode(sorted_archives[i])
            newa = JsonEncoder().encode(saved_loaded[i])
            if olda != newa:
                warn(olda)
                warn(newa)
                assert False


class MasterGitArchives:
    master_git_dir: str
    cache_dir: str
    tmp_dir: str
    cache_data: dict[str, any]
    archives_by_hash: dict[bytes, Archive] | None
    archived_files_by_hash: dict[bytes, list[tuple[Archive, FileInArchive]]] | None
    nhashes: int  # number of hashes already requested; used to make name of tmp dir
    by: str
    dirty: bool

    _LOADOWNTASKNAME = 'sanguine.available.mga.loadown'

    def __init__(self, by: str, mastergitdir: str, cachedir: str, tmpdir: str, cache_data: dict[str, any]) -> None:
        self.by = by
        self.master_git_dir = mastergitdir
        self.cache_dir = cachedir
        self.tmp_dir = tmpdir
        self.cache_data = cache_data
        self.archives_by_hash = None
        self.archived_files_by_hash = None
        self.nhashes = 0
        self.dirty = False

    def _append_archive(self, ar: Archive) -> None:
        # warn(str(len(ar.files)))
        assert ar.archive_hash not in self.archives_by_hash
        self.archives_by_hash[ar.archive_hash] = ar
        for fi in ar.files:
            if fi.file_hash not in self.archived_files_by_hash:
                self.archived_files_by_hash[fi.file_hash] = []
            self.archived_files_by_hash[fi.file_hash].append((ar, fi))

    def _load_archives_own_task_func(self, out: tuple[list[Archive], dict[str, any]]) -> None:
        (archives, cacheoverrides) = out
        assert self.archives_by_hash is None
        assert self.archived_files_by_hash is None
        self.archives_by_hash = {}
        self.archived_files_by_hash = {}
        for ar in archives:
            self._append_archive(ar)
        self.cache_data |= cacheoverrides

    def _archive_hashing_own_task_func(self, out: tuple[list[Archive]]):
        (archives,) = out
        for ar in archives:
            self._append_archive(ar)
        self.dirty = True

    def _done_hashing_own_task_func(self, parallel: tasks.Parallel) -> None:
        if self.dirty:
            savetaskname = 'sanguine.available.mga.save'
            savetask = tasks.Task(savetaskname, _save_archives_task_func,
                                  (self.master_git_dir, list(self.archives_by_hash.values())), [])
            parallel.add_task(savetask)

    def start_tasks(self, parallel: tasks.Parallel) -> None:
        loadtaskname = 'sanguine.available.mga.load'
        loadtask = tasks.Task(loadtaskname, _load_archives_task_func,
                              (self.master_git_dir, self.cache_dir, self.cache_data), [])
        parallel.add_task(loadtask)
        loadowntaskname = MasterGitArchives._LOADOWNTASKNAME
        loadowntask = tasks.OwnTask(loadowntaskname,
                                    lambda _, out: self._load_archives_own_task_func(out), None,
                                    [loadtaskname])
        parallel.add_task(loadowntask)

    @staticmethod
    def ready_to_start_hashing_task_name() -> str:
        return MasterGitArchives._LOADOWNTASKNAME

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

    def start_done_hashing_task(self,  # should be called only after all start_hashing_archive() calls are done
                                parallel: tasks.Parallel) -> str:
        donehashingowntaskname = 'sanguine.available.mga.donehashing'
        donehashingowntask = tasks.OwnTask(donehashingowntaskname,
                                           lambda _: self._done_hashing_own_task_func(parallel), None,
                                           ['sanguine.available.mga.hashown.*'])
        parallel.add_task(donehashingowntask)

        return donehashingowntaskname


class AvailableFiles:
    foldercache: FolderCache
    gitarchives: MasterGitArchives
    origins: dict[bytes, FileOrigin]
    _DONEHASHINGTASKNAME = 'sanguine.available.donehashing'  # does not apply to MGA!

    def __init__(self, by: str, cachedir: str, tmpdir: str, mastergitdir: str, downloads: list[str]) -> None:
        self.foldercache = FolderCache(cachedir, 'downloads', [(d, []) for d in downloads])
        self.gitarchives = MasterGitArchives(by, mastergitdir, cachedir, tmpdir, {})
        self.origins = {}

    def _start_hashing_own_task_func(self, parallel: tasks.Parallel) -> None:
        for ar in self.foldercache.all_files():
            ext = os.path.splitext(ar.file_path)[1]
            if ext == '.meta':
                continue

            origin = file_origin(GameUniverse.Skyrim, ar.file_path)
            if origin is None:
                warn('Available: file without known origin {}'.format(ar.file_path))
            elif origin not in self.origins:
                self.origins[ar.file_hash] = origin
            else:
                assert JsonEncoder().encode(self.origins[ar.file_hash]) == JsonEncoder().encode(origin)

            if not ar.file_hash in self.gitarchives.archives_by_hash:
                if ext in pluginhandler.all_archive_plugins_extensions():
                    self.gitarchives.start_hashing_archive(parallel, ar.file_path, ar.file_hash, ar.file_size)
                else:
                    warn('Available: file with unknown extension {}, ignored'.format(ar.file_path))

        gitarchivesdonehashingtaskname: str = self.gitarchives.start_done_hashing_task(parallel)
        donehashingowntaskname = AvailableFiles._DONEHASHINGTASKNAME
        donehashingowntask = tasks.OwnTask(donehashingowntaskname,
                                           lambda _, _1: AvailableFiles._sync_only_own_task_func(), None,
                                           [gitarchivesdonehashingtaskname])
        parallel.add_task(donehashingowntask)

    @staticmethod
    def _sync_only_own_task_func() -> None:
        pass  # do nothing, this task is necessary only as means to synchronize

    def start_tasks(self, parallel: tasks.Parallel):
        self.foldercache.start_tasks(parallel)
        self.gitarchives.start_tasks(parallel)

        starthashingowntaskname = 'sanguine.available.starthashing'
        starthashingowntask = tasks.OwnTask(starthashingowntaskname,
                                            lambda _, _1, _2: self._start_hashing_own_task_func(parallel), None,
                                            [self.foldercache.ready_task_name(),
                                             MasterGitArchives.ready_to_start_hashing_task_name()])
        parallel.add_task(starthashingowntask)

    @staticmethod
    def ready_task_name() -> str:
        return AvailableFiles._DONEHASHINGTASKNAME


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        from sanguine.sanguine_install_helpers import check_sanguine_prerequisites

        ttmppath = Folders.normalize_dir_path('..\\..\\mo2git.tmp\\')
        add_file_logging(ttmppath + 'sanguine.log.html')

        check_sanguine_prerequisites()

        with TmpPath(ttmppath) as ttmpdir:
            tavailable = AvailableFiles('KTAGirl',
                                        Folders.normalize_dir_path('..\\..\\mo2git.cache\\'),
                                        ttmpdir.tmp_dir(),
                                        Folders.normalize_dir_path('..\\..\\sanguine-skyrim-root\\'),
                                        [Folders.normalize_dir_path('..\\..\\..\\mo2\\downloads')])
            with tasks.Parallel(None) as tparallel:
                tavailable.start_tasks(tparallel)
                tparallel.run([])  # all necessary tasks were already added in acache.start_tasks()

            print(JsonEncoder().encode(tavailable.origins))
