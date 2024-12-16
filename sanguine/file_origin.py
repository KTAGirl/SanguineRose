import re

import sanguine.git_data_file as gitdatafile
from sanguine.common import *
from sanguine.git_data_file import GitDataParam, GitDataType, GitDataHandler
from sanguine.plugin_handler import load_plugins


class FileOrigin(ABC):
    tentative_name: str

    def __init__(self, name: str) -> None:
        self.tentative_name = name

    @abstractmethod
    def eq(self, b: "FileOrigin") -> bool:
        pass

    def parent_eq(self, b: "FileOrigin") -> bool:
        return self.tentative_name == b.tentative_name


class GitFileOriginsWriteHandler(GitDataHandler):
    @abstractmethod
    def legend(self) -> str:
        pass

    @abstractmethod
    def is_my_fo(self, fo: FileOrigin) -> bool:
        pass

    @abstractmethod
    def write_line(self, writer: gitdatafile.GitDataListWriter, h: bytes, fo: FileOrigin) -> None:
        pass

    @staticmethod
    def common_values(h: bytes, fo: FileOrigin) -> tuple[str, bytes]:
        return fo.tentative_name, h


class GitFileOriginsReadHandler(GitDataHandler):
    file_origins: dict[bytes, list[FileOrigin]]
    COMMON_FIELDS: list[GitDataParam] = [
        GitDataParam('n', GitDataType.Str, False),
        GitDataParam('h', GitDataType.Hash),
        # duplicate h can occur if the same file is available from multiple origins
    ]

    def __init__(self, specific_fields: list[GitDataParam], file_origins: dict[bytes, list[FileOrigin]]) -> None:
        super().__init__(specific_fields)
        self.file_origins = file_origins

    @staticmethod
    def init_base_file_origin(fo: FileOrigin, common_param: tuple[str, bytes]) -> None:
        assert type(fo) is FileOrigin  # should be exactly FileOrigin, not a subclass
        (n, _) = common_param
        fo.__init__(n)

    @staticmethod
    def hash_from_common_param(common_param: tuple[str, bytes]) -> bytes:
        (_, h) = common_param
        return h


class MetaFileParser(ABC):
    meta_file_path: str

    def __init__(self, meta_file_path: str) -> None:
        self.meta_file_path = meta_file_path

    @abstractmethod
    def take_ln(self, ln: str) -> None:
        pass

    @abstractmethod
    def make_file_origin(self) -> FileOrigin | None:
        pass


### plugins

class FileOriginPluginBase(ABC):
    def __init__(self) -> None:
        pass

    @abstractmethod
    def write_handler(self) -> GitFileOriginsWriteHandler:
        pass

    @abstractmethod
    def meta_file_parser(self, metafilepath: str) -> MetaFileParser:
        pass

    @abstractmethod
    def read_handler(self, file_origins: dict[bytes, list[FileOrigin]]) -> GitFileOriginsReadHandler:
        pass


_file_origin_plugins: list[FileOriginPluginBase] = []


def _found_origin_plugin(plugin: FileOriginPluginBase):
    global _file_origin_plugins
    assert plugin not in _file_origin_plugins
    _file_origin_plugins.append(plugin)


load_plugins('plugins/fileorigin/', FileOriginPluginBase, lambda plugin: _found_origin_plugin(plugin))


def file_origins_for_file(fpath: str) -> list[FileOrigin] | None:
    global _file_origin_plugins
    assert is_normalized_file_path(fpath)
    assert os.path.isfile(fpath)
    metafpath = fpath + '.meta'
    if os.path.isfile(metafpath):
        with open_3rdparty_txt_file(metafpath) as rf:
            metafileparsers = [plugin.meta_file_parser(metafpath) for plugin in _file_origin_plugins]
            for ln in rf:
                for mfp in metafileparsers:
                    mfp.take_ln(ln)

            origins = [mfp.make_file_origin() for mfp in metafileparsers]
            origins = [o for o in origins if o is not None]
            return origins if len(origins) > 0 else None


### GitFileOriginsJson

class GitFileOriginsJson:
    def __init__(self) -> None:
        pass

    def write(self, wfile: typing.TextIO, forigins: dict[bytes, list[FileOrigin]]) -> None:
        folist: list[tuple[bytes, list[FileOrigin]]] = sorted(forigins.items())
        for fox in folist:
            fox[1].sort(key=lambda fo2: fo2.tentative_name)
        gitdatafile.write_git_file_header(wfile)
        wfile.write(
            '  file_origins: // Legend: n=tentative_name,  h=hash\n')

        global _file_origin_plugins
        handlers = [plugin.write_handler() for plugin in _file_origin_plugins]
        for wh in handlers:
            wfile.write(
                '                //         ' + wh.legend() + '\n')

        da = gitdatafile.GitDataList(GitFileOriginsReadHandler.COMMON_FIELDS, handlers)
        writer = gitdatafile.GitDataListWriter(da, wfile)
        writer.write_begin()
        for fox in folist:
            (h, fos) = fox
            for fo in fos:
                handler = None
                for wh in handlers:
                    if wh.is_my_fo(fo):
                        assert handler is None
                        handler = wh
                        if not __debug__:
                            break
                assert handler is not None
                handler.write_line(writer, h, fo)

        writer.write_end()
        gitdatafile.write_git_file_footer(wfile)

    def read_from_file(self, rfile: typing.TextIO) -> dict[bytes, list[FileOrigin]]:
        file_origins: dict[bytes, list[FileOrigin]] = {}

        # skipping header
        ln, lineno = gitdatafile.skip_git_file_header(rfile)

        # reading file_origins:  ...
        assert re.search(r'^\s*file_origins\s*:\s*//', ln)

        handlers = [plugin.read_handler(file_origins) for plugin in _file_origin_plugins]
        da = gitdatafile.GitDataList(GitFileOriginsReadHandler.COMMON_FIELDS, handlers)
        lineno = gitdatafile.read_git_file_list(da, rfile, lineno)

        # skipping footer
        gitdatafile.skip_git_file_footer(rfile, lineno)

        # warn(str(len(archives)))
        return file_origins
