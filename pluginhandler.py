import os
import glob
import importlib
import inspect

# import wj2git.plugins.archives
from wj2git.debug import dbgWait

def _loadPlugins(plugindir,basecls,found):
    # plugindir is relative to the path of this very file
    thisdir = os.path.split(os.path.abspath(__file__))[0] + '/'
    # print(thisdir)
    for py in glob.glob(thisdir+plugindir+'*.py'):
        # print(py)
        modulename = os.path.splitext(os.path.split(py)[1])[0]
        if modulename == '__init__':
            continue
        # print(modulename)
        module = importlib.import_module('wj2git.plugins.archives.'+modulename)
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
            print('WARNING: no class derived from '+str(basecls)+' found in '+py)

### archive plugins

class ArchivePluginBase:
    def __init__(self):
        pass
       
    # @abstractmethod
    def extensions(self):
        pass
        
    # @abstractmethod
    def extract(self,archive,list_of_files,targetpath):
        pass

def _foundArchivePlugin(archiveplugins,plugin):
    for ext in plugin.extensions():
        archiveplugins[ext]=plugin  

archiveplugins = {} # file_extension -> ArchivePluginBase
_loadPlugins('plugins/archives/',ArchivePluginBase,lambda plugin: _foundArchivePlugin(archiveplugins,plugin))
print(archiveplugins)
# dbgWait()