import base64
import re
import shutil
import urllib

from mo2git.common import *
from mo2git.files import wjHash

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
    assert(path.find('>')<0)
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
