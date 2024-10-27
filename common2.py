import os

from mo2git.common import *
from mo2git.installfile import installfileModidManualUrlAndPrompt
from mo2git.modlist import ModList
import mo2git.cache as cache

def _mo2AndCSAndMasterModList(config):
    mo2=config['mo2']
    compiler_settings_fname=config['compiler_settings']
    with openModTxtFile(mo2+compiler_settings_fname) as rfile:
        compiler_settings = json.load(rfile)
    masterprofilename=compiler_settings['Profile']
    return mo2,compiler_settings_fname,compiler_settings,masterprofilename,ModList(mo2+'profiles\\'+masterprofilename+'\\')

def _openCache(config,mastermodlist,dbgdumpwjdb=None):
    mo2 = config['mo2']
    downloadsdir = config['downloads']
    ownmods=config['ownmods']
    
    allarchivenames = []
    todl = {}
    for mod in mastermodlist.allEnabled():
        if mod in ownmods:
            continue
        installfile,modid,manualurl,prompt = installfileModidManualUrlAndPrompt(mod,mo2)
        if installfile:
            fpath = downloadsdir+installfile
            allarchivenames.append(cache.normalizePath(fpath))
        if manualurl:
            addToDictOfLists(todl,manualurl,prompt)

    mo2excludefolders = [absDir(mo2+'downloads\\'), # even if downloadsdirs is different
                         absDir(downloadsdir), # even if different from mo2+'downloads\\'
                         absDir(mo2+'mods\\')]
    mo2reincludefolders = []
    cachedir = config['cache']
    tmpbasepath = config.get('tmp')
    if not tmpbasepath:
        tmpbasepath = cachedir
    os.makedirs(cachedir,exist_ok=True)
    for mod in mastermodlist.allEnabled():
        mo2reincludefolders.append(absDir(mo2+'mods\\'+mod+'\\'))
        #print('reincluded:'+mod)
    filecache = cache.Cache(allarchivenames,absDir(cachedir),absDir(downloadsdir),absDir(mo2),mo2excludefolders,mo2reincludefolders,tmpbasepath,dbgdumpwjdb)
    return todl,allarchivenames,filecache