import base64
import re
import shutil
import urllib

from mo2git.common import *
from mo2git.files import wjHash,File

# we have reasons to have our own Json writer:
#  1. major. we need very specific gitdiff-friendly format
#  2. minor. we want to keep these files as small as feasible (while keeping it more or less readable), 
#            hence JSON5 quote-less names, and path and elements "compression". It was seen to save 3.8x, for a 50M file it is quite a bit

def _toJsonHash(h):
    assert(isinstance(h,int))
    assert(h>=0)
    assert(h<2**64)
    #print(h)
    b = h.to_bytes(8,'little',signed=False)
    b64 = base64.b64encode(b).decode('ascii')
    #print(b64)
    s = b64.rstrip('=')
    assert(_fromJsonHash(s)==h)
    return s
    
def _fromJsonHash(s):
    ntopad = (3-(len(s)%3))%3
    #print(ntopad)
    s += '=='[:ntopad]
    #print(s)
    b = base64.b64decode(s)
    h = int.from_bytes(b,byteorder='little')
    return h
    
def _toJsonFPath(fpath):
    return urllib.parse.quote(fpath,safe=" +()'&#$[];,!@")
    
def _fromJsonFPath(fpath):
    return urllib.parse.unquote(fpath)
    
def _compressJsonPath(prevpath,path):
    assert(path.find('/')<0)
    #assert(path.find('>')<0)
    path = path.replace('\\','/')
    spl = path.split('/')
    #print(prevpath.val)
    #print(spl)
    nmatch = 0
    for i in range(min(len(prevpath.val),len(spl))):
        if spl[i] == prevpath.val[i]:
            nmatch=i+1
        else:
            break
    assert(nmatch>=0)
    if nmatch <= 9:
        path = '"'+str(nmatch)
    else:
        assert(nmatch<=35)
        path = '"'+chr(nmatch-10+65)
    needslash = False
    for i in range(nmatch,len(spl)):
        if needslash:
            path += '/'
        else:
            needslash = True
        path += _toJsonFPath(spl[i])
    prevpath.val=spl
    assert('"' not in path[1:])
    return path+'"'
    
def _decompressJsonPath(prevpath,path):
    path = _fromJsonFPath(path)
    p0 = path[0]
    if p0 >= '0' and p0 <= '9':
        nmatch = int(p0)
    elif p0 >= 'A' and p0 <= 'Z':
        nmatch = ord(p0) - 65+10
    out = ''
    for i in range(nmatch):
        if i>0:
            out += '/'
        out += prevpath[i]
    out += path[1:]
    prevpath = path.split('/')
    return out
    
def _appendJsonS(prevs,s):
    if prevs.val==s:
        return ''
    prevs.val = s
    return ',s:'+str(s)

def _appendJsonA(preva,a):
    if preva.val==a:
        return ''
    preva.val = a
    return ',a:"'+a+'"'
    
class MasterArchiveItem:
    def __init__(self,name,hash):
        self.name = name
        self.hash = hash
    
class MasterFileItem:
    def __init__(self,path,hash,file_size=None,archive_hash=None,intra_path=None,fromwhere=None,warning=None):
        self.path = path
        self.hash = hash
        self.file_size = file_size
        self.archive_hash = archive_hash
        self.intra_path = intra_path
        self.fromwhere = fromwhere
        self.warning = warning
    
class Master:
    def __init__(self):
        pass
        
    def constructFromCache(self,nesx,nwarn,filecache,allinstallfiles,ownmods):
        aif = []
        for hash, path in allinstallfiles.items():
            fname = os.path.split(path)[1]
            aif.append((fname,hash))
        aif.sort(key=lambda f: f[0])
        self.archives = [MasterArchiveItem(item[0],item[1]) for item in aif]

        files = [fi.file_path for fi in filecache.allFiles()]
        files.sort()

        targetdir = 'mo2\\'
        mo2 = filecache.folders.mo2
        mo2len = len(mo2)
        self.files = []
        for fpath0 in files:
            assert(fpath0.lower() == fpath0)
            assert(fpath0.startswith(mo2))
            fpath = fpath0[mo2len:]

            if isEsx(fpath):
                nesx.val += 1
            
            isown = False
            for own in ownmods:
                ownpath = 'mods\\'+own+'\\'
                if fpath.startswith(ownpath):
                    isown = True
                    break
            if isown:
                targetpath0 = targetdir + fpath
                fpath1 = mo2+fpath
                hash = wjHash(fpath1) #TODO: to Task?
                self.files.append(MasterFileItem(fpath,hash,fromwhere=targetpath0))
                continue
            
            ae,archive = filecache.findFile(fpath0)
            if ae is None:
                processed = False
                m = re.search(r'^mods\\(.*)\\meta.ini$',fpath)
                if m:
                    mod = m.group(1)
                    if not '\\' in mod: #we know only meaning of top-level mod meta.ini's 
                        # print(mod)
                        targetpath0 = fpath
                        targetpath = filecache.folders.github + targetdir + targetpath0
                        # print(realpath)
                        makeDirsForFile(targetpath) #TODO: to Task?
                        srcpath = mo2 + fpath
                        shutil.copyfile(srcpath,targetpath)
                        hash = wjHash(srcpath) 
                        processed = True
                        self.files.append(MasterFileItem(fpath,hash,fromwhere=targetpath0))
                                
                if not processed:
                    self.files.append(MasterFileItem(fpath,None,warning='NF'))
                    nwarn.val += 1
            else:
                if archive is None:
                    assert(ae.file_size==0)
                    self.files.append(MasterFileItem(fpath,None,file_size=0))
                else:
                    fi = MasterFileItem(fpath,ae.file_hash,file_size=ae.file_size,archive_hash=ae.archive_hash,intra_path=[])
                    for path in ae.intra_path:
                        fi.intra_path.append(path)
                    
                    if not allinstallfiles.get(ae.archive_hash):
                        fi.warning = 'NL'
                        nwarn.val += 1
                    self.files.append(fi)

    def write(self,wfile):
        wfile.write('// This is JSON5 file, to save some space compared to JSON.\n') 
        wfile.write('// Still, do not edit it by hand, mo2git parses it itself using regex to save time\n')
        wfile.write('{ archives: [ // Legend: n means "name", h means "hash"\n')
        na = 0
        for ar in self.archives:
            if na:
                wfile.write(",\n")
            na += 1
            wfile.write('{n:"'+_toJsonFPath(ar.name)+'",h:"'+_toJsonHash(ar.hash)+'"}')
        wfile.write('\n], files: [ // Legend: p means "path", h means "hash", s means "size", f means "from",')
        wfile.write('\n            //         a means "archive_hash", i means "intra_path"\n')

        nf = 0
        lastp = Val([])
        lasts = Val(None)
        lasta = Val(None)
        lastf = Val([])
        lasti = [Val(None) for i in range(8)] #8 levels of nesting should be enough for quite a while
        nlasti = 0
        for fi in self.files:
            if nf:
                wfile.write(",\n")
            nf += 1

            wfile.write('{p:'+_compressJsonPath(lastp,fi.path)) #fi.path is mandatory
            if fi.hash is not None:
                wfile.write(',h:"'+_toJsonHash(fi.hash)+'"')
            else:
                pass #there is no lasth
            if fi.file_size is not None:
                wfile.write(_appendJsonS(lasts,fi.file_size))
            else:
                lasts.val = None
            if fi.archive_hash is not None:
                wfile.write(_appendJsonA(lasta,_toJsonHash(fi.archive_hash)))
            else:
                lasta.val = None
            if fi.intra_path is not None:
                wfile.write(',i:[')
                np = 0
                for path in fi.intra_path:
                    if np:
                        wfile.write(',')
                    if np >= nlasti:
                        lasti[np] = Val([])
                    wfile.write(_compressJsonPath(lasti[np],path))
                    np += 1
                wfile.write(']')
                nlasti = np
            else:
                nlasti = 0
            if fi.fromwhere is not None:
                wfile.write(',f:'+_compressJsonPath(lastf,fi.fromwhere))
            else:
                lastf.val = []
            if fi.warning is not None:
                wfile.write(',warning:"'+fi.warning+'"')
            wfile.write('}')

        wfile.write('\n]}\n')
    
def readMaster(rfile):
    files = []
    patphsi=re.compile(r'^{p:"([^"]*)",h:"([^"]*)",s:([0-9]*),i:\["([^"]*)"\]}(.)?')
    patphsai=re.compile(r'^{p:"([^"]*)",h:"([^"]*)",s:([0-9]*),a:"([^"]*)",i:\["([^"]*)"\]}(.)?')
    patphai=re.compile(r'^{p:"([^"]*)",h:"([^"]*)",a:"([^"]*)",i:\["([^"]*)"\]}(.)?')
    patphsii=re.compile(r'^{p:"([^"]*)",h:"([^"]*)",s:([0-9]*),i:\["([^"]*)","([^"]*)"\]}(.)?')
    patphsaii=re.compile(r'^{p:"([^"]*)",h:"([^"]*)",s:([0-9]*),a:"([^"]*)",i:\["([^"]*)","([^"]*)"\]}(.)?')
    patphi=re.compile(r'^{p:"([^"]*)",h:"([^"]*)",i:\["([^"]*)"\]}(.)?')
    patphii=re.compile(r'^{p:"([^"]*)",h:"([^"]*)",i:\["([^"]*)","([^"]*)"\]}(.)?')
    patphf=re.compile(r'^{p:"([^"]*)",h:"([^"]*)",f:"([^"]*)"}(.)?')
    patps0=re.compile(r'^{p:"([^"]*)",s:0}(.)?')
    patpw=re.compile(r'^{p:"([^"]*)",warning:"([^"]*)"}(.)?')
    patp=re.compile(r'^{p:"([^"]*)"}(.)?')
    patnh=re.compile(r'^{n:"([^"]*)",h:"([^"]*)"}(.)?')
    patcomment=re.compile(r'^\s*//')
    patspecial1 = re.compile(r'^{\s*archives\s*:\s*\[\s*//')
    patspecial2 = re.compile(r'^\s*\]\s*,\s*files\s*:\s\[\s*//')
    patspecial3 = re.compile(r'^\s*]\s*}')
    for line in rfile:
        #ordered in rough order of probability to save time
        m = patphsi.match(line)
        if m:
            f=File(_fromJsonHash(m.group(2)),None,m.group(1))
            #print(f.__dict__)
            files.append(f)
            continue
        m = patphsai.match(line)
        if m:
            f=File(_fromJsonHash(m.group(2)),None,m.group(1))
            #print(f.__dict__)
            files.append(f)
            continue
        m = patphi.match(line)
        if m:
            f=File(_fromJsonHash(m.group(2)),None,m.group(1))
            #print(f.__dict__)
            files.append(f)
            continue
        m = patphai.match(line)
        if m:
            f=File(_fromJsonHash(m.group(2)),None,m.group(1))
            #print(f.__dict__)
            files.append(f)
            continue
        m = patphsii.match(line)
        if m:
            f=File(_fromJsonHash(m.group(2)),None,m.group(1))
            #print(f.__dict__)
            files.append(f)
            continue
        m = patphii.match(line)
        if m:
            f=File(_fromJsonHash(m.group(2)),None,m.group(1))
            #print(f.__dict__)
            files.append(f)
            continue
        m = patphsaii.match(line)
        if m:
            f=File(_fromJsonHash(m.group(2)),None,m.group(1))
            #print(f.__dict__)
            files.append(f)
            continue
        m = patphf.match(line)
        if m:
            f=File(_fromJsonHash(m.group(2)),None,m.group(1))
            #print(f.__dict__)
            files.append(f)
            continue
        m = patps0.match(line)
        if m:
            f=File(None,None,m.group(1))
            #print(f.__dict__)
            files.append(f)
            continue
        m = patp.match(line)
        if m:
            f=File(None,None,m.group(1))
            #print(f.__dict__)
            files.append(f)
            continue
        m = patpw.match(line)
        if m:
            f=File(None,None,m.group(1))
            #print(f.__dict__)
            files.append(f)
            continue
        m = patnh.match(line)
        if m:
            #f=File(None,None,m.group(1))
            #print(f.__dict__)
            #files.append(f)
            continue
        m = patcomment.match(line)
        if m:
            continue
        m = patspecial1.match(line)
        if m:
            continue
        m = patspecial2.match(line)
        if m:
            continue
        m = patspecial3.match(line)
        if m:
            continue

        print(line)
        assert(False)
