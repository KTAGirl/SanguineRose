import shutil

import mo2gitlib.pluginhandler as pluginhandler
import mo2gitlib.tasks as tasks
from mo2gitlib.files import calculate_file_hash, truncate_file_hash
from mo2gitlib.folders import Folders
from mo2gitlib.gitdatafile import *
from mo2gitlib.pickledcache import pickled_cache


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

    def write(self, wfile: typing.TextIO, archives: Iterable[Archive]) -> None:
        write_git_file_header_comment(wfile)
        wfile.write(
            '  archives: [ // Legend: i=intra_archive_path, j=intra_archive_path2, a=archive_hash, x=archive_size, h=file_hash, s=file_size\n')

        ahandler = GitDataHandler(GitArchivesHandler.optional)
        da = GitDataList(self._aentry_mandatory, [ahandler])
        writera = GitDataListWriter(da, wfile)
        writera.write_begin()
        for ar in archives:
            for fi in ar.files:
                writera.write_line(ahandler, (
                    fi.intra_path[0], fi.intra_path[1] if len(fi.intra_path) > 1 else None, ar.archive_hash,
                    ar.archive_size, truncate_file_hash(fi.file_hash), fi.file_size))
        writera.write_end()
        wfile.write('\n]}\n')

    def read_from_file(self, rfile: typing.TextIO) -> list[Archive]:
        archives: list[Archive] = []

        # skipping header
        archivestart = re.compile(r'^\s*archives\s*:\s*\[\s*//')
        lineno = skip_git_file_header(rfile, archivestart)

        # reading archives: [ ...
        filesend = re.compile(r'^\s*]\s*}')
        da = GitDataList(self._aentry_mandatory, [GitArchivesHandler(archives)])
        lineno = read_git_file_section(da, rfile, lineno, filesend)

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
    mastergitfile = mastergitdir + 'archives.json'
    return pickled_cache(cachedir, cachedata, 'archivesdata', [mastergitfile],
                         _read_git_archives, (mastergitfile,))


def _write_git_archives(mastergitdir: str, archives: list[Archive]) -> None:
    assert Folders.is_normalized_dir_path(mastergitdir)
    fpath = mastergitdir + 'archives.json'
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
    assert ar.archive_hash not in mga.archives_by_hash
    mga.archives_by_hash[ar.archive_hash] = ar
    for fi in ar.files:
        assert fi.file_hash not in mga.archived_files_by_hash
        mga.archived_files_by_hash[fi.file_hash] = (ar, fi)


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
    if False:
        shutil.rmtree(tmppath)
    return (archive,)


def _archive_hashing_own_task_func(out: tuple[Archive], mga: "MasterGitArchives"):
    (archive,) = out
    _append_archive(mga, archive)


def _save_archives_task_func(param: tuple[str, list[Archive]]) -> None:
    (mastergitdir, archives) = param
    _write_git_archives(mastergitdir, archives)


def _ready_own_task_func() -> None:
    pass  # do nothing, this task is necessary only as means to synchronize


class MasterGitArchives:
    master_git_dir: str
    cache_dir: str
    tmp_dir: str
    cache_data: dict[str, any]
    archives_by_hash: dict[bytes, Archive] | None
    archived_files_by_hash: dict[bytes, tuple[Archive, FileInArchive]] | None
    nhashes : int # number of hashes already requested

    def __init__(self, mastergitdir: str, cachedir: str, tmpdir: str, cache_data: dict[str, any]) -> None:
        self.master_git_dir = mastergitdir
        self.cache_dir = cachedir
        self.tmp_dir = tmpdir
        self.cache_data = cache_data
        self.archives_by_hash = None
        self.archived_files_by_hash = None
        self.nhashes = 0

    def start_tasks(self, parallel: tasks.Parallel) -> None:
        loadtaskname = 'mo2gitlib.mga.load'
        loadtask = tasks.Task(loadtaskname, _load_archives_task_func,
                              (self.master_git_dir, self.cache_dir, self.cache_data), [])
        parallel.add_task(loadtask)
        loadowntaskname = 'mo2gitlib.mga.loadown'
        loadowntask = tasks.OwnTask(loadowntaskname,
                                    lambda _, out: _load_archives_own_task_func(out, self), None,
                                    [loadtaskname])
        parallel.add_task(loadowntask)

    def start_hashing_archive(self, arpath: str, arhash: bytes, arsize: int, parallel: tasks.Parallel) -> None:
        hashingtaskname = 'mo2gitlib.mga.hash.' + arpath
        self.nhashes += 1
        tmp_dir = self.tmp_dir + str(self.nhashes) + '\\'
        hashingtask = tasks.Task(hashingtaskname, _archive_hashing_task_func,
                                 (arpath, arhash, arsize, tmp_dir), [])
        parallel.add_task(hashingtask)
        hashingowntaskname = 'mo2gitlib.mga.hashown.' + arpath
        hashingowntask = tasks.OwnTask(hashingowntaskname,
                                       lambda _, out: _archive_hashing_own_task_func(out, self), None,
                                       [hashingtaskname])
        parallel.add_task(hashingowntask)

    def start_ready_task(self,
                         parallel: tasks.Parallel) -> str:  # should be called only after all start_hashing_archive() calls are done
        readyowntaskname = 'mo2gitlib.mga.ready'
        readyowntask = tasks.OwnTask(readyowntaskname, _ready_own_task_func, None, ['mo2gitlib.mga.hash.*'])
        parallel.add_task(readyowntask)
        return readyowntaskname

    def start_save_tasks(self, parallel: tasks.Parallel) -> None:
        savetaskname = 'mo2gitlib.mga.save'
        savetask = tasks.Task(savetaskname, _save_archives_task_func,
                              (self.master_git_dir, list(self.archives_by_hash.values())), [])
        parallel.add_task(savetask)


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        acache = ArchiveEntriesCache(Folders.normalize_dir_path('..\\..\\mo2git.cache\\'),
                                     Folders.normalize_dir_path('..\\..\\mo2git.tmp\\'), {})
        with tasks.Parallel(None) as tparallel:
            dummyowntask = tasks.OwnTask('dummy.loadown',
                                         lambda _: None, None,
                                         [])
            tparallel.add_task(dummyowntask)
            acache.start_tasks(tparallel, [], 'dummy.loadown')

            tparallel.run([])  # all necessary tasks were already added in acache.start_tasks()
