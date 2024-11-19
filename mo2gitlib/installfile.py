import re
from enum import Enum

from mo2gitlib.common import *
from mo2gitlib.folders import Folders


def installfile_and_modid(mod: str, mo2: str):
    assert Folders.is_normalized_dir_path(mo2)
    modmetaname = mo2 + 'mods\\' + mod + '\\meta.ini'
    # print(modmetaname)
    try:
        with open_3rdparty_txt_file(modmetaname) as modmeta:
            modmetalines = [line.rstrip() for line in modmeta]
    except Exception as e:
        warn('cannot read' + modmetaname + ': ' + str(e))
        return None, None
    installfiles = [fname.replace('/', '\\').lower() for fname in
                    list(filter(lambda s: re.search('^installationFile *= *', s), modmetalines))]
    assert (len(installfiles) <= 1)
    if len(installfiles) == 0:
        # print('#2:'+mod)
        return None, None
    installfile = installfiles[0]
    m = re.search('^installationFile *= *(.*)', installfile)
    installfile = m.group(1)
    absdlpath = Folders.normalize_dir_path(mo2 + 'downloads\\')
    # print(absdlpath)
    if installfile.startswith(absdlpath):
        installfile = installfile[len(absdlpath):]
    if installfile == '':
        installfile = None

    modids = list(filter(lambda s: re.search('^modid *= *', s), modmetalines))
    assert (len(modids) <= 1)
    modid = None
    if len(modids) == 1:
        m = re.search('^modid *= *(.*)', modids[0])
        if m:
            modid = int(m.group(1))
            if modid == -1:
                modid = None
    # print(installfile)
    return installfile, modid


class HowToDownloadReturn(Enum):
    NoMeta = 1
    ManualOk = 2
    NexusOk = 3
    NonNexusNonManual = 4


def how_to_download(installfname: str, mo2: str) -> tuple[HowToDownloadReturn, str | None, str | None]:
    assert Folders.is_normalized_dir_path(mo2)
    filemetaname = mo2 + 'downloads\\' + installfname + '.meta'
    try:
        with open_3rdparty_txt_file(filemetaname) as filemeta:
            filemetalines = [line.rstrip() for line in filemeta]
    except Exception as e:
        warn('cannot read' + filemetaname + ': ' + str(e))
        return HowToDownloadReturn.NoMeta, None, None
    manualurls = list(filter(lambda s: re.search('^manualURL *=', s), filemetalines))
    assert len(manualurls) <= 1
    if len(manualurls) == 1:
        manualurl = manualurls[0]
        m = re.search('^manualURL *= *(.*)', manualurl)
        manualurl = m.group(1)
        # print(manualurl)
        prompts = list(filter(lambda s: re.search('^prompt *=', s), filemetalines))
        assert (len(prompts) == 1)
        prompt = prompts[0]
        m = re.search('^prompt *= *(.*)', prompt)
        prompt = m.group(1)
        return HowToDownloadReturn.ManualOk, manualurl, prompt
    else:
        assert (len(manualurls) == 0)
        urls = list(filter(lambda s: re.search('^url *=', s), filemetalines))
        if len(urls) == 0:
            return HowToDownloadReturn.NonNexusNonManual, None, None
        else:
            assert (len(urls) == 1)
            url = urls[0]
            if not re.search('^url *= *"https://.*.nexusmods.com/', url):
                return HowToDownloadReturn.NonNexusNonManual, None, None
            return HowToDownloadReturn.NexusOk, None, None


def manual_url_and_prompt(installfile: str, mo2: str):
    flag, manualurl, prompt = how_to_download(installfile, mo2)
    match flag:
        case HowToDownloadReturn.NoMeta:
            warn('no .meta file for ' + installfile)
            return None, None
        case HowToDownloadReturn.ManualOk:
            return manualurl, prompt
        case HowToDownloadReturn.NexusOk:
            return None, None
        case HowToDownloadReturn.NonNexusNonManual:
            warn('neither manualURL no Nexus url in ' + installfile + '.meta')
            return None, None


def installfile_modid_manual_url_and_prompt(mod: str, mo2: str):
    installfile, modid = installfile_and_modid(mod, mo2)

    # manualurl = None
    if not installfile:
        print('WARNING: no installedFiles= found for mod ' + mod)
        return None, None, None, None
    else:
        manualurl, prompt = manual_url_and_prompt(installfile, mo2)
        return installfile, modid, manualurl, prompt
