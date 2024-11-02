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

class Archive:
    def __init__(self,archive_hash,archive_modified,archive_path):
        assert(archive_path is not None)
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
                
    def fromJSON(s):
        return json.loads(s, object_hook=lambda d: SimpleNamespace(**d))

    def toJSON(ar):
        # works both for ar=Archive, and ar=SimpleNamespace
        # for SimpleNamespace cannot use return json.dumps(self,default=lambda o: o.__dict__)
        if ar.archive_hash is None:
            return '{"archive_path": '+escapeJSON(ar.archive_path)+', "archive_hash":null}'
        else:
            return '{"archive_hash":'+str(ar.archive_hash)+', "archive_modified": '+str(ar.archive_modified)+', "archive_path": '+escapeJSON(ar.archive_path)+'}'
