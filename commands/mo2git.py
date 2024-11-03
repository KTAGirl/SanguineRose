import json
import re
import shutil

from mo2git.common import *
from mo2git.installfile import manualUrlAndPrompt
from mo2git.modlist import ModList
from mo2git.common import *
from mo2git.commands.cmdcommon import _openCache,_csAndMasterModList
import mo2git.cache as cache
from mo2git.folders import Folders

'''
def mo2AndMasterModList(config):
    mo2,compiler_settings_fname,compiler_settings,masterprofilename,mastermodlist = _mo2AndCSAndMasterModList(config)
    return mo2,mastermodlist
'''    
def _writeManualDownloads(folders,md,modlist,config):
    mo2 = config['mo2']
    modlistname = config['modlistname']
    with openModTxtFileW('manualdl.md') as md:
        md.write('## '+modlistname+' - Manual Downloads\n')
        md.write('|#| URL | Comment |\n')
        md.write('|-----|-----|-----|\n')
        todl = {}
        for arname in folders.allArchiveNames():
                manualurl,prompt = manualUrlAndPrompt(arname,mo2)
                if manualurl:
                    addToDictOfLists(todl,manualurl,prompt)

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

def _loadFromCompilerSettings(config,stats,compiler_settings):
    config['modlistname']=compiler_settings['ModListName']
    stats['VERSION']=compiler_settings['Version']
    
def _fillCompiledStats(stats,statsfilename,prefix=''):
    with openModTxtFile(statsfilename) as rfile:
        statsjson = json.load(rfile)
     
        stats[prefix+'WBSIZE'] = f"{statsjson['Size']/1e9:.1f}G"
        stats[prefix+'DLSIZE'] = f"{statsjson['SizeOfArchives']/1e9:.0f}G"
        stats[prefix+'INSTALLSIZE'] = f"{statsjson['SizeOfInstalledFiles']/1e9:.0f}G"
        stats[prefix+'TOTALSPACE'] = f"{round(((statsjson['Size']+statsjson['SizeOfArchives']+statsjson['SizeOfInstalledFiles'])/1e9+5)/5,0)*5:.0f}G"

def _writeTxtFromTemplate(template,target,stats):
    with openModTxtFile(template) as fr:
        templ = fr.read()
    for key in stats:
        key1 = '%'+key+'%'
        templ = templ.replace(key1,str(stats[key]))
    with openModTxtFileW(target) as fw:
        fw.write(templ)

def _statsFolderSize(folder):
    return f"{folderSize(folder)/1e9:.1f}G"    

def _copyRestOfProfile(mo2,fulltargetdir,profilename):
    srcfdir = mo2+'profiles\\'+profilename+'\\'
    targetfdir = fulltargetdir + 'profiles\\'+profilename+'\\'
    shutil.copyfile(srcfdir+'loadorder.txt',targetfdir+'loadorder.txt')

def _mo2git(jsonconfigfname,config):
    compiler_settings_fname,compiler_settings,masterprofilename,mastermodlist = _csAndMasterModList(config)
    ignore=compiler_settings['Ignore']
    filecache = _openCache(jsonconfigfname,config,mastermodlist,ignore)

    ownmods=config['ownmods']
    
    targetgithub = filecache.folders.github
    targetdir = 'mo2\\'
    stats = {}
    
    # writing beautified compiler settings
    target_settings = targetgithub + targetdir + compiler_settings_fname
    makeDirsForFile(target_settings)
    with openModTxtFileW(target_settings) as wfile:
        json.dump(compiler_settings, wfile, sort_keys=True, indent=4)

    altprofilenames=compiler_settings['AdditionalProfiles']
    print("Processing profiles: "+masterprofilename+","+str(altprofilenames))

    allmods = {}
    for mod in mastermodlist.allEnabled():
        allmods[mod]=1
    altmodlists = {}
    for profile in altprofilenames:
        aml = ModList(filecache.folders.mo2+'profiles\\'+profile+'\\')
        for mod in aml.allEnabled():
            allmods[mod]=1
        altmodlists[profile] = aml

    allinstallfiles = {}
    for arname in filecache.folders.allarchivenames:
        ar = filecache.findArchiveByName(arname)
        if ar is not None:
            assert(ar.file_path.endswith(arname))
            #print(ar.file_hash)
            allinstallfiles[ar.file_hash] = ar.file_path
        else:
            warn('no archive found for '+arname)
    #print(allinstallfiles)
    #dbgWait()

    files = [fi.file_path for fi in filecache.allFiles()]
    files.sort()

    nwarn = 0

    # pre-cleanup
    modsdir = targetgithub+'mods\\'
    if os.path.isdir(modsdir):
        shutil.rmtree(modsdir)
    # dbgWait()

    nesx = 0
    with open(targetgithub+'master.json','wt',encoding='utf-8') as wfile:
        wfile.write('{ "archives": [\n')
        na = 0
        aif = []
        for hash, path in allinstallfiles.items():
            fname = os.path.split(path)[1]
            aif.append((fname,hash))
        aif.sort(key=lambda f: f[0])
        for f in aif:
            if na:
                wfile.write(",\n")
            na += 1
            wfile.write('    { "name": "'+str(f[0])+'", "hash": '+str(f[1])+' }')
        wfile.write('\n], "files": [\n')
        nf = 0
        mo2 = filecache.folders.mo2
        mo2len = len(mo2)
        for fpath0 in files:
            assert(fpath0.lower() == fpath0)
            assert(fpath0.startswith(mo2))
            fpath = fpath0[mo2len:]

            if nf:
                wfile.write(",\n")
            nf += 1
            
            if isEsx(fpath):
                nesx += 1
            
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
                fpath1 = mo2+fpath
                hash = cache.wjHash(fpath1)
                wfile.write( '    { "path":'+cache.escapeJSON(fpath)+', "hash":'+str(hash)+', "source":'+cache.escapeJSON(targetpath0)+' }')
                # dbgWait()
                continue
            
            ae,archive = filecache.findFile(fpath0)
            if ae is None:
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
                        hash = cache.wjHash(srcpath)
                        processed = True
                        # dbgWait()
                        wfile.write('    { "path":'+cache.escapeJSON(fpath)+', "hash":'+str(hash)+', "source":'+cache.escapeJSON(targetpath0)+' }')
                                
                if not processed:
                    wfile.write('    { "path":'+cache.escapeJSON(fpath)+', "warning":"NOT FOUND IN ARCHIVES" }')
                    nwarn += 1
            else:
                if archive is None:
                    assert(ae.file_size==0)
                    wfile.write('    { "path":'+cache.escapeJSON(fpath)+', "size":0 }')
                else:
                    wfile.write('    { "path":'+cache.escapeJSON(fpath)+', "hash":'+str(ae.file_hash)+', "size":'+str(ae.file_size)+', "archive_hash":'+str(ae.archive_hash)+', "in_archive_path":[')
                    np = 0
                    for path in ae.intra_path:
                        if np:
                            wfile.write(',')
                        wfile.write(cache.escapeJSON(path))
                        np += 1
                    wfile.write(']')
                    
                    if not allinstallfiles.get(ae.archive_hash):
                        wfile.write(', "warning":"archive found is NOT one of those listed"')
                        nwarn += 1
                    wfile.write(' }')

        wfile.write('\n]}\n')
                
    print("nn="+str(len(files))+" nwarn="+str(nwarn))
    stats['ESXS'] = nesx

    #validating json
    if DEBUG:
        with open(targetgithub+'master.json', 'rt',encoding='utf-8') as rf:
            json.load(rf)

    # copying own mods
    for mod in ownmods:
        shutil.copytree(mo2+'mods\\'+mod, targetgithub + targetdir+'mods\\'+mod, dirs_exist_ok=True)
 
    # writing profiles
    targetfdir = targetgithub + targetdir + 'profiles\\'+masterprofilename+'\\'
    makeDirsForFile(targetfdir+'modlist.txt')
    mastermodlist.write(targetfdir)
    # shutil.copyfile(mo2+'profiles\\'+masterprofilename+'\\loadorder.txt',targetfdir+'loadorder.txt')
    _copyRestOfProfile(mo2,targetgithub + targetdir,masterprofilename)
    genprofiles = config.get('genprofiles')
    # print(altmodlists)
    for profile in altmodlists: 
        # print(profile)
        ml = altmodlists[profile]
        fname = mo2+'profiles\\'+profile+'\\modlist.txt'
        targetfdir = targetgithub + targetdir + 'profiles\\'+profile+'\\'
        makeDirsForFile(targetfdir+'modlist.txt')
        filteroutpattern = None
        if genprofiles:
            filteroutpattern = genprofiles.get(profile)
        if filteroutpattern is None:
            warn('profile '+profile+"is not found in config['genprofiles']")
        else:
            optionalmods=0
            optionalesxs=0
            optionalesxs_dict={}
            optionalmods_dict={}

            # section = ''
            filteredout = False
            for mod in ml.modlist:
                separ = ModList.isSeparator(mod)
                # print(separ)
                if separ:
                    # section = separ
                    filteredout = re.search(filteroutpattern, separ, re.IGNORECASE) != None
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

            ml.writeDisablingIf(targetgithub+targetdir+'profiles\\'+profile+'\\', lambda mod: optionalmods_dict.get(mod))
            _copyRestOfProfile(mo2,targetgithub + targetdir,profile)

    _loadFromCompilerSettings(config,stats,compiler_settings)

    stats['ACTIVEMODS'] = sum(1 for i in mastermodlist.allEnabled())

    _writeManualDownloads(filecache.folders,targetgithub+'manualdl.md',mastermodlist,config)
        
    # more stats
    wjcompiled = config.get('wjcompiled')
    if wjcompiled:
        _fillCompiledStats(stats,wjcompiled)
    statsmods = config.get('statsmods')
    if statsmods:
        for stmod in statsmods:
            stats[stmod+'.SIZE']=_statsFolderSize(mo2+'mods/'+stmod)

    # generating README.md
    _writeTxtFromTemplate('README-template.md','README.md',stats)

    # return compiler_settings,mastermodlist,todl,stats