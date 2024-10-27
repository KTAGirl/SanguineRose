import sys
import time
import os

from mo2git.common import isEslFlagged, escapeJSON, openModTxtFile, openModTxtFileW, allEsxs
# from mo2git.installfile import installfileModidManualUrlAndPrompt
# from mo2git.mo2git import _mo2git as mo2git, _writeTxtFromTemplate as writeTxtFromTemplate
# from mo2git.mo2git import _loadFromCompilerSettings as loadFromCompilerSettings, _statsFolderSize as statsFolderSize
# from mo2git.mo2git import _writeManualDownloads as writeManualDownloads, _fillCompiledStats as fillCompiledStats
import mo2git.mo2git as mo2git

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
            case 'debug.modsizes':
                if argc == 2:
                    mo2,modlist = mo2git.mo2AndMasterModList(config)
                    sizes = mo2git.enabledModSizes(modlist,mo2)
                    print(sizes)
                    ok = True

    exe = os.path.split(argv[0])[1]
    if ok:
        elapsed = round(time.perf_counter()-started,2)
        print(exe+' took '+str(elapsed)+' sec')
    else:
        print('Usage:\n\t'
               +exe+' mo2git\n\t'
               +exe+' debug.modsizes\n'
             )      