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
    path = path.replace('{CONFIG-DIR}', configdir)
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


def _normalize_mo2_dir_path(path: str, mo2dir: str) -> str:  # relative to mo2 dir
    if os.path.isabs(path):
        out = _normalize_dir_path(path)
    else:
        out = _normalize_dir_path(mo2dir + path)
    abort_if_not(out.startswith(mo2dir), lambda: 'expected path within mo2, got ' + repr(path))
    return out


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
    config_dir: str
    mo2_dir: str
    download_dirs: list[str]
    ignore_dirs: list[str]
    cache_dir: str
    tmp_dir: str
    github_dir: str
    own_mod_names: list[str]

    def __init__(self, jsonconfigfname: str, jsonconfig: dict[str, any]) -> None:
        self.config_dir = _normalize_dir_path(os.path.split(jsonconfigfname)[0])
        abort_if_not('mo2' in jsonconfig, lambda: "'mo2' must be present in config")
        mo2 = jsonconfig['mo2']
        abort_if_not(isinstance(mo2, str), lambda: "config.'mo2' must be a string, got " + repr(mo2))
        self.mo2_dir = _config_dir_path(mo2, self.config_dir, jsonconfig)

        if 'downloads' not in jsonconfig:
            dls = [self.mo2_dir + 'downloads\\']
        else:
            dls = jsonconfig['downloads']
        if isinstance(dls, str):
            dls = [dls]
        abort_if_not(isinstance(dls, list),
                     lambda: "'downloads' in config must be a string or a list, got " + repr(dls))
        self.download_dirs = [_config_dir_path(dl, self.config_dir, jsonconfig) for dl in dls]

        ignores = jsonconfig.get('ignores', ['{DEFAULT-IGNORES}'])
        abort_if_not(isinstance(ignores, list), lambda: "'ignores' in config must be a list, got " + repr(ignores))
        self.ignore_dirs = []
        for ignore in ignores:
            if ignore == '{DEFAULT-IGNORES}':
                self.ignore_dirs += [self.mo2_dir + defignore for defignore in [
                    'plugins\\data\\RootBuilder',
                    'crashDumps',
                    'logs',
                    'webcache',
                    'overwrite\\Root\\Logs',
                    'overwrite\\ShaderCache'
                ]]
            else:
                self.ignore_dirs.append(_normalize_mo2_dir_path(ignore, self.mo2_dir))

        self.cache_dir = _config_dir_path(jsonconfig.get('cache', self.config_dir + '..\\mo2git.cache\\'),
                                          self.config_dir,
                                          jsonconfig)
        self.tmp_dir = _config_dir_path(jsonconfig.get('tmp', self.config_dir + '..\\mo2git.tmp\\'), self.config_dir,
                                        jsonconfig)
        self.github_dir = _config_dir_path(jsonconfig.get('github', self.config_dir), self.config_dir, jsonconfig)

        self.own_mod_names = [Folders.normalize_file_name(om) for om in jsonconfig.get('ownmods', [])]

    def normalize_config_dir_path(self, path: str) -> str:
        return _normalize_config_dir_path(path, self.config_dir)

    def normalize_config_file_path(self, path: str) -> str:
        spl = os.path.split(path)
        return _normalize_config_dir_path(spl[0], self.config_dir) + spl[1]

    def all_own_mods(self) -> Generator[str]:
        for ownmod in self.own_mod_names:
            yield ownmod

    def all_mo2_own_mod_dirs(self) -> Generator[str]:
        for ownmod in self.own_mod_names:
            out = self.mo2_dir + ownmod
            assert Folders.is_normalized_dir_path(out)
            yield out

    def all_git_own_mod_dirs(self) -> Generator[str]:
        for ownmod in self.own_mod_names:
            out = self.github_dir + '\\mo2\\mods' + ownmod
            assert Folders.is_normalized_dir_path(out)
            yield out

    # TODO: all_enabled_mod_dirs()

    def file_path_to_short_path(self, fpath: str) -> str:
        assert (_is_normalized_file_path(fpath))
        return _to_short_path(self.mo2_dir, fpath)

    def dir_path_to_short_path(self, dirpath: str) -> str:
        assert (_is_normalized_dir_path(dirpath))
        return _to_short_path(self.mo2_dir, dirpath)

    def short_file_path_to_path(self, fpath: str) -> str:
        assert (_is_short_file_path(fpath))
        return self.mo2_dir + fpath

    def short_dir_path_to_path(self, dirpath: str) -> str:
        assert (_is_short_dir_path(dirpath))
        return self.mo2_dir + dirpath

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
