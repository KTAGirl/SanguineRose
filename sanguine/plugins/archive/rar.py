# we'll use unrar.exe which we install into tools folder.
# python rarfile module expects some rar installed anyway
import subprocess

from sanguine.helpers.archives import ArchivePluginBase
from sanguine.common import *


def _unrar_exe() -> str:
    return os.path.abspath(os.path.split(__file__)[0] + '\\..\\..\\..\\tools\\UnRAR.exe')


class RarArchivePlugin(ArchivePluginBase):
    def extensions(self) -> list[str]:
        return ['.rar']

    def extract(self, archive: str, list_of_files: list[str], targetpath: str) -> list[str]:
        info('Extracting from {}...'.format(archive))
        assert False

    def extract_all(self, archive: str, targetpath: str) -> None:
        info('Extracting all from {}...'.format(archive))

        syscall = [_unrar_exe(), 'x', archive, targetpath]
        # warn(repr(syscall))
        subprocess.check_call(syscall)
        info('Extraction done')
