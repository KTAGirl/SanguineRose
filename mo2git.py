import sys
import time
import os
import json

sys.path.append(os.path.split(os.path.abspath(__file__))[0])

from mo2gitlib.common import *
from mo2gitlib.folders import Folders
from mo2gitlib.cmdcommon import _openCache,_csAndMasterModList,enabledModSizes,_loadUserConfig
import mo2gitlib.mo2git as mo2git
import mo2gitlib.git2mo as git2mo

if __name__ == '__main__':
    if not sys.version_info >= (3, 10):
        print('Sorry, mo2git needs at least Python 3.10')
        sys.exit(4) # why not 4?

    argv = sys.argv
    argc = len(argv)
    # print(argv)

    thisscriptcalledas = os.path.split(argv[0])[1]
    configfilepath = os.path.abspath(argv[1])
    argv = argv[1:]
    argc -= 1
        
    with open(configfilepath,'rt',encoding='utf-8') as rf:
        config = _loadUserConfig(rf)
        
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

    if ok:
        elapsed = round(time.perf_counter()-started,2)
        print(thisscriptcalledas+' took '+str(elapsed)+' sec')
    else:
        print('Usage:\n\t'
               +thisscriptcalledas+' <project-config> mo2git\n\t'
               +thisscriptcalledas+' <project-config> git2mo\n\t'
               +thisscriptcalledas+' <project-config> debug.dumpwjdb <target-folder>\n\t'
               +thisscriptcalledas+' <project-config> debug.modsizes\n'
             )