import os
import stat
import pathlib
import time
import xxhash
import json

from w2gdebug import DEBUG
from w2gdebug import dbgWait
from modlist import openModTxtFile
from modlist import openModTxtFileW
import wjdb
from wjdb import escapeJSON 

def normalizePath(path):
    path = os.path.abspath(path)
    assert(path.find('/')<0)
    return path
    
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

class Val:
    def __init__(self,initval):
        self.val = initval
        
    def __str__(self):
        return str(self.val)

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

def _diffArchive(jsonarchives,jsonarchivesbypath,nmodified,ar,updatednotadded):
    if ar.archive_path.endswith('.meta'):
        return
    print('WARNING: '+ar.archive_path+' was '+('updated' if updatednotadded else 'added')+' since wj caching')
    jsonarchives[ar.archive_hash]=ar
    jsonarchivesbypath[ar.archive_path]=ar
    nmodified.val += 1
   
def _diffFile(jsonfilesbypath,nmodified,ar,updatednotadded):
    print('WARNING: '+ar.archive_path+' was '+('updated' if updatednotadded else 'added')+' since wj caching')
    jsonfilesbypath[ar.archive_path]=ar
    nmodified.val += 1


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

#############

class Cache:
    def __init__(self,cachedir,downloadsdir,mo2,mo2excludefolders,mo2reincludefolders):
        self.archives = {}
        self.archivesbypath = {}
        self.filesbypath = {}
        timer = Elapsed()
        
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
        
        # Loading JSON HashCache
        self.jsonarchivesbypath = {}
        try:
            self.jsonarchivesbypath = _dictOfArsFromJsonFile(cachedir+'archives.njson')
        except Exception as e:
            print('WARNING: error loading JSON cache archives.json: '+str(e)+'. Will continue w/o archive JSON cache')
            self.jsonarchivesbypath = {} # just in case            
        self.jsonarchives = {}
        for key in self.jsonarchivesbypath:
            val = self.jsonarchivesbypath[key]
            self.jsonarchives[val.archive_hash] = val
        assert(len(self.jsonarchives)==len(self.jsonarchivesbypath)) 
        print(str(len(self.jsonarchives))+' JSON archives')

        self.jsonfilesbypath = {}
        try:
            self.jsonfilesbypath = _dictOfArsFromJsonFile(cachedir+'files.njson')
        except Exception as e:
            print('WARNING: error loading JSON cache files.json: '+str(e)+'. Will continue w/o file JSON cache')
            self.jsonfilesbypath = {} # just in case            

        print(str(len(self.jsonfilesbypath))+' JSON files')
        timer.printAndReset('Loading JSON HashCache')

        nmodified = Val(0)
        nscanned = Cache._loadDir(downloadsdir,self.jsonarchivesbypath,self.archivesbypath,[],[],
                                  lambda ar,updatednotadded: _diffArchive(self.jsonarchives,self.jsonarchivesbypath,nmodified,ar,updatednotadded)
                                 )
        assert(len(self.jsonarchives)==len(self.jsonarchivesbypath)) 
        print('scanned/modified archives:'+str(nscanned)+'/'+str(nmodified)+', '+str(len(self.jsonarchives))+' JSON archives')
        timer.printAndReset('Scanning downloads')
        
        nmodified.val = 0
        nscanned = Cache._loadDir(mo2,self.jsonfilesbypath,self.filesbypath,mo2excludefolders,mo2reincludefolders,
                                  lambda ar,updatednotadded: _diffFile(self.jsonfilesbypath,nmodified,ar,updatednotadded)
                                 )
        print('scanned/modified files:'+str(nscanned)+'/'+str(nmodified)+', '+str(len(self.jsonfilesbypath))+' JSON files')
        timer.printAndReset('Scanning MO2')

        # Writing JSON HashCache
        _dictOfArsToJsonFile(cachedir+'archives.njson',self.jsonarchivesbypath)
        _dictOfArsToJsonFile(cachedir+'files.njson',self.jsonfilesbypath)
        timer.printAndReset('Writing JSON HashCache')

    def _loadDir(dir,dicttolook,dicttolook2,excludefolders,reincludefolders,addar):
        # print(excludefolders)
        # print(reincludefolders)
        nscanned = 0
        if False: #two equivalent implementations; after recent performance fix recursive one performs better 
            # os.walk - based: we're scanning the whole tree at once, but cannot skip ignored parts
            for dirpath, dirs, filenames in os.walk(dir):
                for filename in filenames:
                    # print(dirpath)
                    dirpath1 = dirpath + '\\'
                    exclude = False
                    for x in excludefolders:
                        if dirpath1.startswith(x):
                            exclude = True
                            break
                    if exclude:
                        for i in reincludefolders:
                            if dirpath1.startswith(i):
                                exclude = False
                                break

                    if exclude:
                        continue

                    nscanned += 1
                    fpath = os.path.join(dirpath,filename)
                    if DEBUG:
                        # print(fpath)
                        assert(normalizePath(fpath)==fpath) # if stands - remove all normalizations after os.walk, asserting under dbg.DBG
                    assert(not os.path.islink(fpath))

                    tstamp = _getFileTimestamp(fpath)
                    # print(fpath)
                    found = _getFromOneOfDicts(dicttolook,dicttolook2,fpath.lower()) # dicttolook.get(fpath.lower())
                    if found:
                        tstamp2 = found.archive_modified
                        # print(tstamp,tstamp2,_wjTimestampToPythonTimestamp(tstamp2))
                        if _compareTimestamps(tstamp,tstamp2)!=0:
                            files.append(wjdb.Archive(-1,tstamp,fpath,True))
                    else:
                        files.append(wjdb.Archive(-1,tstamp,fpath,False))
            return nscanned
        else:
            # recursive one: able to skip subtrees, but more calls (lots of os.listdir() instead of single os.walk())
            # still, after recent performance fix seems to win like 1.5x over os.walk-based one
            for f in os.listdir(dir):
                fpath = dir+f
                st = os.lstat(fpath)
                fmode = st.st_mode
                # if os.path.isfile(fpath):
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
                            #print(fpath+':'+str(tstamp)+'!='+str(tstamp2))
                            #print(dicttolook.get(fpath.lower()))
                            #print(dicttolook2.get(fpath.lower()).__dict__)
                            #dbgWait()
                            _diffFound(fpath,tstamp,addar,True)
                    else:
                        _diffFound(fpath,tstamp,addar,False)
                # elif os.path.isdir(fpath):
                elif stat.S_ISDIR(fmode):
                    newdir=fpath+'\\'
                    '''exclude = False
                    for x in excludefolders:
                        if newdir.startswith(x):
                            exclude = True
                            break
                    if exclude:
                        for i in reincludefolders:
                            if newdir.startswith(i):
                                exclude = False
                                break
                    '''
                    # print(newdir)
                    # if len(excludefolders):
                    #    print(excludefolders[2])
                    # print(newdir in excludefolders)
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

    def loadVFS(self,allinstallfiles,dbgfile=None):
        timer = Elapsed()
        self.archiveEntries = wjdb.loadVFS(allinstallfiles,dbgfile) 
        timer.printAndReset('Loading WJ VFS')

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
        with open(folder+'downloads.txt', 'wt', encoding="utf-8") as f:
            for hash in self.archives:
                f.write(str(hash)+':'+str(self.downloads[hash].__dict__)+'\n')
        with open(folder+'archiveentries.txt', 'wt', encoding="utf-8") as f:
            for hash in self.archiveEntries:
                f.write(str(hash)+':'+str(self.archiveEntries[hash].__dict__)+'\n')
                