import os
import stat
import pathlib
#import json
import shutil
from threading import Thread
from queue import Queue
#from multiprocessing import Process, Queue as PQueue

import xxhash

from mo2git.debug import *
from mo2git.common import *
import mo2git.wjdb as wjdb
import mo2git.pluginhandler as pluginhandler
import mo2git.tasks as tasks

def _hcFoundDownload(archives,archivesbypath,ndup,ar):
    if ar.archive_path.endswith('.meta'):
        return
    olda = archives.get(ar.archive_hash)
    if olda!=None and not olda.eq(ar):
        print("WARNING: identical archives: hash="+str(hash)+" old="+str(olda.__dict__)+" new="+str(ar.__dict__))
        # dbgWait()
        ndup.val += 1
        pass
    else:
        # out[idx][hash] = ar
        archives[ar.archive_hash] = ar
        archivesbypath[ar.archive_path] = ar
    
def _hcFoundFile(filesbypath,nex,ndup,ar,excludefolders,reincludefolders):
    exclude = False
    for ex in excludefolders:
        if ar.archive_path.startswith(ex.lower()):
            exclude = True
            break
    if exclude:
        for inc in reincludefolders:
            if ar.archive_path.startswith(inc.lower()):
                exclude = False
                break
    if exclude:
        nex.val += 1
        return
        
    olda = filesbypath.get(ar.archive_path)
    if olda!=None and not olda.eq(ar):
        # print("TODO: multiple archives: hash="+str(hash)+" old="+str(olda.__dict__)+" new="+str(ar.__dict__))
        # wait = input("Press Enter to continue.")
        ndup.val += 1
        pass
    else:
        filesbypath[ar.archive_path] = ar

###

def _getFileTimestamp(s):
    path = pathlib.Path(fname)
    return path.stat().st_mtime

def _getFileTimestampFromSt(st):
    # path = pathlib.Path(fname)
    return st.st_mtime

def _compareTimestamps(a,b):
    if abs(a-b) == 0: #< 0.000001: 
        return 0
    return -1 if a < b else 1

def _wjHash(fname):
    h = xxhash.xxh64()
    blocksize = 1048576
    with open(fname,'rb') as f:
        while True:
            bb = f.read(blocksize)
            h.update(bb)
            assert(len(bb)<=blocksize)
            if len(bb) != blocksize:
                return h.intdigest()

def _getFromOneOfDicts(dicttolook,dicttolook2,key):
    found = dicttolook.get(key)
    if found != None:
        return found
    return dicttolook2.get(key)

def _diffFound(outqitem,fpath,tstamp,addar,updatednotadded):
    # print(fpath)
    hash = _wjHash(fpath)
    newa = wjdb.Archive(hash,tstamp,fpath.lower())
    addar(outqitem,newa,updatednotadded)

def _archiveToEntries(jsonarchiveentries,archive_hash,tmppath,cur_intra_path,plugin,archivepath):
    if not os.path.isdir(tmppath):
        os.makedirs(tmppath)
    plugin.extractAll(archivepath,tmppath)
    #dbgWait()
    exts = pluginhandler.allArchivePluginsExtensions()
    for root, dirs, files in os.walk(tmppath):
        nf = 0
        for f in files:
            nf += 1
            fpath = os.path.join(root, f)
            assert(os.path.isfile(fpath))
            # print(fpath)
            hash = _wjHash(fpath)
            assert(fpath.startswith(tmppath))
            intra_path = cur_intra_path.copy()
            intra_path.append(fpath[len(tmppath):])
            ae = wjdb.ArchiveEntry(archive_hash,intra_path,os.path.getsize(fpath),hash)
            # print(ae.__dict__)
            jsonarchiveentries[ae.file_hash]=ae

            ext = os.path.split(fpath)[1].lower()
            if ext in exts:
                nested_plugin = pluginhandler.archivePluginFor(fpath)
                assert(nested_plugin != None)
                _archiveToEntries(jsonarchiveentries,archive_hash,tmppath + str(nf) + '/',intra_path,nested_plugin,fpath)

def _diffArchive(jsonarchives,jsonarchivesbypath,jsonarchiveentries,tmppathbase,nmodified,ar,updatednotadded):
    if ar.archive_path.endswith('.meta'):
        return
    print('NOTICE: archive '+ar.archive_path+' was '+('updated' if updatednotadded else 'added')+' since wj caching')
    jsonarchives[ar.archive_hash]=ar
    jsonarchivesbypath[ar.archive_path]=ar
    
    tmproot = tmppathbase + 'tmp/'
    if os.path.isdir(tmproot):
        shutil.rmtree(tmproot)
    os.makedirs(tmproot,exist_ok=True)
    plugin = pluginhandler.archivePluginFor(ar.archive_path)
    if plugin == None:
        print('WARNING: no archive plugin found for '+ar.archive_path)
    else:
        _archiveToEntries(jsonarchiveentries,ar.archive_hash,tmproot,[],plugin,ar.archive_path)

    shutil.rmtree(tmproot)
    nmodified.val += 1
  
def _diffFile(jsonfilesbypath,nmodified,ar,updatednotadded):
    print('NOTICE: file '+ar.archive_path+' was '+('updated' if updatednotadded else 'added')+' since wj caching')
    jsonfilesbypath[ar.archive_path]=ar
    nmodified.val += 1

def _scannedFoundFile(scannedfiles,fpath):
    assert(normalizePath(fpath)==fpath)
    scannedfiles[fpath.lower()] = 1

####

def _dictOfArsFromJsonFile(path):
    out = {}
    with openModTxtFile(path) as rfile:
        for line in rfile:
            ar = wjdb.Archive.fromJSON(line)
            assert(out.get(ar.archive_path) is None)
            out[ar.archive_path] = ar
    return out

def _dictOfArsToJsonFile(path,ars):
    with openModTxtFileW(path) as wfile:
        for key in sorted(ars):
            ar = ars[key]
            wfile.write(wjdb.Archive.toJSON(ar)+'\n')

def _dictOfArEntriesFromJsonFile(path):
    out = {}
    with openModTxtFile(path) as rfile:
        for line in rfile:
            ae = wjdb.ArchiveEntry.fromJSON(line)
            # print(ar.__dict__)
            out[ae.file_hash] = ae
    return out

def _dictOfArEntriesToJsonFile(path,aes):
    with openModTxtFileW(path) as wfile:
        for key in sorted(aes):
            ae = aes[key]
            wfile.write(wjdb.ArchiveEntry.toJSON(ae)+'\n')

#############

class _LoadDirQueueItem:
    def __init__(self):
        self.jsonfilesbypath = {}
        self.scannedfiles = {}

def _loadDirThreadFunc(procnum,inq,outq):
    outqitem = _LoadDirQueueItem()
    while True:
        request = inq.get()
        if request is None:
            outq.put(outqitem)
            return        
        Cache._loadDir(None,outqitem,request[0],request[1],request[2],request[3],request[4],request[5],request[6])

'''
def _loadVFS0(unfilteredarchiveentries,dbgfile):
    for ae in wjdb.loadVFS(dbgfile):
        unfilteredarchiveentries.append(ae)
'''
BLOCKSIZE = 65536
def _loadVFS0(unfilteredarchiveentries,dbgfile):
    buf = []
    nleft = BLOCKSIZE
    for ae in wjdb.loadVFS(dbgfile):
        buf.append(ae)
        nleft -= 1
        if nleft <= 0:
            unfilteredarchiveentries.appendBlock(buf)
            buf = []
            nleft = BLOCKSIZE
    if len(buf):
        unfilteredarchiveentries.appendBlock(buf)

def _loadVFS(unfilteredarchiveentries,dbgfolder):
    if dbgfolder:
        with open(dbgfolder+'loadvfs.txt','wt',encoding='utf-8') as dbgfile:
            _loadVFS0(unfilteredarchiveentries,dbgfile)
    else:
        _loadVFS0(unfilteredarchiveentries,None)

def _loadHC(mo2,downloadsdir,mo2excludefolders,mo2reincludefolders):
    ndupdl = Val(0) #passable by ref
    nexf = Val(0)
    ndupf = Val(0)
    archives = {}
    archivesbypath = {}
    filesbypath = {}
    wjdb.loadHC([ 
                    (downloadsdir,lambda ar: _hcFoundDownload(archives, archivesbypath,ndupdl,ar)),
                    (mo2,lambda ar: _hcFoundFile(filesbypath,nexf,ndupf,ar,mo2excludefolders,mo2reincludefolders))
                ])
    return archives,archivesbypath,filesbypath,ndupdl.val,nexf.val,ndupf.val

def _loadHCTaskFunc(param):
    (mo2,downloadsdir,mo2excludefolders,mo2reincludefolders) = param
    archives,archivesbypath,filesbypath,ndupdl,nexf,ndupf = _loadHC(mo2,downloadsdir,mo2excludefolders,mo2reincludefolders)
    return (archives,archivesbypath,filesbypath,ndupdl,nexf,ndupf)
    
def _loadHC2SelfTaskFunc(cache,out):
    (cache.archives,cache.archivesbypath,cache.filesbypath,ndupdl,nexf,ndupf) = out        
    assert(len(cache.archives)==len(cache.archivesbypath)) 
    print(str(len(cache.archives))+' archives ('+str(ndupdl)+' duplicates), '
         +str(len(cache.filesbypath))+' files ('+str(nexf)+' excluded, '+str(ndupf)+' duplicates)')

def _loadVFSTaskFunc(param):
    (unfilteredarchiveentries,dbgfolder) = param
    _loadVFS(unfilteredarchiveentries,dbgfolder)

#def _loadVFS2ValTaskFunc(val,out):
#    (unfilteredarchiveentries,) = out
#    val.val = unfilteredarchiveentries

def _loadJsonArchivesTaskFunc(param):
    (cachedir,) = param
    jsonarchivesbypath = {}
    try:
        jsonarchivesbypath = _dictOfArsFromJsonFile(cachedir+'archives.njson')
    except Exception as e:
        print('WARNING: error loading JSON cache archives.njson: '+str(e)+'. Will continue w/o archive JSON cache')
        jsonarchivesbypath = {} # just in case  
    return (jsonarchivesbypath,)

def _loadJsonArchives2SelfTaskFunc(cache,out):
    (jsonarchivesbypath,) = out
    cache.jsonarchivesbypath = jsonarchivesbypath
    cache.jsonarchives = {}
    for key in cache.jsonarchivesbypath:
        val = cache.jsonarchivesbypath[key]
        cache.jsonarchives[val.archive_hash] = val
    assert(len(cache.jsonarchives)==len(cache.jsonarchivesbypath)) 
    print(str(len(cache.jsonarchives))+' JSON archives')

def _loadJsonFilesTaskFunc(param):
    (cachedir,) = param
    jsonfilesbypath = {}
    try:
        jsonfilesbypath = _dictOfArsFromJsonFile(cachedir+'files.njson')
    except Exception as e:
        print('WARNING: error loading JSON cache files.njson: '+str(e)+'. Will continue w/o file JSON cache')
        jsonfilesbypath = {} # just in case            

    print(str(len(jsonfilesbypath))+' JSON files')
    return (jsonfilesbypath,)
    
def _loadJsonFiles2SelfTaskFunc(cache,out):
    (jsonfilesbypath,) = out
    cache.jsonfilesbypath = jsonfilesbypath

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
    
def _loadJsonArchiveEntries2SelfTaskFunc(cache,out):
    (jsonarchiveentries,) = out
    cache.jsonarchiveentries = jsonarchiveentries
    
class Cache:
    def __init__(self,allarchivenames,cachedir,downloadsdir,mo2,mo2excludefolders,mo2reincludefolders,tmppathbase,dbgfolder):
        self.cachedir = cachedir
        
        self.archives = {}
        self.archivesbypath = {}
        self.filesbypath = {}
        timer = Elapsed()

        with tasks.Parallel(self.cachedir+'parallel.json') as parallel:
            unfilteredarchiveentries = tasks.GrowableSharedList(parallel)
            
            hctask = tasks.Task('loadhc',_loadHCTaskFunc,(mo2,downloadsdir,mo2excludefolders,mo2reincludefolders),[])
            vfstask = tasks.Task('loadvfs',_loadVFSTaskFunc,(unfilteredarchiveentries,dbgfolder),[])
            jsonarchivestask = tasks.Task('jsonarchives',_loadJsonArchivesTaskFunc,(self.cachedir,),[])
            jsonfilestask = tasks.Task('jsonfiles',_loadJsonFilesTaskFunc,(self.cachedir,),[])
            jsonarchiveentriestask = tasks.Task('jsonarchiveentries',_loadJsonArchiveEntriesTaskFunc,(self.cachedir,),[])
            #unfilteredarchiveentries = Val(None)            
            owntaskhc2self = tasks.Task('ownhc2self',lambda param,out: _loadHC2SelfTaskFunc(self,out),None,['loadhc'])
            #owntaskvfs2val = tasks.Task('ownvfs2val',lambda param,out: _loadVFS2ValTaskFunc(unfilteredarchiveentries,out),None,['loadvfs'])
            owntaskjsonarchives2self = tasks.Task('ownjsonarchives2self',lambda param,out: _loadJsonArchives2SelfTaskFunc(self,out),None,['jsonarchives'])
            owntaskjsonfiles2self = tasks.Task('ownjsonfiles2self',lambda param,out: _loadJsonFiles2SelfTaskFunc(self,out),None,['jsonfiles'])
            owntaskjsonarchiveentries2self = tasks.Task('ownjsonarchiveentries2self',lambda param,out: _loadJsonArchiveEntries2SelfTaskFunc(self,out),None,['jsonarchiveentries'])
            parallel.run([hctask,jsonarchivestask,jsonfilestask,jsonarchiveentriestask],
                         [vfstask,owntaskhc2self,
#                         owntaskvfs2val,
                         owntaskjsonarchives2self,owntaskjsonfiles2self,owntaskjsonarchiveentries2self])
        timer.printAndReset('Parallel tasks')
        #dbgWait()

        allarchivehashes = {}
        for arname in allarchivenames:
            ar = _getFromOneOfDicts(self.archivesbypath,self.jsonarchivesbypath,arname.lower())
            if ar:
                allarchivehashes[ar.archive_hash] = 1
            else:
                print('WARNING: no archive hash found for '+arname)
        
        self.archiveentries = {}
 #       for ae in unfilteredarchiveentries.val:
 #           if allarchivehashes.get(ae.archive_hash) is not None:
 #               self.archiveentries[ae.file_hash] = ae
        for ae in unfilteredarchiveentries.allItems():
            ahash = ae.archive_hash
            assert(ahash>=0)
            if allarchivehashes.get(ahash) is not None:
                #print(ae.toJSON())
                #dbgWait()
                self.archiveentries[ae.file_hash] = ae
        print('Filtered: '+str(len(self.archiveentries)))
        timer.printAndReset('Filtering WJ VFS')
        dbgWait()

        if dbgfolder:
            self.dbgDump(dbgfolder)
            timer.printAndReset('Dumping dbgfolder')

        ### Scanning
        # Scanning downloads
        nmodified = Val(0)
        nscanned = Cache._loadDir(None,None,downloadsdir,self.jsonarchivesbypath,self.archivesbypath,[],[],
                                  lambda unused,ar,updatednotadded: _diffArchive(self.jsonarchives,self.jsonarchivesbypath,self.jsonarchiveentries,tmppathbase,nmodified,ar,updatednotadded),
                                  None
                                 )
        assert(len(self.jsonarchives)==len(self.jsonarchivesbypath)) 
        print('scanned/modified archives:'+str(nscanned)+'/'+str(nmodified)+', '+str(len(self.jsonarchives))+' JSON archives')
        timer.printAndReset('Scanning downloads')
        
        # Scanning mo2
        nmodified.val = 0
        scannedfiles = {}
        inq = Queue()
        outq = Queue() 
        outqitem = _LoadDirQueueItem()
        threads = [] #actually, threads for now because of problems with lambdas
        NPROC = min(os.cpu_count(),8)-1 #we're disk bound, but apparently up to 8 threads still get improvement, at least on my box ;)
        assert(NPROC>=0)
        print('Using '+str(NPROC)+' extra threads...')
        for i in range(0,NPROC):
            th = Thread(target=_loadDirThreadFunc,args=(i,inq,outq))
            th.start()
            threads.append(th)
        nscanned = Cache._loadDir(inq if NPROC > 0 else None,outqitem,mo2,self.jsonfilesbypath,self.filesbypath,mo2excludefolders,mo2reincludefolders,
                                  lambda outqitem,ar,updatednotadded: _diffFile(outqitem.jsonfilesbypath,nmodified,ar,updatednotadded),
                                  lambda outqitem,fpath:_scannedFoundFile(outqitem.scannedfiles,fpath)
                                 )
        for i in range(0,NPROC):
            inq.put(None) # to terminate
        self.jsonfilesbypath |= outqitem.jsonfilesbypath
        scannedfiles |= outqitem.scannedfiles
        for i in range(0,NPROC):
            threads[i].join()
        while True:
            if outq.empty(): # after all threads joined, nothing can be added
                break
            procoutqitem = outq.get(False)
            #print(len(procoutqitem.jsonfilesbypath))
            #print(len(procoutqitem.scannedfiles))
            self.jsonfilesbypath |= procoutqitem.jsonfilesbypath
            scannedfiles |= procoutqitem.scannedfiles
            #dbgWait()
        print('scanned/modified files:'+str(nscanned)+'/'+str(nmodified)+', '+str(len(self.jsonfilesbypath))+' JSON files')
        # print(len(scannedfiles))
        # dbgWait()
        timer.printAndReset('Scanning MO2')
        #dbgWait()

        ### Reconciling
        #print('#2:'+str(self.jsonfilesbypath.get('c:\\\\mo2modding\\logs\\usvfs-2024-10-13_19-52-38.log')))
        ndel = 0
        for dict in [self.jsonfilesbypath, self.filesbypath]:
            for fpath in dict:
                if scannedfiles.get(fpath) is None:
                    injson = self.jsonfilesbypath.get(fpath.lower())
                    #print(injson)
                    if injson is not None and injson.archive_hash is None: #special record is already present
                        continue
                    print('NOTICE: '+fpath+' was deleted')
                    self.jsonfilesbypath[fpath] = wjdb.Archive(None,None,fpath.lower())
                    ndel += 1
        print('Reconcile: '+str(ndel)+' files were deleted')
        timer.printAndReset('Reconciling dicts with scannedfiles')
        #dbgWait()
        
        ### Writing JSON HashCache
        _dictOfArsToJsonFile(self.cachedir+'archives.njson',self.jsonarchivesbypath)
        _dictOfArsToJsonFile(self.cachedir+'files.njson',self.jsonfilesbypath)
        _dictOfArEntriesToJsonFile(self.cachedir+'archiveentries.njson',self.jsonarchiveentries)
        timer.printAndReset('Writing JSON HashCache')
        
    def _loadDir(inq,outqitem,dir,dicttolook,dicttolook2,excludefolders,reincludefolders,addar,foundfile):
        # print(excludefolders)
        # print(reincludefolders)
        nscanned = 0
        # recursive implementation: able to skip subtrees, but more calls (lots of os.listdir() instead of single os.walk())
        # still, after recent performance fix seems to win like 1.5x over os.walk-based one
        for f in os.listdir(dir):
            fpath = dir+f
            st = os.lstat(fpath)
            fmode = st.st_mode
            if stat.S_ISREG(fmode):
                #assert(not os.path.islink(fpath))
                assert(not stat.S_ISLNK(fmode))
                if DEBUG:
                    assert(normalizePath(fpath)==fpath)
                nscanned += 1
                if foundfile:
                    foundfile(outqitem,fpath)
                tstamp = _getFileTimestampFromSt(st)
                # print(fpath)
                found = _getFromOneOfDicts(dicttolook,dicttolook2,fpath.lower())
                if found:
                    try:
                        tstamp2 = found.archive_modified
                    except:
                        print(found)
                        dbgWait()
                    # print(tstamp,tstamp2,_wjTimestampToPythonTimestamp(tstamp2))
                    if _compareTimestamps(tstamp,tstamp2)!=0:
                        _diffFound(outqitem,fpath,tstamp,addar,True)
                else:
                    _diffFound(outqitem,fpath,tstamp,addar,False)
            elif stat.S_ISDIR(fmode):
                newdir=fpath+'\\'
                exclude = newdir in excludefolders
                if exclude:
                    # print('Excluding '+newdir)
                    for ff in os.listdir(newdir):
                        newdir2 = newdir + ff 
                        if os.path.isdir(newdir2):
                            newdir2 += '\\'
                            # print(newdir2)
                            if newdir2 in reincludefolders:
                                # print('Re-including '+newdir2)
                                if inq is not None:
                                    inqitem = (newdir2,dicttolook,dicttolook2,excludefolders,reincludefolders,addar,foundfile)
                                    inq.put(inqitem)
                                else:
                                    nscanned += Cache._loadDir(inq,outqitem,newdir2,dicttolook,dicttolook2,excludefolders,reincludefolders,addar,foundfile)
                else:
                    nscanned += Cache._loadDir(inq,outqitem,newdir,dicttolook,dicttolook2,excludefolders,reincludefolders,addar,foundfile)
            else:
                print(fpath)
                assert(False)
        return nscanned

    def findArchive(self,fpath):
        fpath = normalizePath(fpath)
        #ar = self.archivesbypath.get(fpath.lower())
        ar = _getFromOneOfDicts(self.jsonarchivesbypath,self.archivesbypath,fpath.lower())
        if ar == None:
            print("WARNING: path="+fpath+" NOT FOUND")
            return None

        hash=ar.archive_hash
        assert(hash>=0)
        #archive = self.archives.get(hash)
        archive = _getFromOneOfDicts(self.jsonarchives,self.archives,hash)
        if archive == None:
            print("WARNING: archive with path="+fpath+" NOT FOUND")
            return None
        #print(archive.__dict__)
        return archive

    def findFile(self,fpath):
        #ar = self.filesbypath.get(fpath.lower())
        ar = _getFromOneOfDicts(self.jsonfilesbypath,self.filesbypath,fpath.lower())
        if ar == None:
            print("WARNING: path="+fpath+" NOT FOUND")
            return None,None

        hash=ar.archive_hash
        assert(hash>=0)
        #archiveEntry = self.archiveentries.get(hash)
        archiveEntry = _getFromOneOfDicts(self.jsonarchiveentries,self.archiveentries,hash)
        if archiveEntry == None:
            print("WARNING: archiveEntry for path="+fpath+" with hash="+str(hash)+" NOT FOUND")
            return None,None
        #print(archiveEntry.__dict__)

        ahash = archiveEntry.archive_hash
        #archive = self.archives.get(ahash)
        archive = _getFromOneOfDicts(self.jsonarchives,self.archives,ahash)
        if archive == None:
            print("WARNING: archive with hash="+str(ahash)+" NOT FOUND")
            return None,None
        #print(archive.__dict__)
        return archiveEntry, archive
         
    def dbgDump(self,folder):
        with open(folder+'archives.txt', 'wt', encoding="utf-8") as f:
            for hash in self.archives:
                f.write(str(hash)+':'+str(self.archives[hash].__dict__)+'\n')
        with open(folder+'archiveentries.txt', 'wt', encoding="utf-8") as f:
            for hash in self.archiveentries:
                f.write(str(hash)+':'+str(self.archiveentries[hash].__dict__)+'\n')
                