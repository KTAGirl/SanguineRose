import os

from mo2git.debug import *
from mo2git.common import *
import mo2git.cache as cache
from mo2git.common2 import _openCache,_mo2AndCSAndMasterModList

def _git2mo(config):
    mo2,compiler_settings_fname,compiler_settings,masterprofilename,mastermodlist = _mo2AndCSAndMasterModList(config)
    todl,allarchivenames,filecache = _openCache(config,mastermodlist)
    srcgithub = config['github']
    masterjsonfname = srcgithub + 'master.json'
    with open(masterjsonfname, 'rt',encoding="utf-8") as rfile:
        masterjson = json.load(rfile)
    
    mo2 = normalizeDirPath(mo2)
    #print(mo2)
    masterfiles = masterjson['files']
    nwarn = 0
    nwarn2 = 0
    for fentry in masterfiles:
        fname = mo2+fentry['path']
        #print(fname)
        #assert(os.path.isfile(fname))
        incachearentry,incachear = filecache.findFile(fname)
        if incachear is None:
            nwarn += 1
        else:
            #print(fentry)
            if incachearentry.file_hash != fentry['hash']:
                print('WARNING: master.json hash '+str(fentry['hash'])+' != cache hash '+str(incachearentry.file_hash)
                       +' for '+fname)
                nwarn2 += 1
    print('nwarn='+str(nwarn)+' nwarn2='+str(nwarn2))