import base64
import hashlib
import json
import pickle
from bisect import bisect_right
from stat import S_ISREG, S_ISLNK

from sanguine.install.install_common import *


### inter-file interfaces

class GameUniverse(enum.Enum):
    Skyrim = 0,
    Fallout = 1


def game_universe() -> GameUniverse:
    return GameUniverse.Skyrim  # TODO: read from project config


class FolderToCache:
    folder: str
    exdirs: list[str]

    @staticmethod
    def ok_to_construct(folder: str, exdirs: list[str]) -> bool:
        if __debug__:
            assert is_normalized_dir_path(folder)
            for x in exdirs:
                assert is_normalized_dir_path(x)
        for x in exdirs:
            if folder.startswith(x):
                return False
        return True

    def __init__(self, folder: str, exdirs: list[str] = None) -> None:
        assert FolderToCache.ok_to_construct(folder, exdirs)
        self.folder = folder
        self.exdirs = [] if exdirs is None else [x for x in exdirs if x.startswith(self.folder)]

    @staticmethod
    def filter_ex_dirs(exdirs: list[str], path: str) -> list[str]:
        return [x for x in exdirs if x.startswith(path)]

    @staticmethod
    def _is_path_included(path: str, root: str, exdirs: list[str]) -> bool:
        if not path.startswith(root):
            return False
        for x in exdirs:
            if path.startswith(x):
                return False
        return True

    def is_file_path_included(self, fpath: str) -> bool:
        assert is_normalized_file_path(fpath)
        return FolderToCache._is_path_included(fpath, self.folder, self.exdirs)

    @staticmethod
    def static_is_file_path_included(fpath: str, root: str, exdirs: list[str]) -> bool:
        assert is_normalized_file_path(fpath)
        return FolderToCache._is_path_included(fpath, root, exdirs)

    '''
    def is_dir_path_included(self,dpath: str) -> bool:
        assert is_normalized_dir_path(dpath)
        return self._is_path_included(dpath)
    '''


class FolderListToCache:
    folders: list[FolderToCache]

    def __init__(self, folders: list[FolderToCache]) -> None:
        self.folders = folders

    def is_file_path_included(self, fpath: str) -> bool:
        assert is_normalized_file_path(fpath)
        for f in self.folders:
            if f.is_file_path_included(fpath):
                return True
        return False

    def append(self, folder: FolderToCache) -> None:
        self.folders.append(folder)

    def __getitem__(self, item: int) -> FolderToCache:
        return self.folders[item]

    def __len__(self) -> int:
        return len(self.folders)


def calculate_file_hash(
        fpath: str) -> tuple[int, bytes]:  # using SHA-256, the fastest crypto-hash because of hardware instruction
    st = os.lstat(fpath)
    assert S_ISREG(st.st_mode) and not S_ISLNK(st.st_mode)
    h = hashlib.sha256()
    blocksize = 1048576
    fsize = 0
    with open(fpath, 'rb') as f:
        while True:
            bb = f.read(blocksize)
            if not bb:
                break
            h.update(bb)
            lbb = len(bb)
            assert lbb <= blocksize
            fsize += lbb

    # were there any changes while we were working?
    assert st.st_size == fsize
    st2 = os.lstat(fpath)
    assert st2.st_size == st.st_size
    assert st2.st_mtime == st.st_mtime
    return fsize, h.digest()


def truncate_file_hash(h: bytes) -> bytes:
    assert len(h) == 32
    return h[:9]


class GithubFolder:
    author: str
    project_name: str
    local_folder: str

    def __init__(self, author: str, project_name: str, local_folder: str) -> None:
        self.author = author
        self.project_name = project_name
        self.local_folder = local_folder


### generic helpers

class Val:
    val: any

    def __init__(self, initval: any) -> None:
        self.val = initval

    def __str__(self) -> str:
        return str(self.val)


def add_to_dict_of_lists(dicttolook: dict[any, list[any]], key: any, val: any) -> None:
    if key not in dicttolook:
        dicttolook[key] = [val]
    else:
        dicttolook[key].append(val)


class FastSearchOverPartialStrings:
    _strings: list[tuple[str, int, any]]

    def __init__(self, src: list[tuple[str, any]]) -> None:
        self._strings = []
        for s in src:
            self._strings.append((s[0], -1, s[1]))
        self._strings.sort(key=lambda x2: x2[0])

        # filling previdx
        prevrefs: list[int] = []
        for i in range(len(self._strings)):
            (p, _, val) = self._strings[i]
            if len(prevrefs) == 0:
                self._strings[i] = (p, -1, val)
                prevrefs.append(i)
            elif p.startswith(self._strings[prevrefs[-1]][0]):
                self._strings[i] = (p, prevrefs[-1], val)
                prevrefs.append(i)
            else:
                while True:
                    if p.startswith(self._strings[prevrefs[-1]][0]):
                        self._strings[i] = (p, prevrefs[-1], val)
                        prevrefs.append(i)
                        break
                    prevrefs = prevrefs[:-1]
                    if len(prevrefs) == 0:
                        self._strings[i] = (p, -1, val)
                        break

    def find_val_for_str(self, s: str) -> tuple[str, any] | None:
        # k = (s, -1, None)
        idx = bisect_right(self._strings, s, key=lambda x2: x2[0])
        if idx == 0:
            return None
        prev = self._strings[idx - 1]
        if s.startswith(prev[0]):
            return prev[0], prev[2]

        while True:
            if prev[1] < 0:
                return None
            prev = self._strings[prev[1]]
            if s.startswith(prev[0]):
                return prev[0], prev[2]


### JSON-related

def to_json_hash(h: bytes) -> str:
    b64 = base64.b64encode(h).decode('ascii')
    # print(b64)
    s = b64.rstrip('=')
    # assert from_json_hash(s) == h
    return s


def from_json_hash(s: str) -> bytes:
    ntopad = (3 - (len(s) % 3)) % 3
    s += '=='[:ntopad]
    b = base64.b64decode(s)
    return b


class _JsonEncoder(json.JSONEncoder):
    def encode(self, o: any) -> any:
        return json.JSONEncoder.encode(self, self.default(o))

    def default(self, o: any) -> any:
        if isinstance(o, bytes):
            return base64.b64encode(o).decode('ascii')
        elif isinstance(o, Callable):
            return o.__name__
        elif isinstance(o, dict):
            return self._adjust_dict(o)
        elif o is None or isinstance(o, str) or isinstance(o, tuple) or isinstance(o, list):
            return o
        elif isinstance(o, object):
            return o.__dict__
        else:
            return o

    def _adjust_dict(self, d: dict[str, any]) -> dict[str, any]:
        out = {}
        for k, v in d.items():
            if isinstance(k, bytes):
                k = base64.b64encode(k).decode('ascii')
            out[k] = self.default(v)
        return out


def as_json(data: any) -> str:
    return _JsonEncoder().encode(data)


### file-related helpers

def open_3rdparty_txt_file(fname: str) -> typing.TextIO:
    return open(fname, 'rt', encoding='cp1252', errors='replace')


def open_3rdparty_txt_file_w(fname) -> typing.TextIO:
    return open(fname, 'wt', encoding='cp1252')


def read_dict_from_pickled_file(fpath: str) -> dict[str, any]:
    try:
        with open(fpath, 'rb') as rfile:
            return pickle.load(rfile)
    except Exception as e:
        warn('error loading ' + fpath + ': ' + str(e) + '. Will continue without it')
        return {}


### normalized stuff

#  all our dir and file names are always in lowercase, and always end with '\\'

def normalize_dir_path(path: str) -> str:
    path = os.path.abspath(path)
    assert '/' not in path
    assert not path.endswith('\\')
    return path.lower() + '\\'


def is_normalized_dir_path(path: str) -> bool:
    return path == os.path.abspath(path).lower() + '\\'


def normalize_file_path(path: str) -> str:
    assert not path.endswith('\\') and not path.endswith('/')
    path = os.path.abspath(path)
    assert '/' not in path
    return path.lower()


def is_normalized_file_path(path: str) -> bool:
    return path == os.path.abspath(path).lower()


def to_short_path(base: str, path: str) -> str:
    assert path.startswith(base)
    return path[len(base):]


def is_short_file_path(fpath: str) -> bool:
    assert not fpath.endswith('\\') and not fpath.endswith('/')
    if not fpath.islower(): return False
    return not os.path.isabs(fpath)


def is_short_dir_path(fpath: str) -> bool:
    return fpath.islower() and fpath.endswith('\\') and not os.path.isabs(fpath)


def is_normalized_file_name(fname: str) -> bool:
    if '/' in fname or '\\' in fname: return False
    return fname.islower()


def normalize_file_name(fname: str) -> str:
    assert '\\' not in fname and '/' not in fname
    return fname.lower()


def normalize_archive_intra_path(fpath: str):
    assert is_short_file_path(fpath.lower())
    return fpath.lower()


##### esx stuff

def is_esl_flagged(filename: str) -> bool:
    with open(filename, 'rb') as f:
        buf = f.read(10)
        return (buf[0x9] & 0x02) == 0x02


def is_esx(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext == '.esl' or ext == '.esp' or ext == '.esm'


'''
### unused, candidates for removal
def escape_json(s: any) -> str:
    return json.dumps(s)

def all_esxs(mod: str, mo2: str) -> list[str]:
    esxs = glob.glob(mo2 + 'mods/' + mod + '/*.esl')
    esxs = esxs + glob.glob(mo2 + 'mods/' + mod + '/*.esp')
    esxs = esxs + glob.glob(mo2 + 'mods/' + mod + '/*.esm')
    return esxs

def read_dict_from_json_file(fpath: str) -> dict[str, any]:
    try:
        with open(fpath, 'rt', encoding='utf-8') as rfile:
            return json.load(rfile)
    except Exception as e:
        warn('error loading ' + fpath + ': ' + str(e) + '. Will continue without it')
        return {}
'''
