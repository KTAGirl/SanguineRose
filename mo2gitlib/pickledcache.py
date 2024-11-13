from mo2gitlib.common import *
from mo2gitlib.folders import Folders

def pickledCache(cachedir,cachedata,prefix,origfiles,calc,params=None):
    assert(isinstance(origfiles,list))
    readpaths = cachedata.get(prefix+'.files')
    
    if params is not None:
        #comparing as JSONs is important
        readparams = JsonEncoder().encode(cachedata.get(prefix+'.params'))
        jparams = JsonEncoder().encode(params)
        sameparams = (readparams == jparams)
    else:
        sameparams = True
        
    samefiles = (len(readpaths) == len(origfiles))
    if sameparams and samefiles:
        readpaths = sorted(readpaths)
        origfiles = sorted(origfiles)
        for i in range(len(readpaths)):
            rd = readpaths[i]
            of = (origfiles[i],os.path.getmtime(origfiles[i]))
            assert(isinstance(rd,tuple))
            assert(Folders.isNormalizedFilePath(rd[0]))
            assert(Folders.isNormalizedFilePath(of))
            
            jrd = JsonEncoder().encode(rd)
            jof = JsonEncoder().encode(of)
            
            if jrd != jof: #lists are sorted, there should be exact match here
                samefiles = False
                break
            
    pfname = cachedir+prefix+'.pickle'
    if sameparams and samefiles and os.path.isfile(pfname):
        info('pickledCache(): Yahoo! Can use cache for '+prefix)
        with open(pfname,'rb') as rf:
            return (pickle.load(rf),{})

    cachedataoverwrites = {}
    files = []
    for of in origfiles:
        files.append( (origfile,os.path.getmtime(origfile)) )
    out = calc(params)
    
    assert(len(tstamps)==len(origfiles))
    for f in files:
        assert(f[1] == os.path.getmtime(f[0])) #if any of the files we depend on, has changed while calc() was calculated - something really weird is going on here
    
    with open(cachedir+prefix+'.pickle','wb') as wf:
        pickle.dump(out,wf)
    cachedataoverwrites[prefix+'.files'] = files
    if params is not None:
        cachedataoverwrites[prefix+'.params'] = params
    return (out,cachedataoverwrites)