import os

from mo2git.common import *
from mo2git.installfile import installfileModidManualUrlAndPrompt
from mo2git.folders import Folders
from mo2git.modlist import ModList
import mo2git.cache as cache

def _csAndMasterModList(config):
    mo2=config['mo2']
    compiler_settings_fname=config['compiler_settings']
    with openModTxtFile(mo2+compiler_settings_fname) as rfile:
        compiler_settings = json.load(rfile)
    masterprofilename=compiler_settings['Profile']
    return compiler_settings_fname,compiler_settings,masterprofilename,ModList(mo2+'profiles\\'+masterprofilename+'\\')

def _openCache(jsonconfigname,config,mastermodlist,ignore,dbgdumpwjdb=None):
    folders = Folders(jsonconfigname,config,ignore)
    ownmods=config['ownmods']
    
    allarchivenames = []
    for mod in mastermodlist.allEnabled():
        if mod in ownmods:
            continue
        installfile,modid,manualurl,prompt = installfileModidManualUrlAndPrompt(mod,folders.mo2)
        if installfile is not None:
            installfile = installfile.strip('/').strip('\\') #an odd / in the beginning of meta-provided path
            #print(installfile)
            allarchivenames.append(Folders.normalizeFileName(installfile))
    folders.addArchiveNames(allarchivenames)

    mo2exclude = [folders.mo2+'downloads\\', # even if downloadsdirs are different
                  folders.mo2+'mods\\']
    for ddir in folders.downloads:
        mo2exclude.append(ddir) # even if different from mo2+'downloads\\'
    mo2reinclude = []
    cachedir = folders.cache
    tmpbasepath = folders.tmp
    if not tmpbasepath:
        tmpbasepath = cachedir
    os.makedirs(cachedir,exist_ok=True)
    for mod in mastermodlist.allEnabled():
        mo2reinclude.append(folders.mo2+'mods\\'+mod+'\\')
        #print('reincluded:'+mod)
    folders.setExclusions(mo2exclude,mo2reinclude)
    filecache = cache.Cache(folders,dbgdumpwjdb)
    return filecache
    
def enabledModSizes(modlist,mo2):
    sizes=[]
    for mod in modlist.allEnabled():
        sizes.append([mod,round(folderSize(mo2+'mods/'+mod)/1000000,2)])
    sizes.sort(key=lambda x: x[1])
    return sizes
