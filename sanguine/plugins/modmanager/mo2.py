from sanguine.common import *
from sanguine.modlist import ModList
from sanguine.project_config import ModManagerConfig, ModManagerPluginBase, _config_dir_path, _normalize_vfs_dir_path


class Mo2Plugin(ModManagerPluginBase):
    def mod_manager_name(self) -> str:
        return 'mo2'

    def config_factory(self) -> ModManagerConfig:
        return Mo2ProjectConfig(self.mod_manager_name())


class Mo2ProjectConfig(ModManagerConfig):
    mo2dir: FolderToCache | None
    master_profile: str | None
    generated_profiles: list[str] | None
    master_modlist: ModList | None

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.mo2dir = None
        self.master_profile = None
        self.generated_profiles = None
        self.master_modlist = None

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
