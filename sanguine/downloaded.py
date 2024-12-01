import shutil

import sanguine.pluginhandler as pluginhandler
import sanguine.tasks as tasks
from sanguine.files import calculate_file_hash, truncate_file_hash
from sanguine.foldercache import FolderCache
from sanguine.folders import Folders
from sanguine.gitdatafile import *
from sanguine.pickledcache import pickled_cache


class FileInArchive:
    file_hash: bytes
    intra_path: list[str]
    file_size: int

    def __init__(self, file_hash: bytes, file_size: int, intra_path: list[str]) -> None:
        self.file_hash = file_hash
        self.file_size = file_size
        self.intra_path = intra_path


class Archive:
    archive_hash: bytes
    archive_size: int
    files: list[FileInArchive]

    def __init__(self, archive_hash: bytes, archive_size: int, files: list[FileInArchive]) -> None:
        self.archive_hash = archive_hash
        self.archive_size = archive_size
        self.files = sorted(files, key=lambda f: f.intra_path[0] + (f.intra_path[1] if len(f.intra_path) > 1 else ''))


### GitArchivesJson

class GitArchivesHandler(GitDataHandler):
    archives: list[Archive]
    optional: list[GitDataParam] = []

    def __init__(self, archives: list[Archive]) -> None:
        super().__init__(self.optional)
        self.archives = archives

    def decompress(self, param: tuple[str, str, bytes, int, bytes, int]) -> None:
        (i, i2, a, x, h, s) = param
        found = None
        if len(self.archives) > 0:
            ar = self.archives[-1]
            if ar.archive_hash == a:
                assert ar.archive_size == x
                found = ar

        if found is None:
            found = Archive(a, x, [])

        found.files.append(FileInArchive(h, s, [i] if i2 is None else [i, i2]))


class GitArchivesJson:
    _aentry_mandatory: list[GitDataParam] = [
        GitDataParam('i', GitDataType.Path, False),  # intra_path[0]
        GitDataParam('j', GitDataType.Path),  # intra_path[1]
        GitDataParam('a', GitDataType.Hash),  # archive_hash
        GitDataParam('x', GitDataType.Int),  # archive_size
        GitDataParam('h', GitDataType.Hash, False),  # file_hash (truncated)
        GitDataParam('s', GitDataType.Int)  # file_size
    ]

    def __init__(self) -> None:
        pass

    def write(self, wfile: typing.TextIO, archives0: Iterable[Archive]) -> None:
        archives = sorted(archives0, key=lambda a: a.archive_hash)
        # warn(str(len(archives)))
        write_git_file_header(wfile)
        wfile.write(
            '  archives: // Legend: i=intra_archive_path, j=intra_archive_path2, a=archive_hash, x=archive_size, h=file_hash, s=file_size\n')

        ahandler = GitDataHandler(GitArchivesHandler.optional)
        da = GitDataList(self._aentry_mandatory, [ahandler])
        alwriter = GitDataListWriter(da, wfile)
        alwriter.write_begin()
        # warn('archives: ' + str(len(archives)))
        for ar in archives:
            # warn('files: ' + str(len(ar.files)))
            for fi in sorted(ar.files,
                             key=lambda f: f.intra_path[0] + (f.intra_path[1] if len(f.intra_path) > 1 else '')):
                alwriter.write_line(ahandler, (
                    fi.intra_path[0], fi.intra_path[1] if len(fi.intra_path) > 1 else None, ar.archive_hash,
                    ar.archive_size, truncate_file_hash(fi.file_hash), fi.file_size))
        alwriter.write_end()
        write_git_file_footer(wfile)

    def read_from_file(self, rfile: typing.TextIO) -> list[Archive]:
        archives: list[Archive] = []

        # skipping header
        ln, lineno = skip_git_file_header(rfile)

        # reading archives:  ...
        # info(ln)
        assert re.search(r'^\s*archives\s*:\s*//', ln)

        da = GitDataList(self._aentry_mandatory, [GitArchivesHandler(archives)])
        lineno = read_git_file_list(da, rfile, lineno)

        # skipping footer
        skip_git_file_footer(rfile, lineno)

        if __debug__:
            assert len(set([ar.archive_hash for ar in archives])) == len(archives)

        return archives


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
    mastergitfile = mastergitdir + 'known-archives.json'
    return pickled_cache(cachedir, cachedata, 'archivesdata', [mastergitfile],
                         _read_git_archives, (mastergitfile,))


def _write_git_archives(mastergitdir: str, archives: list[Archive]) -> None:
    assert Folders.is_normalized_dir_path(mastergitdir)
    fpath = mastergitdir + 'known-archives.json'
    with open(fpath, 'wt', encoding='utf-8') as wf:
        GitArchivesJson().write(wf, archives)


def _hash_archive(archive: Archive, tmppath: str, curintrapath: list[str],
                  plugin: pluginhandler.ArchivePluginBase, archivepath: str) -> None:  # recursive!
    assert os.path.isdir(tmppath)
    plugin.extract_all(archivepath, tmppath)
    pluginexts = pluginhandler.all_archive_plugins_extensions()  # for nested archives
    for root, dirs, files in os.walk(tmppath):
        nf = 0
        for f in files:
            nf += 1
            fpath = os.path.join(root, f)
            assert os.path.isfile(fpath)
            # print(fpath)
            s, h = calculate_file_hash(fpath)
            assert fpath.startswith(tmppath)
            newintrapath = curintrapath.copy()
            newintrapath.append(Folders.normalize_archive_intra_path(fpath[len(tmppath):]))
            archive.files.append(FileInArchive(h, s, newintrapath))

            ext = os.path.split(fpath)[1].lower()
            if ext in pluginexts:
                nested_plugin = pluginhandler.archive_plugin_for(fpath)
                assert nested_plugin is not None
                newtmppath = tmppath + str(nf) + '\\'
                assert not os.path.isdir(newtmppath)
                os.makedirs(newtmppath)
                _hash_archive(archive, newtmppath, newintrapath, nested_plugin, fpath)


##### Tasks

def _load_archives_task_func(param: tuple[str, str, dict[str, any]]) -> tuple[list[Archive], dict[str, any]]:
    (mastergitdir, cachedir, cachedata) = param
    (archives, cacheoverrides) = _read_cached_git_archives(mastergitdir, cachedir, cachedata)
    return archives, cacheoverrides


def _append_archive(mga: "MasterGitArchives", ar: Archive) -> None:
    # warn(str(len(ar.files)))
    assert ar.archive_hash not in mga.archives_by_hash
    mga.archives_by_hash[ar.archive_hash] = ar
    for fi in ar.files:
        if fi.file_hash not in mga.archived_files_by_hash:
            mga.archived_files_by_hash[fi.file_hash] = []
        mga.archived_files_by_hash[fi.file_hash].append((ar, fi))


def _load_archives_own_task_func(out: tuple[list[Archive], dict[str, any]], mga: "MasterGitArchives") -> None:
    (archives, cacheoverrides) = out
    assert mga.archives_by_hash is None
    assert mga.archived_files_by_hash is None
    mga.archives_by_hash = {}
    mga.archived_files_by_hash = {}
    for ar in archives:
        _append_archive(mga, ar)
    mga.cache_data |= cacheoverrides


def _archive_hashing_task_func(param: tuple[str, bytes, int, str]) -> tuple[Archive]:
    (arpath, arhash, arsize, tmppath) = param
    assert not os.path.isdir(tmppath)
    os.makedirs(tmppath)
    plugin = pluginhandler.archive_plugin_for(arpath)
    assert plugin is not None
    archive = Archive(arhash, arsize, [])
    _hash_archive(archive, tmppath, [], plugin, arpath)
    debug('MGA: about to remove temporary tree {}'.format(tmppath))
    shutil.rmtree(tmppath)
    return (archive,)


def _archive_hashing_own_task_func(out: tuple[Archive], mga: "MasterGitArchives"):
    (archive,) = out
    _append_archive(mga, archive)


def _save_archives_task_func(param: tuple[str, list[Archive]]) -> None:
    (mastergitdir, archives) = param
    _write_git_archives(mastergitdir, archives)


def _done_hashing_own_task_func(mga: "MasterGitArchives", parallel: tasks.Parallel) -> None:
    savetaskname = 'sanguine.downloaded.mga.save'
    savetask = tasks.Task(savetaskname, _save_archives_task_func,
                          (mga.master_git_dir, list(mga.archives_by_hash.values())), [])
    parallel.add_task(savetask)


def _sync_only_own_task_func() -> None:
    pass  # do nothing, this task is necessary only as means to synchronize


class MasterGitArchives:
    master_git_dir: str
    cache_dir: str
    tmp_dir: str
    cache_data: dict[str, any]
    archives_by_hash: dict[bytes, Archive] | None
    archived_files_by_hash: dict[bytes, list[tuple[Archive, FileInArchive]]] | None
    nhashes: int  # number of hashes already requested; used to make name of tmp dir

    _LOADOWNTASKNAME = 'sanguine.downloaded.mga.loadown'

    def __init__(self, mastergitdir: str, cachedir: str, tmpdir: str, cache_data: dict[str, any]) -> None:
        self.master_git_dir = mastergitdir
        self.cache_dir = cachedir
        self.tmp_dir = tmpdir
        self.cache_data = cache_data
        self.archives_by_hash = None
        self.archived_files_by_hash = None
        self.nhashes = 0

    def start_tasks(self, parallel: tasks.Parallel) -> None:
        loadtaskname = 'sanguine.downloaded.mga.load'
        loadtask = tasks.Task(loadtaskname, _load_archives_task_func,
                              (self.master_git_dir, self.cache_dir, self.cache_data), [])
        parallel.add_task(loadtask)
        loadowntaskname = MasterGitArchives._LOADOWNTASKNAME
        loadowntask = tasks.OwnTask(loadowntaskname,
                                    lambda _, out: _load_archives_own_task_func(out, self), None,
                                    [loadtaskname])
        parallel.add_task(loadowntask)

    @staticmethod
    def ready_to_start_hashing_task_name() -> str:
        return MasterGitArchives._LOADOWNTASKNAME

    def start_hashing_archive(self, parallel: tasks.Parallel, arpath: str, arhash: bytes, arsize: int) -> None:
        hashingtaskname = 'sanguine.downloaded.mga.hash.' + arpath
        self.nhashes += 1
        tmp_dir = self.tmp_dir + str(self.nhashes) + '\\'
        hashingtask = tasks.Task(hashingtaskname, _archive_hashing_task_func,
                                 (arpath, arhash, arsize, tmp_dir), [])
        parallel.add_task(hashingtask)
        hashingowntaskname = 'sanguine.downloaded.mga.hashown.' + arpath
        hashingowntask = tasks.OwnTask(hashingowntaskname,
                                       lambda _, out: _archive_hashing_own_task_func(out, self), None,
                                       [hashingtaskname])
        parallel.add_task(hashingowntask)

    def start_done_hashing_task(self,  # should be called only after all start_hashing_archive() calls are done
                                parallel: tasks.Parallel) -> str:
        donehashingowntaskname = 'sanguine.downloaded.mga.donehashing'
        donehashingowntask = tasks.OwnTask(donehashingowntaskname,
                                           lambda _: _done_hashing_own_task_func(self, parallel), None,
                                           ['sanguine.downloaded.mga.hashown.*'])
        parallel.add_task(donehashingowntask)

        return donehashingowntaskname


def _downloaded_start_hashing_task_func(downloaded: "Downloaded", parallel: tasks.Parallel) -> None:
    for ar in downloaded.foldercache.all_files():
        ext = os.path.splitext(ar.file_path)[1]
        if ext == '.meta':
            continue
        if ext == '.7z':
            continue  # TODO! handle 7z decompression with BCJ2
        if not ar.file_hash in downloaded.gitarchives.archives_by_hash:
            if ext in pluginhandler.all_archive_plugins_extensions():
                downloaded.gitarchives.start_hashing_archive(parallel, ar.file_path, ar.file_hash, ar.file_size)
            else:
                warn('Downloaded: file with unknown extension {}, ignored'.format(ar.file_path))

    gitarchivesdonehashingtaskname: str = downloaded.gitarchives.start_done_hashing_task(parallel)
    donehashingowntaskname = Downloaded._DONEHASHINGTASKNAME
    donehashingowntask = tasks.OwnTask(donehashingowntaskname,
                                       lambda _, _1: _sync_only_own_task_func(), None,
                                       [gitarchivesdonehashingtaskname])
    parallel.add_task(donehashingowntask)


class Downloaded:
    foldercache: FolderCache
    gitarchives: MasterGitArchives
    _DONEHASHINGTASKNAME = 'sanguine.downloaded.donehashing'  # does not apply to MGA!

    def __init__(self, cachedir: str, tmpdir: str, mastergitdir: str, downloads: list[str]) -> None:
        self.foldercache = FolderCache(cachedir, 'downloaded', [(d, []) for d in downloads])
        self.gitarchives = MasterGitArchives(mastergitdir, cachedir, tmpdir, {})

    def start_tasks(self, parallel: tasks.Parallel):
        self.foldercache.start_tasks(parallel)
        self.gitarchives.start_tasks(parallel)

        starthashingowntaskname = 'sanguine.downloaded.starthashing'
        starthashingowntask = tasks.OwnTask(starthashingowntaskname,
                                            lambda _, _1, _2: _downloaded_start_hashing_task_func(self, parallel), None,
                                            [self.foldercache.ready_task_name(),
                                             MasterGitArchives.ready_to_start_hashing_task_name()])
        parallel.add_task(starthashingowntask)

    @staticmethod
    def ready_task_name() -> str:
        return Downloaded._DONEHASHINGTASKNAME


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        tdownloaded = Downloaded(Folders.normalize_dir_path('..\\..\\mo2git.cache\\'),
                                 Folders.normalize_dir_path('..\\..\\mo2git.tmp\\'),
                                 Folders.normalize_dir_path('..\\..\\skyrim-universe\\'),
                                 [Folders.normalize_dir_path('..\\..\\..\\mo2\\downloads')])
        with tasks.Parallel(None) as tparallel:
            tdownloaded.start_tasks(tparallel)
            tparallel.run([])  # all necessary tasks were already added in acache.start_tasks()
