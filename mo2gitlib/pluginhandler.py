import os
import glob
import importlib
import inspect

from mo2gitlib.common import *

def _loadPlugins(plugindir,basecls,found):
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
        
     # @abstractmethod
    def extractAll(self,archive,targetpath):
        pass

def _foundArchivePlugin(archiveplugins,plugin):
    for ext in plugin.extensions():
        archiveplugins[ext]=plugin  

archiveplugins = {} # file_extension -> ArchivePluginBase
archiveexts = []
_loadPlugins('plugins/archive/',ArchivePluginBase,lambda plugin: _foundArchivePlugin(archiveplugins,plugin))
#print(archiveplugins)
for ext in archiveplugins:
    assert(ext not in archiveexts)
    archiveexts.append(ext)
#print(archiveexts)
# dbgWait()

def archivePluginFor(path):
    ext=os.path.splitext(path)[1].lower()
    return archiveplugins.get(ext)
    
def allArchivePluginsExtensions():
    return archiveexts