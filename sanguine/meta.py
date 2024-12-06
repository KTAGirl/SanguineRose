import re
from enum import Enum

from sanguine.common import *
from sanguine.folders import Folders


class GameUniverse(Enum):
    Skyrim = 0,
    Fallout = 1


class FileOrigin:
    name: str

    def __init__(self, name: str) -> None:
        self.name = name


class NexusFileOrigin(FileOrigin):
    modid: int
    fileid: int

    # md5: bytes

    def __init__(self, name: str, modid: int, fileid: int):
        super().__init__(name)
        self.modid = modid
        self.fileid = fileid

    @staticmethod
    def is_nexus_gameid_ok(game: GameUniverse, nexusgameid: int) -> bool:
        if game == GameUniverse.Skyrim:
            return nexusgameid in [1704, 110]  # SE, LE
        assert False


def file_origin(game: GameUniverse, fpath: str, nexusgameids: list[int]) -> FileOrigin | None:
    assert Folders.is_normalized_file_path(fpath)
    assert os.path.isfile(fpath)
    metafpath = fpath + '.meta'
    if os.path.isfile(metafpath):
        with open_3rdparty_txt_file(metafpath) as rf:
            fname = os.path.split(fpath)[1]
            modidpattern = re.compile(r'^modID\s*=\s*([0-9]+)\s*$', re.IGNORECASE)
            fileidpattern = re.compile(r'^fileID\s*=\s*([0-9]+)\s*$', re.IGNORECASE)
            urlpattern = re.compile(r'^url\s*=\s"([^"])"\s*$', re.IGNORECASE)
            httpspattern = re.compile(r'^https://.*.nexusmods.com/cdn/([0-9]*)/([0-9]*)/([^?]*).*[?&]md5=([^&]*)&.*',
                                      re.IGNORECASE)

            modid = None
            fileid = None
            url = None

            for ln in rf:
                m = modidpattern.match(ln)
                if m:
                    modid = int(m.group(1))
                m = fileidpattern.match(ln)
                if m:
                    fileid = int(m.group(1))
                m = urlpattern.match(ln)
                if m:
                    url = m.group(1)
                    urls = url.split(';')
                    filename = None
                    md5 = None
                    for u in urls:
                        m2 = httpspattern.match(u)
                        if not m2:
                            warn('meta: unrecognized url {} in {}'.format(u, metafpath))
                            continue
                        urlgameid = int(m2.group(1))
                        urlmodid = int(m2.group(2))
                        urlfname = m2.group(3)
                        urlmd5 = m2.group(4)
                        if not NexusFileOrigin.is_nexus_gameid_ok(game, urlgameid):
                            warn('meta: unexpected gameid {} in {}'.format(urlgameid, metafpath))
                        if urlmodid != modid:
                            warn('meta: unmatching url modid {} in {}'.format(urlmodid, metafpath))
                        if filename is None:
                            filename = urlfname
                        elif urlfname != filename:
                            warn('meta: unmatching url filename {} in {}'.format(urlfname, metafpath))
                        if md5 is None:
                            md5 = urlmd5
                        elif urlmd5 != md5:
                            warn('meta: unmatching url md5 {} in {}'.format(urlmd5, metafpath))
                    if filename is None:
                        fname = filename

            if modid is not None and fileid is not None and url is not None:
                return NexusFileOrigin(fname, modid, fileid)
            elif modid is None and fileid is None and url is None:
                return None
            else:
                warn('meta: incomplete modid+fileid+url in {}'.format(metafpath))
