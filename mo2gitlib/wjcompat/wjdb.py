import sqlite3
import gzip
import os
import json
import traceback

from mo2gitlib.common import *
from mo2gitlib.files import File,ArchiveEntry
import mo2gitlib.wjcompat.binaryreader as binaryreader

def compareTimestampWithWj(a,b):
    if abs(a-b) == 0: #< 0.000001: 
        return 0
    return -1 if a < b else 1

class _Img:
    def __init__(self,br):
        binaryreader.traceReader('Img:')
        self.w = br.ReadUint16()
        self.h = br.ReadUint16()
        self.mip = br.ReadByte()
        self.fmt = br.ReadByte()
        self.phash = br.ReadBytes(40)
        
    def dbgString(self):
        return '{ w='+str(self.w)+' h='+str(self.h)+' mip='+str(self.mip)+' fmt='+str(self.fmt)+' phash=['+str(len(self.phash))+']}'
 
class _HashedFile:
    def __init__(self,br):
        binaryreader.traceReader('_HashedFile:')
        self.path = br.ReadString()
        self.hash = br.ReadUint64()
        if br.ReadBoolean():
            self.img = _Img(br)
            # print(self.img.__dict__)
            # br.dbg()
        else:
            self.img = None
        self.size = br.ReadInt64()
        assert(self.size>=0)
        n = br.ReadInt32()
        assert(n>=0)
        self.children = []
        for i in range(n):
            self.children.append(_HashedFile(br))
            
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

def _parseContents(hash,contents,gzipped=True):
    if gzipped:
        contents = gzip.decompress(contents)
    # print(contents)
    # print(rowi)
    # print(contents)
    try:
        br = binaryreader.BinaryReader(contents)
        
        hf = _HashedFile(br)
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

def _normalizeHash(hash):
    if hash < 0:
        return hash + (1<<64)
    else:
        return hash
        
def _aEntries(paths,hf,root_archive_hash):
    aes = []
    for child in hf.children:
        cp = paths + [child.path]
        aes.append(ArchiveEntry(root_archive_hash,cp,child.size,child.hash))
        if len(child.children)>0:
            aes2 = aes + _aEntries(cp,child,root_archive_hash)
            aes = aes2
            #print('NESTED:')
            #for ae in aes:
            #    print(ae.__dict__)
            #dbgWait()
    return aes
    
def vfsFile():
    home_dir = os.path.expanduser("~")
    return home_dir+'\\AppData\\Local\\Wabbajack\\GlobalVFSCache5.sqlite'

def loadVFS(dbgfile=None):
    con = sqlite3.connect(vfsFile())
    cur = con.cursor()
    # rowi = -1
    nn = 0
    nx = 0
    for row in cur.execute('SELECT Hash,Contents FROM VFSCache'): 
        contents = row[1]

        hf = _parseContents(row[0],contents)
        nn += 1
        if hf is None:
            nx += 1
            if dbgfile:
                dbgfile.write('WARNING: CANNOT PARSE'+str(contents)+' FOR hash='+str(hash)+'\n')
        else:
            if dbgfile:
                dbgfile.write(str(hf.hash)+':'+hf.dbgString()+'\n')
            aes = _aEntries([],hf,hf.hash)
            for ae in aes:
                #if archiveentries.get(ae.file_hash) is None or allarchivehashes.get(ae.archive_hash):
                #    archiveentries[ae.file_hash]=ae
                #if allarchivehashes.get(ae.archive_hash) is not None:
                yield ae
                #else:
                #    print('WARNING/loadVFS(): archive with hash='+str(ae.archive_hash)+' is not found')
                
    con.close()
    print('loadVFS: nn='+str(nn)+' nx='+str(nx))

def _wjTimestampToPythonTimestamp(wjftime):
    return (wjftime - 116444736000000000) / 10**7

def hcFile():
    home_dir = os.path.expanduser("~")
    return home_dir+'\\AppData\\Local\\Wabbajack\\GlobalHashCache2.sqlite'

def loadHC(dst):    
    con = sqlite3.connect(hcFile())
    cur = con.cursor()
    nn = 0
    nfiltered = 0
    for row in cur.execute('SELECT Path,LastModified,Hash FROM HashCache'):
        hash = _normalizeHash(row[2])        
        fi = File(hash,_wjTimestampToPythonTimestamp(row[1]),row[0])
        # olda = out[idx].get(hash)
        dst(fi)
    con.close()
    print('loadHC: nn='+str(nn)+' filtered out:'+str(nfiltered))
