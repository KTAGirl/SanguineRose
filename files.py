import xxhash
import json
from types import SimpleNamespace

from mo2git.common import *

def wjHash(fname): #mot only wj, we ourselves are also using it
    h = xxhash.xxh64()
    blocksize = 1048576
    with open(fname,'rb') as f:
        while True:
            bb = f.read(blocksize)
            h.update(bb)
            assert(len(bb)<=blocksize)
            if len(bb) != blocksize:
                return h.intdigest()

class File:
    def __init__(self,file_hash,file_modified,file_path):
        assert(file_path is not None)
        self.file_hash=file_hash
        self.file_modified=file_modified
        self.file_path=file_path
        
    def eq(self,other):
        if self.file_hash != other.file_hash:
            return False
        if self.file_modified != other.file_modified:
            return False
        if self.file_path != other.file_path:
            return False
        return True
                
    def fromJSON(s):
        return json.loads(s, object_hook=lambda d: SimpleNamespace(**d))

    def toJSON(fi):
        # works both for ar=Archive, and ar=SimpleNamespace
        # for SimpleNamespace cannot use return json.dumps(self,default=lambda o: o.__dict__)
        if fi.file_hash is None:
            return '{"file_path": '+escapeJSON(fi.file_path)+', "file_hash":null}'
        else:
            return '{"file_hash":'+str(fi.file_hash)+', "file_modified": '+str(fi.file_modified)+', "file_path": '+escapeJSON(fi.file_path)+'}'

class ArchiveEntry:
    def __init__(self,archive_hash,intra_path,file_size,file_hash):
        self.archive_hash = archive_hash
        self.intra_path = intra_path
        self.file_size = file_size
        self.file_hash = file_hash
        
    def fromJSON(s):
        return json.loads(s, object_hook=lambda d: SimpleNamespace(**d))

    def toJSON(ar):
        # works both for ar=ArchiveEntry, and ar=SimpleNamespace
        # for SimpleNamespace cannot use return json.dumps(self,default=lambda o: o.__dict__)
        return '{"archive_hash":'+str(ar.archive_hash)+', "intra_path": '+escapeJSON(ar.intra_path)+', "file_size": '+str(ar.file_size)+', "file_hash": '+str(ar.file_hash)+'}'
