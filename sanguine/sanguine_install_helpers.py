import importlib
import os
import shutil
import subprocess
import sys

import sanguine.simple_download as simple_download
from sanguine.common import info, critical


def _install_pip_module(module: str) -> None:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', module])


REQUIRED_PIP_MODULES = ['json5', 'bethesda-structs']
PIP2PYTHON_MODULE_NAME_REMAPPING = {'bethesda-structs':'bethesda_structs'}

def _print_yellow(s: str) -> None:
    print('\x1b[93;20m' + s + '\x1b[0m')


def _print_redbold(s: str) -> None:
    print('\x1b[91;1m' + s + '\x1b[0m')


##### install

def _run_installer(cmd: list[str], sitefrom: str, localonly: bool = True) -> None:
    _print_redbold("We're about to run the following installer: {}".format(cmd[0]))
    _print_yellow("It was downloaded from {}".format(sitefrom))
    _print_yellow("Feel free to run it through your favorite virus checker,")
    _print_yellow("     but when, after entering 'Y' below, Windows will ask you stupid questions,")
    _print_redbold("     please make sure to tell Windows that you're ok with it")
    if localonly:
        _print_yellow(
            "We'll tell installer not to install anything system-wide, only into sanguine-rose\\tools folder.")
    while True:
        ok = input('Do you want to proceed (Y/N)?')
        if ok == 'Y' or ok == 'y':
            break
        if ok == 'N' or ok == 'n':
            _print_redbold('Aborting installation. sanguine-rose is likely to be unusable')
            os._exit(1)

    subprocess.check_call(cmd, shell=True)


def _tools_dir() -> str:
    return os.path.abspath(os.path.split(os.path.abspath(__file__))[0] + '\\..\\tools')


def _install_7z_exe() -> None:
    toolsdir = _tools_dir()
    os.makedirs(toolsdir + '\\7z', exist_ok=True)
    assert os.path.isdir(toolsdir)
    x64s = simple_download.pattern_from_url('https://7-zip.org/download.html', r'href="a/7z([0-9]*)-x64\.exe"')
    assert len(x64s) > 0
    ix64s = [int(x) for x in x64s]
    mx = ix64s.index(max(ix64s))
    assert 0 <= mx < len(ix64s)
    exename = '7z' + x64s[mx] + '-x64.exe'
    url = 'https://7-zip.org/a/' + exename
    x64exedl = simple_download.download_temp(url)
    x64exe = os.path.split(x64exedl)[0] + '\\' + exename
    assert os.path.isfile(x64exedl)
    shutil.move(x64exedl, x64exe)
    assert os.path.isfile(x64exe)

    _run_installer([x64exe, '/S', '/D=' + toolsdir + '\\7z'], url)
    os.remove(x64exe)


def install_sanguine_prerequisites() -> None:
    for m in REQUIRED_PIP_MODULES:
        _install_pip_module(m)

    _install_7z_exe()


##### checks

def _check_module_installed(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except ImportError:
        return False


def _not_installed(msg: str) -> None:
    critical(msg)
    critical('Aborting. Please make sure to run sanguine-rose/sanguine-install.py')
    os._exit(1)


def check_sanguine_prerequisites() -> None:
    for m in REQUIRED_PIP_MODULES:
        if m in PIP2PYTHON_MODULE_NAME_REMAPPING:
            m = PIP2PYTHON_MODULE_NAME_REMAPPING[m]
        if not _check_module_installed(m):
            _not_installed('Module {} is not installed.'.format(m))

    if not os.path.isfile(_tools_dir() + '\\7z\\7z.exe'):
        _not_installed('tools\\7z\\7z.exe is not installed.')

    info('All sanguine prerequisites are ok.')