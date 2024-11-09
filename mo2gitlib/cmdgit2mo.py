import os

from mo2gitlib.common import *
import mo2gitlib.cache as cache
from mo2gitlib.cmdcommon import _openCache,_csAndMasterModList
from mo2gitlib.master import Master

def _git2mo(jsonconfigfname,config):
    compiler_settings_fname,compiler_settings,masterprofilename,mastermodlist = _csAndMasterModList(config)
    ignore=compiler_settings['Ignore']
    filecache = _openCache(jsonconfigfname,config,mastermodlist,ignore)
    print('Cache loaded')
    
    srcgithub = filecache.folders.github
    masterjsonfname = srcgithub + 'master.json'
    masterjson = Master()
    with open(masterjsonfname, 'rt',encoding='utf-8') as rf:
        masterjson.constructFromFile(rf)
        
    mo2 = filecache.folders.mo2
    needtorestore = {}
    needzerosize = []
    needtocopy = []
    for fimaster in masterjson.allFiles():
        fpath = mo2+fimaster.file_path
        if fimaster.gitpath is not None:
            needtocopy.append(fpath)
            continue
        fimasterhash = cache.ZEROHASH if fimaster.file_size == 0 else fimaster.file_hash
        ficache = filecache.findFileOnly(fpath)
        if ficache is not None and ficache.file_hash == fimasterhash:
            #print(fimaster.file_path)
            #dbgWait()
            continue
        ae,archive,fi = filecache.findArchiveForFile(fpath)
        if ae is None:
            print("WARNING: don't know how to restore "+fpath)
        else:
            if ae.file_size == 0:
                needzerosize.append(fpath)
            else:
                addToDictOfLists(needtorestore,archive.file_path,ae)
        
    dbgWait()
    print('zerosize:'+str(needzerosize))
    dbgWait()
    print('copy:'+str(needtocopy))
    dbgWait()
    print('restore:'+str(needtorestore))
    dbgWait()
    '''
    mo2 = filecache.folders.mo2
    #print(mo2)
    masterfiles = masterjson.files
    nnotfound = 0
    nmodified = 0
    masterfilesbypath = {}
    for fentry in masterfiles:
        fe = fentry.path
        fname = mo2+fe
        masterfilesbypath[fe.lower()] = fentry
        #print(fe)
        #print(fname)
        #assert(os.path.isfile(fname))
        incacheae,incachear,_ = filecache.findFile(fname)
        if incachear is None:
            nnotfound += 1
        else:
            #print(fentry)
            if incacheae.file_hash != fentry.hash:
                print('WARNING: master.json hash '+str(fentry['hash'])+' != cache hash '+str(incachearentry.file_hash)
                       +' for '+fname)
                nmodified += 1
    info('not found (WARNINGS)='+str(nnotfound)+' modified='+str(nmodified))
    
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
            hash = mfile.hash
            if hash is None:
                nnohash += 1
                #print(fasinjson)
            elif hash != file.file_hash:
                nmodified2 += 1
        #print(fasinjson)
    print('nincache='+str(nincache)+' nmaster='+str(len(masterfiles)))
    assert(len(masterfiles)==len(masterfilesbypath))
    print('nnohash='+str(nnohash)+' nmissing='+str(nmissing)+' modified2='+str(nmodified2))
    '''
    