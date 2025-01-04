import re

import sanguine.gitdata.git_data_file as gitdatafile
from sanguine.common import *
from sanguine.gitdata.file_origin import FileOrigin, FileOriginPluginBase, MetaFileParser
from sanguine.gitdata.git_data_file import GitDataParam, GitDataType, GitDataReadHandler, GitDataWriteHandler


### FileOrigin

class NexusFileOrigin(FileOrigin):
    gameid: int  # nexus game #
    modid: int
    fileid: int

    # md5: bytes

    def __init__(self, gameid: int, modid: int, fileid: int):
        super().__init__()
        self.gameid = gameid
        self.modid = modid
        self.fileid = fileid

    @staticmethod
    def is_nexus_gameid_ok(game: GameUniverse, nexusgameid: int) -> bool:
        if game == GameUniverse.Skyrim:
            return nexusgameid in [1704, 110]  # SE, LE
        assert False

    def eq(self, b: "NexusFileOrigin") -> bool:
        return self.fileid == b.fileid and self.modid == b.modid and self.gameid == b.gameid


### known-nexus-data.json5

class _GitNexusHashMappingReadHandler(GitDataReadHandler):
    COMMON_FIELDS: list[GitDataParam] = [
        GitDataParam('h', GitDataType.Hash, False),
        GitDataParam('m', GitDataType.Hash),
    ]
    nexus_hash_mapping: dict[bytes, bytes]  # our hash -> md5

    def __init__(self, nexus_hash_mapping: dict[bytes, bytes]) -> None:
        super().__init__()
        self.nexus_hash_mapping = nexus_hash_mapping

    def decompress(self, common_param: tuple[bytes, bytes], specific_param: tuple) -> None:
        assert len(specific_param) == 0
        (h, m) = common_param
        assert h not in self.nexus_hash_mapping  # if we'll ever run into md5 collision - we'll handle it separately
        self.nexus_hash_mapping[h] = m


class _GitNexusFileOriginsReadHandler(GitDataReadHandler):
    COMMON_FIELDS: list[GitDataParam] = [
        GitDataParam('h', GitDataType.Hash, False),
        GitDataParam('f', GitDataType.Int),
        GitDataParam('m', GitDataType.Int),
        GitDataParam('g', GitDataType.Int),
    ]
    nexus_file_origins: dict[bytes, list[NexusFileOrigin]]

    def __init__(self, file_origins: dict[bytes, list[NexusFileOrigin]]) -> None:
        super().__init__()
        self.nexus_file_origins = file_origins

    def decompress(self, common_param: tuple[bytes, int, int, int], specific_param: tuple) -> None:
        assert len(specific_param) == 0
        (h, f, m, g) = common_param

        fo = NexusFileOrigin(g, m, f)
        if h not in self.nexus_file_origins:
            self.nexus_file_origins[h] = [fo]
        else:
            self.nexus_file_origins[h].append(fo)


class GitNexusData:
    def __init__(self) -> None:
        pass

    def write(self, wfile: typing.TextIO, nexus_hash_mapping: dict[bytes, bytes],
              nexus_file_origins: dict[bytes, list[NexusFileOrigin]]) -> None:
        hmap: list[tuple[bytes, bytes]] = sorted(nexus_hash_mapping.items(), key=lambda item: item[0])
        allfos: list[tuple[bytes, NexusFileOrigin]] = []
        for h, fos in sorted(nexus_file_origins.items(), key=lambda item: item[0]):
            for fo in sorted(fos, key=lambda item: (item.gameid, item.modid, item.fileid)):
                allfos.append((h, fo))

        gitdatafile.write_git_file_header(wfile)
        wfile.write(
            '  hash_remap: // Legend: h=hash,  m=md5\n')

        hrhandler = GitDataWriteHandler()
        dhr = gitdatafile.GitDataWriteList(_GitNexusHashMappingReadHandler.COMMON_FIELDS, [hrhandler])
        hwriter = gitdatafile.GitDataListWriter(dhr, wfile)
        hwriter.write_begin()
        for hm in hmap:
            hwriter.write_line(hrhandler, (hm[0], hm[1]))
        hwriter.write_end()

        wfile.write(
            '  file_origins: // Legend: h=hash,  f=fileid, m=modid, g=gameid\n')

        fohandler = GitDataWriteHandler()
        dfo = gitdatafile.GitDataWriteList(_GitNexusFileOriginsReadHandler.COMMON_FIELDS, [fohandler])
        fwriter = gitdatafile.GitDataListWriter(dfo, wfile)
        fwriter.write_begin()
        for fo in allfos:
            fwriter.write_line(hrhandler, (fo[0], fo[1].fileid, fo[1].modid, fo[1].gameid))
        fwriter.write_end()

        gitdatafile.write_git_file_footer(wfile)

    def read_from_file(self, rfile: typing.TextIO) -> tuple[dict[bytes, bytes], dict[bytes, list[NexusFileOrigin]]]:
        nexus_hash_mapping: dict[bytes, bytes] = {}
        nexus_file_origins: dict[bytes, list[NexusFileOrigin]] = {}

        # skipping header
        ln, lineno = gitdatafile.skip_git_file_header(rfile)

        # reading hash_remap:  ...
        assert re.search(r'^\s*hash_remap\s*:\s*//', ln)

        dhm = gitdatafile.GitDataReadList(_GitNexusHashMappingReadHandler.COMMON_FIELDS,
                                          [_GitNexusHashMappingReadHandler(nexus_hash_mapping)])
        lineno = gitdatafile.read_git_file_list(dhm, rfile, lineno)

        # reading file_origins:  ...
        ln = rfile.readline()
        lineno += 1
        if not re.search(r'^\s*file_origins\s*:\s*//', ln):
            alert('GitNexusData.read_from_file(): Unexpected line #{}: {}'.format(lineno, ln))
            abort_if_not(False)

        dfo = gitdatafile.GitDataReadList(_GitNexusFileOriginsReadHandler.COMMON_FIELDS,
                                          [_GitNexusFileOriginsReadHandler(nexus_file_origins)])
        lineno = gitdatafile.read_git_file_list(dfo, rfile, lineno)

        # skipping footer
        gitdatafile.skip_git_file_footer(rfile, lineno)

        # warn(str(len(archives)))
        return nexus_hash_mapping, nexus_file_origins


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
            return NexusFileOrigin(self.game_id, self.mod_id, self.file_id)
        elif self.game_id is None and self.mod_id is None and self.file_id is None and self.url is None:
            return None
        elif self.game_id is not None and self.mod_id is not None and self.file_id is not None and self.url is None:
            warn('meta/nexus: missing url in {}, will do without'.format(self.meta_file_path))
            return NexusFileOrigin(self.game_id, self.mod_id, self.file_id)
        else:
            warn('meta/nexus: incomplete modid+fileid+url in {}'.format(self.meta_file_path))
            return None


def _load_nexus_json5(rf: typing.TextIO):
    return GitNexusData().read_from_file(rf)


def _save_nexus_json5(wf: typing.TextIO, data: tuple[dict[bytes, bytes], dict[bytes, list[NexusFileOrigin]]]):
    return GitNexusData().write(wf, data[0], data[1])


### Plugin

class NexusFileOriginPlugin(FileOriginPluginBase):
    nexus_hash_mapping: dict[bytes, bytes]
    nexus_file_origins: dict[bytes, list[NexusFileOrigin]]

    def __init__(self) -> None:
        super().__init__()
        self.nexus_hash_mapping = {}
        self.nexus_file_origins = {}

    def name(self) -> str:
        return 'nexus'

    def meta_file_parser(self, metafilepath: str) -> MetaFileParser:
        return NexusMetaFileParser(metafilepath)

    ### reading and writing is split into two parts, to facilitate multiprocessing
    # reading, part 1 (to be run in a separate process)
    def load_json5_file_func(self) -> Callable[[typing.TextIO], any]:  # function returning function
        return _load_nexus_json5

    # reading, part 2 (to be run locally)
    def got_loaded_data(self, data: any) -> None:
        self.nexus_hash_mapping = data[0]
        self.nexus_file_origins = data[1]

    # writing, part 1 (to be run locally)
    def data_for_saving(self) -> any:
        return self.nexus_hash_mapping, self.nexus_file_origins

    # writing, part 2 (to be run in a separate process)
    def save_json5_file_func(self) -> Callable[[typing.TextIO, any], None]:
        return _save_nexus_json5

    def add_file_origin(self, h: bytes, fo: FileOrigin) -> bool:
        assert isinstance(fo, NexusFileOrigin)
        if h in self.nexus_file_origins:
            for fo2 in self.nexus_file_origins[h]:
                assert isinstance(fo2, NexusFileOrigin)
                if fo2.eq(fo):
                    return False
            self.nexus_file_origins[h].append(fo)
            return True
        else:
            self.nexus_file_origins[h] = [fo]
            return True
