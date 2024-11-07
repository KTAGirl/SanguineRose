from enum import Enum
import os
import re

from mo2gitlib.common import *

def installfileAndModid(mod,mo2):
    modmetaname = mo2+'mods/' + mod + '/meta.ini'
    # print(modmetaname)
    try:
        with openModTxtFile(modmetaname) as modmeta:
            modmetalines = [line.rstrip() for line in modmeta]
    except Exception as e:
        print('WARNING: cannot read'+modmetaname+': '+str(e))
        return None,None
    installfiles = list(filter(lambda s: re.search('^installationFile *= *',s),modmetalines))
    assert(len(installfiles)<=1)
    if len(installfiles) == 0:
        # print('#2:'+mod)
        return None,None
    installfile = installfiles[0]
    m = re.search('^installationFile *= *(.*)',installfile)
    installfile = m.group(1)
    absdlpath = os.path.abspath(mo2+'downloads/').lower()
    absdlpath2 = absdlpath.replace('\\','/')
    assert(len(absdlpath)==len(absdlpath2))
    # print(absdlpath)
    if(installfile.lower().startswith(absdlpath) or installfile.lower().startswith(absdlpath2)):
        # print('##: '+installfile)
        # dbg.dbgWait()
        installfile = installfile[len(absdlpath):]
    if(installfile==''):
        # print('#3:'+mod)
        installfile=None

    modids = list(filter(lambda s: re.search('^modid *= *',s),modmetalines))
    assert(len(modids)<=1)
    modid = None
    if(len(modids)==1):
        m = re.search('^modid *= *(.*)',modids[0])
        if m:
            modid = int(m.group(1))
            if modid==-1:
                modid = None
    # print(installfile)
    return installfile,modid

class HowToDownloadReturn(Enum):
    NoMeta = 1
    ManualOk = 2
    NexusOk = 3
    NonNexusNonManual = 4
        
def howToDownload(installfile,mo2):
    filemetaname = mo2 + 'downloads/' + installfile + '.meta'
    try:
        with openModTxtFile(filemetaname) as filemeta:
            filemetalines = [line.rstrip() for line in filemeta]
    except:
        return HowToDownloadReturn.NoMeta,None,None
    manualurls = list(filter(lambda s: re.search('^manualURL *=',s),filemetalines))
    assert(len(manualurls)<=1)
    if(len(manualurls)==1):
        manualurl=manualurls[0]
        m = re.search('^manualURL *= *(.*)',manualurl)
        manualurl = m.group(1)
        # print(manualurl)
        prompts = list(filter(lambda s: re.search('^prompt *=',s),filemetalines))
        assert(len(prompts)==1)
        prompt=prompts[0]
        m = re.search('^prompt *= *(.*)',prompt)
        prompt = m.group(1)
        return HowToDownloadReturn.ManualOk,manualurl,prompt
    else:
        assert(len(manualurls)==0)
        urls = list(filter(lambda s: re.search('^url *=',s),filemetalines))
        if len(urls) == 0:
            return HowToDownloadReturn.NonNexusNonManual,None,None
        else:
            assert(len(urls)==1)
            url = urls[0]
            if not re.search('^url *= *"https://.*.nexusmods.com/',url):
                return HowToDownloadReturn.NonNexusNonManual,None,None
            return HowToDownloadReturn.NexusOk,None,None
            
def manualUrlAndPrompt(installfile,mo2):
    flag, manualurl, prompt = howToDownload(installfile,mo2)
    match flag:
        case HowToDownloadReturn.NoMeta:
            print("WARNING: no .meta file for "+installfile)
            return None,None
        case HowToDownloadReturn.ManualOk:
            return manualurl,prompt
        case HowToDownloadReturn.NexusOk:
            return None,None
        case HowToDownloadReturn.NonNexusNonManual:
            print("WARNING: neither manualURL no Nexus url in "+installfile+".meta")
            return None,None    

def installfileModidManualUrlAndPrompt(mod,mo2):
    installfile,modid = installfileAndModid(mod,mo2)

    manualurl = None
    if not installfile:
        print('WARNING: no installedFiles= found for mod '+mod)
        return None,None,None,None
    else:
        manualurl,prompt = manualUrlAndPrompt(installfile,mo2)
        return installfile,modid,manualurl,prompt
        