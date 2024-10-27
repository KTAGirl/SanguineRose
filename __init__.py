import sys
import time

from mo2git.common import isEslFlagged, escapeJSON, openModTxtFile, openModTxtFileW, allEsxs
from mo2git.installfile import installfileModidManualUrlAndPrompt
from mo2git.mo2git import _mo2git as mo2git, _writeTxtFromTemplate as writeTxtFromTemplate
from mo2git.mo2git import _loadFromCompilerSettings as loadFromCompilerSettings, _statsFolderSize as statsFolderSize
from mo2git.mo2git import _writeManualDownloads as writeManualDownloads, _fillCompiledStats as fillCompiledStats

if not sys.version_info >= (3, 10):
    print('Sorry, mo2git needs at least Python 3.10')
    sys.exit(4) # why not?
    
_mo2gitLoadedAt = time.perf_counter()

def elapsedTime():
    return round(time.perf_counter()-_mo2gitLoadedAt,2)