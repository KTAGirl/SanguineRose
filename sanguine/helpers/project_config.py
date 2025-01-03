import re

import json5

from sanguine.common import *
from sanguine.helpers.plugin_handler import load_plugins


def _normalize_config_dir_path(path: str, configdir: str) -> str:  # relative to config dir
    if os.path.isabs(path):
        return normalize_dir_path(path)
    else:
        return normalize_dir_path(configdir + path)


def config_dir_path(path: str, configdir: str, config: dict[str, any]):
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
        return config_dir_path(path, configdir, config)
    else:
        return path


def normalize_vfs_dir_path(path: str, vfsdir: str) -> str:  # relative to vfs dir
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
    mod_manager_name: str

    def __init__(self, modmanagername: str) -> None:
        self.mod_manager_name = modmanagername

    @abstractmethod
    def parse_config_section(self, section: dict[str, any], configdir: str, fullconfig: dict[str, any],
                             download_dirs: list[str]) -> None:
        pass

    @abstractmethod
    def default_download_dirs(self) -> list[str]:
        pass

    @abstractmethod
    def active_vfs_folders(self) -> FolderListToCache:
        pass


class ModManagerPluginBase(ABC):
    def __init__(self) -> None:
        pass

    @abstractmethod
    def mod_manager_name(self) -> str:
        pass

    @abstractmethod
    def config_factory(self) -> ModManagerConfig:
        pass


_modmanager_plugins: list[ModManagerPluginBase] = []


def _found_plugin(plugin: ModManagerPluginBase):
    global _modmanager_plugins
    _modmanager_plugins.append(plugin)


load_plugins('plugins/modmanager/', ModManagerPluginBase, lambda plugin: _found_plugin(plugin))


def _find_config(name: str) -> ModManagerConfig | None:
    global _modmanager_plugins
    for mm in _modmanager_plugins:
        if mm.mod_manager_name() == name:
            mmc = mm.config_factory()
            assert mmc.mod_manager_name == name
            return mmc
    return None


def _all_configs_string() -> str:
    global _modmanager_plugins
    out = ''
    for mm in _modmanager_plugins:
        if out != '':
            out += ','
        out += "'" + mm.mod_manager_name() + "'"
    return out


def _load_github_folder(dirpath: str) -> GithubFolder:
    assert is_normalized_dir_path(dirpath)
    abort_if_not(os.path.isfile(dirpath + '.git\\config'), lambda: '{}.git\\config not found'.format(dirpath))
    pattern = re.compile(r'\s*url\s*=\s*https://github.com/([^/]*)/([^\n]*)')
    with open_3rdparty_txt_file(dirpath + '.git\\config') as f:
        author = None
        project = None
        for line in f:
            m = pattern.match(line)
            if m:
                author = m.group(1)
                prj = m.group(2)
                if prj.endswith('.git'):
                    project = prj[:-len('.git')]
        abort_if_not(author is not None and project is not None, 'author or project not found for {}'.format(dirpath))

        return GithubFolder(author, project, dirpath)


class ProjectConfig:
    config_dir: str
    mod_manager_config: ModManagerConfig
    download_dirs: list[str]
    cache_dir: str
    tmp_dir: str
    github_folders: list[GithubFolder]
    own_mod_names: list[str]

    # TODO: check that sanguine-rose itself, cache_dir, and tmp_dir don't overlap with any of the dirs
    def __init__(self, jsonconfigfname: str) -> None:
        self.config_dir = normalize_dir_path(os.path.split(jsonconfigfname)[0])
        with (open_3rdparty_txt_file(jsonconfigfname) as f):
            jsonconfig = json5.loads(f.read())

            abort_if_not('modmanager' in jsonconfig, "'modmanager' must be present in config")
            modmanager = jsonconfig['modmanager']
            self.mod_manager_config = _find_config(modmanager)
            abort_if_not(self.mod_manager_config is not None,
                         lambda: "config.modmanager must be one of [{}]".format(_all_configs_string()))

            abort_if_not(self.mod_manager_config.mod_manager_name in jsonconfig,
                         lambda: "'{}' must be present in config for modmanager={}".format(
                             self.mod_manager_config.mod_manager_name,
                             self.mod_manager_config.mod_manager_name))
            mmc_config = jsonconfig[self.mod_manager_config.mod_manager_name]
            abort_if_not(isinstance(mmc_config, dict),
                         lambda: "config.{} must be a dictionary, got {}".format(
                             self.mod_manager_config.mod_manager_name,
                             repr(mmc_config)))

            if 'downloads' not in jsonconfig:
                dls = self.mod_manager_config.default_download_dirs()
            else:
                dls = jsonconfig['downloads']
            if isinstance(dls, str):
                dls = [dls]
            abort_if_not(isinstance(dls, list),
                         lambda: "'downloads' in config must be a string or a list, got " + repr(dls))
            self.download_dirs = [config_dir_path(dl, self.config_dir, jsonconfig) for dl in dls]

            self.mod_manager_config.parse_config_section(mmc_config, self.config_dir, jsonconfig, self.download_dirs)

            self.cache_dir = config_dir_path(jsonconfig.get('cache', self.config_dir + '..\\sanguine.cache\\'),
                                             self.config_dir,
                                             jsonconfig)
            self.tmp_dir = config_dir_path(jsonconfig.get('tmp', self.config_dir + '..\\sanguine.tmp\\'),
                                           self.config_dir,
                                           jsonconfig)

            gh = None
            if 'github' not in jsonconfig:
                gh = [self.config_dir]
            else:
                gh = jsonconfig['github']
            if isinstance(gh, str):
                gh = [gh]
            abort_if_not(isinstance(gh, list),
                         lambda: "'gh' in config must be a string or a list, got " + repr(gh))
            self.github_folders = [_load_github_folder(gf) for gf in gh]
            assert 'githubroot' in jsonconfig
            self.github_root = config_dir_path(jsonconfig['githubroot'], self.config_dir, jsonconfig)

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
