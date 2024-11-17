import importlib
import inspect
from abc import abstractmethod

from mo2gitlib.common import *


def _load_plugins(plugindir : str, basecls:any, found:Callable[[any],None]) -> None:
    # plugindir is relative to the path of this very file
    thisdir = os.path.split(os.path.abspath(__file__))[0] + '/'
    # print(thisdir)
    for py in glob.glob(thisdir+plugindir+'*.py'):
        # print(py)
        modulename = os.path.splitext(os.path.split(py)[1])[0]
        if modulename == '__init__' or modulename.startswith('_'):
            continue
        # print(modulename)
        module = importlib.import_module('mo2gitlib.'+plugindir.replace('/','.')+modulename)
        ok = False
        for name, obj in inspect.getmembers(module):
            if inspect.isclass(obj):
                cls = obj
                mro = inspect.getmro(cls)
                if len(mro) >= 2:
                    parent = mro[1]
                    if parent is basecls:
                        plugin = cls()
                        found(plugin)
                        ok = True
        if not ok:
            warn('no class derived from '+str(basecls)+' found in '+py)

### archive plugins

class ArchivePluginBase:
    def __init__(self) -> None:
        pass
       
    @abstractmethod
    def extensions(self) -> list[str]:
        pass
        
    @abstractmethod
    def extract(self,archive:str,list_of_files:list[str],targetpath:str) -> None:
        pass
        
    @abstractmethod
    def extract_all(self, archive:str, targetpath:str) -> None:
        pass

_archive_plugins: dict[str,ArchivePluginBase] = {} # file_extension -> ArchivePluginBase
_archive_exts:list[str] = []

def _found_archive_plugin(plugin:"ArchivePluginBase"):
    global _archive_plugins
    global _archive_exts
    for ext in plugin.extensions():
        _archive_plugins[ext]=plugin
        assert ext not in _archive_exts
        _archive_exts.append(ext)

_load_plugins('plugins/archive/', ArchivePluginBase, lambda plugin: _found_archive_plugin(plugin))

def archive_plugin_for(path:str) -> ArchivePluginBase:
    global _archive_plugins
    ext=os.path.splitext(path)[1].lower()
    return _archive_plugins.get(ext)
    
def all_archive_plugins_extensions() -> list[str]:
    global _archive_exts
    return _archive_exts