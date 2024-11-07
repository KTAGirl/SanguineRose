import os

from mo2git.common import *

# we are compatible with wj paths, which are os.abspath.lower()
# all our dir end with '\\'

def _normalizeDirPath(path):
    path = os.path.abspath(path)
    assert('/' not in path)
    assert(not path.endswith('\\'))
    return path.lower()+'\\'

def _assertNormalizedDirPath(path):
    assert(path == os.path.abspath(path).lower()+'\\')

def _normalizeFilePath(path):
    assert(not path.endswith('\\') and not path.endswith('/'))
    path = os.path.abspath(path)
    assert('/' not in path)
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
    
def _assertNormalizedFileName(fname):
    assert('/' not in fname)
    assert('\\' not in fname)
    assert(fname.lower()==fname)
    
def _normalizeConfigDirPath(path,configdir): #relative to config dir
    if os.path.isabs(path):
        return _normalizeDirPath(path)
    else:
        return _normalizeDirPath(configdir+path)
    
def _configDirPath(path,configdir,config):
    path = _normalizeConfigDirPath(path,configdir)
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
        self.configdir = _normalizeDirPath(os.path.split(jsonconfigfname)[0])
        aAssert('mo2' in jsonconfig, lambda: "'mo2' must be present in config")
        mo2 = jsonconfig['mo2']
        aAssert(isinstance(mo2,str), lambda: "config.'mo2' must be a string, got "+repr(mo2))
        self.mo2 = _configDirPath(mo2,self.configdir,jsonconfig)

        if 'downloads' not in jsonconfig:
            dls = [self.mo2+'downloads\\']
        else:
            dls = jsonconfig['downloads']
        if isinstance(dls,str):
            dls = [dls]
        aAssert(isinstance(dls,list),lambda: "'downloads' in config must be a string or a list, got "+repr(dls))
        self.downloads = [_configDirPath(dl,self.configdir,jsonconfig) for dl in dls]
       
        self.ignore = [_normalizeDirPath(self.mo2+ig) for ig in ignore]
        #print(self.ignore)
        #dbgWait()
 
        self.cache = _configDirPath(jsonconfig.get('cache',self.configdir + '..\\mo2git.cache\\'),self.configdir,jsonconfig)
        self.tmp = _configDirPath(jsonconfig.get('tmp',self.configdir + '..\\mo2git.tmp\\'),self.configdir,jsonconfig)
        self.github=_configDirPath(jsonconfig.get('github',self.configdir),self.configdir,jsonconfig)
        #print(self.__dict__)
        #dbgWait()

        self.ownmods = [Folders.normalizeFileName(om) for om in jsonconfig.get('ownmods',[])]
        
        toolinstallfiles = jsonconfig.get('toolinstallfiles',[])
        self.allarchivenames = [Folders.normalizeFileName(arname) for arname in toolinstallfiles]
        
    def normalizeConfigDirPath(self,path):
        return _normalizeConfigDirPath(path,self.configdir)

    def normalizeConfigFilePath(self,path):
        spl = os.path.split(path)
        return _normalizeConfigDirPath(spl[0],self.configdir)+spl[1]
        
    def addArchiveNames(self,addarchivenames):
        for arname in addarchivenames:
            self.allarchivenames.append(Folders.normalizeFileName(arname))
        
    def setExclusions(self,mo2excludes,mo2reincludes):
        self.mo2excludes = [_normalizeDirPath(ex) for ex in mo2excludes]
        self.mo2reincludes = [_normalizeDirPath(rein) for rein in mo2reincludes]        
        
    def allArchiveNames(self):
        for arname in self.allarchivenames:
            yield arname
   
    def isKnownArchive(self,arpath):
        arname = Folders.normalizeFileName(os.path.split(arpath)[1])
        return arname in self.allarchivenames
        
    def isOwnMod(self,mod):
        _assertNormalizedFileName(mod)
        return mod in self.ownmods
        
    def isOwnModsFile(self,fpath):
        _assertNormalizedFilePath(fpath)
        for ownmod in self.ownmods:
            ownpath = self.mo2+'mods\\'+ownmod+'\\'
            if fpath.startswith(ownpath):
                return True
        return False
        
    def allOwnMods(self):
        for ownmod in self.ownmods:
            yield ownmod
   
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
