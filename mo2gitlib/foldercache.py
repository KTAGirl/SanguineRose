from mo2gitlib.common import *
import mo2gitlib.tasks as tasks
from mo2gitlib.files import File

def _getFileTimestamp(s):
    path = pathlib.Path(fname)
    return path.lstat().st_mtime

def _getFileTimestampFromSt(st):
    return st.st_mtime

def _getFromOneOfDicts(dicttolook,dicttolook2,key):
    found = dicttolook.get(key)
    if found is not None:
        return found
    return dicttolook2.get(key)

def _allValuesInBothDicts(dicttoscan,dicttoscan2):
    for key,val in dicttoscan.items():
        yield val
    for key,val in dicttoscan2.items():
        yield val

def _dictOfFilesFromJsonFile(path):
    out = {}
    with openModTxtFile(path) as rfile:
        for line in rfile:
            ar = File.fromJSON(line)
            assert(out.get(ar.file_path) is None)
            out[ar.file_path] = ar
    return out

def _dictOfFilesToJsonFile(path,files,filteredfiles):
    with openModTxtFileW(path) as wfile:
        for key in sorted(files):
            fi = files[key]
            wfile.write(File.toJSON(fi)+'\n')
        for fi in filteredfiles:
            wfile.write(File.toJSON(fi)+'\n')

class FolderScanStats:
    def __init__(self):
        self.nmodified = 0
        self.nscanned = 0
        self.ndel = 0
        
    def add(self,stats2):
        self.nmodified += stats2.nmodified
        self.nscanned += stats2.nscanned

class FolderScanDirOut:
    def __init__(self):
        self.filesbypath = {}
        self.scannedfiles = {}
        
class FolderScanFilter:
    def __init__(self,dirPathIsOk,filePathIsOk):
        assert(isinstance(filePathIsOk,tasks.LambdaReplacement) and isinstance(dirPathIsOk,tasks.LambdaReplacement))        
        self.dirPathIsOk = dirPathIsOk
        self.filePathIsOk = filePathIsOk

# heuristics to enable splitting/merging tasks

def _shouldSplit(t):  
    return t > 0.5
    
def _shouldMerge(t):
    return t < 0.3

class _TaskNode:
    def __init__(self,parent,path,t):
        self.parent = parent
        self.path = path
        self.t = t
        self.children = []
        
    def addChild(self,chpath):
        child = _TaskNode(self,chpath)
        self.children = child
        return child
        
def _mergeNode(node): #recursive
    t = node.t
    if t is None:
        return
    for ch in node.children:
        t += _mergeNode(ch)
    if _shouldMerge(t):
        children = []
        node.t = t
    return t
    
def _allNodes(allnodes2,node): #recursive
    allnodes2.append(node)
    for ch in node.children:
        _allNodes(ch)
        
def _scannedTaskName(name,dirpath):
    assert(Folders.isNormalizedDirPath(dirpath))
    return 'mo2gitlib.foldercache.'+name+'.'+dirpath

def _scannedOwnTaskName(name,dirpath):
    assert(Folders.isNormalizedDirPath(dirpath))
    return 'mo2gitlib.foldercache.own.'+name+'.'+dirpath

def _reconcileOwnTaskName(name):
    return 'mo2gitlib.foldercache.reconcile.'+name
    
### Tasks
    
def _loadFilesTaskFunc(param):
    (cachedir,name) = param
    filesbypath = {}
    try:
        filesbypath = _dictOfFilesFromJsonFile(cachedir+name+'.njson')
    except Exception as e:
        warn('error loading JSON cache '+name+'.njson: '+str(e)+'. Will continue w/o respective JSON cache')
        filesbypath = {} # just in case  

    return (filesbypath,)

def _loadFilesOwnTaskFunc(out,foldercache):
    (filesbypath,) = out
    foldercache.filesbypath = {}
    foldercache.filteredfiles = {}
    for key,val in filesbypath.items():
        assert(key==val.file_path)
        if foldercache.filter.filePathIsOk.call(key):
            foldercache.filesbypath[key] = val
        else:
            foldercache.filteredfiles.append(val)

    scannedfiles |= sdout.scannedfiles
    stats.add(gotstats)
    foldercache.filesbypath |= sdout.filesbypath
    self.pubfilesbypath = tasks.SharedPublication(parallel,self.underlyingfilesbypath)
    return (self.pubfilesbypath,)

def _scanFolderTaskFunc(param,fromownload):
    (taskroot,exdirs,name,filter,pubunderlying) = param
    (pubfilesbypath,) = fromownload
    sdout = FolderScanDirOut()
    stats = FolderScanStats()
    filesbypath = tasks.fromPublication(pubfilesbypath)
    underlying = tasks.fromPublication(pubunderlying)
    started = time.perf_counter()
    _scanDir(started,sdout,stats,taskroot,filesbypath,underlying,pubunderlying,exdirs,name,filter)
    return (stats,sdout)
    
def _scanFolderOwnTaskFunc(out,foldercache,scannedfiles,stats):
    (gotstats,sdout) = out
    scannedfiles |= sdout.scannedfiles
    stats.add(gotstats)
    foldercache.filesbypath |= sdout.filesbypath

def _ownReconcileTaskFunc(foldercache,parallel,scannedfiles):
        info('FolderCache('+rootfolder+'): '+str(len(scannedfiles))+' files scanned')
        ndel = 0
        for file in _allValuesInBothDicts(foldercache.filesbypath,foldercache.underlyingfilesbypath):
            fpath = file.file_path
            assert(Folders.isNormalizedFilePath(fpath))
            if scannedfiles.get(fpath) is None:
                inhere = foldercache.filesbypath.get(fpath)
                #print(injson)
                if inhere is not None and inhere.file_hash is None: #special record is already present
                    continue
                info(fpath+' was deleted')
                #dbgWait()
                foldercache.filesbypath[fpath] = File(None,None,fpath)
                ndel += 1
        info('FolderCache reconcile: '+str(ndel)+' files were deleted')
        timer.printAndReset('Reconciling dicts with scannedfiles')
        #dbgWait()
        
        savetaskname = 'mo2git.foldercache.save.'+self.name
        savetask = tasks.Task(savetaskname,_saveFilesTaskFunc,
                              (foldercache.cachedir,foldercache.name,foldercache.filesbypath,foldercache.filteredfiles),[])
        parallel.addLateTask(savetask) # we won't explicitly wait for savetask, it will be handled in Parallel.__exit__

def _saveFilesTaskFunc(param):
    (cachedir,name,filesbypath,filteredfiles) = param
    _dictOfFilesToJsonFile(cachedir+name+'.njson',filesbypath,filteredfiles)
    
class FolderCache: #single (recursive) folder cache
    def __init__(self,cachedir,name,rootfolder,externalfilesbypath,filter):
        assert(isinstance(filter,FolderScanFilter))
        
        self.underlyingfilesbypath = {}
        assert(isinstance(externalfilesbypath,dict))
        for key,val in externalfilesbypath.items():
            assert(val.file_path == key)
            if filter.filePathIsOk.call(key):
                self.underlyingfilesbypath[key] = val
            
        self.name = name
        self.rootfolder = rootfolder
        self.filesbypath = {}
        self.filteredjsonfiles = []
        self.filter = filter
        
        self.pubunderlyingfilesbypath = tasks.SharedPublication(parallel,self.underlyingfilesbypath)
        
    def startTasks(self,parallel):
        #building tree of known tasks
        rootnode = _TaskNode(None,'',None)
        allnodes = [('',rootnode)] #sorted in ascending order (but we'll scan it in reverse)
        for est in sorted(parallel.allEstimatesForPrefix(_scannedTaskName(self.name,self.rootfolder))):
            (path,t) = est
            parent = None
            for an in reversed(allnodes):
                (p,node) = an
                if path.startswith(p):
                    if path == p:
                        assert(node==rootnode)
                        rootnode.t = t
                    else:
                        ch = node.addChild(path,t)
                        allnodes.append( (path,ch) )
                        break #for an
        #task tree is complete, now we can try merging nodes
        _mergeNode(rootnode) #recursive
        
        #merged, starting tasks
        allnodes2 = [] #after merging, unsorted
        _allNodes(allnodes2,rootnode) #recursive
        
        alldirs = [self.rootfolder+n.path for n in allnodes2]

        scannedfiles = {}
        stats = FolderScanStats()
        
        loadtaskname = 'mo2git.foldercache.load.'+self.name
        loadtask = tasks.Task(loadtaskname,_loadFilesTaskFunc,(self.cachedir,self.name),[])
        parallel.addLateTask(loadtask)
        
        loadowntaskname = 'mo2git.foldercache.loadown.'+self.name
        loadowntask = tasks.Task(loadowntaskname,lambda _,out: _loadFilesTaskFunc(out,self),None,[loadtaskname])
        parallel.addLateOwnTask(loadowntask)

        for node in allnodes2:
            fullpath = self.rootfolder + node.path
            taskname = _scannedTaskName(self.name,path)
            alldirexthisone = [d for d in alldirs if d != fullpath]
            assert(len(alldirexthisone)==len(alldirs)-1)
            task = tasks.Task(taskname,_scanFolderTaskFunc,
                              (fullpath,alldirsexthisone,self.name,self.filter,makeSharedPublicationParam(self.pubunderlyingfilesbypath)),
                              [loadowntaskname])
            owntaskname = _scannedOwnTaskName(self.name,fullpath)
            owntask = tasks.Task(owntaskname,
                                 lamda _,out: _scanFolderOwnTaskFunc(out,self,scannedfiles,stats),
                                 None, [taskname])
                                 
            parallel.addLateTask(task)
            parallel.addLateOwnTask(owntask)
        
        reconciletask = tasks.Task(_reconcileOwnTaskName(self.name),
                                   lambda _,_1: _ownReconcileTaskFunc(self,parallel,scannedfiles),
                                   None, [_scannedOwnTaskName(self.name,self.rootfolder)+'*'])
        parallel.addLateOwnTask(reconciletask)
    
    def readyTaskName(self):
        return _reconcileOwnTaskName(self.name)
        
    def _scanDir(started,sdout,stats,dir,filesbypath,underlying,pubunderlying,exdirs,name,filter): #recursive over dir
        assert(Folders.isNormalizedDirPath(dir))
        # recursive implementation: able to skip subtrees, but more calls (lots of os.listdir() instead of single os.walk())
        # still, after recent performance fix seems to win like 1.5x over os.walk-based one
        for f in os.listdir(dir):
            fpath = dir+Folders.normalizeFileName(f)
            st = os.lstat(fpath)
            fmode = st.st_mode
            if stat.S_ISREG(fmode):
                assert(not stat.S_ISLNK(fmode))
                assert(Folders.isNormalizedFilePath(fpath))

                #if(not filter.filePathIsOk.call(fpath)):
                #    continue
                assert(filter.filePathIsOk.call(fpath))

                stats.nscanned += 1
                tstamp = _getFileTimestampFromSt(st)
                # print(fpath)
                found = _getFromOneOfDicts(filesbypath,underlying,fpath)
                sdout.scannedfiles.append(fpath)
                matched = False
                if found is not None:
                    if found.file_hash is not None:#file in cache marked as deleted, re-adding
                        tstamp2 = found.file_modified
                        # print(tstamp,tstamp2,_wjTimestampToPythonTimestamp(tstamp2))
                        if wjdb.compareTimestampWithWj(tstamp,tstamp2)==0:
                            matched = True
                if not matched:
                    sdout.filesbypath[fpath] = File(wjHash(fpath),tstamp,fpath)
            elif stat.S_ISDIR(fmode):
                newdir=fpath+'\\'
                assert(Folders.isNormalizedDirPath(newdir))
                if newdir in exdirs:
                    continue 
                if filter.dirPathIsOk.call(newdir):
                    est = parallels.estimatedTime(_scannedTaskName(name,newdir),1.)
                    elapsed = time.perf_counter() - started
                    if _shouldSplit(elapsed + est):
                        # new task
                        taskname = _scannedTaskName(fpath)
                        task = tasks.Task(taskname,_scanFolderTaskFunc,
                                          (fpath,exdirs,name,filter,pubunderlying),
                                          [])
                        owntaskname = _scannedOwnTaskName(fpath)
                        owntask = tasks.Task(owntaskname,
                                             lamda _,out: _scanFolderOwnTaskFunc(out,foldercache,scannedfiles,stats),
                                             None, [taskname])
                        parallel.addLateTask(task)
                        parallel.addLateOwnTask(owntask)
                    else:
                        _scanDir(started,sdout,stats,fpath,filesbypath,underlying,pubunderlying,exdirs,name,filter)
            else:
                critical(fpath+' is neither dir or file, aborting')
                aAssert(False)
