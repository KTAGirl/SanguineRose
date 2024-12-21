import re

import sanguine.gitdata.git_data_file as gitdatafile
from sanguine.common import *
from sanguine.gitdata.git_data_file import GitDataParam, GitDataType, GitDataWriteHandler, GitDataReadHandler
from sanguine.helpers.archives import FileInArchive
from sanguine.helpers.file_retriever import (FileRetriever, ZeroFileRetriever, GithubFileRetriever,
                                             ArchiveFileRetriever, ArchiveFileRetrieverHelper)


##### Handlers

### base read/write handlers

class GitRetrievedFileWriteHandler(GitDataWriteHandler):
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


class GitRetrievedFileReadHandler(GitDataReadHandler):
    retrieved_files: list[tuple[str, FileRetriever]]
    COMMON_FIELDS: list[GitDataParam] = [
        GitDataParam('p', GitDataType.Path, False, compress_level=0),  # no path compression for readability
        GitDataParam('s', GitDataType.Int),
        GitDataParam('h', GitDataType.Hash)
    ]

    def __init__(self, specific_fields: list[GitDataParam], files: list[tuple[str, FileRetriever]]) -> None:
        super().__init__(specific_fields)
        self.retrieved_files = files

    @abstractmethod
    def decompress(self, common_param: tuple, specific_param: tuple) -> None:
        pass

    @staticmethod
    def init_base_file_retriever(fr: FileRetriever, common_param: tuple[str, int, bytes]) -> None:
        assert type(fr) == FileRetriever  # should be exactly FileRetriever, not a subclass
        (p, s, h) = common_param
        fr.__init__(filehash=h, filesize=s)

    @staticmethod
    def rel_path(common_param: tuple[str, int, bytes]) -> str:
        return common_param[0]

    @staticmethod
    def hash_and_size(common_param: tuple[str, int, bytes]) -> tuple[bytes, int]:
        return common_param[2], common_param[1]


### specifications for Handlers (all Retrievers are known here, no need to deal with plugins)

### for ZeroFileRetriever

class GitRetrievedZeroFileReadHandler(GitRetrievedFileReadHandler):
    SPECIFIC_FIELDS: list[GitDataParam] = []

    def __init__(self, files: list[tuple[str, FileRetriever]]) -> None:
        super().__init__(GitRetrievedZeroFileReadHandler.SPECIFIC_FIELDS, files)

    def decompress(self, common_param: tuple[str | int, ...], specific_param: tuple) -> None:
        assert len(specific_param) == 0
        (p, s, h) = common_param  # not using init_base_file_retriever as we've overrridden h with None
        assert h is None and s == 0
        self.retrieved_files.append((p, ZeroFileRetriever((ZeroFileRetriever.ZEROHASH, 0))))


class GitRetrievedZeroFileWriteHandler(GitRetrievedFileWriteHandler):
    def legend(self) -> str:
        return '[ nothing else if Zero ]'

    def is_my_retriever(self, fr: FileRetriever) -> bool:
        return isinstance(fr, ZeroFileRetriever)

    def write_line(self, writer: gitdatafile.GitDataListWriter, rel_path: str, fr: FileRetriever) -> None:
        writer.write_line(self,
                          (rel_path, 0,
                           None))  # not using GitRetrievedFileWriteHandler.common_values() to override h with None


### for GithubFileRetriever

class GitRetrievedGithubFileReadHandler(GitRetrievedFileReadHandler):
    SPECIFIC_FIELDS: list[GitDataParam] = [
        GitDataParam('g', GitDataType.Path, False),
        GitDataParam('a', GitDataType.Str),
        GitDataParam('p', GitDataType.Str),
    ]

    def __init__(self, files: list[tuple[str, FileRetriever]]) -> None:
        super().__init__(GitRetrievedGithubFileReadHandler.SPECIFIC_FIELDS, files)

    def decompress(self, common_param: tuple[str, int, bytes], specific_param: tuple[str, str, str]) -> None:
        (g, a, p) = specific_param
        fr = GithubFileRetriever(lambda fr2: GitRetrievedFileReadHandler.init_base_file_retriever(fr2, common_param),
                                 a, p, g)
        self.retrieved_files.append((GitRetrievedFileReadHandler.rel_path(common_param), fr))


class GitRetrievedGithubFileWriteHandler(GitRetrievedFileWriteHandler):
    def legend(self) -> str:
        return '[ g:github file path in project, a:github project author, p:github project name if Github ]'

    def is_my_retriever(self, fr: FileRetriever) -> bool:
        return isinstance(fr, GithubFileRetriever)

    def write_line(self, writer: gitdatafile.GitDataListWriter, rel_path: str, fr: FileRetriever) -> None:
        assert isinstance(fr, GithubFileRetriever)
        writer.write_line(self,
                          GitRetrievedFileWriteHandler.common_values(rel_path, fr),
                          (fr.from_path, fr.github_author, fr.github_project))


### for ArchiveFileRetriever

type _IntermediateArchives = dict[bytes, ArchiveFileRetrieverHelper]


class GitRetrievedArchiveFileReadHandler(GitRetrievedFileReadHandler):
    SPECIFIC_FIELDS: list[GitDataParam] = [
        GitDataParam('i', GitDataType.Path, False),
        # 'i' refers either to IntermediateArchives, or to downloadable archive
        GitDataParam('a', GitDataType.Hash),
        GitDataParam('x', GitDataType.Int),
    ]
    intermediate_archives: _IntermediateArchives

    def __init__(self, iar: _IntermediateArchives, files: list[tuple[str, FileRetriever]]) -> None:
        super().__init__(GitRetrievedArchiveFileReadHandler.SPECIFIC_FIELDS, files)
        self.intermediate_archives = iar

    def decompress(self, common_param: tuple[str, int, bytes], specific_param: tuple[str, bytes, int]) -> None:
        (i, a, x) = specific_param
        (h, s) = GitRetrievedFileReadHandler.hash_and_size(common_param)
        fr = ArchiveFileRetriever(
            lambda fr2: GitRetrievedFileReadHandler.init_base_file_retriever(fr2, common_param),
            [ArchiveFileRetrieverHelper((h, s), a, x, FileInArchive(h, s, i))])
        while fr.single_archive_retrievers[0].archive_hash in self.intermediate_archives:
            fr = ArchiveFileRetriever(
                lambda fr2: GitRetrievedFileReadHandler.init_base_file_retriever(fr2, common_param),
                fr.constructor_parameter_prepending_parent(
                    self.intermediate_archives[fr.single_archive_retrievers[0].archive_hash])
            )
        self.retrieved_files.append((GitRetrievedFileReadHandler.rel_path(common_param), fr))


class GitRetrievedArchiveFileWriteHandler(GitRetrievedFileWriteHandler):
    def legend(self) -> str:
        return '[ i:intra-archive path, a:archive hash, x:archive size if Archive ]'

    def is_my_retriever(self, fr: FileRetriever) -> bool:
        return isinstance(fr, ArchiveFileRetriever)

    def write_line(self, writer: gitdatafile.GitDataListWriter, rel_path: str, fr: FileRetriever) -> None:
        assert isinstance(fr, ArchiveFileRetriever)
        last = fr.single_archive_retrievers[-1]
        writer.write_line(self,
                          GitRetrievedFileWriteHandler.common_values(rel_path, fr),
                          (last.file_in_archive, last.archive_hash, last.archive_size))


### all write handlers

_write_handlers: list[GitRetrievedFileWriteHandler] = [
    GitRetrievedZeroFileWriteHandler(),
    GitRetrievedGithubFileWriteHandler(),
    GitRetrievedArchiveFileWriteHandler(),
]


### GitProjectJson

class GitProjectJson:
    def __init__(self) -> None:
        pass

    def write(self, wfile: typing.TextIO, retrievers: list[tuple[str, FileRetriever]]) -> None:
        rsorted: list[tuple[str, FileRetriever]] = sorted(retrievers, key=lambda tpl: tpl[0])
        gitdatafile.write_git_file_header(wfile)

        # TODO: write intermediate_archives

        wfile.write(
            '  files: // Legend: p=path (relative to VFS), s=size, h=hash\n')

        global _write_handlers
        for wh in _write_handlers:
            legend = wh.legend()
            if legend:
                wfile.write(
                    '         //         ' + legend + '\n')

        da = gitdatafile.GitDataWriteList(GitRetrievedFileReadHandler.COMMON_FIELDS, _write_handlers)
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

        intermediate_archives: _IntermediateArchives = {}

        # TODO: read intermediate_archives

        # reading file_origins:  ...
        assert re.search(r'^\s*files\s*:\s*//', ln)

        handlers: list[GitRetrievedFileReadHandler] = [
            GitRetrievedZeroFileReadHandler(retrievers),
            GitRetrievedGithubFileReadHandler(retrievers),
            GitRetrievedArchiveFileReadHandler(intermediate_archives, retrievers),
        ]
        da = gitdatafile.GitDataReadList(GitRetrievedFileReadHandler.COMMON_FIELDS, handlers)
        lineno = gitdatafile.read_git_file_list(da, rfile, lineno)

        # skipping footer
        gitdatafile.skip_git_file_footer(rfile, lineno)

        # warn(str(len(archives)))
        return retrievers
