import os.path

from sanguine.common import *
from sanguine.helpers.archives import archive_plugin_for
from sanguine.helpers.file_retriever import FileRetriever, ArchiveFileRetriever


class ArchiveRetrieverAggregator:
    archives: dict[bytes, list[ArchiveFileRetriever]]  # all items in the list must have the same archive_hash()

    def __init__(self) -> None:
        self.archives = {}

    @staticmethod
    def is_my_retriever(fr: FileRetriever) -> bool:
        return isinstance(fr, ArchiveFileRetriever)

    def add_retriever(self, fr: ArchiveFileRetriever):
        assert ArchiveRetrieverAggregator.is_my_retriever(fr)
        arh = fr.archive_hash()
        if arh not in self.archives:
            self.archives[arh] = []
        self.archives[arh].append(fr)

    def is_empty(self) -> bool:
        return len(self.archives) == 0

    def all_archives_needed(self) -> list[bytes]:
        return list(self.archives.keys())

    def extract_all_from_one_archive(self, tmpdir: str, arh: bytes, arpath: str) -> dict[bytes, str]:
        # returning file_hash -> temp_path
        assert is_normalized_dir_path(tmpdir)
        assert is_normalized_file_path(arpath)
        assert arh in self.archives

        tmpdir0 = tmpdir + '0\\'
        plugin = archive_plugin_for(arpath)
        assert plugin is not None
        flist: list[str] = [aretr.single_archive_retrievers[0].file_in_archive.intra_path for aretr in
                            self.archives[arh]]
        plugin.extract(arpath, flist, tmpdir0)

        out: dict[bytes, str] = {}
        nextagg = ArchiveRetrieverAggregator()
        existingars: dict[bytes, str] = {}
        for aretr in self.archives[arh]:
            a0 = aretr.single_archive_retrievers[0]
            ipath = a0.file_in_archive.intra_path
            fpath = tmpdir0 + ipath
            assert os.path.isfile(fpath)
            if len(aretr.single_archive_retrievers) == 1:  # final one
                assert a0.file_hash not in out
                out[a0.file_hash] = fpath
            else:  # nested
                nextagg.add_retriever(
                    ArchiveFileRetriever((a0.file_hash, a0.file_size), aretr.constructor_parameter_removing_parent()))
                assert a0.file_hash not in existingars
                existingars[a0.file_hash] = fpath

        assert len(existingars) == len(nextagg.archives)
        if not nextagg.is_empty():
            tmpi = 1
            for arh1 in nextagg.all_archives_needed():
                assert arh1 in existingars
                arpath = existingars[arh1]
                tmpdir1 = tmpdir + str(tmpi) + '\\'
                tmpi += 1
                out |= nextagg.extract_all_from_one_archive(tmpdir1, arh1, arpath)

        assert len(out) == len(self.archives)
        return out
