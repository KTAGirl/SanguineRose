import os
import stat
import pathlib
import json
import shutil

import xxhash

from mo2git.debug import *
from mo2git.common import *
import mo2git.wjdb as wjdb
import mo2git.pluginhandler as pluginhandler

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
    
def _hcFoundFile(filesbypath,ndup,ar):
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

def _diffFound(fpath,tstamp,addar,updatednotadded):
    # print(fpath)
    hash = _wjHash(fpath)
    newa = wjdb.Archive(hash,tstamp,fpath.lower())
    addar(newa,updatednotadded)

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
    print('WARNING: '+ar.archive_path+' was '+('updated' if updatednotadded else 'added')+' since wj caching')
    jsonarchives[ar.archive_hash]=ar
    jsonarchivesbypath[ar.archive_path]=ar
    
    tmproot = tmppathbase + 'tmp/'
    if os.path.isdir(tmproot):
        shutil.rmtree(tmproot)
    os.makedirs(tmproot,exist_ok=True)
    plugin = pluginhandler.archivePluginFor(ar.archive_path)
    #print(plugin)
    #dbgWait()
    if plugin == None:
        print('WARNING: no archive plugin found for '+ar.archive_path)
    else:
        _archiveToEntries(jsonarchiveentries,ar.archive_hash,tmproot,[],plugin,ar.archive_path)

    shutil.rmtree(tmproot)
    nmodified.val += 1
  
def _diffFile(jsonfilesbypath,nmodified,ar,updatednotadded):
    print('WARNING: '+ar.archive_path+' was '+('updated' if updatednotadded else 'added')+' since wj caching')
    jsonfilesbypath[ar.archive_path]=ar
    nmodified.val += 1

####

def _dictOfArsFromJsonFile(path):
    out = {}
    with openModTxtFile(path) as rfile:
        for line in rfile:
            ar = wjdb.Archive.fromJSON(line)
            # print(ar.__dict__)
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

class Cache:
    def __init__(self,allarchivenames,cachedir,downloadsdir,mo2,mo2excludefolders,mo2reincludefolders,tmppathbase,dbgfolder):
        self.cachedir = cachedir
        
        self.archives = {}
        self.archivesbypath = {}
        self.filesbypath = {}
        timer = Elapsed()
        
        ### Loading HashCache
        # Loading WJ HashCache
        ndupdl = Val(0) #passable by ref
        ndupf = Val(0)
        wjdb.loadHC([ 
                        (downloadsdir,lambda ar: _hcFoundDownload(self.archives, self.archivesbypath,ndupdl,ar)),
                        (mo2,lambda ar: _hcFoundFile(self.filesbypath,ndupf,ar))
                    ])
        assert(len(self.archives)==len(self.archivesbypath)) 
        print(str(len(self.archives))+' archives ('+str(ndupdl)+' duplicates), '+str(len(self.filesbypath))+' files ('+str(ndupf)+' duplicates)')
        timer.printAndReset('Loading WJ HashCache')

        if dbgfolder:
            dbgDmp(dbgfolder)
            timer.printAndReset('Dumping dbgfolder')

        # Loading NJSON HashCache
        self.jsonarchivesbypath = {}
        try:
            self.jsonarchivesbypath = _dictOfArsFromJsonFile(self.cachedir+'archives.njson')
        except Exception as e:
            print('WARNING: error loading JSON cache archives.njson: '+str(e)+'. Will continue w/o archive JSON cache')
            self.jsonarchivesbypath = {} # just in case            
        self.jsonarchives = {}
        for key in self.jsonarchivesbypath:
            val = self.jsonarchivesbypath[key]
            self.jsonarchives[val.archive_hash] = val
        assert(len(self.jsonarchives)==len(self.jsonarchivesbypath)) 
        print(str(len(self.jsonarchives))+' JSON archives')

        self.jsonfilesbypath = {}
        try:
            self.jsonfilesbypath = _dictOfArsFromJsonFile(self.cachedir+'files.njson')
        except Exception as e:
            print('WARNING: error loading JSON cache files.njson: '+str(e)+'. Will continue w/o file JSON cache')
            self.jsonfilesbypath = {} # just in case            

        print(str(len(self.jsonfilesbypath))+' JSON files')
        timer.printAndReset('Loading JSON HashCache')

        ### Loading VFS Cache
        # Loading WJ VFS
        allarchivehashes = {}
        for arname in allarchivenames:
            ar = _getFromOneOfDicts(self.archivesbypath,self.jsonarchivesbypath,arname.lower())
            if ar:
                allarchivehashes[ar.archive_hash] = 1
            else:
                print('WARNING: no archive hash found for '+arname)
                
        if dbgfolder:
            with open(dbgfolder+'loadvfs.txt','wt',encoding='utf-8') as dbgfile:
                self.archiveentries = wjdb.loadVFS(allarchivehashes,dbgfile) 
        else:
            self.archiveentries = wjdb.loadVFS(allarchivehashes)            
        timer.printAndReset('Loading WJ VFS')
        
        # Loading NJSON VFS Cache
        self.jsonarchiveentries = {}
        try:
            self.jsonarchiveentries = _dictOfArEntriesFromJsonFile(self.cachedir+'archiveentries.njson')
        except Exception as e:
            print('WARNING: error loading JSON cache archiveentries.njson: '+str(e)+'. Will continue w/o archiveentries JSON cache')
            self.jsonarchiveentries = {} # just in case            
        print(str(len(self.jsonarchiveentries))+' JSON archiveentries')
        timer.printAndReset('Loading JSON archiveentries')

        ### Scanning
        # Scanning downloads
        nmodified = Val(0)
        nscanned = Cache._loadDir(downloadsdir,self.jsonarchivesbypath,self.archivesbypath,[],[],
                                  lambda ar,updatednotadded: _diffArchive(self.jsonarchives,self.jsonarchivesbypath,self.jsonarchiveentries,tmppathbase,nmodified,ar,updatednotadded)
                                 )
        assert(len(self.jsonarchives)==len(self.jsonarchivesbypath)) 
        print('scanned/modified archives:'+str(nscanned)+'/'+str(nmodified)+', '+str(len(self.jsonarchives))+' JSON archives')
        timer.printAndReset('Scanning downloads')
        
        # Scanning mo2
        nmodified.val = 0
        nscanned = Cache._loadDir(mo2,self.jsonfilesbypath,self.filesbypath,mo2excludefolders,mo2reincludefolders,
                                  lambda ar,updatednotadded: _diffFile(self.jsonfilesbypath,nmodified,ar,updatednotadded)
                                 )
        print('scanned/modified files:'+str(nscanned)+'/'+str(nmodified)+', '+str(len(self.jsonfilesbypath))+' JSON files')
        timer.printAndReset('Scanning MO2')

        ### Writing JSON HashCache
        _dictOfArsToJsonFile(self.cachedir+'archives.njson',self.jsonarchivesbypath)
        _dictOfArsToJsonFile(self.cachedir+'files.njson',self.jsonfilesbypath)
        _dictOfArEntriesToJsonFile(self.cachedir+'archiveentries.njson',self.jsonarchiveentries)
        timer.printAndReset('Writing JSON HashCache')
        
    def _loadDir(dir,dicttolook,dicttolook2,excludefolders,reincludefolders,addar):
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
                tstamp = _getFileTimestampFromSt(st)
                # print(fpath)
                found = _getFromOneOfDicts(dicttolook,dicttolook2,fpath.lower()) # dicttolook.get(fpath.lower())
                if found:
                    tstamp2 = found.archive_modified
                    # print(tstamp,tstamp2,_wjTimestampToPythonTimestamp(tstamp2))
                    if _compareTimestamps(tstamp,tstamp2)!=0:
                        _diffFound(fpath,tstamp,addar,True)
                else:
                    _diffFound(fpath,tstamp,addar,False)
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
                                nscanned += Cache._loadDir(newdir2,dicttolook,dicttolook2,excludefolders,reincludefolders,addar)
                else:
                    nscanned += Cache._loadDir(newdir,dicttolook,dicttolook2,excludefolders,reincludefolders,addar)
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
        with open(folder+'downloads.txt', 'wt', encoding="utf-8") as f:
            for hash in self.archives:
                f.write(str(hash)+':'+str(self.downloads[hash].__dict__)+'\n')
        with open(folder+'archiveentries.txt', 'wt', encoding="utf-8") as f:
            for hash in self.archiveentries:
                f.write(str(hash)+':'+str(self.archiveentries[hash].__dict__)+'\n')
                