import os

import wjdb

def normalizePath(path):
    path = os.path.abspath(path)
    assert(path.find('/')<0)
    return path
    
def _foundArchive(archives,archivesbypath,ar):
    return archives.get(ar.archive_hash)
'''    out = archives.get(ar.archive_hash)
    if out:
        if not archivesbypath.get(ar.archive_path):
            print('WARNING: hash '+str(ar.archive_hash)+' is already in Cache, but path '+ar.archive_path+' is not')
            return None
        else:
            return out
    else:
        assert(not archivesbypath.get(ar.archive_path))
        return None
'''
    
def _addArchive(archives,archivesbypath,ar):
    # to get around lambda restrictions
    archives[ar.archive_hash] = ar
    archivesbypath[ar.archive_path] = ar
    
def _addFile(files,ar):
    # to get around lambda restrictions
    files[ar.archive_path] = ar

class Cache:
    def __init__(self,config):
        self.archives = {}
        self.archivesbypath = {}
        self.filesbypath = {}
        wjdb.loadHC([ 
                        (normalizePath(config['downloads']),lambda ar: _foundArchive(self.archives, self.archivesbypath,ar), lambda ar: _addArchive(self.archives,self.archivesbypath,ar)),
                        (normalizePath(config['mo2']),lambda ar: self.filesbypath.get(ar.archive_path), lambda ar: _addFile(self.filesbypath,ar))
                    ])
        assert(len(self.archives)==len(self.archivesbypath)) 
        print(str(len(self.archives))+" archives, "+str(len(self.filesbypath))+" files")

    def loadVFS(self,allinstallfiles,dbgfile=None):
        self.archiveEntries = wjdb.loadVFS(allinstallfiles,dbgfile) 

    def findArchive(self,fpath):
        fpath = normalizePath(fpath)
        ar = self.archivesbypath.get(fpath.lower())
        if ar == None:
            print("WARNING: path="+fpath+" NOT FOUND")
            return None

        hash=ar.archive_hash
        assert(hash>=0)
        archive = self.archives.get(hash)
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
        archive = self.archives.get(ahash)
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
            for hash in self.archiveEntries:
                f.write(str(hash)+':'+str(self.archiveEntries[hash].__dict__)+'\n')
                