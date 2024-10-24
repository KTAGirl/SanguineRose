import sqlite3
import gzip
import os
import traceback

import binaryreader
from w2gdebug import DEBUG
from w2gdebug import dbgWait
    
class Img:
    def __init__(self,br):
        binaryreader.traceReader('Img:')
        self.w = br.ReadUint16()
        self.h = br.ReadUint16()
        self.mip = br.ReadByte()
        self.fmt = br.ReadByte()
        self.phash = br.ReadBytes(40)
        
    def dbgString(self):
        return '{ w='+str(self.w)+' h='+str(self.h)+' mip='+str(self.mip)+' fmt='+str(self.fmt)+' phash=['+str(len(self.phash))+']}'

 
class HashedFile:
    def __init__(self,br):
        binaryreader.traceReader('HashedFile:')
        self.path = br.ReadString()
        self.hash = br.ReadUint64()
        if br.ReadBoolean():
            self.img = Img(br)
            # print(self.img.__dict__)
            # br.dbg()
        else:
            self.img = None
        self.size = br.ReadInt64()
        assert(self.size>=0)
        n = br.ReadInt32()
        assert(n>=0)
        self.children = []
        for i in range(0,n):
            self.children.append(HashedFile(br))
            
    def dbgString(self):
        s = '{ path='+self.path+' hash='+str(self.hash)
        if self.img:
            s += ' img=' + self.img.dbgString()
        if len(self.children):
            s += ' children=['
            ci = 0
            for child in self.children:
                if ci:
                    s += ','
                s += child.dbgString()
                ci += 1
            s += ']'
        s += ' }'
        return s

def parseContents(hash,contents,gzipped=True):
    if gzipped:
        contents = gzip.decompress(contents)
    # print(contents)
    # print(rowi)
    # print(contents)
    try:
        br = binaryreader.BinaryReader(contents)
        
        hf = HashedFile(br)
        assert(br.isEOF())
        # print(br.contents[br.offset:])
        # print(str(hash)+':'+hf.dbg())
        return hf
    except Exception as e:
        print("Parse Exception with hash="+str(hash)+": "+str(e))
        print(traceback.format_exc())
        print(contents)
        dbgWait()
        return None

def normalizeHash(hash):
    if hash < 0:
        return hash + (1<<64)
    else:
        return hash

class ArchiveEntry:
    def __init__(self,archive_hash,intra_path,file_size,file_hash):
        self.archive_hash = archive_hash
        self.intra_path = intra_path
        self.file_size = file_size
        self.file_hash = file_hash

def aEntries(paths,hf,root_archive_hash):
    aes = []
    for child in hf.children:
        cp = paths + [child.path]
        aes.append(ArchiveEntry(root_archive_hash,cp,child.size,child.hash))
        if len(child.children)>0:
            aes2 = aes + aEntries(cp,child,root_archive_hash)
            aes = aes2
            #print('NESTED:')
            #for ae in aes:
            #    print(ae.__dict__)
            #dbgWait()
    return aes

def loadVFS(allinstallfiles,dbgfile=None):
    home_dir = os.path.expanduser("~")
    con = sqlite3.connect(home_dir+'/AppData/Local/Wabbajack/GlobalVFSCache5.sqlite')
    cur = con.cursor()
    # rowi = -1
    nn = 0
    nx = 0
    archiveEntries = {}
    for row in cur.execute('SELECT Hash,Contents FROM VFSCache'): # WHERE Hash=-8778729428874073019"):
        contents = row[1]

        hf = parseContents(row[0],contents)
        nn += 1
        if hf == None:
            nx += 1
            if dbgfile:
                dbgfile.write('WARNING: CANNOT PARSE'+str(contents)+' FOR hash='+str(hash)+'\n')
        else:
            if dbgfile:
                dbgfile.write(str(hf.hash)+':'+hf.dbgString()+'\n')
            aes = aEntries([],hf,hf.hash)
            for ae in aes:
                if archiveEntries.get(ae.file_hash) is None or allinstallfiles.get(ae.archive_hash):
                    archiveEntries[ae.file_hash]=ae
    con.close()
    print('loadVFS: nn='+str(nn)+' nx='+str(nx))
    return archiveEntries

class Archive:
    def __init__(self,archive_hash,archive_modified,archive_path):
        self.archive_hash=archive_hash
        self.archive_modified=archive_modified
        self.archive_path=archive_path
        
    def eq(self,other):
        if self.archive_hash != other.archive_hash:
            return False
        if self.archive_modified != other.archive_modified:
            return False
        if self.archive_path != other.archive_path:
            return False
        return True

def loadHC(dirs):
    lodirs = []
    for dir in dirs:
        dirlo = dir[0].lower()
        lodirs.append(dirlo)
        for d2 in lodirs:
            # print(d2)
            # print(dirlo)
            if d2 == dirlo:
                break
            assert(not dirlo.startswith(d2)) # if folders are overlapping, smaller one MUST go first
            if d2.startswith(dirlo):
                print('NOTICE: loadHC(): overlapping dirs, '+d2+' will be excluded from '+dirlo)
    
    home_dir = os.path.expanduser("~")
    con = sqlite3.connect(home_dir+'/AppData/Local/Wabbajack/GlobalHashCache2.sqlite')
    cur = con.cursor()
    nn = 0
    nfiltered = 0
    for row in cur.execute('SELECT Path,LastModified,Hash FROM HashCache'):
        nn += 1
        idx = -1
        for i in range(0,len(lodirs)):
            if row[0].startswith(lodirs[i]):
                idx = i
                break
        if idx < 0:
            nfiltered += 1
            continue
        hash = normalizeHash(row[2])
        
        newa = Archive(hash,row[1],row[0])
        # olda = out[idx].get(hash)
        dirs[idx][1](newa)
    con.close()
    print('loadHC: nn='+str(nn)+' filtered out:'+str(nfiltered))
    #+' sizes=[')
    #for o in out:
    #    print(len(o))
    #print(']')
    # return out



     