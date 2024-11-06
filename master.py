import base64
import re
import shutil
import urllib

from mo2git.common import *
from mo2git.files import wjHash

# we have reasons to have our own Json writer:
#  1. major. we need very specific gitdiff-friendly format
#  2. minor. we want to keep these files as small as feasible (while keeping it more or less readable), 
#            hence JSON5 quote-less names, and path and elements "compression". It was seen to save 3.8x (2x for default pcompression=0), for a 50M file it is quite a bit

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
    
def _compressJsonPath(prevn,prevpath,path,level=2):
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
    if level==2 or (level==1 and prevn.val<=nmatch):
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
    else:#skipping compression because of level restrictions
        path = '"0'+path
    prevpath.val=spl
    if prevn is not None:
        prevn.val=nmatch
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
    
    #print(prevpath)
    #print(nmatch)
    for i in range(nmatch):
        if i>0:
            out += '/'
        out += prevpath.val[i]
    if out != '':
        out += '/'
    out += path[1:]
    prevpath.val = out.split('/')
    return out.replace('/','\\')
    
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

    def eq(self,b):
        if self.name != b.name:
            return False
        if self.hash != b.hash:
            return False
        return True
    
class MasterFileItem:
    def __init__(self,path,hash,file_size=None,archive_hash=None,intra_path=None,fromwhere=None,warning=None):
        self.path = path
        self.hash = hash
        self.file_size = file_size
        self.archive_hash = archive_hash
        self.intra_path = intra_path
        self.fromwhere = fromwhere
        self.warning = warning
        
    def eq(self,b):
        if self.path != b.path:
            return False
        if self.hash != b.hash:
            return False
        if self.file_size != b.file_size:
            return False
        if self.archive_hash != b.archive_hash:
            return False
        if self.fromwhere != b.fromwhere:
            return False
        if self.warning != b.warning:
            return False
        return True
    
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
            
            ae,archive,fi = filecache.findFile(fpath0)
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
                    if fi is not None:
                        self.files.append(MasterFileItem(fpath,fi.file_hash,warning='NF'))
                    else:
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

    def write(self,wfile,masterconfig):
        level = masterconfig.get('pcompression',1) if masterconfig is not None else 1
        
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
        lasti = [Val(None) for i in range(2)] #increasing it here will need adding more patterns to constructFromFile()
        nlasti = 0
        lastpn = Val(0)
        for fi in self.files:
            if nf:
                wfile.write(",\n")
            nf += 1

            wfile.write('{p:'+_compressJsonPath(lastpn,lastp,fi.path,level)) #fi.path is mandatory
            if fi.hash is not None:
                wfile.write(',h:"'+_toJsonHash(fi.hash)+'"')
            else:
                #there is no lasth, but it is a special record (size==0)
                #print(fi.__dict__)
                assert(fi.warning is not None or fi.file_size==0)
                
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
                    wfile.write(_compressJsonPath(None,lasti[np],path))
                    np += 1
                wfile.write(']')
                nlasti = np
            else:
                nlasti = 0
            if fi.fromwhere is not None:
                wfile.write(',f:'+_compressJsonPath(None,lastf,fi.fromwhere))
            else:
                lastf.val = []
            if fi.warning is not None:
                wfile.write(',warning:"'+fi.warning+'"')
            wfile.write('}')

        wfile.write('\n]}\n')
        
    def constructFromFile(self,rfile):
        self.archives = []
        self.files = []
        state = 0 #0 - before archives, 1 - within archives, 2 - within files, 3 - finished

        patphsi=re.compile(r'^{p:"([^"]*)",h:"([^"]*)",s:([0-9]*),i:\["([^"]*)"\]}(.)?')
        patphsai=re.compile(r'^{p:"([^"]*)",h:"([^"]*)",s:([0-9]*),a:"([^"]*)",i:\["([^"]*)"\]}(.)?')
        patphai=re.compile(r'^{p:"([^"]*)",h:"([^"]*)",a:"([^"]*)",i:\["([^"]*)"\]}(.)?')
        patphsii=re.compile(r'^{p:"([^"]*)",h:"([^"]*)",s:([0-9]*),i:\["([^"]*)","([^"]*)"\]}(.)?')
        patphsaii=re.compile(r'^{p:"([^"]*)",h:"([^"]*)",s:([0-9]*),a:"([^"]*)",i:\["([^"]*)","([^"]*)"\]}(.)?')
        patphi=re.compile(r'^{p:"([^"]*)",h:"([^"]*)",i:\["([^"]*)"\]}(.)?')
        patphii=re.compile(r'^{p:"([^"]*)",h:"([^"]*)",i:\["([^"]*)","([^"]*)"\]}(.)?')
        patphf=re.compile(r'^{p:"([^"]*)",h:"([^"]*)",f:"([^"]*)"}(.)?')
        patps0=re.compile(r'^{p:"([^"]*)",s:0}(.)?')
        patphw=re.compile(r'^{p:"([^"]*)",h:"([^"]*)",warning:"([^"]*)"}(.)?')
        patpw=re.compile(r'^{p:"([^"]*)",warning:"([^"]*)"}(.)?')
        patp=re.compile(r'^{p:"([^"]*)"}(.)?')
        patnh=re.compile(r'^{n:"([^"]*)",h:"([^"]*)"}(.)?')
        patcomment=re.compile(r'^\s*//')
        patspecial1 = re.compile(r'^{\s*archives\s*:\s*\[\s*//')
        patspecial2 = re.compile(r'^\s*\]\s*,\s*files\s*:\s\[\s*//')
        patspecial3 = re.compile(r'^\s*]\s*}')

        lastp = Val([])
        lasts = Val(None)
        lasta = Val(None)
        lastf = Val([])
        lasti = [Val(None) for i in range(2)]
        nlasti = Val(0)
        lastf = Val([])
        for line in rfile:
            #ordered in rough order of probability to save time
            m = patphsi.match(line)
            if m:
                assert(state==2)
                fi = _readPhsaii(m.group(1),m.group(2),m.group(3),None,m.group(4),None,lastp,lasts,lasta,nlasti,lasti)
                self.files.append(fi)
                lastf.val = []
                continue
            m = patphsai.match(line)
            if m:
                assert(state==2)
                fi = _readPhsaii(m.group(1),m.group(2),m.group(3),m.group(4),m.group(5),None,lastp,lasts,lasta,nlasti,lasti)
                self.files.append(fi)
                lastf.val = []
                continue
            m = patphi.match(line)
            if m:
                assert(state==2)
                fi = _readPhsaii(m.group(1),m.group(2),None,None,m.group(3),None,lastp,lasts,lasta,nlasti,lasti)
                self.files.append(fi)
                lastf.val = []
                continue
            m = patphai.match(line)
            if m:
                assert(state==2)
                fi = _readPhsaii(m.group(1),m.group(2),None,m.group(3),m.group(4),None,lastp,lasts,lasta,nlasti,lasti)
                self.files.append(fi)
                lastf.val = []
                continue
            m = patphsii.match(line)
            if m:
                assert(state==2)
                fi = _readPhsaii(m.group(1),m.group(2),m.group(3),None,m.group(4),m.group(5),lastp,lasts,lasta,nlasti,lasti)
                self.files.append(fi)
                lastf.val = []
                continue
            m = patphii.match(line)
            if m:
                assert(state==2)
                fi = _readPhsaii(m.group(1),m.group(2),None,None,m.group(3),m.group(4),lastp,lasts,lasta,nlasti,lasti)
                self.files.append(fi)
                lastf.val = []
                continue
            m = patphsaii.match(line)
            if m:
                assert(state==2)
                fi = _readPhsaii(m.group(1),m.group(2),m.group(3),m.group(4),m.group(5),m.group(6),lastp,lasts,lasta,nlasti,lasti)
                self.files.append(fi)
                lastf.val = []
                continue
            m = patphf.match(line)
            if m:
                assert(state==2)
                fi=MasterFileItem(_decompressJsonPath(lastp,m.group(1)),_fromJsonHash(m.group(2)))
                ff = _decompressJsonPath(lastf,m.group(3))
                fi.fromwhere=ff
                self.files.append(fi)
                lasts.val = None
                lasta.val = None
                nlasti.val = 0
                continue
            m = patps0.match(line)
            if m:
                assert(state==2)
                fi=MasterFileItem(_decompressJsonPath(lastp,m.group(1)),None)
                ss = 0
                fi.file_size = ss
                self.files.append(fi)
                lasts.val = ss
                lasta.val = None
                nlasti.val = 0
                lastf.val = []
                continue
            m = patp.match(line)
            if m:
                assert(state==2)
                fi=MasterFileItem(_decompressJsonPath(lastp,m.group(1)),None)
                fi.file_size = lasts.val
                self.files.append(fi)
                lasta.val = None
                nlasti.val = 0
                lastf.val = []
                continue
            m = patphw.match(line)
            if m:
                assert(state==2)
                fi=MasterFileItem(_decompressJsonPath(lastp,m.group(1)),_fromJsonHash(m.group(2)))
                fi.warning = m.group(3)
                self.files.append(fi)
                lasts.val = None
                lasta.val = None
                nlasti.val = 0
                lastf.val = []
                continue
            m = patpw.match(line)
            if m:
                assert(state==2)
                fi=MasterFileItem(_decompressJsonPath(lastp,m.group(1)),None)
                fi.warning = m.group(2)
                self.files.append(fi)
                lasts.val = None
                lasta.val = None
                nlasti.val = 0
                lastf.val = []
                continue
            m = patnh.match(line)
            if m:
                assert(state==1)
                ar=MasterArchiveItem(_fromJsonFPath(m.group(1)),_fromJsonHash(m.group(2)))
                self.archives.append(ar)
                continue
            m = patcomment.match(line)
            if m:
                continue
            m = patspecial1.match(line)
            if m:
                assert(state == 0)
                state = 1
                continue
            m = patspecial2.match(line)
            if m:
                assert(state == 1)
                state = 2
                continue
            m = patspecial3.match(line)
            if m:
                assert(state==2)
                state = 3
                continue

            print(line)
            assert(False)
        
        assert(state==3)
    
def _readPhsaii(p,h,s,a,i1,i2,lastp,lasts,lasta,nlasti,lasti):
    fi=MasterFileItem(_decompressJsonPath(lastp,p),_fromJsonHash(h) if h is not None else None)
    
    if s is None:
        fi.file_size = lasts.val
    else:
        ss = int(s)
        fi.file_size = ss
        lasts.val = ss
    if a is None:
        fi.archive_hash = lasta.val
    else:
        aa = _fromJsonHash(a)
        fi.archive_hash = aa
        lasta.val = aa
    if i1 is not None:
        if nlasti.val == 0:
            lasti[0] = Val([])
            nlasti.val = 1
        fi.intra_path = [_decompressJsonPath(lasti[0],i1)]
    if i2 is not None:
        assert(i1 is not None)
        assert(nlasti.val>0)
        assert(len(fi.intra_path)==1)
        if nlasti.val == 1:
            lasti[1] = Val([])
            nlasti.val = 2
        fi.intra_path.append(_decompressJsonPath(lasti[1],i2))
    return fi
