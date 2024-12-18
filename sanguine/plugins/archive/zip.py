import zipfile

from sanguine.helpers.archives import ArchivePluginBase
from sanguine.common import *


class ZipArchivePlugin(ArchivePluginBase):
    def extensions(self) -> list[str]:
        return ['.zip']

    def extract(self, archive: str, list_of_files: list[str], targetpath: str) -> list[str]:
        info('Extracting from {}...'.format(archive))
        z = zipfile.ZipFile(archive)
        names = z.namelist()
        lof_normalized = []
        for f in list_of_files:
            normf = f.replace('\\', '/')
            lof_normalized.append(normf)
            if normf not in names:
                warn('{} NOT FOUND in {}'.format(f, archive))
        out = []
        for f in lof_normalized:
            z.extract(f, path=targetpath)
            if os.path.isfile(targetpath + f):
                out.append(targetpath + f)
            else:
                warn('{} NOT EXTRACTED from {}'.format(f, archive))
                out.append(None)
        z.close()
        print('Extraction done')
        return out

    def extract_all(self, archive: str, targetpath: str) -> None:
        info('Extracting all from {}...'.format(archive))
        z = zipfile.ZipFile(archive)
        z.extractall(targetpath)
        z.close()
        info('Extraction done')
