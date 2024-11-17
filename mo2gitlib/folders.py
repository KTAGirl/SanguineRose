from mo2gitlib.common import *


# mo2git is compatible with wj paths, which are os.abspath.lower()
#   all our dirs always end with '\\'

def _normalize_dir_path(path: str) -> str:
    path = os.path.abspath(path)
    assert '/' not in path
    assert not path.endswith('\\')
    return path.lower() + '\\'


def _is_normalized_dir_path(path: str) -> bool:
    return path == os.path.abspath(path).lower() + '\\'


def _normalize_file_path(path: str) -> str:
    assert not path.endswith('\\') and not path.endswith('/')
    path = os.path.abspath(path)
    assert '/' not in path
    return path.lower()


def _is_normalized_file_path(path: str) -> bool:
    return path == os.path.abspath(path).lower()


def _to_short_path(base: str, path: str) -> str:
    assert (path.startswith(base))
    return path[len(base):]


def _is_short_file_path(fpath: str) -> bool:
    assert not fpath.endswith('\\') and not fpath.endswith('/')
    if not fpath.islower(): return False
    return not os.path.isabs(fpath)


def _is_short_dir_path(fpath: str) -> bool:
    return fpath.islower() and fpath.endswith('\\') and not os.path.isabs(fpath)


def _is_normalized_file_name(fname: str) -> bool:
    if '/' in fname or '\\' in fname: return False
    return fname.islower()


def _normalize_config_dir_path(path: str, configdir: str) -> str:  # relative to config dir
    if os.path.isabs(path):
        return _normalize_dir_path(path)
    else:
        return _normalize_dir_path(configdir + path)


def _config_dir_path(path: str, configdir: str, config: dict[str, any]):
    path = _normalize_config_dir_path(path, configdir)
    path = path.replace('{CONFIGDIR}', configdir)
    replaced = False
    for key, val in config.items():
        if isinstance(val, str):
            newpath = path.replace('{' + key + '}', val)
            if newpath != path:
                replaced = True
                path = newpath

    if replaced:
        return _config_dir_path(path, configdir, config)
    else:
        return path


def make_dirs_for_file(fname: str) -> None:
    os.makedirs(os.path.split(fname)[0], exist_ok=True)


def folder_size(rootpath: str):
    total = 0
    for dirpath, dirnames, filenames in os.walk(rootpath):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            assert (not os.path.islink(fp))
            total += os.path.getsize(fp)
    return total


class Folders:
    configdir: str
    mo2: str
    downloads: list[str]
    ignore: list[str]
    cache: str
    tmp: str
    github: str
    own_mods: list[str]
    all_archive_names: list[str]
    mo2_excludes: list[str]
    mo2_reincludes: list[str]

    def __init__(self, jsonconfigfname: str, jsonconfig: dict[str, any], ignore: list[str]) -> None:
        self.configdir = _normalize_dir_path(os.path.split(jsonconfigfname)[0])
        aassert('mo2' in jsonconfig, lambda: "'mo2' must be present in config")
        mo2 = jsonconfig['mo2']
        aassert(isinstance(mo2, str), lambda: "config.'mo2' must be a string, got " + repr(mo2))
        self.mo2 = _config_dir_path(mo2, self.configdir, jsonconfig)

        if 'downloads' not in jsonconfig:
            dls = [self.mo2 + 'downloads\\']
        else:
            dls = jsonconfig['downloads']
        if isinstance(dls, str):
            dls = [dls]
        aassert(isinstance(dls, list), lambda: "'downloads' in config must be a string or a list, got " + repr(dls))
        self.downloads = [_config_dir_path(dl, self.configdir, jsonconfig) for dl in dls]

        self.ignore = [_normalize_dir_path(self.mo2 + ig) for ig in ignore]
        # print(self.ignore)
        # dbgWait()

        self.cache = _config_dir_path(jsonconfig.get('cache', self.configdir + '..\\mo2git.cache\\'), self.configdir,
                                      jsonconfig)
        self.tmp = _config_dir_path(jsonconfig.get('tmp', self.configdir + '..\\mo2git.tmp\\'), self.configdir,
                                    jsonconfig)
        self.github = _config_dir_path(jsonconfig.get('github', self.configdir), self.configdir, jsonconfig)

        self.own_mods = [Folders.normalize_file_name(om) for om in jsonconfig.get('ownmods', [])]

        toolinstallfiles = jsonconfig.get('toolinstallfiles', [])
        self.all_archive_names = [Folders.normalize_file_name(arname) for arname in toolinstallfiles]

        self.mo2_excludes = []
        self.mo2_reincludes = []

    def normalize_config_dir_path(self, path: str) -> str:
        return _normalize_config_dir_path(path, self.configdir)

    def normalize_config_file_path(self, path: str) -> str:
        spl = os.path.split(path)
        return _normalize_config_dir_path(spl[0], self.configdir) + spl[1]

    def add_archive_names(self, addarchivenames: list[str]) -> None:
        for arname in addarchivenames:
            self.all_archive_names.append(Folders.normalize_file_name(arname))

    def set_exclusions(self, mo2excludes: list[str], mo2reincludes: list[str]) -> None:
        self.mo2_excludes = [_normalize_dir_path(ex) for ex in mo2excludes]
        self.mo2_reincludes = [_normalize_dir_path(rein) for rein in mo2reincludes]

    def all_archive_names(self) -> Generator[str]:
        for arname in self.all_archive_names:
            yield arname

    def is_known_archive(self, arpath: str) -> bool:
        arname = Folders.normalize_file_name(os.path.split(arpath)[1])
        return arname in self.all_archive_names

    def is_own_mod(self, mod: str) -> bool:
        assert (_is_normalized_file_name(mod))
        return mod in self.own_mods

    def is_own_mods_file(self, fpath: str) -> bool:
        assert (_is_normalized_file_path(fpath))
        for ownmod in self.own_mods:
            ownpath = self.mo2 + 'mods\\' + ownmod + '\\'
            if fpath.startswith(ownpath):
                return True
        return False

    def all_own_mods(self) -> Generator[str]:
        for ownmod in self.own_mods:
            yield ownmod

    def is_mo2_exact_dir_included(self, dirpath: str) -> bool | None:
        # returns: None if ignored, False if mo2_excluded, 1 if regular (not excluded)
        # unlike isMo2FilePathIncluded(), does not return 2; instead, on receiving False, caller should call getReinclusions()
        # print(dirpath)
        assert _is_normalized_dir_path(dirpath)
        assert dirpath.startswith(self.mo2)
        if dirpath in self.ignore:
            return None
        return False if dirpath in self.mo2_excludes else True

    def is_mo2_file_path_included(self, fpath: str) -> bool | int:
        # returns: None if ignored, False if mo2_excluded, 1 if regular (not excluded), 2 if mo2_reincluded
        assert (_is_normalized_file_path(fpath))
        assert (fpath.startswith(self.mo2))
        included = True
        for ig in self.ignore:
            if fpath.startswith(ig):
                included = None
                break
        if included:
            for ex in self.mo2_excludes:
                if fpath.startswith(ex):
                    included = False
                    break
        if included:
            return 1
        for rein in self.mo2_reincludes:
            if fpath.startswith(rein):
                return 2
        return included

    def file_path_to_short_path(self, fpath: str) -> str:
        assert (_is_normalized_file_path(fpath))
        return _to_short_path(self.mo2, fpath)

    def dir_path_to_short_path(self, dirpath: str) -> str:
        assert (_is_normalized_dir_path(dirpath))
        return _to_short_path(self.mo2, dirpath)

    def short_file_path_to_path(self, fpath: str) -> str:
        assert (_is_short_file_path(fpath))
        return self.mo2 + fpath

    def short_dir_path_to_path(self, dirpath: str) -> str:
        assert (_is_short_dir_path(dirpath))
        return self.mo2 + dirpath

    @staticmethod
    def normalize_file_name(fname: str) -> str:
        assert ('\\' not in fname and '/' not in fname)
        return fname.lower()

    @staticmethod
    def is_normalized_file_path(fpath: str) -> bool:
        return _is_normalized_file_path(fpath)

    @staticmethod
    def normalize_file_path(fpath: str) -> str:
        return _normalize_file_path(fpath)

    @staticmethod
    def normalize_dir_path(fpath: str) -> str:
        return _normalize_dir_path(fpath)

    @staticmethod
    def is_normalized_dir_path(fpath: str) -> bool:
        return _is_normalized_dir_path(fpath)

    @staticmethod
    def normalize_archive_intra_path(fpath: str):
        assert (_is_short_file_path(fpath.lower()))
        return fpath.lower()
