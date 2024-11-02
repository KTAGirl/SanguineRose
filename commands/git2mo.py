import os

from mo2git.common import *
import mo2git.cache as cache
from mo2git.commands.cmdcommon  import _openCache,_mo2AndCSAndMasterModList

def _git2mo(config):
    mo2,compiler_settings_fname,compiler_settings,masterprofilename,mastermodlist = _mo2AndCSAndMasterModList(config)
    todl,allarchivenames,filecache = _openCache(config,mastermodlist)
    print('Cache loaded')
    srcgithub = config['github']
    masterjsonfname = srcgithub + 'master.json'
    with open(masterjsonfname, 'rt',encoding="utf-8") as rfile:
        masterjson = json.load(rfile)
    
    mo2 = normalizeDirPath(mo2).lower()
    #print(mo2)
    masterfiles = masterjson['files']
    nnotfound = 0
    nmodified = 0
    masterfilesbypath = {}
    for fentry in masterfiles:
        fe = fentry['path']
        fname = mo2+fe
        masterfilesbypath[fe.lower()] = fentry
        #print(fe)
        #print(fname)
        #assert(os.path.isfile(fname))
        incachearentry,incachear = filecache.findFile(fname)
        if incachear is None:
            nnotfound += 1
        else:
            #print(fentry)
            if incachearentry.file_hash != fentry['hash']:
                print('WARNING: master.json hash '+str(fentry['hash'])+' != cache hash '+str(incachearentry.file_hash)
                       +' for '+fname)
                nmodified += 1
    print('not found (WARNINGS)='+str(nnotfound)+' modified='+str(nmodified))
    
    nmodified2 = 0
    nmissing = 0
    #print(mo2lo)
    lmo2 = len(mo2)
    nnohash = 0
    nincache = 0
    #print(mo2)
    for file in filecache.allFiles():
        nincache += 1
        #print(file.file_path)
        assert(file.file_path.startswith(mo2))
        fasinjson = file.file_path[lmo2:]
        mfile = masterfilesbypath.get(fasinjson)
        if mfile is None:
            nmissing += 1
            #print(fasinjson)
        else:
            #print(mfile)
            hash = mfile.get('hash')
            if hash is None:
                nnohash += 1
                #print(fasinjson)
            elif hash != file.file_hash:
                nmodified2 += 1
        #print(fasinjson)
    print('nincache='+str(nincache)+' nmaster='+str(len(masterfiles)))
    assert(len(masterfiles)==len(masterfilesbypath))
    print('nnohash='+str(nnohash)+' nmissing='+str(nmissing)+' modified2='+str(nmodified2))
    
    