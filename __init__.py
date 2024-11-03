import sys
import time
import os
import json

from mo2git.folders import Folders
from mo2git.common import isEslFlagged,scriptDirFrom__file__
from mo2git.commands.cmdcommon import _openCache,_csAndMasterModList,enabledModSizes
import mo2git.commands.mo2git as mo2git
import mo2git.commands.git2mo as git2mo

if not sys.version_info >= (3, 10):
    print('Sorry, mo2git needs at least Python 3.10')
    sys.exit(4) # why not?
    
def run(configfilepath):
    with open(configfilepath,'rt',encoding='utf-8') as rf:
        config = json.load(rf)
        
    argv = sys.argv
    argc = len(argv)
    # print(argv)
    ok = False
    started = time.perf_counter()    
    if argc >= 2:
        match argv[1].lower():
            case 'mo2git':
                if argc == 2:
                   mo2git._mo2git(configfilepath,config)
                   ok = True 
            case 'git2mo':
                if argc == 2:
                   git2mo._git2mo(configfilepath,config)
                   ok = True
            case 'debug.dumpwjdb':
                if argc == 3:
                    compiler_settings_fname,compiler_settings,masterprofilename,mastermodlist = _csAndMasterModList(config)
                    ignore=compiler_settings['Ignore']
                    dumpwjdb = Folders.normalizeDirPath(argv[2])
                    filecache = _openCache(configfilepath,config,mastermodlist,ignore,dumpwjdb)
                    ok = True
            case 'debug.modsizes':
                if argc == 2:
                    compiler_settings_fname,compiler_settings,masterprofilename,mastermodlist = _csAndMasterModList(config)
                    sizes = enabledModSizes(mastermodlist,config['mo2'])
                    print(sizes)
                    ok = True

    exe = os.path.split(argv[0])[1]
    if ok:
        elapsed = round(time.perf_counter()-started,2)
        print(exe+' took '+str(elapsed)+' sec')
    else:
        print('Usage:\n\t'
               +exe+' mo2git\n\t'
               +exe+' debug.dumpwjdb <target-folder>\n\t'
               +exe+' debug.modsizes\n'
             )