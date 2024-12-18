import re

from sanguine.common import *
from sanguine.folder_cache import FolderToCache
from sanguine.modlist import ModList


def _normalize_config_dir_path(path: str, configdir: str) -> str:  # relative to config dir
    if os.path.isabs(path):
        return normalize_dir_path(path)
    else:
        return normalize_dir_path(configdir + path)


def _config_dir_path(path: str, configdir: str, config: dict[str, any]):
    path = _normalize_config_dir_path(path, configdir)
    path = path.replace('{CONFIG-DIR}', configdir)
    replaced = False
    pattern = re.compile(r'\{(.*)}')
    m = pattern.search(path)
    if m:
        found = m.group(1)
        spl = found.split('.')
        cur = config
        for name in spl:
            abort_if_not(name in cur, lambda: 'unable to resolve {} in {}'.format(found, configdir))
            cur = cur[name]
        abort_if_not(isinstance(cur, str), lambda: '{} in {} must be a string'.format(found, configdir))
        path = pattern.sub(cur, path)
        replaced = True

    if replaced:
        return _config_dir_path(path, configdir, config)
    else:
        return path


def _normalize_vfs_dir_path(path: str, vfsdir: str) -> str:  # relative to vfs dir
    if os.path.isabs(path):
        out = normalize_dir_path(path)
    else:
        out = normalize_dir_path(vfsdir + path)
    abort_if_not(out.startswith(vfsdir), lambda: 'expected path within vfs, got ' + repr(path))
    return out


def make_dirs_for_file(fname: str) -> None:
    os.makedirs(os.path.split(fname)[0], exist_ok=True)


def folder_size(rootpath: str):
    total = 0
    for dirpath, dirnames, filenames in os.walk(rootpath):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            assert not os.path.islink(fp)
            total += os.path.getsize(fp)
    return total


class ModManagerConfig:
    def __init__(self) -> None:
        pass

    @abstractmethod
    def mod_manager_name(self) -> str:  # also used as config section name
        pass

    @abstractmethod
    def parse_config_section(self, section: dict[str, any], configdir: str, fullconfig: dict[str, any]) -> None:
        pass

    @abstractmethod
    def default_download_dirs(self) -> list[str]:
        pass

    @abstractmethod
    def active_vfs_folders(self) -> FolderListToCache:
        pass


class Mo2ProjectConfig(ModManagerConfig):
    mo2dir: FolderToCache | None
    master_profile: str | None
    generated_profiles: list[str] | None
    master_modlist: ModList | None

    def __init__(self) -> None:
        super().__init__()
        self.mo2dir = None
        self.master_profile = None
        self.generated_profiles = None
        self.master_modlist = None

    def mod_manager_name(self) -> str:
        return 'mo2'

    def parse_config_section(self, section: dict[str, any], configdir: str, fullconfig: dict[str, any]) -> None:
        abort_if_not('mo2dir' in section, "'mo2dir' must be present in config.mo2 for modmanager=mo2")
        mo2dir = _config_dir_path(section['mo2dir'], configdir, fullconfig)
        abort_if_not(isinstance(mo2dir, str), 'config.mo2.mo2dir must be a string')

        ignores = section.get('ignores', ['{DEFAULT-MO2-IGNORES}'])
        abort_if_not(isinstance(ignores, list), lambda: "config.mo2.ignores must be a list, got " + repr(ignores))
        ignore_dirs = []
        for ignore in ignores:
            if ignore == '{DEFAULT-MO2-IGNORES}':
                ignore_dirs += [normalize_dir_path(mo2dir + defignore) for defignore in [
                    'plugins\\data\\RootBuilder',
                    'crashDumps',
                    'logs',
                    'webcache',
                    'overwrite\\Root\\Logs',
                    'overwrite\\ShaderCache'
                ]]
            else:
                ignore_dirs.append(_normalize_vfs_dir_path(ignore, mo2dir))

        assert self.mo2dir is None
        self.mo2dir = FolderToCache(mo2dir, ignore_dirs)

        assert self.master_profile is None
        assert self.generated_profiles is None
        self.master_profile = fullconfig.get('masterprofile')
        abort_if_not(self.master_profile is not None and isinstance(self.master_profile, str),
                     lambda: "'masterprofile' in config must be a string, got " + repr(self.master_profile))
        abort_if_not(os.path.isdir(self.mo2dir.folder + 'profiles\\' + self.master_profile))

        self.generated_profiles = fullconfig.get('generatedprofiles')
        abort_if_not(self.generated_profiles is not None and isinstance(self.generated_profiles, list),
                     lambda: "'genprofiles' in config must be a list, got " + repr(self.generated_profiles))
        for gp in self.generated_profiles:
            abort_if_not(os.path.isdir(self.mo2dir.folder + 'profiles\\' + gp))

        assert self.master_modlist is None
        self.master_modlist = ModList(self.mo2dir.folder + 'profiles\\' + self.master_profile + '\\')

    def active_vfs_folders(self) -> FolderListToCache:
        out: FolderListToCache = [self.mo2dir]
        for mod in self.master_modlist.all_enabled():
            out.append(FolderToCache(self.mo2dir.folder + 'mods\\' + mod + '\\', self.mo2dir.exdirs))
        return out

    def default_download_dirs(self) -> list[str]:
        return ['{mo2.mo2dir}downloads\\']


_mod_manager_configs: list[ModManagerConfig] = [Mo2ProjectConfig()]


def _find_config(name: str) -> ModManagerConfig | None:
    global _mod_manager_configs
    for mmc in _mod_manager_configs:
        if mmc.mod_manager_name() == name:
            return mmc
    return None


def _all_configs_string() -> str:
    global _mod_manager_configs
    out = ''
    for mmc in _mod_manager_configs:
        if out != '':
            out += ','
        out += "'" + mmc.mod_manager_name() + "'"
    return out


class ProjectConfig:
    config_dir: str
    # vfs_dir: str
    mod_manager_config: ModManagerConfig
    download_dirs: list[str]
    # ignore_dirs: list[str]
    cache_dir: str
    tmp_dir: str
    github_dir: str
    own_mod_names: list[str]

    # TODO: check that sanguine-rose itself, cache_dir, and tmp_dir don't overlap with any of the dirs
    def __init__(self, jsonconfigfname: str, jsonconfig: dict[str, any]) -> None:
        self.config_dir = normalize_dir_path(os.path.split(jsonconfigfname)[0])

        abort_if_not('modmanager' in jsonconfig, "'modmanager' must be present in config")
        modmanager = jsonconfig['modmanager']
        mmc = _find_config(modmanager)
        abort_if_not(mmc is not None, lambda: "config.modmanager must be one of [{}]".format(_all_configs_string()))

        abort_if_not(mmc.mod_manager_name() in jsonconfig,
                     lambda: "'{}' must be present in config for modmanager={}".format(mmc.mod_manager_name(),
                                                                                       mmc.mod_manager_name()))
        mmc_config = jsonconfig[mmc.mod_manager_name()]
        abort_if_not(isinstance(mmc_config, dict),
                     lambda: "config.{} must be a dictionary, got {}".format(mmc.mod_manager_name(), repr(mmc_config)))
        mmc.parse_config_section(mmc_config, self.config_dir, jsonconfig)

        if 'downloads' not in jsonconfig:
            dls = mmc.default_download_dirs()
        else:
            dls = jsonconfig['downloads']
        if isinstance(dls, str):
            dls = [dls]
        abort_if_not(isinstance(dls, list),
                     lambda: "'downloads' in config must be a string or a list, got " + repr(dls))
        self.download_dirs = [_config_dir_path(dl, self.config_dir, jsonconfig) for dl in dls]

        self.cache_dir = _config_dir_path(jsonconfig.get('cache', self.config_dir + '..\\sanguine.cache\\'),
                                          self.config_dir,
                                          jsonconfig)
        self.tmp_dir = _config_dir_path(jsonconfig.get('tmp', self.config_dir + '..\\sanguine.tmp\\'), self.config_dir,
                                        jsonconfig)
        self.github_dir = _config_dir_path(jsonconfig.get('github', self.config_dir), self.config_dir, jsonconfig)

        self.own_mod_names = [normalize_file_name(om) for om in jsonconfig.get('ownmods', [])]

    '''
    def normalize_config_dir_path(self, path: str) -> str:
        return _normalize_config_dir_path(path, self.config_dir)

    def normalize_config_file_path(self, path: str) -> str:
        spl = os.path.split(path)
        return _normalize_config_dir_path(spl[0], self.config_dir) + spl[1]

    def file_path_to_short_path(self, fpath: str) -> str:
        assert is_normalized_file_path(fpath)
        return to_short_path(self.mo2_dir, fpath)

    def dir_path_to_short_path(self, dirpath: str) -> str:
        assert is_normalized_dir_path(dirpath)
        return to_short_path(self.mo2_dir, dirpath)

    def short_file_path_to_path(self, fpath: str) -> str:
        assert is_short_file_path(fpath)
        return self.mo2_dir + fpath

    def short_dir_path_to_path(self, dirpath: str) -> str:
        assert is_short_dir_path(dirpath)
        return self.mo2_dir + dirpath
    '''

    def active_vfs_folders(self) -> FolderListToCache:
        return self.mod_manager_config.active_vfs_folders()
