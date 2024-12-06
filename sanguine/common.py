# common is used by sanguine_install_helpers, so it must not import any installable modules

import base64
import glob
import json
import logging
import logging.handlers
import multiprocessing
import os
import pickle
import shutil
import time
import traceback
import typing
# noinspection PyUnresolvedReferences
from collections.abc import Callable, Generator, Iterable
# noinspection PyUnresolvedReferences
from types import TracebackType

Type = typing.Type


def dbgwait() -> None:
    input("Press Enter to continue.")


def dbgfirst(data: any) -> any:
    if isinstance(data, list):
        print(len(data))
        return data[0]
    elif isinstance(data, dict):
        # print(len(data))
        it = iter(data)
        key = next(it)
        # print(key)
        return data[key]
    else:
        return data


class Mo2gitError(Exception):
    pass


def abort_if_not(cond: bool,
                 f: Callable[
                     [], str] = None):  # 'always assert', even if __debug__ is False. f is a lambda printing error message before throwing
    if not cond:
        msg = 'abort_if_not() failed'
        if f is not None:
            msg += ':' + f()
        where = traceback.extract_stack(limit=2)[0]
        critical(msg + ' @line ' + str(where.lineno) + ' of ' + os.path.split(where.filename)[1])
        raise Mo2gitError(msg)


### logging

class _SanguineFormatter(logging.Formatter):
    FORMAT: str = '[%(levelname)s]: %(message)s (%(filename)s:%(lineno)d)'
    FORMATS: dict[int, str] = {
        logging.DEBUG: '\x1b[38;20m' + FORMAT + '\x1b[0m',
        logging.INFO: '\x1b[32m' + FORMAT + '\x1b[0m',
        logging.WARNING: '\x1b[93;20m' + FORMAT + '\x1b[0m',
        logging.ERROR: FORMAT,  # not really using it (yet?)
        logging.CRITICAL: '\x1b[91;1m' + FORMAT + '\x1b[0m'
    }

    def format(self, record) -> str:
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


_FORMAT: str = '[%(levelname)s@%(asctime)s]: %(message)s (%(filename)s:%(lineno)d)'


def _html_format(color: str, bold: bool = False) -> str:
    return '<div style="margin: -1em -1em; padding: 0.5em 1em; white-space:nowrap; font-size:1.2em; background-color:black; color:' + color + (
        '; font-weight:600' if bold else '') + '; font-family:monospace;">' + _FORMAT + '</div>'


class _SanguineFileFormatter(logging.Formatter):
    FORMATS: dict[int, str] = {
        logging.DEBUG: _html_format('#888888'),
        logging.INFO: _html_format('#008000'),
        logging.WARNING: _html_format('#e5bf00'),
        logging.ERROR: _html_format('red'),  # not really using it (yet?)
        logging.CRITICAL: _html_format('#ff0000', True)
    }

    def __init__(self) -> None:
        super().__init__(datefmt='%H:%M:%S')

    def format(self, record) -> str:
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


_logger = multiprocessing.get_logger()
_logger.setLevel(logging.DEBUG if __debug__ else logging.INFO)

_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.DEBUG)
_console_handler.setFormatter(_SanguineFormatter())

_logger.addHandler(_console_handler)


def add_file_logging(fpath: str) -> None:
    global _logger
    file_handler = logging.handlers.RotatingFileHandler(fpath, mode='w', backupCount=5)
    file_handler.setLevel(logging.DEBUG if __debug__ else logging.INFO)
    file_handler.setFormatter(_SanguineFileFormatter())
    _logger.addHandler(file_handler)


def warn(msg: str) -> None:
    global _logger
    _logger.warning(msg, stacklevel=2)


def info(msg: str) -> None:
    global _logger
    _logger.info(msg, stacklevel=2)


def critical(msg: str) -> None:
    global _logger
    _logger.critical(msg, stacklevel=2)


def debug(msg: str) -> None:
    if not __debug__:
        return
    global _logger
    _logger.debug(msg, stacklevel=2)


###

class JsonEncoder(json.JSONEncoder):
    def default(self, o: any) -> any:
        if isinstance(o, bytes):
            return base64.b64encode(o).decode('ascii')
        elif isinstance(o, object):
            return o.__dict__
        else:
            return o


def open_3rdparty_txt_file(fname: str) -> typing.TextIO:
    return open(fname, 'rt', encoding='cp1252', errors='replace')


def open_3rdparty_txt_file_w(fname) -> typing.TextIO:
    return open(fname, 'wt', encoding='cp1252')


def escape_json(s: any) -> str:
    return json.dumps(s)


def is_esl_flagged(filename: str) -> bool:
    with open(filename, 'rb') as f:
        buf = f.read(10)
        return (buf[0x9] & 0x02) == 0x02


def add_to_dict_of_lists(dicttolook: dict[list[any]], key: any, val: any) -> None:
    if key not in dicttolook:
        dicttolook[key] = [val]
    else:
        dicttolook[key].append(val)


def is_esx(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext == '.esl' or ext == '.esp' or ext == '.esm'


def all_esxs(mod: str, mo2: str) -> list[str]:
    esxs = glob.glob(mo2 + 'mods/' + mod + '/*.esl')
    esxs = esxs + glob.glob(mo2 + 'mods/' + mod + '/*.esp')
    esxs = esxs + glob.glob(mo2 + 'mods/' + mod + '/*.esm')
    return esxs


def read_dict_from_pickled_file(fpath: str) -> dict[str, any]:
    try:
        with open(fpath, 'rb') as rfile:
            return pickle.load(rfile)
    except Exception as e:
        warn('error loading ' + fpath + ': ' + str(e) + '. Will continue without it')
        return {}


def read_dict_from_json_file(fpath: str) -> dict[str, any]:
    try:
        with open(fpath, 'rt', encoding='utf-8') as rfile:
            return json.load(rfile)
    except Exception as e:
        warn('error loading ' + fpath + ': ' + str(e) + '. Will continue without it')
        return {}


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


class Val:
    val: any

    def __init__(self, initval: any) -> None:
        self.val = initval

    def __str__(self) -> str:
        return str(self.val)
