import os
import glob
import json
import time

from mo2git.debug import DEBUG

def openModTxtFile(fname):
    return open(fname,'rt',encoding='cp1252',errors='replace')

def openModTxtFileW(fname):
    return open(fname,'wt',encoding='cp1252')

def escapeJSON(s):
    return json.dumps(s)
    
def isEslFlagged(filename):
    with open(filename, 'rb') as f:
        buf = f.read(10)
        return (buf[0x9] & 0x02) == 0x02

def addToDictOfLists(dict,key,val):
    if key not in dict:
        dict[key]=[val]
    else:
        dict[key].append(val)          

def makeDirsForFile(fname):
    os.makedirs(os.path.split(fname)[0],exist_ok=True)

def folderSize(rootpath):
    total = 0
    for dirpath, dirnames, filenames in os.walk(rootpath):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            assert(not os.path.islink(fp))
            total += os.path.getsize(fp)
    return total

def isEsx(path):
    ext = os.path.splitext(path)[1].lower()
    return ext == '.esl' or ext == '.esp' or ext == '.esm'

def allEsxs(mod,mo2):
    esxs = glob.glob(mo2+'mods/' + mod + '/*.esl')
    esxs = esxs + glob.glob(mo2+'mods/' + mod + '/*.esp')
    esxs = esxs + glob.glob(mo2+'mods/' + mod + '/*.esm')
    return esxs

def absDir(dir):
    if DEBUG:
        assert(dir.endswith('\\') or dir.endswith('/'))
    return os.path.abspath(dir)+'\\'

def normalizePath(path):
    path = os.path.abspath(path)
    assert(path.find('/')<0)
    return path

def denormalizePath(base,path):
    assert(path.startswith(base))
    return path[len(base):]

class Elapsed:
    def __init__(self):
        self.t0 = time.perf_counter()
        
    def printAndReset(self,where):
        t1 = time.perf_counter()
        print(where+' took '+str(round(t1-self.t0,2))+'s')
        self.t0 = t1

class Val:
    def __init__(self,initval):
        self.val = initval
        
    def __str__(self):
        return str(self.val)
        
def scriptDirFrom__file__(file):
    return os.path.split(os.path.abspath(file))[0] + '\\'