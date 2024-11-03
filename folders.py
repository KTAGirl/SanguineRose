import os

from mo2git.common import *

# we are compatible with wj paths, which are os.abspath.lower()

def _normalizeDirPath(path):
    path = os.path.abspath(path)
    assert(path.find('/')<0)
    assert(not path.endswith('\\'))
    return path.lower()+'\\'

def _assertNormalizedDirPath(path):
    assert(path == os.path.abspath(path).lower()+'\\')

def _normalizeFilePath(path):
    assert(not path.endswith('\\') and not path.endswith('/'))
    path = os.path.abspath(path)
    assert(path.find('/')<0)
    return path.lower()

def _assertNormalizedFilePath(path):
    assert(path == os.path.abspath(path).lower())

def _toShortPath(base,path):
    assert(path.startswith(base))
    return path[len(base):]

def _assertShortFilePath(fpath):
    assert(fpath == fpath.lower())
    assert(not fpath.endswith('\\') and not fpath.endswith('/'))
    assert(not os.path.isabs(fpath))

def _assertShortDirPath(fpath):
    assert(fpath == fpath.lower())
    assert(fpath.endswith('\\'))
    assert(not os.path.isabs(fpath))
    
def _configDirPath(path,configdir,config):
    if os.path.isabs(path):
        path = _normalizeDirPath(path)
    else:
        path = _normalizeDirPath(configdir+path)
    path = path.replace('{CONFIGDIR}',configdir)
    replaced = False
    for key,val in config.items():
        if isinstance(val,str):
            newpath = path.replace('{'+key+'}',val)
            if newpath != path:
                replaced = True
                path = newpath
    
    if replaced:
        return _configDirPath(path,configdir,config)
    else:
        return path

class Folders:
    def __init__(self,jsonconfigfname,jsonconfig,ignore):
        configdir = _normalizeDirPath(os.path.split(jsonconfigfname)[0])
        dls = jsonconfig['downloads']
        assert(isinstance(dls,list))
        self.downloads = [_configDirPath(dl,configdir,jsonconfig) for dl in dls]
        self.ignore = [_configDirPath(ig,configdir,jsonconfig) for ig in ignore]
        self.mo2 = _configDirPath(jsonconfig['mo2'],configdir,jsonconfig)
        self.cache = _configDirPath(jsonconfig.get('cache',configdir + '..\\mo2git.cache\\'),configdir,jsonconfig)
        self.tmp = _configDirPath(jsonconfig.get('tmp',configdir + '..\\mo2git.tmp\\'),configdir,jsonconfig)
        self.targetgithub=_configDirPath(jsonconfig.get('github',configdir),configdir,jsonconfig)
        #print(self.__dict__)
        #dbgWait()
        
    def setExclusions(self,mo2excludes,mo2reincludes):
        self.mo2excludes = [_normalizeDirPath(ex) for ex in mo2excludes]
        self.mo2reincludes = [_normalizeDirPath(rein) for rein in mo2reincludes]        
        
    def isMo2ExactDirIncluded(self,dirpath):
        # returns: None if ignored, False if mo2excluded, 1 if regular (not excluded)
        # unlike isMo2FilePathIncluded(), does not return 2; instead, on receiving False, caller should call getReinclusions()
        #print(dirpath)
        _assertNormalizedDirPath(dirpath)
        assert(dirpath.startswith(self.mo2))
        if dirpath in self.ignore:
            return None
        return False if dirpath in self.mo2excludes else 1
        
    def allReinclusionsForIgnoredOrExcluded(self,dirpath):
        _assertNormalizedDirPath(dirpath)
        assert(dirpath in self.ignore or dirpath in self.mo2excludes)
        out = []
        for rein in self.mo2reincludes:
            if rein.startswith(dirpath):
                yield rein
        
    def isMo2FilePathIncluded(self,fpath): 
        # returns: None if ignored, False if mo2excluded, 1 if regular (not excluded), 2 if mo2reincluded
        _assertNormalizedFilePath(fpath)
        assert(fpath.startswith(self.mo2))
        included = True
        for ig in self.ignore:
            if fpath.startswith(ig):
                included = None
                break
        if included:
            for ex in self.mo2excludes:
                if fpath.startswith(ex):
                    included = False
                    break
        if included:
            return 1
        for rein in self.mo2reincludes:
            if fpath.startswith(rein):
                return 2
        return included

    def filePathToShortPath(self,fpath):
        _assertNormalizedFilePath(fpath)
        return _renormalizeToShortPath(self.mo2,dirpath)

    def dirPathToShortPath(self,dirpath):
        _assertNormalizedDirPath(dirpath)
        return _renormalizeToShortPath(self.mo2,dirpath)
            
    def shortFilePathToPath(self,fpath):
        _assertShortFilePath(fpath)
        return self.mo2+fpath
        
    def shortDirPathToPath(self,dirpath):
        _assertShortDirPath(dirpath)
        return self.mo2+dirpath
        
    def normalizeFileName(fname):
        assert('\\' not in fname and '/' not in fname)
        return fname.lower()
        
    def normalizeFilePath(fpath):
        return _normalizeFilePath(fpath)
        
    def normalizeDirPath(fpath):
        return _normalizeDirPath(fpath)
        
    def normalizeArchiveIntraPath(fpath):
        _assertShortFilePath(fpath.lower())
        return fpath.lower()
        
class NoFolders:
    #mimics Folders for limited purposes
    def __init__(self):
        pass
        
    def isMo2ExactDirIncluded(self,dirpath):
        return 1
        
    def isMo2FilePathIncluded(self,fpath): 
        return 1
