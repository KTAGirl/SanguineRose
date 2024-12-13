import re
from abc import abstractmethod

import sanguine.gitdatafile as gitdatafile
from sanguine.available import FileRetriever, AvailableFiles, ZeroFileRetriever, GithubFileRetriever
from sanguine.common import *
from sanguine.gitdatafile import GitDataParam, GitDataType, GitDataHandler


##### Handlers

class GitRetrievedFileWriteHandler(GitDataHandler):
    @abstractmethod
    def legend(self) -> str:
        pass

    @abstractmethod
    def is_my_retriever(self, fr: FileRetriever) -> bool:
        pass

    @abstractmethod
    def write_line(self, writer: gitdatafile.GitDataListWriter, rel_path: str, fr: FileRetriever) -> None:
        pass

    @staticmethod
    def common_values(rel_path: str, fr: FileRetriever) -> tuple[str, int, bytes]:
        return rel_path, fr.file_size, fr.file_hash


class GitRetrievedFileReadHandler(GitDataHandler):
    retrieved_files: list[tuple[str, FileRetriever]]
    COMMON_FIELDS: list[GitDataParam] = [
        GitDataParam('p', GitDataType.Path, False, compress_level=0),  # no path compression for readability
        GitDataParam('s', GitDataType.Int),
        GitDataParam('h', GitDataType.Hash)
    ]

    def __init__(self, specific_fields: list[GitDataParam], files: list[tuple[str, FileRetriever]]) -> None:
        super().__init__(specific_fields)
        self.retrieved_files = files

    @staticmethod
    def init_base_file_retriever(available: AvailableFiles, fr: FileRetriever,
                                 common_param: tuple[str, int, bytes]) -> None:
        assert type(fr) == FileRetriever  # should be exactly FileRetriever, not a subclass
        (p, s, h) = common_param
        fr.__init__(available, filehash=h, filesize=s)

    @staticmethod
    def rel_path(common_param: tuple[str, int, bytes]) -> str:
        return common_param[0]


### specifications for Handlers (all Retrievers are known here, no need to deal with plugins)

class GitRetrievedZeroFileReadHandler(GitRetrievedFileReadHandler):
    SPECIFIC_FIELDS: list[GitDataParam] = []
    available: AvailableFiles

    def __init__(self, available: AvailableFiles, files: list[tuple[str, FileRetriever]]) -> None:
        super().__init__(GitRetrievedZeroFileReadHandler.SPECIFIC_FIELDS, files)
        self.available = available

    def decompress(self, common_param: tuple[str | int, ...], specific_param: tuple[str | int, ...]) -> None:
        (p, s, h) = common_param  # not using init_base_file_retriever as we've overrridden h with None
        assert h is None and s == 0
        self.retrieved_files.append((p, ZeroFileRetriever(self.available, (ZeroFileRetriever.ZEROHASH, 0))))


class GitRetrievedZeroFileWriteHandler(GitRetrievedFileWriteHandler):
    def legend(self) -> str:
        return ''

    def is_my_retriever(self, fr: FileRetriever) -> bool:
        return isinstance(fr, ZeroFileRetriever)

    def write_line(self, writer: gitdatafile.GitDataListWriter, rel_path: str, fr: FileRetriever) -> None:
        writer.write_line(self,
                          (rel_path, 0,
                           None))  # not using GitRetrievedFileWriteHandler.common_values() to override h with None


class GitRetrievedGithubFileReadHandler(GitRetrievedFileReadHandler):
    SPECIFIC_FIELDS: list[GitDataParam] = [
        GitDataParam('g', GitDataType.Str, False),
        GitDataParam('f', GitDataType.Path),
    ]
    available: AvailableFiles

    def __init__(self, available: AvailableFiles, files: list[tuple[str, FileRetriever]]) -> None:
        super().__init__(GitRetrievedGithubFileReadHandler.SPECIFIC_FIELDS, files)
        self.available = available

    def decompress(self, common_param: tuple[str, int, bytes], specific_param: tuple[str | int, ...]) -> None:
        (g, f) = specific_param
        fr = GithubFileRetriever(self.available,
                                 lambda fr2: GitRetrievedFileReadHandler.init_base_file_retriever(self.available, fr2,
                                                                                                  common_param),
                                 g, f)
        self.retrieved_files.append((GitRetrievedFileReadHandler.rel_path(common_param), fr))


class GitRetrievedGithubFileWriteHandler(GitRetrievedFileWriteHandler):
    def legend(self) -> str:
        return '[ g:github project, f:file if GitHub ]'

    def is_my_retriever(self, fr: FileRetriever) -> bool:
        return isinstance(fr, GithubFileRetriever)

    def write_line(self, writer: gitdatafile.GitDataListWriter, rel_path: str, fr: FileRetriever) -> None:
        writer.write_line(self,
                          GitRetrievedFileWriteHandler.common_values(rel_path, fr))


_write_handlers: list[GitRetrievedFileWriteHandler] = [
    GitRetrievedZeroFileWriteHandler(),
    GitRetrievedGithubFileWriteHandler()]


### GitProjectJson

class GitProjectJson:
    available: AvailableFiles

    def __init__(self, available: AvailableFiles) -> None:
        self.available = available

    def write(self, wfile: typing.TextIO, retrievers: list[tuple[str, FileRetriever]]) -> None:
        rsorted: list[tuple[str, FileRetriever]] = sorted(retrievers, key=lambda tpl: tpl[0])
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
        for rx in rsorted:
            (p, r) = rx
            handler = None
            for wh in _write_handlers:
                if wh.is_my_retriever(r):
                    assert handler is None
                    handler = wh
                    if not __debug__:
                        break
            assert handler is not None
            handler.write_line(writer, p, r)

        writer.write_end()
        gitdatafile.write_git_file_footer(wfile)

    def read_from_file(self, rfile: typing.TextIO) -> list[tuple[str, FileRetriever]]:
        retrievers: list[tuple[str, FileRetriever]] = []

        # skipping header
        ln, lineno = gitdatafile.skip_git_file_header(rfile)

        # reading file_origins:  ...
        assert re.search(r'^\s*files\s*:\s*//', ln)

        handlers: list[GitRetrievedFileReadHandler] = [GitRetrievedZeroFileReadHandler(self.available, retrievers)]
        da = gitdatafile.GitDataList(GitRetrievedFileReadHandler.COMMON_FIELDS, handlers)
        lineno = gitdatafile.read_git_file_list(da, rfile, lineno)

        # skipping footer
        gitdatafile.skip_git_file_footer(rfile, lineno)

        # warn(str(len(archives)))
        return retrievers
