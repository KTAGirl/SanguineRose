import re
from abc import abstractmethod

import sanguine.gitdatafile as gitdatafile
from sanguine.common import *
from sanguine.files import FileRetriever, ZeroFileRetriever, _ZEROHASH
from sanguine.gitdatafile import GitDataParam, GitDataType, GitDataHandler


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


class GitRetrievedFileHandler(GitDataHandler):
    retrieved_files: list[FileRetriever]
    COMMON_FIELDS: list[GitDataParam] = [
        GitDataParam('h', GitDataType.Hash, False),
        GitDataParam('p', GitDataType.Path),
        GitDataParam('s', GitDataType.Int)
    ]

    def __init__(self, specific_fields: list[GitDataParam], files: list[FileRetriever]) -> None:
        super().__init__(specific_fields)
        self.retrieved_files = files


### specifications for Handlers (all Retrievers are known here, no need to deal with plugins)

class GitRetrievedZeroFileHandler(GitRetrievedFileHandler):
    SPECIFIC_FIELDS: list[GitDataParam] = []

    def __init__(self, files: list[FileRetriever]) -> None:
        super().__init__(GitRetrievedZeroFileHandler.SPECIFIC_FIELDS, files)


class GitRetrievedZeroFileWriteHandler(GitRetrievedFileWriteHandler):
    def legend(self) -> str:
        return ''

    def is_my_retriever(self, fr: FileRetriever) -> bool:
        return isinstance(fr, ZeroFileRetriever)

    def write_line(self, writer: gitdatafile.GitDataListWriter, fr: FileRetriever) -> None:
        writer.write_line(self, (_ZEROHASH, fr.relative_path(), 0))


_write_handlers: list[GitRetrievedFileWriteHandler] = [GitRetrievedZeroFileWriteHandler()]


### GitProjectJson

class GitProjectJson:
    def __init__(self) -> None:
        pass

    def write(self, wfile: typing.TextIO, retrievers: list[FileRetriever]) -> None:
        rsorted: list[FileRetriever] = sorted(retrievers, key=lambda rs: rs.relative_path())
        gitdatafile.write_git_file_header(wfile)
        wfile.write(
            '  files: // Legend: h=hash, p=path (relative to MO2), s=size\n')

        global _write_handlers
        for wh in _write_handlers:
            legend = wh.legend()
            if legend:
                wfile.write(
                    '         //         ' + legend + '\n')

        da = gitdatafile.GitDataList(GitRetrievedFileHandler.COMMON_FIELDS, _write_handlers)
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

        handlers: list[GitRetrievedFileHandler] = [GitRetrievedZeroFileHandler(retrievers)]
        da = gitdatafile.GitDataList(GitRetrievedFileHandler.COMMON_FIELDS, handlers)
        lineno = gitdatafile.read_git_file_list(da, rfile, lineno)

        # skipping footer
        gitdatafile.skip_git_file_footer(rfile, lineno)

        # warn(str(len(archives)))
        return retrievers
