import py7zr

from sanguine.common import *
from sanguine.pluginhandler import ArchivePluginBase


class SevenzArchivePlugin(ArchivePluginBase):
    def extensions(self) -> list[str]:
        return ['.7z']

    def extract(self, archive: str, list_of_files: list[str], targetpath: str) -> list[str]:
        info('Extracting from {}...'.format(archive))
        sevenz = py7zr.SevenZipFile(archive)
        names = sevenz.namelist()
        lof_normalized = []
        for f in list_of_files:
            normf = f.replace('\\', '/')
            lof_normalized.append(normf)
            if normf not in names:
                warn('{} NOT FOUND in {}'.format(f, archive))
        sevenz.extract(path=targetpath, targets=lof_normalized)
        out = []
        for f in list_of_files:
            if os.path.isfile(targetpath + f):
                out.append(targetpath + f)
            else:
                warn('{} NOT EXTRACTED from {}'.format(f, archive))
                out.append(None)
        sevenz.close()
        info('Extraction done')
        return out

    def extract_all(self, archive: str, targetpath: str) -> None:
        info('Extracting all from {}...'.format(archive))
        sevenz = py7zr.SevenZipFile(archive)
        sevenz.extractall(path=targetpath)
        sevenz.close()
        info('Extraction done')
