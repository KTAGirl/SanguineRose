import os
import sys
import traceback
import json
import re
import shutil
import glob
import time
# import pathlib
# import xxhash

# import wjdb
import cache
from w2gdebug import DEBUG
from w2gdebug import dbgWait
from modlist import openModTxtFile
from modlist import openModTxtFileW
from modlist import ModList
from installfile import installfileModidManualUrlAndPrompt
from installfile import manualUrlAndPrompt
from archives import extract

# e = extract('..\\..\\mo2\\downloads\\1419098688_DeviousFollowers-ContinuedSEv2_14.5.7z',['Devious Followers - Continued SE v 2.14.5\\meshes\\armor\\shitty\\Blade\\9no1_0.nif'],'')
# e = extract('..\\..\\mo2\\downloads\\SexLab Strapon 3BA SOS Bodyslide.zip',['data\\CalienteTools\\BodySlide\\ShapeData\\strapon 3BA SOS\\strapon 3BA SOS.nif'],'')
# e = extract('..\\..\\mo2\\mods\\Suspicious City Guards\\suspiciouscityguards.bsa',['scripts\\source\\sf_scgalarmscene_0100690c.psc'],'.\\')
# print(e)
# dbgWait()

if not sys.version_info >= (3, 10):
    print('Sorry, wj2git needs at least Python 3.10')
    sys.exit(42)
    
wj2gitLoadedAt = time.perf_counter()

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

def isEslFlagged(filename):
    with open(filename, 'rb') as f:
        buf = f.read(10)
        return (buf[0x9] & 0x02) == 0x02
        
def loadFromCompilerSettings(config,stats,compiler_settings):
    config['modlistname']=compiler_settings['ModListName']
    stats['VERSION']=compiler_settings['Version']
        
def allEsxs(mod,mo2):
    esxs = glob.glob(mo2+'mods/' + mod + '/*.esl')
    esxs = esxs + glob.glob(mo2+'mods/' + mod + '/*.esp')
    esxs = esxs + glob.glob(mo2+'mods/' + mod + '/*.esm')
    return esxs

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
    
def elapsedTime():
    return round(time.perf_counter()-wj2gitLoadedAt,2)

def _absDir(dir):
    if DEBUG:
        assert(dir.endswith('\\') or dir.endswith('/'))
    return os.path.abspath(dir)+'\\'

###
    
def wj2git(config):
    #contents=b''
    #print(contents)
    #parseContents(0,contents,False)
    #dbgWait()
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

    downloadsdir = config['downloads']
    allarchivenames = []
    todl = {}
    for mod in modlist.allEnabled():
        if mod in ownmods:
            continue
        installfile,modid,manualurl,prompt = installfileModidManualUrlAndPrompt(mod,mo2)
        if installfile:
            fpath = downloadsdir+installfile
            allarchivenames.append(cache.normalizePath(fpath))
        if manualurl:
            addToDictOfLists(todl,manualurl,prompt)

    mo2excludefolders = [_absDir(mo2+'downloads\\'), # even if downloadsdirs is different
                         _absDir(downloadsdir), # even if different from mo2+'downloads\\'
                         _absDir(mo2+'mods\\')]
    mo2reincludefolders = []
    cachedir = config['cache']
    os.makedirs(cachedir,exist_ok=True)
    for mod in modlist.allEnabled():
        mo2reincludefolders.append(_absDir(mo2+'mods\\'+mod+'\\'))
    filecache = cache.Cache(allarchivenames,_absDir(cachedir),_absDir(downloadsdir),_absDir(mo2),mo2excludefolders,mo2reincludefolders,config.get('dbgdumpdb'))

    allinstallfiles = {}
    for arname in allarchivenames:
        archive = filecache.findArchive(arname)
        if archive:
            allinstallfiles[archive.archive_hash] = cache.denormalizePath(cache.normalizePath(downloadsdir)+'\\',arname)
        else:
            print('WARNING: no archive found for '+arname)
    #print(allinstallfiles)
    #dbgWait()

    files = []
    nn = 0
    for modname in allmods:
        print("mod="+modname)
        for dirpath, dirs, filenames in os.walk(mo2+'\\mods\\'+modname):
            for filename in filenames:
                # print("file="+filename)
                nn += 1
                fpath = cache.normalizePath(os.path.join(dirpath,filename))
                assert(not os.path.islink(fpath))
                files.append(fpath)

    files.sort()

    nwarn = 0
    mo2abs = cache.normalizePath(mo2)+'\\'
    ignore=compiler_settings['Ignore']

    # pre-cleanup
    modsdir = targetgithub+'mods'
    if os.path.isdir(modsdir):
        shutil.rmtree(modsdir)
    # dbgWait()

    with open(targetgithub+'master.json','wt',encoding="utf-8") as wfile:
        wfile.write('{ "archives": [\n')
        na = 0
        aif = []
        for key, value in allinstallfiles.items():
            aif.append([value,key])
        aif.sort(key=lambda f: f[0])
        for f in aif:
            if na:
                wfile.write(",\n")
            na += 1
            wfile.write('    { "name": "'+str(f[0])+'", "hash": "'+str(f[1])+'" }')
        wfile.write('\n], "files": [\n')
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
                wfile.write( '    { "path":'+cache.escapeJSON(fpath)+', "source":'+cache.escapeJSON(targetpath0)+' }')
                # dbgWait()
                continue
            
            # archiveEntry, archive = wjdb.findFile(filesbypath,archives,archiveEntries,fpath0)
            archiveEntry, archive = filecache.findFile(fpath0)
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
                        # dbgWait()
                        wfile.write( '    { "path":'+cache.escapeJSON(fpath)+', "source":'+cache.escapeJSON(targetpath0)+' }')
                                
                if not processed:
                    wfile.write( '    { "path":'+cache.escapeJSON(fpath)+', "warning":"NOT FOUND IN ARCHIVES" }')
                    nwarn += 1
            else:
                wfile.write( '    { "path":'+cache.escapeJSON(fpath)+', "hash":"'+str(archiveEntry.file_hash)+'", "size":"'+str(archiveEntry.file_hash)+'", "archive_hash":"'+str(archiveEntry.archive_hash)+'", "in_archive_path":[')
                np = 0
                for path in archiveEntry.intra_path:
                    if np:
                        wfile.write(',')
                    wfile.write(cache.escapeJSON(path))
                    np += 1
                wfile.write(']')
                
                if not allinstallfiles.get(archiveEntry.archive_hash):
                    wfile.write(', "warning":"archive found is NOT one of those listed"')
                    nwarn += 1
                wfile.write(' }')

        wfile.write('\n]}\n')
                
    print("nn="+str(nn)+" nwarn="+str(nwarn))

    #validating json
    if DEBUG:
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