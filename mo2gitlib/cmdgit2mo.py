import os

from mo2gitlib.common import *
import mo2gitlib.cache as cache
from mo2gitlib.cmdcommon import _openCache,_csAndMasterModList
from mo2gitlib.master import Master
from mo2gitlib.folders import Folders
import mo2gitlib.mo2compat as mo2compat

def _git2mo(jsonconfigfname,config):
    compiler_settings_fname,compiler_settings,masterprofilename,mastermodlist = _csAndMasterModList(config)
    ignore=compiler_settings['Ignore']
    folders = Folders(jsonconfigfname,config,ignore)
    with mo2compat.LockMO2(folders.mo2_dir):
        filecache = _openCache(jsonconfigfname,config,mastermodlist,folders)
        print('Cache loaded')
        
        srcgithub = filecache.folders.github_dir
        masterjsonfname = srcgithub + 'master.json'
        masterjson = Master()
        with open(masterjsonfname, 'rt',encoding='utf-8') as rf:
            masterjson.construct_from_file(rf)
            
        mo2 = filecache.folders.mo2_dir
        needtorestore = {}
        needzerosize = []
        needtocopy = []
        for fimaster in masterjson.all_files():
            fpath = mo2+fimaster.file_path
            if fimaster.gitpath is not None:
                needtocopy.append(fpath)
                continue
            fimasterhash = cache.ZEROHASH if fimaster.file_size == 0 else fimaster.file_hash
            ficache = filecache.findFileOnly(fpath)
            if ficache is not None and ficache.file_hash == fimasterhash:
                #print(fimaster.file_path)
                #dbgWait()
                continue
            ae,archive,fi = filecache.findArchiveForFile(fpath)
            if ae is None:
                print("WARNING: don't know how to restore "+fpath)
            else:
                if ae.file_size == 0:
                    needzerosize.append(fpath)
                else:
                    add_to_dict_of_lists(needtorestore, archive.file_path, ae)
            
        dbgwait()
        print('zerosize:'+str(needzerosize))
        dbgwait()
        #print('copy:'+str(needtocopy))
        #dbgWait()
        print('restore:'+str(needtorestore))
        dbgwait()
