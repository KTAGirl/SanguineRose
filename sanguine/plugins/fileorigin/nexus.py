import re

import sanguine.gitdata.git_data_file as gitdatafile
from sanguine.common import *
from sanguine.gitdata.file_origin import FileOrigin, FileOriginPluginBase, MetaFileParser
from sanguine.gitdata.file_origin import GitFileOriginsReadHandler, GitFileOriginsWriteHandler
from sanguine.gitdata.git_data_file import GitDataParam, GitDataType


### FileOrigin

class NexusFileOrigin(FileOrigin):
    gameid: int  # nexus game #
    modid: int
    fileid: int

    # md5: bytes

    def __init__(self, baseinit: Callable[[FileOrigin], None] | str, gameid: int, modid: int, fileid: int):
        if isinstance(baseinit, str):
            super().__init__(baseinit)
        else:
            baseinit(super())  # calls super().__init__(...) within
        self.gameid = gameid
        self.modid = modid
        self.fileid = fileid

    @staticmethod
    def is_nexus_gameid_ok(game: GameUniverse, nexusgameid: int) -> bool:
        if game == GameUniverse.Skyrim:
            return nexusgameid in [1704, 110]  # SE, LE
        assert False

    def eq(self, b: "NexusFileOrigin") -> bool:
        return self.parent_eq(b) and self.fileid == b.fileid and self.modid == b.modid


### Handler

class GitNexusFileOriginsReadHandler(GitFileOriginsReadHandler):
    SPECIFIC_FIELDS: list[GitDataParam] = [
        GitDataParam('f', GitDataType.Int, False),
        GitDataParam('m', GitDataType.Int),
        GitDataParam('g', GitDataType.Int),
    ]

    def __init__(self, file_origins: dict[bytes, list[FileOrigin]]) -> None:
        super().__init__(GitNexusFileOriginsReadHandler.SPECIFIC_FIELDS, file_origins)

    def decompress(self, common_param: tuple[str, bytes], specific_param: tuple[int, int, int]) -> None:
        (f, m, g) = specific_param

        fo = NexusFileOrigin(lambda fo2: GitFileOriginsReadHandler.init_base_file_origin(fo2, common_param),
                             g, m, f)
        h = GitFileOriginsReadHandler.hash_from_common_param(common_param)
        if h not in self.file_origins:
            self.file_origins[h] = [fo]
        else:
            self.file_origins[h].append(fo)


class GitNexusFileOriginsWriteHandler(GitFileOriginsWriteHandler):
    def __init__(self) -> None:
        super().__init__(GitNexusFileOriginsReadHandler.SPECIFIC_FIELDS)

    def is_my_fo(self, fo: FileOrigin) -> bool:
        return isinstance(fo, NexusFileOrigin)

    def write_line(self, writer: gitdatafile.GitDataListWriter, h: bytes, fo: FileOrigin) -> None:
        assert isinstance(fo, NexusFileOrigin)
        writer.write_line(self, GitFileOriginsWriteHandler.common_values(h, fo),
                          (fo.fileid, fo.modid, fo.gameid))

    def legend(self) -> str:
        return '[ f:fileid, m:modid, g:gameid if Nexus ]'

    ### MetaFileParser


class NexusMetaFileParser(MetaFileParser):
    MOD_ID_PATTERN = re.compile(r'^modID\s*=\s*([0-9]+)\s*$', re.IGNORECASE)
    FILE_ID_PATTERN = re.compile(r'^fileID\s*=\s*([0-9]+)\s*$', re.IGNORECASE)
    URL_PATTERN = re.compile(r'^url\s*=\s*"([^"]*)"\s*$', re.IGNORECASE)
    HTTPS_PATTERN = re.compile(r'^https://.*\.nexus.*\.com.*/([0-9]*)/([0-9]*)/([^?]*).*[?&]md5=([^&]*)&.*',
                               re.IGNORECASE)

    game_id: int | None
    mod_id: int | None
    file_id: int | None
    url: str | None
    file_name: str

    def __init__(self, meta_file_path: str) -> None:
        super().__init__(meta_file_path)
        self.game_id = None
        self.mod_id = None
        self.file_id = None
        self.url = None
        self.file_name = os.path.split(meta_file_path)[1]

    def take_ln(self, ln: str) -> None:
        m = NexusMetaFileParser.MOD_ID_PATTERN.match(ln)
        if m:
            self.mod_id = int(m.group(1))
        m = NexusMetaFileParser.FILE_ID_PATTERN.match(ln)
        if m:
            self.file_id = int(m.group(1))
        m = NexusMetaFileParser.URL_PATTERN.match(ln)
        if m:
            self.url = m.group(1)
            urls = self.url.split(';')
            filename_from_url = None
            md5 = None
            for u in urls:
                m2 = NexusMetaFileParser.HTTPS_PATTERN.match(u)
                if not m2:
                    warn('meta/nexus: unrecognized url {} in {}'.format(u, self.meta_file_path))
                    continue
                urlgameid = int(m2.group(1))
                urlmodid = int(m2.group(2))
                urlfname = m2.group(3)
                urlmd5 = m2.group(4)
                if NexusFileOrigin.is_nexus_gameid_ok(game_universe(), urlgameid):
                    if self.game_id is None:
                        self.game_id = urlgameid
                    elif self.game_id != urlgameid:
                        warn('meta/nexus: mismatching game id {} in {}'.format(urlgameid, self.meta_file_path))
                else:
                    warn('meta/nexus: unexpected gameid {} in {}'.format(urlgameid, self.meta_file_path))
                if urlmodid != self.mod_id:
                    warn('meta/nexus: unmatching url modid {} in {}'.format(urlmodid, self.meta_file_path))
                if filename_from_url is None:
                    filename_from_url = urlfname
                elif urlfname != filename_from_url:
                    warn('meta/nexus: unmatching url filename {} in {}'.format(urlfname, self.meta_file_path))
                if md5 is None:
                    md5 = urlmd5
                elif urlmd5 != md5:
                    warn('meta/nexus: unmatching url md5 {} in {}'.format(urlmd5, self.meta_file_path))
            if filename_from_url is not None:
                self.file_name = filename_from_url

    def make_file_origin(self) -> FileOrigin | None:
        # warn(str(modid))
        # warn(str(fileid))
        # warn(url)
        if self.game_id is not None and self.mod_id is not None and self.file_id is not None and self.url is not None:
            return NexusFileOrigin(self.file_name, self.game_id, self.mod_id, self.file_id)
        elif self.game_id is None and self.mod_id is None and self.file_id is None and self.url is None:
            return None
        elif self.game_id is not None and self.mod_id is not None and self.file_id is not None and self.url is None:
            warn('meta/nexus: missing url in {}, will do without'.format(self.meta_file_path))
            return NexusFileOrigin(self.file_name, self.game_id, self.mod_id, self.file_id)
        else:
            warn('meta/nexus: incomplete modid+fileid+url in {}'.format(self.meta_file_path))
            return None


### Plugin

class NexusFileOriginPlugin(FileOriginPluginBase):
    def write_handler(self) -> GitFileOriginsWriteHandler:
        return GitNexusFileOriginsWriteHandler()

    def meta_file_parser(self, metafilepath: str) -> MetaFileParser:
        return NexusMetaFileParser(metafilepath)

    def read_handler(self, file_origins: dict[bytes, list[FileOrigin]]) -> GitFileOriginsReadHandler:
        return GitNexusFileOriginsReadHandler(file_origins)
