from cache import Cache
from sanguine.files import calculate_file_hash, ZEROHASH
from sanguine.gitdatafile import *


class MasterArchiveItem:
    name: str
    item_hash: int

    def __init__(self, name: str, item_hash: int) -> None:
        self.name = name
        self.item_hash = item_hash

    def eq(self, b: "MasterArchiveItem") -> bool:
        if self.name != b.name:
            return False
        if self.item_hash != b.item_hash:
            return False
        return True


class MasterFileItem:
    file_path: str
    file_hash: int | None
    file_size: int | None
    archive_hash: int | None
    intra_path: list[str] | None
    gitpath: str | None
    warning: str | None

    def __init__(self, path: str, file_hash: int | None, file_size: int | None = None, archive_hash: int | None = None,
                 intra_path: list[str] | None = None, gitpath: str | None = None, warning: str | None = None) -> None:
        self.file_path = path
        self.file_hash = file_hash
        self.file_size = file_size
        self.archive_hash = archive_hash
        self.intra_path = intra_path
        self.gitpath = gitpath
        self.warning = warning

    def eq(self, b: "MasterFileItem") -> bool:
        if self.file_path != b.file_path:
            return False
        if self.file_hash != b.file_hash:
            return False
        if self.file_size != b.file_size:
            return False
        if self.archive_hash != b.archive_hash:
            return False
        if self.gitpath != b.gitpath:
            return False
        if self.warning != b.warning:
            return False
        return True


class ArchiveReadHandler(GitDataHandler):
    archives: list[MasterArchiveItem]
    optional: list[GitDataParam] = []

    def __init__(self, archives: list[MasterArchiveItem]) -> None:
        super().__init__(self.optional)
        self.archives = archives

    def decompress(self, param: tuple[str, int]) -> None:
        (p, h) = param
        assert h >= 0
        self.archives.append(MasterArchiveItem(p, h))


class FilesDataHandlerS0(GitDataHandler):
    files: list[MasterFileItem]
    optional: list[GitDataParam] = [
        GitDataParam('s', GitDataType.Int, False)
    ]

    def __init__(self, files: list[MasterFileItem]) -> None:
        super().__init__(self.optional)
        self.files = files

    def decompress(self, param: tuple[str, None, int]) -> None:
        (p, h, s) = param
        assert s == 0
        assert h is None
        self.files.append(MasterFileItem(p, file_hash=ZEROHASH, file_size=0))


class FilesDataHandlerA(GitDataHandler):
    files: list[MasterFileItem]
    optional: list[GitDataParam] = [
        GitDataParam('i', GitDataType.Path, False),
        GitDataParam('i2', GitDataType.Path),
        GitDataParam('a', GitDataType.Hash),
        GitDataParam('s', GitDataType.Int, False)  # to avoid too many regexps
    ]

    def __init__(self, files: list[MasterFileItem]) -> None:
        super().__init__(self.optional)
        self.files = files

    def decompress(self, param: tuple[str, int, str, str | None, int, int]) -> None:
        (p, h, i, i2, a, s) = param
        assert s == 0
        inpath = [i]
        if i2 is not None:
            inpath.append(i2)
        self.files.append(MasterFileItem(p, file_hash=h, file_size=s, archive_hash=a, intra_path=inpath))


class FilesDataHandlerG(GitDataHandler):
    files: list[MasterFileItem]
    optional: list[GitDataParam] = [
        GitDataParam('g', GitDataType.Path, False),
    ]

    def __init__(self, files: list[MasterFileItem]) -> None:
        super().__init__(self.optional)
        self.files = files

    def decompress(self, param: tuple[str, int, str]) -> None:
        (p, h, g) = param
        self.files.append(MasterFileItem(p, file_hash=h, gitpath=g))


class FilesDataHandlerWarning(GitDataHandler):
    files: list[MasterFileItem]
    optional: list[GitDataParam] = [
        GitDataParam('warning', GitDataType.Str, False),
    ]

    def __init__(self, files: list[MasterFileItem]) -> None:
        super().__init__(self.optional)
        self.files = files

    def decompress(self, param: tuple[str, int, str]) -> None:
        (p, h, warning) = param
        self.files.append(MasterFileItem(p, file_hash=h, warning=warning))


class Master:
    archives: list[MasterArchiveItem]
    files: list[MasterFileItem]

    _a_mandatory: list[GitDataParam] = [
        GitDataParam('n', GitDataType.Path, False),
        GitDataParam('h', GitDataType.Hash)
    ]

    _f_mandatory: list[GitDataParam] = [
        GitDataParam('p', GitDataType.Path, False),
        GitDataParam('h', GitDataType.Hash)
    ]

    def __init__(self) -> None:
        self.archives = []
        self.files = []

    def construct_from_cache(self, nesx: Val, nwarn: Val, filecache: Cache, allinstallfiles: dict[int, str]) -> None:
        aif = []
        for h, path in allinstallfiles.items():
            fname = os.path.split(path)[1]
            aif.append((fname, h))
        aif.sort(key=lambda f: f[0])
        self.archives = [MasterArchiveItem(item[0], item[1]) for item in aif]

        files = [fi.file_path for fi in filecache.allFiles()]
        files.sort()

        targetdir = 'mo2\\'
        mo2 = filecache.folders.mo2_dir
        mo2len = len(mo2)
        self.files = []
        for fpath0 in files:
            assert (fpath0.islower())
            assert (fpath0.startswith(mo2))
            fpath = fpath0[mo2len:]

            if is_esx(fpath):
                nesx.val += 1

            ae, archive, fi = filecache.findArchiveForFile(fpath0)
            if ae is None:
                processed = False

                srcpath = filecache.folders.github_dir + targetdir + fpath
                if os.path.isfile(srcpath):  # TODO: add github tree to filecache and search/read hash from there
                    h = calculate_file_hash(srcpath)
                    self.files.append(MasterFileItem(fpath, h, gitpath=fpath))
                    processed = True

                if not processed:
                    if fi is not None:
                        self.files.append(MasterFileItem(fpath, fi.file_hash, warning='NF'))
                    else:
                        self.files.append(MasterFileItem(fpath, None, warning='NF'))
                    nwarn.val += 1
            else:
                if archive is None:
                    assert (ae.file_size == 0)
                    self.files.append(MasterFileItem(fpath, None, file_size=0))
                else:
                    fi = MasterFileItem(fpath, ae.file_hash, file_size=ae.file_size,
                                        archive_hash=ae.archive_hash, intra_path=[])
                    for path in ae.intra_path:
                        fi.intra_path.append(path)

                    if not allinstallfiles.get(ae.archive_hash):
                        fi.warning = 'NL'
                        nwarn.val += 1
                    self.files.append(fi)

    def all_files(self) -> Generator[MasterFileItem]:
        for fi in self.files:
            yield fi

    def write(self, wfile: typing.TextIO, masterconfig: dict[str, any]) -> None:
        level = masterconfig.get('pcompression', 0) if masterconfig is not None else 0
        assert isinstance(level, int)

        write_git_file_header(wfile)
        wfile.write('{ config: { pcompression: ' + str(level) + ' },\n')
        wfile.write('  archives: [ // Legend: n means "name", h means "hash"\n')

        ahandler = GitDataHandler(ArchiveReadHandler.optional)
        da = GitDataList(self._a_mandatory, [ahandler])
        writera = GitDataListWriter(da, wfile)
        writera.write_begin()
        for ar in self.archives:
            writera.write_line(ahandler, (ar.name, ar.item_hash))
        writera.write_end()
        wfile.write('\n], files: [ // Legend: p means "path", h means "hash", s means "size", f means "from",')
        wfile.write('\n            //         a means "archive_hash", i means "intra_path"\n')

        handler_s0 = GitDataHandler(FilesDataHandlerS0.optional)
        handler_a = GitDataHandler(FilesDataHandlerA.optional)
        handler_g = GitDataHandler(FilesDataHandlerG.optional)
        handler_warning = GitDataHandler(FilesDataHandlerWarning.optional)
        handlers = [
            handler_s0,
            handler_a,
            handler_g,
            handler_warning
        ]
        df = GitDataList(self._f_mandatory, handlers)
        writer = GitDataListWriter(df, wfile)
        writer.write_begin()
        for fi in self.files:
            if fi.file_hash == ZEROHASH:
                assert fi.warning is None
                assert fi.gitpath is None
                writer.write_line(handler_s0, (fi.file_path, None, 0))
                continue
            if fi.warning is not None:
                assert fi.gitpath is None
                writer.write_line(handler_warning, (fi.file_path, fi.file_hash, fi.warning))
                continue
            if fi.gitpath is not None:
                writer.write_line(handler_g, (fi.file_path, fi.file_hash, fi.gitpath))
                continue
            writer.write_line(handler_a, (fi.file_path, fi.file_hash,
                                          fi.intra_path[0], fi.intra_path[1] if len(fi.intra_path) > 1 else None,
                                          fi.archive_hash, fi.file_size
                                          ))
        writer.write_end()
        wfile.write('\n]}\n')

    def construct_from_file(self, rfile: typing.TextIO) -> None:
        assert len(self.archives) == 0
        assert len(self.files) == 0

        # skipping header
        archivestart = re.compile(r'^\s*archives\s*:\s*\[\s*//')
        lineno = skip_git_file_header(rfile, archivestart)

        # reading archives: [ ...
        filesstart = re.compile(r'^\s*]\s*,\s*files\s*:\s\[\s*//')
        da = GitDataList(self._a_mandatory, [ArchiveReadHandler(self.archives)])
        lineno = read_git_file_list(da, rfile, lineno, filesstart)

        # reading files: [ ...
        filesend = re.compile(r'^\s*]\s*}')
        handler_s0 = FilesDataHandlerS0(self.files)
        handler_a = FilesDataHandlerA(self.files)
        handler_g = FilesDataHandlerG(self.files)
        handler_warning = FilesDataHandlerWarning(self.files)
        handlers = [
            handler_s0,
            handler_a,
            handler_g,
            handler_warning
        ]
        df = GitDataList(self._f_mandatory, handlers)
        lineno = read_git_file_list(df, rfile, lineno, filesend)

        skip_git_file_footer(rfile, lineno)
