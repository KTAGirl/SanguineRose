import importlib
import subprocess

# for install_checks we cannot use any files with non-guaranteed dependencies, so we:
#                    1. may use only those Python modules installed by default, and
#                    2. may use only those sanguine modules which are specifically designated as install-friendly

REQUIRED_PIP_MODULES = ['json5', 'bethesda-structs', 'pywin32']
PIP2PYTHON_MODULE_NAME_REMAPPING = {'bethesda-structs': 'bethesda_structs', 'pywin32': ['win32api', 'win32file']}


def print_yellow(s: str) -> None:
    print('\x1b[93m' + s + '\x1b[0m')


def print_redbold(s: str) -> None:
    print('\x1b[91;1m' + s + '\x1b[0m')


def print_green(s: str) -> None:
    print('\x1b[32m' + s + '\x1b[0m')


def _is_module_installed(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except ImportError:
        return False


def _not_installed(msg: str) -> None:
    print_redbold(msg)
    print_redbold('Aborting. Please make sure to run sanguine-rose/sanguine-install.py')
    # noinspection PyProtectedMember, PyUnresolvedReferences
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
        print_redbold('git is not found in PATH.')
        print_redbold(
            'Aborting. Please make sure to install "Git for Windows" or "GitHub Desktop" (preferred) and include folder with git.exe into PATH.')

    print_green('All sanguine prerequisites are ok.')
