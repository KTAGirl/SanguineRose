import os
import pathlib
import time
import xxhash

from w2gdebug import DEBUG
from w2gdebug import dbgWait
import wjdb

def normalizePath(path):
    path = os.path.abspath(path)
    assert(path.find('/')<0)
    return path
    
def _foundDownload(downloads,downloadsbypath,ar):
    return downloads.get(ar.archive_hash)
''' TODO: review   
    out = downloads.get(ar.archive_hash)
    if out:
        if not downloadsbypath.get(ar.archive_path):
            print('WARNING: hash '+str(ar.archive_hash)+' is already in Cache, but path '+ar.archive_path+' is not')
            return None
        else:
            return out
    else:
        assert(not downloadsbypath.get(ar.archive_path))
        return None
'''
    
def _addDownload(downloads,downloadsbypath,ar):
    # to get around lambda restrictions
    downloads[ar.archive_hash] = ar
    downloadsbypath[ar.archive_path] = ar
    
def _addFile(files,ar):
    # to get around lambda restrictions
    files[ar.archive_path] = ar

###

def _wjTimestampToPythonTimestamp(wjftime):
    return (wjftime - 116444736000000000) / 10**7

def _getFileTimestamp(fname):
    path = pathlib.Path(fname)
    return path.stat().st_mtime

def _compareTimestamps(a,b):
    if abs(a-b) == 0: #< 0.000001: 
        return 0
    return -1 if a < b else 1

#last_modified = getFileTimestamp('..\\..\\mo2\\downloads\\1419098688_DeviousFollowers-ContinuedSEv2_14.5.7z')
#print(last_modified)
#wjts = wjTimestampToPythonTimestamp(133701668551156765)
#print(wjts)
#print(compareTimestamps(last_modified,wjts))
#
#dbgWait()

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

# tohash = '..\\..\\mo2\\mods\\Suspicious City Guards\\suspiciouscityguards.bsa'
# with open(tohash, 'rb') as rfile:
#    data = rfile.read() 
# h = xxhash.xxh64_intdigest(data)
# print(h)
# print(wjHash(tohash))
#
# dbgWait()

class Elapsed:
    def __init__(self):
        self.t0 = time.perf_counter()
        
    def printAndReset(self,where):
        t1 = time.perf_counter()
        print(where+' took '+str(round(t1-self.t0,2))+'s')
        self.t0 = t1

#############

class Cache:
    def __init__(self,config):
        mo2 = normalizePath(config['mo2'])
        downloadsdir = normalizePath(config['downloads'])

        self.downloads = {}
        self.downloadsbypath = {}
        self.filesbypath = {}
        timer = Elapsed()
        wjdb.loadHC([ 
                        (downloadsdir,lambda ar: _foundDownload(self.downloads, self.downloadsbypath,ar), lambda ar: _addDownload(self.downloads,self.downloadsbypath,ar)),
                        (mo2,lambda ar: self.filesbypath.get(ar.archive_path), lambda ar: _addFile(self.filesbypath,ar))
                    ])
        assert(len(self.downloads)==len(self.downloadsbypath)) 
        print(str(len(self.downloads))+" downloads, "+str(len(self.filesbypath))+" files")
        timer.printAndReset('Loading WJ HashCache')
        
        self.modifieddownloads = self._loadDir(downloadsdir,self.downloadsbypath)
        print('modified downloads:'+str(len(self.modifieddownloads)))
        timer.printAndReset('Scanning downloads')
        #for key in self.downloads:
        #    print(self.downloads[key].__dict__)
        
        self.modifiedfiles = self._loadDir(mo2,self.filesbypath,downloadsdir)
        print('modified files:'+str(len(self.modifiedfiles)))
        timer.printAndReset('Scanning MO2')
 
    def _loadDir(self,dir,dicttolook,ignoredir=None):
        files = []
        for dirpath, dirs, filenames in os.walk(dir):
            for filename in filenames:
                if ignoredir and dirpath.startswith(ignoredir):
                    continue
                fpath = os.path.join(dirpath,filename)
                if DEBUG:
                    assert(normalizePath(fpath)==fpath) # if stands - remove all normalizations after os.walk, asserting under dbg.DBG
                assert(not os.path.islink(fpath))
                tstamp = _getFileTimestamp(fpath)
                # print(fpath)
                found = dicttolook.get(fpath.lower())
                if found:
                    tstamp2 = found.archive_modified
                    # print(tstamp,tstamp2,_wjTimestampToPythonTimestamp(tstamp2))
                    if _compareTimestamps(tstamp,_wjTimestampToPythonTimestamp(tstamp2))!=0:
                        print('WARNING: '+fpath+' was updated since wj caching')
                        files.append(wjdb.Archive(-1,tstamp,fpath))
                else:
                    print('WARNING: '+fpath+' was added since wj caching')
                    files.append(wjdb.Archive(-1,tstamp,fpath))
        return files

    def loadVFS(self,allinstallfiles,dbgfile=None):
        timer = Elapsed()
        self.archiveEntries = wjdb.loadVFS(allinstallfiles,dbgfile) 
        timer.printAndReset('Loading WJ VFS')

    def findArchive(self,fpath):
        fpath = normalizePath(fpath)
        ar = self.downloadsbypath.get(fpath.lower())
        if ar == None:
            print("WARNING: path="+fpath+" NOT FOUND")
            return None

        hash=ar.archive_hash
        assert(hash>=0)
        archive = self.downloads.get(hash)
        if archive == None:
            print("WARNING: archive with path="+fpath+" NOT FOUND")
            return None
        #print(archive.__dict__)
        return archive

    def findFile(self,fpath):
        ar = self.filesbypath.get(fpath.lower())
        if ar == None:
            print("WARNING: path="+fpath+" NOT FOUND")
            return None,None

        hash=ar.archive_hash
        assert(hash>=0)
        archiveEntry = self.archiveEntries.get(hash)
        if archiveEntry == None:
            print("WARNING: archiveEntry for path="+fpath+" with hash="+str(hash)+" NOT FOUND")
            return None,None
        #print(archiveEntry.__dict__)

        ahash = archiveEntry.archive_hash
        archive = self.downloads.get(ahash)
        if archive == None:
            print("WARNING: archive with hash="+str(ahash)+" NOT FOUND")
            return None,None
        #print(archive.__dict__)
        return archiveEntry, archive
         
    def dbgDump(self,folder):
        with open(folder+'downloads.txt', 'wt', encoding="utf-8") as f:
            for hash in self.downloads:
                f.write(str(hash)+':'+str(self.downloads[hash].__dict__)+'\n')
        with open(folder+'archiveentries.txt', 'wt', encoding="utf-8") as f:
            for hash in self.archiveEntries:
                f.write(str(hash)+':'+str(self.archiveEntries[hash].__dict__)+'\n')
                