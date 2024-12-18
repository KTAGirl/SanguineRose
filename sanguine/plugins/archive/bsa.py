from bethesda_structs.archive import BSAArchive

from sanguine.helpers.archives import ArchivePluginBase
from sanguine.common import *


class BsaArchivePlugin(ArchivePluginBase):
    def extensions(self) -> list[str]:
        return ['.bsa']

    def extract(self, archive: str, list_of_files: list[str], targetpath: str) -> list[str]:
        info('Extracting from {}...'.format(archive))
        bsa = BSAArchive.parse_file(archive)
        # names = bsa.container.file_names
        # print(names)
        bsa.extract(targetpath)
        out = []
        for f in list_of_files:
            if os.path.isfile(targetpath + f):
                out.append(targetpath + f)
            else:
                warn('{} NOT EXTRACTED from {}'.format(f, archive))
                out.append(None)
        info('Extraction done')
        return out

    def extract_all(self, archive: str, targetpath: str) -> None:
        info('Extracting all from {}...'.format(archive))
        bsa = BSAArchive.parse_file(archive)
        bsa.extract(targetpath)
        info('Extraction done')
