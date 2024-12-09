import importlib
import os
import re
import shutil
import subprocess
import sys

import sanguine.simple_download as simple_download
from sanguine.common import info, critical


def _install_pip_module(module: str) -> None:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', module])


REQUIRED_PIP_MODULES = ['json5', 'bethesda-structs', 'pywin32']
PIP2PYTHON_MODULE_NAME_REMAPPING = {'bethesda-structs': 'bethesda_structs', 'pywin32': ['win32api', 'win32file']}


def _print_yellow(s: str) -> None:
    print('\x1b[93m' + s + '\x1b[0m')


def _print_redbold(s: str) -> None:
    print('\x1b[91;1m' + s + '\x1b[0m')


def _print_green(s: str) -> None:
    print('\x1b[32m' + s + '\x1b[0m')


##### install

def _run_installer(cmd: list[str], sitefrom: str, msg: str) -> None:
    _print_redbold("We're about to run the following installer: {}".format(cmd[0]))
    _print_yellow("It was downloaded from {}".format(sitefrom))
    _print_yellow("Feel free to run it through your favorite virus checker,")
    _print_yellow("     but when, after entering 'Y' below, Windows will ask you stupid questions,")
    _print_redbold("     please make sure to tell Windows that you're ok with it")

    if msg:
        _print_redbold(msg)

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


def _download_file_nice_name(url: str) -> str:
    tfname = simple_download.download_temp(url)
    desired_fname = url.split('/')[-1]
    new_fname = os.path.split(tfname)[0] + '\\' + desired_fname
    assert os.path.isfile(tfname)
    shutil.move(tfname, new_fname)
    assert os.path.isfile(new_fname)
    return new_fname


### Specific installers

def _install_vs_build_tools() -> None:
    # trying to find one
    programfiles = os.environ['ProgramFiles(x86)']
    vswhere = os.path.join(programfiles, 'Microsoft Visual Studio\\Installer\\vswhere.exe')
    if os.path.exists(vswhere):
        out = subprocess.run([vswhere, '-products', 'Microsoft.VisualStudio.Product.BuildTools',
                              'Microsoft.VisualStudio.Product.Community',
                              'Microsoft.VisualStudio.Product.Professional',
                              'Microsoft.VisualStudio.Product.Enterprise'], text=True, capture_output=True)

        if out.returncode == 0:
            outstr = out.stdout
            # _print_yellow(outstr)
            m = re.search(r'productId\s*:\s*(Microsoft.VisualStudio.Product.[a-zA-Z0-9]*)', outstr)
            if m:
                _print_green('{} found, no need to download/install Visual Studio'.format(m.group(1)))
                return

    urls = simple_download.pattern_from_url('https://visualstudio.microsoft.com/visual-cpp-build-tools/',
                                            r'href="(https://aka.ms/vs/.*/release/vs_BuildTools.exe)"')
    assert len(urls) == 1
    url = urls[0]
    _print_green('Downloading {}...'.format(url))
    exe = _download_file_nice_name(url)
    _print_green('Download complete.')
    _run_installer([exe], url, 'Make sure to check "Desktop Development with C++" checkbox.')
    _print_green('Visual C++ build tools successfully installed.')


def install_sanguine_prerequisites() -> None:
    _install_vs_build_tools()  # should run before installing pip modules

    for m in REQUIRED_PIP_MODULES:
        _install_pip_module(m)
        _print_green('pip module {} successfully installed.'.format(m))


##### checks

def _is_module_installed(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except ImportError:
        return False


def _not_installed(msg: str) -> None:
    critical(msg)
    critical('Aborting. Please make sure to run sanguine-rose/sanguine-install.py')
    os._exit(1)


def _check_module(m: str) -> None:
    if not _is_module_installed(m):
        _not_installed('Module {} is not installed.'.format(m))


def check_sanguine_prerequisites() -> None:
    # we don't really need to check for MSVC being installed, as without it pip modules won't be available

    for m in REQUIRED_PIP_MODULES:
        if m in PIP2PYTHON_MODULE_NAME_REMAPPING:
            val = PIP2PYTHON_MODULE_NAME_REMAPPING[m]
            if isinstance(val, list):
                for v in val:
                    _check_module(v)
            else:
                _check_module(val)
        else:
            _check_module(m)

    if subprocess.call(['git', '--version']) != 0:
        critical('git is not found in PATH.')
        critical(
            'Aborting. Please make sure to install "Git for Windows" or "GitHub Desktop" (preferred) and include folder with git.exe into PATH.')

    info('All sanguine prerequisites are ok.')
