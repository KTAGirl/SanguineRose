import os
import stat
import pathlib
import pickle
import json
import shutil

from mo2gitlib.common import *
from mo2gitlib.files import File,ArchiveEntry,wjHash
import mo2gitlib.wjcompat.wjdb as wjdb
import mo2gitlib.pluginhandler as pluginhandler
import mo2gitlib.tasks as tasks
from mo2gitlib.folders import Folders
from mo2gitlib.pickledcache import pickledCache
from mo2gitlib.foldercache import FolderCache,FolderScanFilter

ZEROHASH = 17241709254077376921 #xxhash for 0 size

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
                assert(nested_plugin is not None)
                _archiveToEntries(jsonarchiveentries,archive_hash,tmppath + str(nf) + '\\',new_intra_path,nested_plugin,fpath)

#### JSON loading helpers

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

############# Parallelizable Tasks

### Loading WJ HashCache

def _loadHCAddFi(dls,mo2s,folders,fi):    
    fpath = fi.file_path
    
    if folders.isKnownArchive(fpath):
        for dl in folders.downloads:
            if fpath.startswith(dl):
                assert(fpath not in dls)
                dls[fpath] = fi
    
    if fpath.startswith(folders.mo2):
        if isMo2FilePathIncluded(fpath):
            assert(fpath not in mo2s)
            mo2s[fpath] = fi

def _loadHC(params):
    (folders,) = params
    dls = {}
    mo2s = {}

    wjdb.loadHC( lambda fi:_loadHCAddFi(dls,mo2s,folders,fi) )
    return (dls,mo2s)

def _loadHCTaskFunc(param):
    (folders,cachedata) = param
    return pickledCache(folders.cache,cachedata,'wjdb.hcfile',[wjdb.hcFile()],
                        _loadHC,(folders,))
    
def _ownHC2SelfTaskFunc(cache,parallel,taskout):
    (hcout,cachedataoverwrites) = taskout
    (dls,mo2s) = hcout
    cache.cachedata |= cachedataoverwrites
    
    ndup = 0
    cache.archivesbypath = dls
    cache.archivesbyhash = {}
    for key,val in cache.archivesbypath:
        h = val.file_hash
        if h in cache.archivesbyhash:
            ndup += 1
        else:
            cache.archivesbyhash[val.file_hash] = val
    
    cache.filesbypath = mo2s
    info(str(len(cache.archives))+' archives ('+str(ndup)+' duplicates), '
         +str(len(cache.filesbypath))+' files')

    cache.publishedarchives = tasks.SharedPublication(parallel,cache.archives)

    cache.downloads = []
    for i in range(len(cache.folders.downloads)):
        fc = FolderCache(cache.folders.cachedir,'downloads'+str(i),cache.folders.downloads[i],cache.archivesbypath,
                         FilterForDownloads(cache.folders)
                        )
        fc.startTasks(parallel)
        cache.downloads.append(fc)
        #cache.taskstowait.append(fc.readyTaskName())

    cache.mo2cache = FolderCache(cache.cachedir,'mo2',cache.folders.mo2,{},
                                 FilterForMo2(cache.folders)
                                )
    cache.mo2cache.startTasks(parallel)
    #cache.taskstowait.append(cache.mo2cache.readyTaskName())
    
### Loading VFS
        
def _loadVFS0(dbgfile):
    unfilteredarchiveentries = []
    for ae in wjdb.loadVFS(dbgfile):
        unfilteredarchiveentries.append(ae)    
    return unfilteredarchiveentries

def _loadVFS(cachedir,cachedata,dbgfile):
    (unfilteredarchiveentries,cachedataoverwrites) = pickledCache(cachedir,cachedata,'wjdb.vfsfile',[wjdb.vfsFile()],
                                                                  lambda _: _loadVFS0(dbgfile))

    shared = tasks.SharedReturn(unfilteredarchiveentries)
    return (tasks.makeSharedReturnParam(shared),cachedataoverwrites)

def _loadVFSTaskFunc(param):
    (cachedir,cachedata,dbgfolder) = param
    if dbgfolder:
        with open(dbgfolder+'loadvfs.txt','wt',encoding='utf-8') as dbgfile:
            return _loadVFS(cachedir,cachedata,dbgfile)
    else:
        return _loadVFS(cachedir,cachedata,None)

def _findArByName(dict1,dict2,arname):
    arname1 = '\\'+arname
    for ar in _allValuesInBothDicts(dict1,dict2):
        if ar.file_path.endswith(arname1):
            return ar
    return None

def _ownFilterTaskFunc(cache,parallel,fromloadvfs):
    t0 = time.perf_counter()

    (sharedparam,cachedataoverwrites) = fromloadvfs
    cache.cachedata |= cachedataoverwrites
    
    tsh0 = time.perf_counter()
    unfilteredarchiveentries = tasks.receivedSharedReturn(parallel,sharedparam)
    tsh = time.perf_counter()-tsh0

    allarchivehashes = {}
    #print(dbgFirst(cache.archivesbypath).__dict__)
    for arname in folders.allArchiveNames():
        assert(arname.islower())
        #print(arname)
        #ar = _getFromOneOfDicts(cache.jsonarchivesbypath,cache.archivesbypath,arname)
        ar = _findArByName(cache.jsonarchivesbypath,cache.archivesbypath,arname)
        if ar:
            allarchivehashes[ar.file_hash] = 1
        else:
            warn('no archive hash found for '+arname)
    
    cache.archiveentries = {}
    for ae in unfilteredarchiveentries:
        ahash = ae.archive_hash
        assert(ahash>=0)
        if allarchivehashes.get(ahash) is not None:
            #print(ae.toJSON())
            #dbgWait()
            cache.archiveentries[ae.file_hash] = ae

    tsh0 = time.perf_counter()
    info('Filtering VFS: '+str(len(cache.archiveentries))+' survived out of '+str(len(unfilteredarchiveentries)))
    tsh += time.perf_counter()-tsh0
    info('Filtering took '+str(round(time.perf_counter()-t0,2))+'s, including '+str(round(tsh,2))+'s working with shared memory (pickling/unpickling)')
    #dbgWait()
    
#### Filters for FolderCaches

class FilterForDownloads(FolderScanFilter):
    def __init__(self,folders):
        super().__init__(tasks.LambdaReplacement( _dirPathIsOk, None ),  
                         tasks.LambdaReplacement( _filePathIsOk, (folders,) ))

    def _dirPathIsOk(capture, param):
        return True
    
    def _filePathIsOk(capture, param):
        (folders,) = capture
        fpath = param
        return folders.isKnownArchive(fpath)

class FilterForMo2(FolderScanFilter):
    def __init__(self,folders):
        super().__init__(tasks.LambdaReplacement( _dirPathIsOk, None ),  
                         tasks.LambdaReplacement( _filePathIsOk, (folders,) ))

    def _dirPathIsOk(capture, param):
        (folders,) = capture
        dirpath = param
        return folders.isMo2ExactDirIncluded(dirpath)
    
    def _filePathIsOk(capture, param):
        (folders,) = capture
        fpath = param
        return folders.isMo2FilePathIncluded(fpath)

#### Cache itself

class Cache:
    def __init__(self,folders,dbgfolder):
        self.folders = folders

        self.cachedata = {}
        try:
            with open(self.folders.cache+'cache.json','rt',encoding='utf-8') as rf:
                self.cachedata = json.load(rf)
        except Exception as e:
            print('WARNING: error loading JSON cachedata: '+str(e)+'. Will continue w/o cachedata')
            self.cachedata = {} # just in case

        #self.taskstowait = []
        scannedfiles = {}
        with tasks.Parallel(self.folders.cache+'parallel.json') as parallel:
            unfilteredarchiveentries = Val(None)
            
            hctask = tasks.Task('loadhc',_loadHCTaskFunc,(self.folders,self.cachedata),[])
            vfstask = tasks.Task('loadvfs',_loadVFSTaskFunc,(self.folders.cache,self.cachedata,dbgfolder),[])
            
            owntaskhc2self = tasks.Task('ownhc2self',
                                        lambda _,out: _ownHC2SelfTaskFunc(self,parallel,out), #creates and launches cache.downloads[] FolderCaches 
                                        None,['loadhc']) 
                        
            ownfiltertask = tasks.Task('filteraes',
                                        lambda _,fromloadvfs,_2,_3: _ownFilterTaskFunc(self,parallel,fromloadvfs),
                                        None,['loadvfs','loadhc','ownjsonarchives2self'])
            
            parallel.run([hctask,vfstask],
                         [owntaskhc2self,ownfiltertask])
                         
        # at this point, parallel is done, and we have:
        #    self.downloads[] of FolderCache
        #    self.mo2cache as FolderCache
        #    self.archiveentries as {} (from filteraes task)

        if dbgfolder:
            self.dbgDump(dbgfolder)

        #Writing CacheData
        with open(self.folders.cache+'cache.json','wt',encoding='utf-8') as wf:
            wf.write(JsonEncoder(indent=4).encode(self.cachedata))
        
    def findArchiveByName(self,fname):
        assert(Folders.normalizeFileName(fname)==fname)
        #ar = self.archivesbypath.get(fpath.lower())
        ar = None
        for a in _allValuesInBothDicts(self.jsonarchivesbypath,self.archivesbypath):
            if os.path.split(a.file_path)[1] == fname:
                ar = a
                break
        if ar is None:
            return ar

        hash=ar.file_hash
        assert(hash>=0)
        assert(_getFromOneOfDicts(self.jsonarchives,self.archives,hash) is not None)
        return ar
        
    def findArchiveForFile(self,fpath):
        fi = self.findFileOnly(fpath)
        if fi is None:
            return None,None,None

        if fi.file_hash==ZEROHASH: 
            ae=ArchiveEntry(None,None,0,fi.file_hash)
            return ae,None,None #there is no archive, size=0 is enough to restore the file

        hash=fi.file_hash
        if hash is None:#file was deleted
            return None,None,fi
        #print(fi.__dict__)
        assert(hash>=0)
        #archiveEntry = self.archiveentries.get(hash)
        ae = _getFromOneOfDicts(self.jsonarchiveentries,self.archiveentries,hash)
        if ae is None:
            return None,None,fi
        #print(ae.__dict__)

        ahash = ae.archive_hash
        #archive = self.archives.get(ahash)
        archive = _getFromOneOfDicts(self.jsonarchives,self.archives,ahash)
        if archive is None:
            return None,None,fi
        #print(archive.__dict__)
        return ae,archive,fi
        
    def findFileOnly(self,fpath):
        assert(fpath.islower())
        fi = _getFromOneOfDicts(self.jsonfilesbypath,self.filesbypath,fpath)
        return fi
    
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
                
'''
def _hcFoundDownload(archivesbypath,ndup,ar):
    olda = archives.get(ar.file_hash)
    if olda is not None and not olda.eq(ar):
        warn("identical archives: hash="+str(hash)+" old="+str(olda.__dict__)+" new="+str(ar.__dict__))
        # dbgWait()
        ndup.val += 1
    else:
        archivesbypath[ar.file_path] = ar
    
def _hcFoundFile(filesbypath,nex,ndup,fi,folders):
    if not folders.isMo2FilePathIncluded(fi.file_path): #ignored or mo2excluded
        nex.val += 1
        return
        
    olda = filesbypath.get(fi.file_path)
    if olda is not None and not olda.eq(fi):
        # print("TODO: multiple archives: hash="+str(hash)+" old="+str(olda.__dict__)+" new="+str(fi.__dict__))
        # wait = input("Press Enter to continue.")
        ndup.val += 1
        pass
    else:
        filesbypath[fi.file_path] = fi
'''
##### Lambda parts

'''
def _diffFound(folders,ldout,fpath,tstamp,addfi,updatednotadded):
    #print(fpath)
    hash = wjHash(fpath) #TODO: to Task (only for larger files)
    assert(Folders.normalizeFilePath(fpath)==fpath)
    newa = File(hash,tstamp,fpath)
    addfi.call((folders,ldout,newa,updatednotadded))

def _diffArchive(folders,jsonarchives,jsonarchivesbypath,jsonarchiveentries,tmppathbase,nmodified,ar,updatednotadded):
    if ar.file_path.endswith('.meta'):
        return
    if not folders.isKnownArchive(ar.file_path):
        return
    info('archive '+ar.file_path+' was '+('updated' if updatednotadded else 'added')+' since wj caching')
    jsonarchives[ar.file_hash]=ar
    jsonarchivesbypath[ar.file_path]=ar
    
    tmproot = tmppathbase + 'mo2git.tmp\\' + str(tasks.thisProcNum()+1) + '\\'
    if os.path.isdir(tmproot):
        shutil.rmtree(tmproot)
    os.makedirs(tmproot,exist_ok=True)
    plugin = pluginhandler.archivePluginFor(ar.file_path)
    if plugin is None:
        warn('no archive plugin found for '+ar.file_path)
    else:
        _archiveToEntries(jsonarchiveentries,ar.file_hash,tmproot,[],plugin,ar.file_path)

    shutil.rmtree(tmproot)
    nmodified.val += 1
  
def _diffFile(jsonfilesbypath,nmodified,fi,updatednotadded):
    #info('file '+fi.file_path+' was '+('updated' if updatednotadded else 'added')+' since wj caching')
    jsonfilesbypath[fi.file_path]=fi
    nmodified.val += 1

def _scannedFoundFile(scannedfiles,fpath):
    assert(Folders.normalizeFilePath(fpath)==fpath)
    scannedfiles[fpath] = 1
'''
'''
### Loading JSON Caches

def _ownJsonArchives2SelfTaskFunc(cache,out):
    (jsonarchivesbypath,) = out
    cache.jsonarchivesbypath = {}
    cache.filteredjsonarchives = []
    for key,val in jsonarchivesbypath.items():
        assert(key==val.file_path)
        if cache.folders.isKnownArchive(key):
            cache.jsonarchivesbypath[key] = val
        else:
            cache.filteredjsonarchives.append(val)

    cache.jsonarchives = {}
    for key in cache.jsonarchivesbypath:
        val = cache.jsonarchivesbypath[key]
        cache.jsonarchives[val.file_hash] = val
    assert(len(cache.jsonarchives)==len(cache.jsonarchivesbypath)) 
    info(str(len(cache.jsonarchives))+' JSON archives')
    return (cache.jsonarchives,cache.jsonarchivesbypath)

def _loadJsonFilesTaskFunc(param):
    (cachedir,) = param
    jsonfilesbypath = {}
    try:
        jsonfilesbypath = _dictOfFilesFromJsonFile(cachedir+'files.njson')
    except Exception as e:
        warn('error loading JSON cache files.njson: '+str(e)+'. Will continue w/o file JSON cache')
        jsonfilesbypath = {} # just in case            

    info(str(len(jsonfilesbypath))+' JSON files')
    return (jsonfilesbypath,)
    
def _ownJsonFiles2SelfTaskFunc(cache,parallel,out):
    (jsonfilesbypath,) = out
    cache.jsonfilesbypath = {}
    cache.filteredjsonfiles = []
    for key,val in jsonfilesbypath.items():
        assert(key==val.file_path)
        if cache.folders.isMo2FilePathIncluded(key):
            cache.jsonfilesbypath[key] = val
        else:
            cache.filteredjsonfiles.append(val)
    cache.pubjsonfilesbypath = tasks.SharedPublication(parallel,cache.jsonfilesbypath)
    return (tasks.makeSharedPublicationParam(cache.pubjsonfilesbypath),)

def _loadJsonArchiveEntriesTaskFunc(param):
    (cachedir,) = param
    jsonarchiveentries = {}
    try:
        jsonarchiveentries = _dictOfArEntriesFromJsonFile(cachedir+'archiveentries.njson')
    except Exception as e:
        warn('error loading JSON cache archiveentries.njson: '+str(e)+'. Will continue w/o archiveentries JSON cache')
        jsonarchiveentries = {} # just in case            
    info(str(len(jsonarchiveentries))+' JSON archiveentries')
    return (jsonarchiveentries,)
    
def _ownJsonArchiveEntries2SelfTaskFunc(cache,out):
    (jsonarchiveentries,) = out
    cache.jsonarchiveentries = jsonarchiveentries
    return (cache.jsonarchiveentries,)
'''
'''
### Scanning

def _notALambda0(capture,param):
  (folders,_,ar,updatednotadded) = param
  (jsonarchives,jsonarchivesbypath,jsonarchiveentries,tmppathbase,nmodified) = capture
  _diffArchive(folders,jsonarchives,jsonarchivesbypath,jsonarchiveentries,tmppathbase,nmodified,ar,updatednotadded)

def _notALambda1(capture,param):
    (_,ldout,fi,updatednotadded) = param
    (nmodified,) = capture
    _diffFile(ldout.jsonfilesbypath,nmodified,fi,updatednotadded)
    
def _notALambda2(capture,param):
    assert(capture is None)
    (ldout,fpath) = param
    _scannedFoundFile(ldout.scannedfiles,fpath)

def _ownScanDownloads2SelfTaskFunc(cache,out):
    (nscanned,nmodified,jsonarchives,jsonarchivesbypath,jsonarchiveentries) = out
    cache.jsonarchives = jsonarchives
    cache.jsonarchivesbypath = jsonarchivesbypath
    cache.jsonarchiveentries = jsonarchiveentries
    assert(len(cache.jsonarchives)==len(cache.jsonarchivesbypath)) 
    print('scanned/modified archives:'+str(nscanned)+'/'+str(nmodified)+', '
          +str(len(cache.jsonarchives))+' JSON archives')

_cachedFilesByPath = None #it is constant, so we can memoize it
_cachedJsonFilesByPath = None

def _scanMo2TaskFunc(param,fromhc2toself,fromjsonfiles2self):
    (dir,folders) = param
    (_,pubfilesbypath) = fromhc2toself
    (pubjsonfilesbypath,) = fromjsonfiles2self
    
    global _cachedFilesByPath
    if _cachedFilesByPath is None:
        filesbypath = tasks.fromPublication(pubfilesbypath)
        _cachedFilesByPath = filesbypath
    else:
        filesbypath = _cachedFilesByPath
    
    global _cachedJsonFilesByPath
    if _cachedJsonFilesByPath is None:
        jsonfilesbypath = tasks.fromPublication(pubjsonfilesbypath)
        _cachedJsonFilesByPath = jsonfilesbypath
    else:
        jsonfilesbypath = _cachedJsonFilesByPath
    
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
    print('Merging scannedfiles (nmodified='+str(nmodified)+'): added '+str(len(ldout.scannedfiles))+', now '+str(len(scannedfiles)))
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
'''
    ''' from class Cache
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
                    if found.file_hash is None:#file in cache marked as deleted
                        _diffFound(folders,ldout,fpath,tstamp,addfi,False) #False as we probably can treat 're-added' as 'added'
                    else:
                        tstamp2 = found.file_modified
                        # print(tstamp,tstamp2,_wjTimestampToPythonTimestamp(tstamp2))
                        if wjdb.compareTimestampWithWj(tstamp,tstamp2)!=0:
                            _diffFound(folders,ldout,fpath,tstamp,addfi,True)
                else:
                    _diffFound(folders,ldout,fpath,tstamp,addfi,False)
            elif stat.S_ISDIR(fmode):
                newdir=fpath+'\\'
                included = folders.isMo2ExactDirIncluded(newdir)
                if not included: #ignored or mo2excluded
                    # print('Excluding '+newdir)
                    for newdir2 in folders.allReinclusionsForIgnoredOrExcluded(newdir):
                        assert(Folders.normalizeDirPath(newdir2) == newdir2) 
                        if ldout is not None:
                            ldout.requested.append(newdir2)
                        else:
                            nscanned += Cache._loadDir(None,newdir2,dicttolook,dicttolook2,pdicttolook2,folders,addfi,foundfile)
                else:
                    nscanned += Cache._loadDir(ldout,newdir,dicttolook,dicttolook2,pdicttolook2,folders,addfi,foundfile)
            else:
                print(fpath+' is neither dir or file, aborting')
                aAssert(False)
        return nscanned
    '''