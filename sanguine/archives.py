from abc import abstractmethod

import sanguine.pluginhandler as pluginhandler
from sanguine.common import *


class FileInArchive:
    file_hash: bytes
    intra_path: str
    file_size: int

    def __init__(self, file_hash: bytes, file_size: int, intra_path: str) -> None:
        self.file_hash = file_hash
        self.file_size = file_size
        self.intra_path = intra_path


class Archive:
    archive_hash: bytes
    archive_size: int
    files: list[FileInArchive]
    by: str

    def __init__(self, archive_hash: bytes, archive_size: int, by: str,
                 files: list[FileInArchive] | None = None) -> None:
        self.archive_hash = archive_hash
        self.archive_size = archive_size
        self.files = files if files is not None else []
        self.by = by


class ArchivePluginBase:
    def __init__(self) -> None:
        pass

    @abstractmethod
    def extensions(self) -> list[str]:
        pass

    @abstractmethod
    def extract(self, archive: str, list_of_files: list[str], targetpath: str) -> None:
        pass

    @abstractmethod
    def extract_all(self, archive: str, targetpath: str) -> None:
        pass


_archive_plugins: dict[str, ArchivePluginBase] = {}  # file_extension -> ArchivePluginBase
_archive_exts: list[str] = []


def _found_archive_plugin(plugin: ArchivePluginBase):
    global _archive_plugins
    global _archive_exts
    for ext in plugin.extensions():
        _archive_plugins[ext] = plugin
        assert ext not in _archive_exts
        _archive_exts.append(ext)


pluginhandler.load_plugins('plugins/archive/', ArchivePluginBase, lambda plugin: _found_archive_plugin(plugin))


def archive_plugin_for(path: str) -> ArchivePluginBase:
    global _archive_plugins
    ext = os.path.splitext(path)[1].lower()
    return _archive_plugins.get(ext)


def all_archive_plugins_extensions() -> list[str]:
    global _archive_exts
    return _archive_exts
