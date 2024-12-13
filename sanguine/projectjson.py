import hashlib
import re
import tempfile
from abc import abstractmethod

import sanguine.gitdatafile as gitdatafile
from sanguine.available import FileRetriever
from sanguine.common import *
from sanguine.foldercache import FileOnDisk
from sanguine.gitdatafile import GitDataParam, GitDataType, GitDataHandler

_ZEROHASH = hashlib.sha256(b"").digest()


class ZeroFileRetriever(FileRetriever):
    def __init__(self, baseinit: Callable[[FileRetriever], None] | str) -> None:
        if isinstance(baseinit, str):
            super().__init__(baseinit, _ZEROHASH, 0)
        else:
            baseinit(super())  # calls super().__init__(...) within

    @abstractmethod
    def fetch(self, mo2dir: str):
        assert is_normalized_dir_path(mo2dir)
        open(self._target_fpath(mo2dir), 'wb').close()

    @abstractmethod
    def fetch_for_reading(self, tmpdirpath: str) -> str:
        wf, tfname = tempfile.mkstemp(dir=tmpdirpath)
        os.close(wf)  # yep, it is exactly enough to create temp zero file
        return tfname


def make_zero_retriever_if(mo2dir: str, fi: FileOnDisk) -> ZeroFileRetriever | None:
    assert is_normalized_dir_path(mo2dir)
    if fi.file_hash == _ZEROHASH or fi.file_size == 0:
        assert fi.file_hash == _ZEROHASH and fi.file_size == 0
        return ZeroFileRetriever(to_short_path(mo2dir, fi.file_path))
    else:
        return None


class GithubFileRetriever(FileRetriever):  # only partially specialized, needs further specialization to be usable
    from_project: str  # '' means 'this project'
    from_path: str

    def __init__(self, baseinit: Callable[[FileRetriever], None] | tuple[str, bytes, int], fromproject: str,
                 frompath: str) -> None:
        if isinstance(baseinit, tuple):
            (p, h, s) = baseinit
            super().__init__(p, h, s)
        else:
            baseinit(super())  # calls super().__init__(...) within
        self.from_project = fromproject
        self.from_path = frompath

    def _full_path(self) -> str:
        pass  # TODO!

    def fetch(self, mo2dir: str):
        shutil.copyfile(self._full_path(), self._target_fpath(mo2dir))

    @abstractmethod
    def fetch_for_reading(self, tmpdirpath: str) -> str:
        return self._full_path()


class GitRetrievedFileWriteHandler(GitDataHandler):
    @abstractmethod
    def legend(self) -> str:
        pass

    @abstractmethod
    def is_my_retriever(self, fr: FileRetriever) -> bool:
        pass

    @abstractmethod
    def write_line(self, writer: gitdatafile.GitDataListWriter, fr: FileRetriever) -> None:
        pass

    @staticmethod
    def common_values(fr: FileRetriever) -> tuple[str, int, bytes]:
        return fr.rel_path, fr.file_size, fr.file_hash


class GitRetrievedFileReadHandler(GitDataHandler):
    retrieved_files: list[FileRetriever]
    COMMON_FIELDS: list[GitDataParam] = [
        GitDataParam('p', GitDataType.Path, False, compress_level=0),  # no path compression for readability
        GitDataParam('s', GitDataType.Int),
        GitDataParam('h', GitDataType.Hash)
    ]

    def __init__(self, specific_fields: list[GitDataParam], files: list[FileRetriever]) -> None:
        super().__init__(specific_fields)
        self.retrieved_files = files

    @staticmethod
    def init_base_file_retriever(fr: FileRetriever, common_param: tuple[str, int, bytes]) -> None:
        assert type(fr) == FileRetriever  # should be exactly FileRetriever, not a subclass
        (p, s, h) = common_param
        fr.__init__(p, filehash=h, filesize=s)


### specifications for Handlers (all Retrievers are known here, no need to deal with plugins)

class GitRetrievedZeroFileReadHandler(GitRetrievedFileReadHandler):
    SPECIFIC_FIELDS: list[GitDataParam] = []

    def __init__(self, files: list[FileRetriever]) -> None:
        super().__init__(GitRetrievedZeroFileReadHandler.SPECIFIC_FIELDS, files)

    def decompress(self, common_param: tuple[str | int, ...], specific_param: tuple[str | int, ...]) -> None:
        (p, s, h) = common_param  # not using init_base_file_retriever as we've overrridden h with None
        assert h is None and s == 0
        self.retrieved_files.append(ZeroFileRetriever(p))


class GitRetrievedZeroFileWriteHandler(GitRetrievedFileWriteHandler):
    def legend(self) -> str:
        return ''

    def is_my_retriever(self, fr: FileRetriever) -> bool:
        return isinstance(fr, ZeroFileRetriever)

    def write_line(self, writer: gitdatafile.GitDataListWriter, fr: FileRetriever) -> None:
        writer.write_line(self,
                          (fr.rel_path, 0,
                           None))  # not using GitRetrievedFileWriteHandler.common_values() to override h with None


class GitRetrievedGithubFileReadHandler(GitRetrievedFileReadHandler):
    SPECIFIC_FIELDS: list[GitDataParam] = [
        GitDataParam('g', GitDataType.Str, False),
        GitDataParam('f', GitDataType.Path),
    ]

    def __init__(self, files: list[FileRetriever]) -> None:
        super().__init__(GitRetrievedGithubFileReadHandler.SPECIFIC_FIELDS, files)

    def decompress(self, common_param: tuple[str, int, bytes], specific_param: tuple[str | int, ...]) -> None:
        (g, f) = specific_param
        fr = GithubFileRetriever(lambda fr2: GitRetrievedFileReadHandler.init_base_file_retriever(fr2, common_param),
                                 g, f)
        self.retrieved_files.append(fr)


class GitRetrievedGithubFileWriteHandler(GitRetrievedFileWriteHandler):
    def legend(self) -> str:
        return '[ g:github project, f:file if GitHub ]'

    def is_my_retriever(self, fr: FileRetriever) -> bool:
        return isinstance(fr, GithubFileRetriever)

    def write_line(self, writer: gitdatafile.GitDataListWriter, fr: FileRetriever) -> None:
        writer.write_line(self,
                          GitRetrievedFileWriteHandler.common_values(fr))


_write_handlers: list[GitRetrievedFileWriteHandler] = [
    GitRetrievedZeroFileWriteHandler(),
    GitRetrievedGithubFileWriteHandler()]


### GitProjectJson

class GitProjectJson:
    def __init__(self) -> None:
        pass

    def write(self, wfile: typing.TextIO, retrievers: list[FileRetriever]) -> None:
        rsorted: list[FileRetriever] = sorted(retrievers, key=lambda rs: rs.relative_path())
        gitdatafile.write_git_file_header(wfile)
        wfile.write(
            '  files: // Legend: p=path (relative to MO2), s=size, h=hash\n')

        global _write_handlers
        for wh in _write_handlers:
            legend = wh.legend()
            if legend:
                wfile.write(
                    '         //         ' + legend + '\n')

        da = gitdatafile.GitDataList(GitRetrievedFileReadHandler.COMMON_FIELDS, _write_handlers)
        writer = gitdatafile.GitDataListWriter(da, wfile)
        writer.write_begin()
        for r in rsorted:
            handler = None
            for wh in _write_handlers:
                if wh.is_my_retriever(r):
                    assert handler is None
                    handler = wh
                    if not __debug__:
                        break
            assert handler is not None
            handler.write_line(writer, r)

        writer.write_end()
        gitdatafile.write_git_file_footer(wfile)

    def read_from_file(self, rfile: typing.TextIO) -> list[FileRetriever]:
        retrievers: list[FileRetriever] = []

        # skipping header
        ln, lineno = gitdatafile.skip_git_file_header(rfile)

        # reading file_origins:  ...
        assert re.search(r'^\s*files\s*:\s*//', ln)

        handlers: list[GitRetrievedFileReadHandler] = [GitRetrievedZeroFileReadHandler(retrievers)]
        da = gitdatafile.GitDataList(GitRetrievedFileReadHandler.COMMON_FIELDS, handlers)
        lineno = gitdatafile.read_git_file_list(da, rfile, lineno)

        # skipping footer
        gitdatafile.skip_git_file_footer(rfile, lineno)

        # warn(str(len(archives)))
        return retrievers
