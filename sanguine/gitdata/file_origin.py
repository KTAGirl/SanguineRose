import re

import sanguine.gitdata.git_data_file as gitdatafile
from sanguine.common import *
from sanguine.gitdata.git_data_file import GitDataParam, GitDataType, GitDataWriteHandler, GitDataReadHandler
from sanguine.helpers.plugin_handler import load_plugins


class FileOrigin(ABC):
    def __init__(self) -> None:
        pass

    @abstractmethod
    def eq(self, b: "FileOrigin") -> bool:
        pass


### MetaFileParser

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
    def name(self) -> str:
        pass

    @abstractmethod
    def meta_file_parser(self, metafilepath: str) -> MetaFileParser:
        pass

    ### reading and writing is split into two parts, to facilitate multiprocessing
    # reading, part 1 (to be run in a separate process)
    @abstractmethod
    def load_json5_file_func(self) -> Callable[
        any, [typing.TextIO]]:  # function returning function; returned function cannot be a lambda
        pass

    # reading, part 2 (to be run locally)
    @abstractmethod
    def got_loaded_data(self, data: any) -> None:
        pass

    # writing, part 1 (to be run locally)
    @abstractmethod
    def data_for_saving(self) -> any:
        pass

    # writing, part 2 (to be run in a separate process)
    @abstractmethod
    def save_json5_file_func(self) -> Callable[None, [typing.TextIO, any]]:
        pass

    @abstractmethod
    def add_file_origin(self, h: bytes, fo: FileOrigin) -> None:
        pass


_file_origin_plugins: dict[str, FileOriginPluginBase] = {}


def _found_origin_plugin(plugin: FileOriginPluginBase):
    global _file_origin_plugins
    assert plugin.name() not in _file_origin_plugins
    _file_origin_plugins[plugin.name()] = plugin


load_plugins('plugins/fileorigin/', FileOriginPluginBase, lambda plugin: _found_origin_plugin(plugin))


def file_origins_for_file(fpath: str) -> list[FileOrigin] | None:
    global _file_origin_plugins
    assert is_normalized_file_path(fpath)
    assert os.path.isfile(fpath)
    metafpath = fpath + '.meta'
    if os.path.isfile(metafpath):
        with open_3rdparty_txt_file(metafpath) as rf:
            metafileparsers = [plugin.meta_file_parser(metafpath) for plugin in _file_origin_plugins.values()]
            for ln in rf:
                for mfp in metafileparsers:
                    mfp.take_ln(ln)

            origins = [mfp.make_file_origin() for mfp in metafileparsers]
            origins = [o for o in origins if o is not None]
            return origins if len(origins) > 0 else None


def file_origin_plugins() -> Iterable[FileOriginPluginBase]:
    global _file_origin_plugins
    return _file_origin_plugins.values()


def file_origin_plugin_by_name(name: str) -> FileOriginPluginBase:
    global _file_origin_plugins
    return _file_origin_plugins[name]


### known-tentative-archive-names.json5, GitTentativeArchiveNames
# as there are no specific handlers, we don't need to have _GitTentativeArchiveNamesHandler,
#          and can use generic GitWriteHandler for writing

class _GitTentativeArchiveNamesReadHandler(GitDataReadHandler):
    COMMON_FIELDS: list[GitDataParam] = [
        GitDataParam('n', GitDataType.Str, False),
        GitDataParam('h', GitDataType.Hash),
        # duplicate h can occur if the same file is known under different names
    ]
    tentative_file_names_by_hash: dict[bytes, list[str]]

    def __init__(self, tentative_file_names_by_hash: dict[bytes, list[str]]) -> None:
        super().__init__()
        self.tentative_file_names_by_hash = tentative_file_names_by_hash

    def decompress(self, common_param: tuple[str, bytes], specific_param: tuple) -> None:
        assert len(specific_param) == 0
        (n, h) = common_param
        if h in self.tentative_file_names_by_hash:
            self.tentative_file_names_by_hash[h].append(n)
        else:
            self.tentative_file_names_by_hash[h] = [n]


class GitTentativeArchiveNames:
    def __init__(self) -> None:
        pass

    def write(self, wfile: typing.TextIO, tentativearchivenames: dict[bytes, list[str]]) -> None:
        folist: list[tuple[bytes, list[str]]] = sorted(tentativearchivenames.items())
        for fox in folist:
            fox[1].sort(key=lambda fo2: fo2.tentative_name)
        gitdatafile.write_git_file_header(wfile)
        wfile.write(
            '  file_origins: // Legend: n=tentative_name,  h=hash\n')

        tahandler = GitDataWriteHandler()
        da = gitdatafile.GitDataWriteList(_GitTentativeArchiveNamesReadHandler.COMMON_FIELDS, [tahandler])
        writer = gitdatafile.GitDataListWriter(da, wfile)
        writer.write_begin()
        for fox in folist:
            for tname in fox[1]:
                writer.write_line(tahandler, (tname, fox[0]))
        writer.write_end()
        gitdatafile.write_git_file_footer(wfile)

    def read_from_file(self, rfile: typing.TextIO) -> dict[bytes, list[str]]:
        tentativearchivenames: dict[bytes, list[str]] = {}

        # skipping header
        ln, lineno = gitdatafile.skip_git_file_header(rfile)

        # reading file_origins:  ...
        assert re.search(r'^\s*file_origins\s*:\s*//', ln)

        da = gitdatafile.GitDataReadList(_GitTentativeArchiveNamesReadHandler.COMMON_FIELDS,
                                         [_GitTentativeArchiveNamesReadHandler(tentativearchivenames)])
        lineno = gitdatafile.read_git_file_list(da, rfile, lineno)

        # skipping footer
        gitdatafile.skip_git_file_footer(rfile, lineno)

        # warn(str(len(archives)))
        return tentativearchivenames
