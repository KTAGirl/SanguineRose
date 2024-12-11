import os
import re
import json5 #only for user configs! Very slow for any other purpose

from sanguine.common import *
from sanguine.installfile import installfile_modid_manual_url_and_prompt
from sanguine.projectconfig import ProjectConfig
from sanguine.modlist import ModList
import sanguine.cache as cache
import sanguine.mo2compat as mo2compat

def _loadUserConfig(rf): #don't use for anything except for hand-editable user configs! Very slow for any other purpose
    try:
        return json5.load(rf)
    except Exception as e:
        #print(repr(e))
        msg = 'error parsing json5 config file'
        m=re.match(r'<string>:([0-9]*)',str(e))
        if m:
            msg += ' at line #'+m.group(1)
        abort_if_not(False, lambda: msg)

def _csAndMasterModList(config):
    abort_if_not('mo2' in config, lambda: "'mo2' must be present in config")
    mo2=config['mo2']
    abort_if_not('compiler_settings' in config, lambda: "'compiler_settings' must be present in config")
    compiler_settings_fname=config['compiler_settings']
    with open_3rdparty_txt_file(mo2 + compiler_settings_fname) as rfile:
        compiler_settings = json.load(rfile)
    masterprofilename=compiler_settings['Profile']
    return compiler_settings_fname,compiler_settings,masterprofilename,ModList(mo2+'profiles\\'+masterprofilename+'\\')

def _openCache(jsonconfigname,config,mastermodlist,folders,dbgdumpwjdb=None):
    allarchivenames = []
    for mod in mastermodlist.all_enabled():
        if folders.is_own_mod(mod.lower()):
            continue
        installfile,modid,manualurl,prompt = installfile_modid_manual_url_and_prompt(mod, folders.mo2_dir)
        if installfile is not None:
            installfile = installfile.strip('/').strip('\\') #an odd / in the beginning of meta-provided path
            #print(installfile)
            allarchivenames.append(ProjectConfig.normalize_file_name(installfile))
    folders.add_archive_names(allarchivenames)

    mo2exclude = [folders.mo2_dir + 'downloads\\',  # even if downloadsdirs are different
                  folders.mo2_dir + 'mods\\']
    for ddir in folders.download_dirs:
        mo2exclude.append(ddir) # even if different from mo2+'downloads\\'
    mo2reinclude = []
    cachedir = folders.cache_dir
    tmpbasepath = folders.tmp_dir
    if not tmpbasepath:
        tmpbasepath = cachedir
    os.makedirs(cachedir,exist_ok=True)
    for mod in mastermodlist.all_enabled():
        mo2reinclude.append(folders.mo2_dir + 'mods\\' + mod + '\\')
        #print('reincluded:'+mod)
    folders.set_exclusions(mo2exclude, mo2reinclude)
    filecache = cache.Cache(folders,dbgdumpwjdb)
    return filecache
    
def enabledModSizes(modlist,mo2):
    sizes=[]
    for mod in modlist.all_enabled():
        sizes.append([mod, round(folder_size(mo2 + 'mods/' + mod) / 1000000, 2)])
    sizes.sort(key=lambda x: x[1])
    return sizes
