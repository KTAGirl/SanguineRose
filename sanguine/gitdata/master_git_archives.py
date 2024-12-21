import re

import sanguine.gitdata.git_data_file as gitdatafile
from sanguine.common import *
from sanguine.gitdata.git_data_file import GitDataParam, GitDataType, GitDataWriteHandler, GitDataReadHandler
from sanguine.helpers.archives import Archive, FileInArchive


# as there are no specific handlers, we don't need to have _GitArchivesWriteHandler,
#          and can use generic GitWriteHandler for writing

class _GitArchivesReadHandler(GitDataReadHandler):
    archives: list[Archive]

    def __init__(self, archives: list[Archive]) -> None:
        super().__init__()
        self.archives = archives

    def decompress(self, common_param: tuple[bytes, str, bytes, int, int, str], specific_param: tuple) -> None:
        assert len(specific_param) == 0
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

        ahandler = GitDataWriteHandler()
        da = gitdatafile.GitDataWriteList(self._COMMON_FIELDS, [ahandler])
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

        da = gitdatafile.GitDataReadList(self._COMMON_FIELDS, [_GitArchivesReadHandler(archives)])
        lineno = gitdatafile.read_git_file_list(da, rfile, lineno)

        # skipping footer
        gitdatafile.skip_git_file_footer(rfile, lineno)

        if __debug__:
            assert len(set([ar.archive_hash for ar in archives])) == len(archives)

        # warn(str(len(archives)))
        return archives
