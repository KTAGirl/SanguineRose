# apparently, we cannot use py7zr module as it doesn't support BCJ2 coder
# we'll use 7za.exe from 7zXXXX-extra.7z instead
import subprocess

from sanguine.common import *
from sanguine.pluginhandler import ArchivePluginBase


def _7za_exe() -> str:
    return os.path.abspath(os.path.split(__file__)[0] + '\\..\\..\\..\\tools\\7za.exe')


class SevenzArchivePlugin(ArchivePluginBase):
    def extensions(self) -> list[str]:
        return ['.7z']

    def extract(self, archive: str, list_of_files: list[str], targetpath: str) -> list[str]:
        info('Extracting from {}...'.format(archive))
        assert False
        '''
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
        '''

    def extract_all(self, archive: str, targetpath: str) -> None:
        info('Extracting all from {}...'.format(archive))

        syscall = [_7za_exe(), 'x', '-o' + targetpath, archive]
        warn(repr(syscall))
        subprocess.check_call(syscall)
        # sevenz = py7zr.SevenZipFile(archive)
        # sevenz.extractall(path=targetpath)
        # sevenz.close()
        info('Extraction done')
