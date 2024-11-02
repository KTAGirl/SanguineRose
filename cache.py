import os
import stat
import pathlib
import pickle
import json
import shutil

from mo2git.common import *
from mo2git.files import File,ArchiveEntry,wjHash
import mo2git.wjcompat.wjdb as wjdb
import mo2git.pluginhandler as pluginhandler
import mo2git.tasks as tasks
from mo2git.folders import Folders,NoFolders

def _hcFoundDownload(archives,archivesbypath,ndup,ar):
    if ar.file_path.endswith('.meta'):
        return
    olda = archives.get(ar.file_hash)
    if olda!=None and not olda.eq(ar):
        warn("identical archives: hash="+str(hash)+" old="+str(olda.__dict__)+" new="+str(ar.__dict__))
        # dbgWait()
        ndup.val += 1
        pass
    else:
        # out[idx][hash] = ar
        archives[ar.file_hash] = ar
        archivesbypath[ar.file_path] = ar
    
def _hcFoundFile(filesbypath,nex,ndup,fi,folders):
    if not folders.isMo2FilePathIncluded(fi.file_path): #ignored or mo2excluded
        nex.val += 1
        return
        
    olda = filesbypath.get(fi.file_path)
    if olda!=None and not olda.eq(fi):
        # print("TODO: multiple archives: hash="+str(hash)+" old="+str(olda.__dict__)+" new="+str(fi.__dict__))
        # wait = input("Press Enter to continue.")
        ndup.val += 1
        pass
    else:
        filesbypath[fi.file_path] = fi

#### Generic helpers

def _getFileTimestamp(s):
    path = pathlib.Path(fname)
    return path.lstat().st_mtime

def _getFileTimestampFromSt(st):
    return st.st_mtime

def _getFromOneOfDicts(dicttolook,dicttolook2,key):
    found = dicttolook.get(key)
    if found != None:
        return found
    return dicttolook2.get(key)

def _allValuesInBothDicts(dicttoscan,dicttoscan2):
    for key,val in dicttoscan.items():
        yield val
    for key,val in dicttoscan2.items():
        yield val

##### hashing archive file into ArchiveEntries

def _archiveToEntries(jsonarchiveentries,archive_hash,tmppath,cur_intra_path,plugin,archivepath):
    if not os.path.isdir(tmppath):
        os.makedirs(tmppath)
    plugin.extractAll(archivepath,tmppath)
    #dbgWait()
    pluginexts = pluginhandler.allArchivePluginsExtensions()
    for root, dirs, files in os.walk(tmppath):
        nf = 0
        for f in files:
            nf += 1
            fpath = os.path.join(root, f)
            assert(os.path.isfile(fpath))
            # print(fpath)
            hash = wjHash(fpath)
            assert(fpath.startswith(tmppath))
            new_intra_path = cur_intra_path.copy()
            new_intra_path.append(Folders.normalizeArchiveIntraPath(fpath[len(tmppath):]))
            ae = ArchiveEntry(archive_hash,new_intra_path,os.path.getsize(fpath),hash)
            # print(ae.__dict__)
            jsonarchiveentries[ae.file_hash]=ae

            ext = os.path.split(fpath)[1].lower()
            if ext in pluginexts:
                nested_plugin = pluginhandler.archivePluginFor(fpath)
                assert(nested_plugin != None)
                _archiveToEntries(jsonarchiveentries,archive_hash,tmppath + str(nf) + '\\',new_intra_path,nested_plugin,fpath)

##### Lambda parts

def _diffFound(ldout,fpath,tstamp,addfi,updatednotadded):
    #print(fpath)
    hash = wjHash(fpath) #TODO: to Task (only for larger files)
    assert(Folders.normalizeFilePath(fpath)==fpath)
    newa = File(hash,tstamp,fpath)
    addfi.call((ldout,newa,updatednotadded))

def _diffArchive(jsonarchives,jsonarchivesbypath,jsonarchiveentries,tmppathbase,nmodified,ar,updatednotadded):
    if ar.file_path.endswith('.meta'):
        return
    info('archive '+ar.file_path+' was '+('updated' if updatednotadded else 'added')+' since wj caching')
    jsonarchives[ar.file_hash]=ar
    jsonarchivesbypath[ar.file_path]=ar
    
    tmproot = tmppathbase + 'mo2git.tmp\\' + str(tasks.thisProcNum()+1) + '\\'
    if os.path.isdir(tmproot):
        shutil.rmtree(tmproot)
    os.makedirs(tmproot,exist_ok=True)
    plugin = pluginhandler.archivePluginFor(ar.file_path)
    if plugin == None:
        warn('no archive plugin found for '+ar.file_path)
    else:
        _archiveToEntries(jsonarchiveentries,ar.file_hash,tmproot,[],plugin,ar.file_path)

    shutil.rmtree(tmproot)
    nmodified.val += 1
  
def _diffFile(jsonfilesbypath,nmodified,fi,updatednotadded):
    info('file '+fi.file_path+' was '+('updated' if updatednotadded else 'added')+' since wj caching')
    jsonfilesbypath[fi.file_path]=fi
    nmodified.val += 1

def _scannedFoundFile(scannedfiles,fpath):
    assert(Folders.normalizeFilePath(fpath)==fpath)
    scannedfiles[fpath] = 1

#### JSON loading helpers

def _dictOfFisFromJsonFile(path):
    out = {}
    with openModTxtFile(path) as rfile:
        for line in rfile:
            ar = File.fromJSON(line)
            assert(out.get(ar.file_path) is None)
            out[ar.file_path] = ar
    return out

def _dictOfFisToJsonFile(path,ars):
    with openModTxtFileW(path) as wfile:
        for key in sorted(ars):
            ar = ars[key]
            wfile.write(File.toJSON(ar)+'\n')

def _dictOfArEntriesFromJsonFile(path):
    out = {}
    with openModTxtFile(path) as rfile:
        for line in rfile:
            ae = ArchiveEntry.fromJSON(line)
            # print(ar.__dict__)
            out[ae.file_hash] = ae
    return out

def _dictOfArEntriesToJsonFile(path,aes):
    with openModTxtFileW(path) as wfile:
        for key in sorted(aes):
            ae = aes[key]
            wfile.write(ArchiveEntry.toJSON(ae)+'\n')

############# MicroCache

def _microCache(cachedir,cachedata,prefix,origfile,calc,params=None):
    readpath = cachedata.get(prefix+'.path')
    readtstamp = cachedata.get(prefix+'.timestamp')
    
    if params is not None:
        #comparing as JSONs is important
        readparams = JsonEncoder().encode(cachedata.get(prefix+'.params'))
        jparams = JsonEncoder().encode(params)
        sameparams = (readparams == jparams)
    else:
        sameparams = True
    #print(params)
    #print(readparams)
    if readpath == origfile and sameparams:
        tstamp = os.path.getmtime(origfile)
        if tstamp == readtstamp:
            print('_microCache(): Yahoo! Can read cache for '+prefix)
            with open(cachedir+prefix+'.pickle','rb') as rf:
                return (pickle.load(rf),{})

    cachedataoverwrites = {}
    tstamp = os.path.getmtime(origfile)
    out = calc(params)
    assert(tstamp == os.path.getmtime(origfile))
    with open(cachedir+prefix+'.pickle','wb') as wf:
        pickle.dump(out,wf)
    cachedataoverwrites[prefix+'.path'] = origfile
    cachedataoverwrites[prefix+'.timestamp'] = tstamp
    cachedataoverwrites[prefix+'.params'] = params
    return (out,cachedataoverwrites)

############# Parallelizable Tasks

class _LoadDirOut:
    def __init__(self):
        self.jsonfilesbypath = {}
        self.scannedfiles = {}
        self.requested = []
        
def _loadVFS00(dbgfile):
    unfilteredarchiveentries = []
    for ae in wjdb.loadVFS(dbgfile):
        unfilteredarchiveentries.append(ae)    
    return unfilteredarchiveentries

def _loadVFS0(cachedir,cachedata,dbgfile):
    (unfilteredarchiveentries,cachedataoverwrites) = _microCache(cachedir,cachedata,'wjdb.vfsfile',wjdb.vfsFile(),
                                                                 lambda _: _loadVFS00(dbgfile))

    shared = tasks.SharedReturn(unfilteredarchiveentries)
    return (tasks.makeSharedReturnParam(shared),cachedataoverwrites)

def _loadVFS(cachedir,cachedata,dbgfolder):
    if dbgfolder:
        with open(dbgfolder+'loadvfs.txt','wt',encoding='utf-8') as dbgfile:
            return _loadVFS0(cachedir,cachedata,dbgfile)
    else:
        return _loadVFS0(cachedir,cachedata,None)

def _loadVFSTaskFunc(param):
    (cachedir,cachedata,dbgfolder) = param
    return _loadVFS(cachedir,cachedata,dbgfolder)

def _loadHC0(params):
    (folders,) = params
    ndupdl = Val(0) #passable by ref
    nexf = Val(0)
    ndupf = Val(0)
    archives = {}
    archivesbypath = {}
    filesbypath = {}

    hclist = [(dl,lambda ar: _hcFoundDownload(archives, archivesbypath,ndupdl,ar)) for dl in folders.downloads]
    hclist.append((folders.mo2,lambda fi: _hcFoundFile(filesbypath,nexf,ndupf,fi,folders)))
    wjdb.loadHC(hclist)
    return (archives,archivesbypath,filesbypath,ndupdl.val,nexf.val,ndupf.val)

def _loadHC(folders,cachedata):
    return _microCache(folders.cache,cachedata,'wjdb.hcfile',wjdb.hcFile(),
                       _loadHC0,
                       (folders,))

def _loadHCTaskFunc(param):
    (folders,cachedata) = param
    return _loadHC(folders,cachedata)
    
def _ownHC2SelfTaskFunc(cache,parallel,out):
    (hcout,cachedataoverwrites) = out
    cache.cachedata |= cachedataoverwrites
    (cache.archives,cache.archivesbypath,cache.filesbypath,ndupdl,nexf,ndupf) = hcout        
    assert(len(cache.archives)==len(cache.archivesbypath)) 
    print(str(len(cache.archives))+' archives ('+str(ndupdl)+' duplicates), '
         +str(len(cache.filesbypath))+' files ('+str(nexf)+' excluded, '+str(ndupf)+' duplicates)')
         
    cache.publishedarchives = tasks.SharedPublication(parallel,cache.archives)
    cache.publishedarchivesbypath = tasks.SharedPublication(parallel,cache.archivesbypath)
    cache.publishedfilesbypath = tasks.SharedPublication(parallel,cache.filesbypath)
    return (tasks.makeSharedPublicationParam(cache.publishedarchivesbypath),tasks.makeSharedPublicationParam(cache.publishedfilesbypath))

def _loadJsonArchivesTaskFunc(param):
    (cachedir,) = param
    jsonarchivesbypath = {}
    try:
        jsonarchivesbypath = _dictOfFisFromJsonFile(cachedir+'archives.njson')
    except Exception as e:
        print('WARNING: error loading JSON cache archives.njson: '+str(e)+'. Will continue w/o archive JSON cache')
        jsonarchivesbypath = {} # just in case  
    return (jsonarchivesbypath,)

def _ownJsonArchives2SelfTaskFunc(cache,out):
    (jsonarchivesbypath,) = out
    cache.jsonarchivesbypath = jsonarchivesbypath
    cache.jsonarchives = {}
    for key in cache.jsonarchivesbypath:
        val = cache.jsonarchivesbypath[key]
        cache.jsonarchives[val.file_hash] = val
    assert(len(cache.jsonarchives)==len(cache.jsonarchivesbypath)) 
    print(str(len(cache.jsonarchives))+' JSON archives')
    return (cache.jsonarchives,cache.jsonarchivesbypath)

def _loadJsonFilesTaskFunc(param):
    (cachedir,) = param
    jsonfilesbypath = {}
    try:
        jsonfilesbypath = _dictOfFisFromJsonFile(cachedir+'files.njson')
    except Exception as e:
        print('WARNING: error loading JSON cache files.njson: '+str(e)+'. Will continue w/o file JSON cache')
        jsonfilesbypath = {} # just in case            

    print(str(len(jsonfilesbypath))+' JSON files')
    return (jsonfilesbypath,)
    
def _ownJsonFiles2SelfTaskFunc(cache,out):
    (jsonfilesbypath,) = out
    cache.jsonfilesbypath = jsonfilesbypath
    return (cache.jsonfilesbypath,)

def _loadJsonArchiveEntriesTaskFunc(param):
    (cachedir,) = param
    jsonarchiveentries = {}
    try:
        jsonarchiveentries = _dictOfArEntriesFromJsonFile(cachedir+'archiveentries.njson')
    except Exception as e:
        print('WARNING: error loading JSON cache archiveentries.njson: '+str(e)+'. Will continue w/o archiveentries JSON cache')
        jsonarchiveentries = {} # just in case            
    print(str(len(jsonarchiveentries))+' JSON archiveentries')
    return (jsonarchiveentries,)
    
def _ownJsonArchiveEntries2SelfTaskFunc(cache,out):
    (jsonarchiveentries,) = out
    cache.jsonarchiveentries = jsonarchiveentries
    return (cache.jsonarchiveentries,)
    
# filtering and scanning

def _ownFilterTaskFunc(cache,parallel,allarchivenames,fromloadvfs):
    (sharedparam,cachedataoverwrites) = fromloadvfs
    cache.cachedata |= cachedataoverwrites
    unfilteredarchiveentries = tasks.receivedSharedReturn(parallel,sharedparam)

    allarchivehashes = {}
    for arname in allarchivenames:
        ar = _getFromOneOfDicts(cache.archivesbypath,cache.jsonarchivesbypath,arname.lower())
        if ar:
            allarchivehashes[ar.file_hash] = 1
        else:
            print('WARNING: no archive hash found for '+arname)
    
    cache.archiveentries = {}
#       for ae in unfilteredarchiveentries.val:
#           if allarchivehashes.get(ae.archive_hash) is not None:
#               cache.archiveentries[ae.file_hash] = ae
    for ae in unfilteredarchiveentries:
        ahash = ae.archive_hash
        assert(ahash>=0)
        if allarchivehashes.get(ahash) is not None:
            #print(ae.toJSON())
            #dbgWait()
            cache.archiveentries[ae.file_hash] = ae
    cache.publishedarchiveentries = tasks.SharedPublication(parallel,cache.archiveentries)
    print('Filtered: '+str(len(cache.archiveentries))+' out of '+str(len(unfilteredarchiveentries)))

def _notALambda0(capture,param):
  (_,ar,updatednotadded) = param
  (jsonarchives,jsonarchivesbypath,jsonarchiveentries,tmppathbase,nmodified) = capture
  _diffArchive(jsonarchives,jsonarchivesbypath,jsonarchiveentries,tmppathbase,nmodified,ar,updatednotadded)

def _notALambda1(capture,param):
    (ldout,fi,updatednotadded) = param
    (nmodified,) = capture
    _diffFile(ldout.jsonfilesbypath,nmodified,fi,updatednotadded)
    
def _notALambda2(capture,param):
    assert(capture is None)
    (ldout,fpath) = param
    _scannedFoundFile(ldout.scannedfiles,fpath)

def _scanDownloadsTaskFunc(param,fromhc2toself,fromjsonarchives2self,fromjsonarchiveentries2self):
    (downloadsdir,tmppathbase) = param
    (pubarchivesbypath,_) = fromhc2toself
    (jsonarchives,jsonarchivesbypath) = fromjsonarchives2self
    (jsonarchiveentries,) = fromjsonarchiveentries2self
    archivesbypath = tasks.fromPublication(pubarchivesbypath)
    nmodified = Val(0)
    #ldout = _LoadDirOut()
    nscanned = Cache._loadDir(None,downloadsdir,
                              jsonarchivesbypath,
                              archivesbypath,pubarchivesbypath,
                              NoFolders(),
                              tasks.LambdaReplacement(_notALambda0,
                                                      (jsonarchives,jsonarchivesbypath,jsonarchiveentries,
                                                       tmppathbase,nmodified)
                                                     ),
                              None
                             )                             
    return (nscanned,nmodified.val,jsonarchives,jsonarchivesbypath,jsonarchiveentries)

def _ownScanDownloads2SelfTaskFunc(cache,out):
    (nscanned,nmodified,jsonarchives,jsonarchivesbypath,jsonarchiveentries) = out
    cache.jsonarchives = jsonarchives
    cache.jsonarchivesbypath = jsonarchivesbypath
    cache.jsonarchiveentries = jsonarchiveentries
    assert(len(cache.jsonarchives)==len(cache.jsonarchivesbypath)) 
    print('scanned/modified archives:'+str(nscanned)+'/'+str(nmodified)+', '
          +str(len(cache.jsonarchives))+' JSON archives')

_cachedFilesByPath = None #it is constant, so we can memoize it

def _scanMo2TaskFunc(param,fromhc2toself,fromjsonfiles2self):
    (dir,folders) = param
    (_,pubfilesbypath) = fromhc2toself
    (jsonfilesbypath,) = fromjsonfiles2self
    global _cachedFilesByPath
    if _cachedFilesByPath is None:
        filesbypath = tasks.fromPublication(pubfilesbypath)
        _cachedFilesByPath = filesbypath
    else:
        filesbypath = _cachedFilesByPath
    nmodified = Val(0)
    ldout = _LoadDirOut()
    nscanned = Cache._loadDir(ldout,dir,
                              jsonfilesbypath,
                              filesbypath,pubfilesbypath,
                              folders,
                              tasks.LambdaReplacement(_notALambda1,(nmodified,)),
                              tasks.LambdaReplacement(_notALambda2,None)
                             )
    return (nscanned,nmodified.val,ldout,pubfilesbypath,folders)

def _ownScanMo22SelfTaskFunc(cache,parallel,scannedfiles,out):
    (nscanned,nmodified,ldout,pubfilesbypath,folders) = out
    cache.jsonfilesbypath |= ldout.jsonfilesbypath
    scannedfiles |= ldout.scannedfiles
    for requested in ldout.requested:
        taskname = 'scanmo2.'+requested
        # recursive task
        task = tasks.Task(taskname,_scanMo2TaskFunc,
                          (requested,folders),
                          ['ownhc2self','ownjsonfiles2self'])
        parallel.addLateTask(task)
        owntaskname = 'ownscanmo22self.'+requested
        owntask = tasks.Task(owntaskname,
                             lambda _,out: _ownScanMo22SelfTaskFunc(cache,parallel,scannedfiles,out),
                             None,[taskname])
        parallel.addLateOwnTask(owntask)

class Cache:
    def __init__(self,allarchivenames,folders,dbgfolder):
        self.folders = folders
        
        self.archives = {}
        self.archivesbypath = {}
        self.filesbypath = {}
        timer = Elapsed()
        
        self.cachedata = {}
        try:
            with open(self.folders.cache+'cache.json', 'rt',encoding='utf-8') as rf:
                self.cachedata = json.load(rf)
        except Exception as e:
            print('WARNING: error loading JSON cachedata: '+str(e)+'. Will continue w/o cachedata')
            self.cachedata = {} # just in case

        scannedfiles = {}
        with tasks.Parallel(self.folders.cache+'parallel.json') as parallel:
            unfilteredarchiveentries = Val(None)
            
            hctask = tasks.Task('loadhc',_loadHCTaskFunc,(self.folders,self.cachedata),[])
            vfstask = tasks.Task('loadvfs',_loadVFSTaskFunc,(self.folders.cache,self.cachedata,dbgfolder),[])
            jsonarchivestask = tasks.Task('jsonarchives',_loadJsonArchivesTaskFunc,(self.folders.cache,),[])
            jsonfilestask = tasks.Task('jsonfiles',_loadJsonFilesTaskFunc,(self.folders.cache,),[])
            jsonarchiveentriestask = tasks.Task('jsonarchiveentries',_loadJsonArchiveEntriesTaskFunc,(self.folders.cache,),[])
            #unfilteredarchiveentries = Val(None)
            
            owntaskhc2self = tasks.Task('ownhc2self',
                                        lambda _,out: _ownHC2SelfTaskFunc(self,parallel,out),
                                        None,['loadhc'])
            #owntaskvfs2val = tasks.Task('ownvfs2val',
            #                            lambda _,out: _ownVFS2ValTaskFunc(parallel,unfilteredarchiveentries,out),
            #                            None,['loadvfs'])
            owntaskjsonarchives2self = tasks.Task('ownjsonarchives2self',
                                        lambda _,out: _ownJsonArchives2SelfTaskFunc(self,out),
                                        None,['jsonarchives'])
            owntaskjsonfiles2self = tasks.Task('ownjsonfiles2self',
                                        lambda _,out: _ownJsonFiles2SelfTaskFunc(self,out),
                                        None,['jsonfiles'])
            owntaskjsonarchiveentries2self = tasks.Task('ownjsonarchiveentries2self',
                                        lambda _,out: _ownJsonArchiveEntries2SelfTaskFunc(self,out),
                                        None,['jsonarchiveentries'])
                        
            ownfiltertask = tasks.Task('filteraes',
                                        lambda _,fromloadvfs,_2,_3: _ownFilterTaskFunc(self,parallel,allarchivenames,fromloadvfs),
                                        None,['loadvfs','loadhc','ownjsonarchives2self'])
            for i in range(len(self.folders.downloads)):
                taskname = 'scandls.'+str(i)
                scandlstask = tasks.Task(taskname,_scanDownloadsTaskFunc,
                                     (self.folders.downloads[i],self.folders.tmp),
                                     ['ownhc2self','ownjsonarchives2self','ownjsonarchiveentries2self'])
                owntaskname = 'ownscandls2self.'+str(i)
                owntaskscansdl2self = tasks.Task(owntaskname,
                                        lambda _,out: _ownScanDownloads2SelfTaskFunc(self,out),
                                        None,[taskname])

            scanmo2task = tasks.Task('scanmo2',_scanMo2TaskFunc,
                                     (self.folders.mo2,self.folders),
                                     ['ownhc2self','ownjsonfiles2self'])
            ownscanmo22selftask = tasks.Task('ownscanmo22self',
                                        lambda _,out: _ownScanMo22SelfTaskFunc(self,parallel,scannedfiles,out),
                                        None,['scanmo2'])
            
            parallel.run([hctask,vfstask,jsonarchivestask,jsonfilestask,
                          jsonarchiveentriestask,scandlstask,scanmo2task],
                         [owntaskhc2self,ownfiltertask,owntaskjsonarchives2self,owntaskjsonfiles2self,
                          owntaskjsonarchiveentries2self,owntaskscansdl2self,ownscanmo22selftask])
        timer.printAndReset('Parallel tasks')
        #dbgWait()

        if dbgfolder:
            self.dbgDump(dbgfolder)
            timer.printAndReset('Dumping dbgfolder')

        #print('scanned/modified files:'+str(nscanned)+'/'+str(nmodified)+', '+str(len(self.jsonfilesbypath))+' JSON files')
        print(len(scannedfiles))
        #dbgWait()
        # timer.printAndReset('Scanning MO2')
        #dbgWait()

        ### Reconciling
        #print('#2:'+str(self.jsonfilesbypath.get('c:\\\\mo2modding\\logs\\usvfs-2024-10-13_19-52-38.log')))
        ndel = 0
        for dict in [self.jsonfilesbypath, self.filesbypath]:
            for fpath in dict:
                assert(Folders.normalizeFilePath(fpath)==fpath)
                if scannedfiles.get(fpath) is None:
                    injson = self.jsonfilesbypath.get(fpath)
                    #print(injson)
                    if injson is not None and injson.file_hash is None: #special record is already present
                        continue
                    info(fpath+' was deleted')
                    #dbgWait()
                    self.jsonfilesbypath[fpath] = File(None,None,fpath.lower())
                    ndel += 1
        print('Reconcile: '+str(ndel)+' files were deleted')
        timer.printAndReset('Reconciling dicts with scannedfiles')
        #dbgWait()
        
        ### Writing JSON HashCache
        _dictOfFisToJsonFile(self.folders.cache+'archives.njson',self.jsonarchivesbypath)
        _dictOfFisToJsonFile(self.folders.cache+'files.njson',self.jsonfilesbypath)
        _dictOfArEntriesToJsonFile(self.folders.cache+'archiveentries.njson',self.jsonarchiveentries)
        
        #Writing CacheData
        with open(self.folders.cache+'cache.json','wt',encoding='utf-8') as wf:
            wf.write(JsonEncoder().encode(self.cachedata))
        
        timer.printAndReset('caches')
        
    def _loadDir(ldout,dir,dicttolook,dicttolook2,pdicttolook2,folders,addfi,foundfile):
        # print(excludefolders)
        # print(reincludefolders)
        nscanned = 0
        # recursive implementation: able to skip subtrees, but more calls (lots of os.listdir() instead of single os.walk())
        # still, after recent performance fix seems to win like 1.5x over os.walk-based one
        for f in os.listdir(dir):
            fpath = dir+Folders.normalizeFileName(f)
            st = os.lstat(fpath)
            fmode = st.st_mode
            if stat.S_ISREG(fmode):
                #assert(not os.path.islink(fpath))
                assert(not stat.S_ISLNK(fmode))
                assert(Folders.normalizeFilePath(fpath)==fpath)
                nscanned += 1
                if foundfile:
                    foundfile.call((ldout,fpath))
                tstamp = _getFileTimestampFromSt(st)
                # print(fpath)
                found = _getFromOneOfDicts(dicttolook,dicttolook2,fpath)
                if found:
                    try:
                        tstamp2 = found.file_modified
                    except:
                        print(found)
                        dbgWait()
                    # print(tstamp,tstamp2,_wjTimestampToPythonTimestamp(tstamp2))
                    if wjdb.compareTimestampWithWj(tstamp,tstamp2)!=0:
                        _diffFound(ldout,fpath,tstamp,addfi,True)
                else:
                    _diffFound(ldout,fpath,tstamp,addfi,False)
            elif stat.S_ISDIR(fmode):
                newdir=fpath+'\\'
                included = folders.isMo2ExactDirIncluded(newdir)
                if not included: #ignored or mo2excluded
                    # print('Excluding '+newdir)
                    for ff in os.listdir(newdir):
                        newdir2 = newdir + Folders.normalizeFileName(ff) 
                        if os.path.isdir(newdir2):
                            newdir2 += '\\'
                            # print(newdir2)
                            newincluded = folders.isMo2ExactDirIncluded(newdir2)
                            assert(newincluded is not False)
                            if newincluded == 2: #mo2reincluded
                                # print('Re-including '+newdir2)
                                if ldout is not None:
                                    ldout.requested.append(newdir2)
                                else:
                                    nscanned += Cache._loadDir(None,newdir2,dicttolook,dicttolook2,pdicttolook2,folders,addfi,foundfile)
                else:
                    nscanned += Cache._loadDir(ldout,newdir,dicttolook,dicttolook2,pdicttolook2,folders,addfi,foundfile)
            else:
                print(fpath)
                assert(False)
        return nscanned

    def findArchiveByName(self,fname):
        assert(Folders.normalizeFileName(fname)==fname)
        #ar = self.archivesbypath.get(fpath.lower())
        ar = None
        for a in _allValuesInBothDicts(self.jsonarchivesbypath,self.archivesbypath):
            if os.path.split(a.file_path)[1] == fname:
                ar = a
                break
        if ar == None:
            return ar

        hash=ar.file_hash
        assert(hash>=0)
        assert(_getFromOneOfDicts(self.jsonarchives,self.archives,hash) is not None)
        return ar
    
    def findFile(self,fpath):
        #fi = self.filesbypath.get(fpath.lower())
        fi = _getFromOneOfDicts(self.jsonfilesbypath,self.filesbypath,fpath.lower())
        if fi == None:
            print("WARNING: path="+fpath+" NOT FOUND")
            return None,None

        hash=fi.file_hash
        assert(hash>=0)
        #archiveEntry = self.archiveentries.get(hash)
        archiveEntry = _getFromOneOfDicts(self.jsonarchiveentries,self.archiveentries,hash)
        if archiveEntry == None:
            #print("WARNING: archiveEntry for path="+fpath+" with hash="+str(hash)+" NOT FOUND")
            return None,None
        #print(archiveEntry.__dict__)

        ahash = archiveEntry.archive_hash
        #archive = self.archives.get(ahash)
        archive = _getFromOneOfDicts(self.jsonarchives,self.archives,ahash)
        if archive == None:
            #print("WARNING: archive with hash="+str(ahash)+" NOT FOUND")
            return None,None
        #print(archive.__dict__)
        return archiveEntry, archive
    
    def allFiles(self):
        for file in self.jsonfilesbypath:
            yield self.jsonfilesbypath[file]
        for file in self.filesbypath:
            if file not in self.jsonfilesbypath:
                yield self.filesbypath[file]
        return None
    
    def dbgDump(self,folder):
        with open(folder+'archives.txt', 'wt', encoding="utf-8") as f:
            for hash in self.archives:
                f.write(str(hash)+':'+str(self.archives[hash].__dict__)+'\n')
        with open(folder+'archiveentries.txt', 'wt', encoding="utf-8") as f:
            for hash in self.archiveentries:
                f.write(str(hash)+':'+str(self.archiveentries[hash].__dict__)+'\n')
                