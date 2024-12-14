import importlib
import subprocess

# unlike install_helpers, install_checks runs after install, so we're free to use anything we want
from sanguine.common import *
from sanguine.install_helpers import REQUIRED_PIP_MODULES, PIP2PYTHON_MODULE_NAME_REMAPPING


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
