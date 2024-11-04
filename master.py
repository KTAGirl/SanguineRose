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
    
def _toJsonPath(prevpath,path):
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
        path += urllib.parse.quote(spl[i],safe=" +()'&#$[];,!@")
    prevpath.val=spl
    assert('"' not in path[1:])
    return path+'"'
    
def _fromJsonPath(prevpath,path):
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

def writeMaster(wfile,filecache,nesx,nwarn,allinstallfiles,ownmods,files):
    targetdir = 'mo2\\'
    wfile.write('// This is JSON5 file, to save some space compared to JSON.\n') 
    wfile.write('// Still, do not edit it by hand, mo2git parses it itself using regex to save time\n')
    wfile.write('{ archives: [ // Legend: n means "name", h means "hash"\n')
    na = 0
    aif = []
    for hash, path in allinstallfiles.items():
        fname = os.path.split(path)[1]
        aif.append((fname,hash))
    aif.sort(key=lambda f: f[0])
    for f in aif:
        if na:
            wfile.write(",\n")
        na += 1
        wfile.write('{n:"'+str(f[0])+'",h:"'+_toJsonHash(f[1])+'"}')
    wfile.write('\n], files: [ // Legend: p means "path", h means "hash", s means "size", f means "from",')
    wfile.write('\n            //         a means "archive", i means "intra_archive_path"\n')
    mo2 = filecache.folders.mo2
    mo2len = len(mo2)
    nf = 0
    lastp = Val([])
    lasts = Val(None)
    lasta = Val(None)
    lastf = Val([])
    lasti = [Val(None) for i in range(8)] #8 levels of nesting should be enough for quite a while
    nlasti = 0
    for fpath0 in files:
        assert(fpath0.lower() == fpath0)
        assert(fpath0.startswith(mo2))
        fpath = fpath0[mo2len:]

        if nf:
            wfile.write(",\n")
        nf += 1
        
        if isEsx(fpath):
            nesx.val += 1
        
#        commonpath = os.path.commonpath([fpath,dirs])
#        assert(not commonpath.endswith('\\'))
#        commonpath1 = commonpath + '\\'
        isown = False
        # print(fpath)
        for own in ownmods:
            ownpath = 'mods\\'+own+'\\'
            # print(ownpath)
            # print(fpath)
            if fpath.startswith(ownpath):
                isown = True
                break
        if isown:
            targetpath0 = targetdir + fpath
            fpath1 = mo2+fpath
            hash = wjHash(fpath1)
            wfile.write('{p:'+_toJsonPath(lastp,fpath)+',h:"'+_toJsonHash(hash)+'",f:'+_toJsonPath(lastf,targetpath0)+'}')
            #lastp.val = []
            lasts.val = None
            lasta.val = None
            #lastf.val = []
            nlasti = 0
            # dbgWait()
            continue
        
        ae,archive = filecache.findFile(fpath0)
        if ae is None:
            processed = False
            m = re.search('^mods\\\\(.*)\\\\meta.ini$',fpath)
            if m:
                mod = m.group(1)
                if mod.find('\\') < 0:
                    # print(mod)
                    targetpath0 = fpath
                    targetpath = filecache.folders.github + targetdir + targetpath0
                    # print(realpath)
                    makeDirsForFile(targetpath)
                    srcpath = mo2 + fpath
                    shutil.copyfile(srcpath,targetpath)
                    hash = wjHash(srcpath)
                    processed = True
                    # dbgWait()
                    wfile.write('{p:'+_toJsonPath(lastp,fpath)+',h:"'+_toJsonHash(hash)+'",f:'+_toJsonPath(lastf,targetpath0)+'}')
                    #lastp.val = []
                    lasts.val = None
                    lasta.val = None
                    #lastf.val = []
                    nlasti = 0
                            
            if not processed:
                wfile.write('{p:'+_toJsonPath(lastp,fpath)+',warning:"NF"}')
                nwarn.val += 1
                #lastp.val = []
                lasts.val = None
                lasta.val = None
                lastf.val = []
                nlasti = 0
        else:
            if archive is None:
                assert(ae.file_size==0)
                wfile.write('{p:'+_toJsonPath(lastp,fpath)+',s:0}')
                #lastp.val = []
                lasts.val = 0
                lasta.val = None
                lastf.val = []
                nlasti = 0
            else:
                wfile.write('{p:'+_toJsonPath(lastp,fpath)+',h:"'+_toJsonHash(ae.file_hash)+'"'+_appendJsonS(lasts,ae.file_size)
                                    +_appendJsonA(lasta,_toJsonHash(ae.archive_hash))+',i:[')
                np = 0
                for path in ae.intra_path:
                    if np:
                        wfile.write(',')
                    if np >= nlasti:
                        lasti[np] = Val([])
                    wfile.write(_toJsonPath(lasti[np],path))
                    np += 1
                wfile.write(']')
                nlasti = np
                
                if not allinstallfiles.get(ae.archive_hash):
                    wfile.write(',warning:"NL"')
                    nwarn.val += 1
                wfile.write('}')
                #lastp.val = []
                #lasts.val = None
                #lasta.val = None
                lastf.val = []
                #nlasti = 0

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
