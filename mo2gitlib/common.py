import os
import glob
import json
import time
import logging
import traceback

def dbgWait():
    wait = input("Press Enter to continue.")
    
def dbgFirst(data):
    if isinstance(data,list):
        print(len(data))
        return data[0]
    elif isinstance(data,dict):
        print(len(data))
        it = iter(data)
        key = next(it)
        print(key)
        return data[key]
    else:
        return data
        
def dbgPrint(s):
    if __debug__:
        print(s)
  
class Mo2gitError(Exception):
    pass
  
def aAssert(cond,f=None): #'always assert', even if __debug__ is False. f is a lambda printing error message before throwing
    if not cond:
        msg = 'aAssert() failed'
        if f is not None:
            msg += ':'+f()
        where = traceback.extract_stack(limit=2)[0]
        critical(msg+' @line '+str(where.lineno)+' of '+os.path.split(where.filename)[1])
        raise Mo2gitError(msg)

_logger = logging.getLogger('mo2git')
logging.basicConfig(level=logging.DEBUG)
def warn(msg):
    global _logger
    _logger.warning(msg)
def info(msg):
    global _logger
    _logger.info(msg)
def critical(msg):
    global _logger
    _logger.critical(msg)
    
###

class JsonEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o,object):
            return o.__dict__
        else:
            return o

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

'''
class Elapsed:
    def __init__(self):
        self.t0 = time.perf_counter()
        
    def printAndReset(self,where):
        t1 = time.perf_counter()
        print(where+' took '+str(round(t1-self.t0,2))+'s')
        self.t0 = t1
'''

class Val:
    def __init__(self,initval):
        self.val = initval
        
    def __str__(self):
        return str(self.val)
        
