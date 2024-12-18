import shutil
import time

from sanguine.common import *


class TmpPath:  # as we're playing with rmtree() here, we need to be super-careful not to delete too much
    tmpdir: str
    ADDED_FOLDER: str = 'JBSLtet9'  # seriously unique
    MAX_RMTREE_RETRIES: int = 3
    MAX_RESERVE_FOLDERS: int = 10

    def __init__(self, basetmpdir: str) -> None:
        assert basetmpdir.endswith('\\')
        self.tmpdir = basetmpdir + TmpPath.ADDED_FOLDER + '\\'

    def __enter__(self) -> "TmpPath":
        if os.path.isdir(self.tmpdir):
            try:
                shutil.rmtree(
                    self.tmpdir)  # safe not to remove too much as we're removing a folder with a UUID-based name
            except Exception as e:
                warn('Error removing {}: {}'.format(self.tmpdir, e))
                # we cannot remove whole tmpdir, but maybe we'll have luck with one of 'reserve' subfolders?
                ok = False
                for i in range(self.MAX_RESERVE_FOLDERS):
                    reservefolder = self.tmpdir + '_' + str(i) + '\\'
                    if not os.path.isdir(reservefolder):
                        self.tmpdir = reservefolder
                        ok = True
                        break  # for i
                    try:
                        shutil.rmtree(reservefolder)
                        self.tmpdir = reservefolder
                        ok = True
                        break  # for i
                    except Exception as e2:
                        warn('Error removing {}: {}'.format(reservefolder, e2))

                abort_if_not(ok)
                info('Will use {} as tmpdir'.format(self.tmpdir))

        os.makedirs(self.tmpdir)
        return self

    def tmp_dir(self) -> str:
        return self.tmpdir

    @staticmethod
    def tmp_in_tmp(tmpbase: str, prefix: str, num: int) -> str:
        assert tmpbase.endswith('\\')
        assert '\\' + TmpPath.ADDED_FOLDER + '\\' in tmpbase
        return tmpbase + prefix + str(num) + '\\'

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        TmpPath.rm_tmp_tree(self.tmpdir)
        if exc_val is not None:
            raise exc_val

    @staticmethod
    def rm_tmp_tree(
            tmppath) -> None:  # Sometimes, removing tmp tree doesn't work right after work with archive is done.
        # I suspect f...ing indexing service, but have not much choice rather than retrying.
        assert '\\' + TmpPath.ADDED_FOLDER + '\\' in tmppath
        nretries = TmpPath.MAX_RMTREE_RETRIES
        while True:
            nretries -= 1
            try:
                shutil.rmtree(tmppath)
                return
            except OSError as e:
                if nretries <= 0:
                    warn('Error trying to remove temp tree {}: {}. Will not retry, should be removed on restart'.format(
                        tmppath, e))
                    return
                warn('Error trying to remove temp tree {}: {}. Will retry in 1 sec, {} retries left'.format(
                    tmppath, e, nretries))
                time.sleep(1.)
