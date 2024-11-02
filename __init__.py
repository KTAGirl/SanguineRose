import sys
import time
import os

from mo2git.common import isEslFlagged,scriptDirFrom__file__,normalizeDirPath
from mo2git.commands.cmdcommon import _openCache
import mo2git.commands.mo2git as mo2git
import mo2git.commands.git2mo as git2mo

if not sys.version_info >= (3, 10):
    print('Sorry, mo2git needs at least Python 3.10')
    sys.exit(4) # why not?
    
def run(config):
    argv = sys.argv
    argc = len(argv)
    # print(argv)
    ok = False
    started = time.perf_counter()    
    if argc >= 2:
        match argv[1].lower():
            case 'mo2git':
                if argc == 2:
                   mo2git._mo2git(config)
                   ok = True 
                '''
                if argc >= 2:
                    i = 2
                    dbgdumpwjdb = None
                    optionsok = True
                    while i < len(argv):
                        if argv[i].lower() == '-debug.dumpwjdb':
                            if i+1 == len(argv):
                                optionsok = False
                                break
                            else:
                                dbgdumpwjdb = argv[i+1]
                                i += 2
                        else:
                            optionsok = False
                            break
                    if optionsok:
                        mo2git._mo2git(config,dbgdumpwjdb)
                        ok = True
                '''
            case 'git2mo':
                if argc == 2:
                   git2mo._git2mo(config)
                   ok = True
            case 'debug.dumpwjdb':
                if argc == 3:
                    mo2,mastermodlist = mo2git.mo2AndMasterModList(config)
                    dumpwjdb = argv[2]
                    _openCache(config,mastermodlist,normalizeDirPath(argv[2]))
                    ok = True
            case 'debug.modsizes':
                if argc == 2:
                    mo2,mastermodlist = mo2git.mo2AndMasterModList(config)
                    sizes = mo2git.enabledModSizes(mastermodlist,mo2)
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