import os
import re
import json5 #only for user configs! Very slow for any other purpose

from mo2gitlib.common import *
from mo2gitlib.installfile import installfileModidManualUrlAndPrompt
from mo2gitlib.folders import Folders
from mo2gitlib.modlist import ModList
import mo2gitlib.cache as cache
import mo2gitlib.mo2compat as mo2compat

def _loadUserConfig(rf): #don't use for anything except for hand-editable user configs! Very slow for any other purpose
    try:
        return json5.load(rf)
    except Exception as e:
        #print(repr(e))
        msg = 'error parsing json5 config file'
        m=re.match(r'<string>:([0-9]*)',str(e))
        if m:
            msg += ' at line #'+m.group(1)
        aAssert(False,lambda: msg)

def _csAndMasterModList(config):
    aAssert('mo2' in config, lambda: "'mo2' must be present in config")
    mo2=config['mo2']
    aAssert('compiler_settings' in config, lambda: "'compiler_settings' must be present in config")
    compiler_settings_fname=config['compiler_settings']
    with openModTxtFile(mo2+compiler_settings_fname) as rfile:
        compiler_settings = json.load(rfile)
    masterprofilename=compiler_settings['Profile']
    return compiler_settings_fname,compiler_settings,masterprofilename,ModList(mo2+'profiles\\'+masterprofilename+'\\')

def _openCache(jsonconfigname,config,mastermodlist,folders,dbgdumpwjdb=None):
    allarchivenames = []
    for mod in mastermodlist.allEnabled():
        if folders.isOwnMod(mod.lower()):
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
