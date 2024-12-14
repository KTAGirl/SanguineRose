# apparently, we cannot use py7zr module as it doesn't support BCJ2 coder
# we'll use 7z.exe which we install into tools folder instead
import subprocess

from sanguine.archives import ArchivePluginBase
from sanguine.common import *


def _7z_exe() -> str:
    return os.path.abspath(os.path.split(__file__)[0] + '\\..\\..\\..\\tools\\7za.exe')


class SevenzArchivePlugin(ArchivePluginBase):
    def extensions(self) -> list[str]:
        return ['.7z']

    def extract(self, archive: str, list_of_files: list[str], targetpath: str) -> list[str]:
        info('Extracting from {}...'.format(archive))
        assert False

    def extract_all(self, archive: str, targetpath: str) -> None:
        info('Extracting all from {}...'.format(archive))

        syscall = [_7z_exe(), 'x', '-o' + targetpath, archive]
        # warn(repr(syscall))
        subprocess.check_call(syscall)
        info('Extraction done')
