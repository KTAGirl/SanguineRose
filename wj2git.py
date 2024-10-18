import os
import sys
import traceback
import json
import re
import shutil
import glob
from enum import Enum

import dbg
import wjdb

if not sys.version_info >= (3, 10):
    print('Sorry, wj2git needs at least Python 3.10')
    sys.exit(42)

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
            # skip if it is symbolic link
            if not os.path.islink(fp):
                total += os.path.getsize(fp)
    return total

def isEslFlagged(filename):
    with open(filename, 'rb') as f:
        buf = f.read(10)
        return (buf[0x9] & 0x02) == 0x02
        
def loadFromCompilerSettings(config,stats,compiler_settings):
    config['modlistname']=compiler_settings['ModListName']
    stats['VERSION']=compiler_settings['Version']

def escapeJSON(s):
    return json.dumps(s)

def openModTxtFile(fname):
    return open(fname,'rt',encoding='cp1252',errors='replace')

def openModTxtFileW(fname):
    return open(fname,'wt',encoding='cp1252')

class ModList:
    def __init__(self,path):
        fname = path + 'modlist.txt'
        self.modlist = None
        with openModTxtFile(fname) as rfile:
            self.modlist = [line.rstrip() for line in rfile]
        self.modlist = list(filter(lambda s: s.endswith('_separator') or not s.startswith('-'),self.modlist))
        self.modlist.reverse() # 'natural' order

    def write(self,path):
        fname = path + 'modlist.txt'
        with openModTxtFileW(fname) as wfile:
            wfile.write("# This file was automatically modified by wj2git.\n")
            for line in reversed(self.modlist):
                wfile.write(line+'\n')
            
    def writeDisablingIf(self,path,f):
        fname = path + 'modlist.txt'
        with openModTxtFileW(fname) as wfile:
            wfile.write("# This file was automatically modified by wj2git.\n")
            for mod0 in reversed(self.modlist):
                if mod0[0]=='+':
                    mod = mod0[1:]
                    if f(mod):
                        wfile.write('-'+mod+'\n')
                    else:
                        wfile.write(mod0+'\n')
                else:
                    wfile.write(mod0+'\n')
    
    def allEnabled(self):
        for mod in self.modlist:
            if mod[0]=='+':
                yield mod[1:]
            
    def isSeparator(modname):
        if modname.endswith('_separator'):
            return modname[:len(modname)-len('_separator')]
        return None
        
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
        
def allEsxs(mod,mo2):
    esxs = glob.glob(mo2+'mods/' + mod + '/*.esl')
    esxs = esxs + glob.glob(mo2+'mods/' + mod + '/*.esp')
    esxs = esxs + glob.glob(mo2+'mods/' + mod + '/*.esm')
    return esxs
    
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

def writeManualDownloads(md,modlist,todl0,config):
    mo2 = config['mo2']
    toolinstallfiles = config['toolinstallfiles']
    modlistname = config['modlistname']
    with openModTxtFileW('manualdl.md') as md:
        md.write('## '+modlistname+' - Manual Downloads\n')
        md.write('|#| URL | Comment |\n')
        md.write('|-----|-----|-----|\n')
        todl = {}
        if toolinstallfiles:
            for installfile in toolinstallfiles:
                manualurl,prompt = manualUrlAndPrompt(installfile,mo2)
                if manualurl:
                    addToDictOfLists(todl,manualurl,prompt)

        todl = todl | todl0


        rowidx = 1
        sorted_todl = dict(sorted(todl.items()))
        for manualurl in sorted_todl:
            prompts = sorted_todl[manualurl]
            # print(manualurl+' '+str(prompts))
            xprompt = ''
            for prompt in prompts:
                if len(xprompt) > 0:
                    xprompt = xprompt + '<br>'
                xprompt = xprompt + ':lips:' + prompt
            md.write('|'+str(rowidx)+'|['+manualurl+']('+manualurl+')|'+xprompt+'|\n')
            rowidx = rowidx + 1

def fillCompiledStats(stats,statsfilename,prefix=''):
    with openModTxtFile(statsfilename) as rfile:
        statsjson = json.load(rfile)
     
        stats[prefix+'WBSIZE'] = f"{statsjson['Size']/1e9:.1f}G"
        stats[prefix+'DLSIZE'] = f"{statsjson['SizeOfArchives']/1e9:.0f}G"
        stats[prefix+'INSTALLSIZE'] = f"{statsjson['SizeOfInstalledFiles']/1e9:.0f}G"
        stats[prefix+'TOTALSPACE'] = f"{round(((statsjson['Size']+statsjson['SizeOfArchives']+statsjson['SizeOfInstalledFiles'])/1e9+5)/5,0)*5:.0f}G"

def statsFolderSize(folder):
    return f"{folderSize(folder)/1e9:.1f}G"    

def enabledModSizes(modlist,mo2):
    sizes=[]
    for mod in modlist.allEnabled():
        sizes.append([mod,round(folderSize(mo2+'mods/'+mod)/1000000,2)])
    sizes.sort(key=lambda x: x[1])
    return sizes

def writeTxtFromTemplate(template,target,stats):
    with openModTxtFile(template) as fr:
        templ = fr.read()
    for key in stats:
        key1 = '%'+key+'%'
        templ = templ.replace(key1,str(stats[key]))
    with openModTxtFileW(target) as fw:
        fw.write(templ)

def _copyRestOfProfile(mo2,fulltargetdir,profilename):
    srcfdir = mo2+'profiles\\'+profilename+'\\'
    targetfdir = fulltargetdir + 'profiles\\'+profilename+'\\'
    shutil.copyfile(srcfdir+'loadorder.txt',targetfdir+'loadorder.txt')

#############

def wj2git(config):
    #contents=b''
    #print(contents)
    #parseContents(0,contents,False)
    #dbg.dbgWait()
    mo2=config['mo2']
    compiler_settings_fname=config['compiler_settings']
    targetgithub=config['targetgithub']
    ownmods=config['ownmods']
    
    targetdir = 'MO2\\'
    stats = {}

    with openModTxtFile(mo2+compiler_settings_fname) as rfile:
        compiler_settings = json.load(rfile)
    
    # writing beautified compiler settings
    target_settings = targetgithub + targetdir + compiler_settings_fname
    makeDirsForFile(target_settings)
    with openModTxtFileW(target_settings) as wfile:
        json.dump(compiler_settings, wfile, sort_keys=True, indent=4)
    
    masterprofilename=compiler_settings['Profile']
    altprofilenames=compiler_settings['AdditionalProfiles']
    print("Processing profiles: "+masterprofilename+","+str(altprofilenames))

    archives = wjdb.loadHC()
    archiveEntries = wjdb.loadVFS() 

    home_dir = os.path.expanduser("~")
    chc = wjdb.openHashCache(home_dir)

    allmods = {}
    mastermodlist = ModList(mo2+'profiles\\'+masterprofilename+'\\')
    for mod in mastermodlist.allEnabled():
        allmods[mod]=1
    altmodlists = {}
    for profile in altprofilenames:
        modlist = ModList(mo2+'profiles\\'+profile+'\\')
        for mod in modlist.allEnabled():
            allmods[mod]=1
        altmodlists[profile] = modlist

    todl = {}
    for mod in modlist.allEnabled():
        if mod in ownmods:
            continue
        installfile,modid,manualurl,prompt = installfileModidManualUrlAndPrompt(mod,mo2)
        if manualurl:
            addToDictOfLists(todl,manualurl,prompt)

    files = []
    nn = 0
    for modname in allmods:
            print("mod="+modname)
            for root, dirs, filenames in os.walk(mo2+'\\mods\\'+modname):
                for filename in filenames:
                    # print("file="+filename)
                    nn += 1
                    fpath = os.path.abspath(os.path.join(root,filename))
                    files.append(fpath)

    files.sort()

    nwarn = 0
    mo2abs = os.path.abspath(mo2)+'\\'
    ignore=compiler_settings['Ignore']

    # pre-cleanup
    modsdir = targetgithub+'mods'
    if os.path.isdir(modsdir):
        shutil.rmtree(modsdir)
    # dbg.dbgWait()

    with open(targetgithub+'master.json','wt',encoding="utf-8") as wfile:
        wfile.write('[\n')
        nf = 0
        for fpath0 in files:            
            assert(fpath0.lower().startswith(mo2abs.lower()))
            fpath = fpath0[len(mo2abs):]
            toignore=False
            for ign in ignore:
                if fpath.startswith(ign):
                    toignore = True
                    break
            if toignore:
                continue

            if nf:
                wfile.write(",\n")
            nf += 1
            
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
                wfile.write( '    { "path":'+escapeJSON(fpath)+', "source":'+escapeJSON(targetpath0)+' }')
                # dbg.dbgWait()
                continue
            
            archiveEntry, archive = wjdb.findFile(chc,archives,archiveEntries,fpath0)
            if archiveEntry == None:
                processed = False
                m = re.search('^mods\\\\(.*)\\\\meta.ini$',fpath)
                if m:
                    mod = m.group(1)
                    if mod.find('\\') < 0:
                        # print(mod)
                        targetpath0 = targetdir + fpath
                        targetpath = targetgithub + targetpath0
                        # print(realpath)
                        makeDirsForFile(targetpath)
                        srcpath = mo2 + fpath
                        shutil.copyfile(srcpath,targetpath)
                        processed = True
                        # dbg.dbgWait()
                        wfile.write( '    { "path":'+escapeJSON(fpath)+', "source":'+escapeJSON(targetpath0)+' }')
                                
                if not processed:
                    wfile.write( '    { "path":'+escapeJSON(fpath)+', "warning":"NOT FOUND IN ARCHIVES" }')
                    nwarn += 1
            else:
                wfile.write( '    { "path":'+escapeJSON(fpath)+', "hash":"'+str(archiveEntry.file_hash)+'", "size":"'+str(archiveEntry.file_hash)+'", "archive_hash":"'+str(archiveEntry.archive_hash)+'", "in_archive_path":[')
                np = 0
                for path in archiveEntry.intra_path:
                    if np:
                        wfile.write(',')
                    wfile.write(escapeJSON(path))
                    np += 1
                wfile.write('] }')

        wfile.write('\n]\n')
                
    print("nn="+str(nn)+" nwarn="+str(nwarn))

    #validating json
    if dbg.DBG:
        with open(targetgithub+'master.json', 'rt',encoding="utf-8") as rfile:
            dummy = json.load(rfile)

    # copying own mods
    for mod in ownmods:
        shutil.copytree(mo2+'mods/'+mod, targetgithub + targetdir+'mods\\'+mod, dirs_exist_ok=True)
 
    # writing profiles
    targetfdir = targetgithub + targetdir + 'profiles\\'+masterprofilename+'\\'
    makeDirsForFile(targetfdir+'modlist.txt')
    mastermodlist.write(targetfdir)
    # shutil.copyfile(mo2+'profiles\\'+masterprofilename+'\\loadorder.txt',targetfdir+'loadorder.txt')
    _copyRestOfProfile(mo2,targetgithub + targetdir,masterprofilename)
    cfgaltprof = config.get('altprofiles')
    # print(altmodlists)
    for profile in altmodlists:
        # print(profile)
        modlist = altmodlists[profile]
        fname = mo2+'profiles\\'+profile+'\\modlist.txt'
        targetfdir = targetgithub + targetdir + 'profiles\\'+profile+'\\'
        makeDirsForFile(targetfdir+'modlist.txt')
        filterout = None
        if cfgaltprof:
            filterout = cfgaltprof.get(profile)
        if filterout is None:
            print('WARNING: no filterout lambda in config for profile'+profile)
        else:
            optionalmods=0
            optionalesxs=0
            optionalesxs_dict={}
            optionalmods_dict={}

            # section = ''
            filteredout = False
            for mod in modlist.modlist:
                separ = ModList.isSeparator(mod)
                # print(separ)
                if separ:
                    # section = separ
                    filteredout = bool(filterout(separ))
                    # print(separ+':'+str(filteredout))
                else:
                    if mod[0] != '+':
                        continue
                    mod = mod[1:]
                    # print('mod='+mod)
                    if filteredout:
                        optionalmods += 1
                        # print('OPTIONAL:'+mod)
                        optionalmods_dict[mod] = 1
                        esxs=allEsxs(mod,mo2)
                        for esx in esxs:
                            optionalesxs += 1
                            key = os.path.split(esx)[1]
                            # print(key)
                            # assert(optionalesxs_dict.get(key)==None)
                            optionalesxs_dict[key] = esx #rewriting if applicable
                    else:
                        esxs=allEsxs(mod,mo2)
                        for esx in esxs:
                            key = os.path.split(esx)[1]
                            path = optionalesxs_dict.get(key)
                            if path != None:
                                # print(path + ' is overridden by '+ esx)
                                optionalesxs_dict[key] = esx
            
            stats[profile+'.OPTIONALMODS']=optionalmods
            stats[profile+'.OPTIONALESXS']=optionalesxs

            # print(optionalesxs_dict)
            for key in optionalesxs_dict:
                esx = optionalesxs_dict.get(key)
                assert(esx!=None)
                if not isEslFlagged(esx):
                    print('WARNING: OPTIONAL '+esx+' is not esl-flagged')

            modlist.writeDisablingIf(targetgithub+targetdir+'profiles\\'+profile+'\\', lambda mod: optionalmods_dict.get(mod))
            _copyRestOfProfile(mo2,targetgithub + targetdir,profile)

    return compiler_settings,mastermodlist,todl,stats