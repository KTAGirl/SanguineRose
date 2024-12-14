# dash in the .py file name is non-Pythonic only for module files, and not for end-user scripts

import os
import sys
import time

sys.path.append(os.path.split(os.path.abspath(__file__))[0])

from sanguine.common import *
from sanguine.install_checks import check_sanguine_prerequisites

if __name__ == '__main__':
    if not sys.version_info >= (3, 10):
        critical('Sorry, sanguine-rose needs at least Python 3.10')
        sys.exit(1)
    check_sanguine_prerequisites()

    argv = sys.argv
    argc = len(argv)
    # print(argv)

    thisscriptcalledas = os.path.split(argv[0])[1]
    configfilepath = os.path.abspath(argv[1])
    argv = argv[1:]
    argc -= 1

    ok = False
    started = time.perf_counter()
    if argc >= 2:
        match argv[1].lower():
            case 'mo2git':
                ok = True
            case 'git2mo':
                if argc == 2:
                    ok = True

    if ok:
        elapsed = round(time.perf_counter() - started, 2)
        print(thisscriptcalledas + ' took ' + str(elapsed) + ' sec')
    else:
        print('Usage:\n\t'
              + thisscriptcalledas + ' <project-config> mo2git\n\t'
              + thisscriptcalledas + ' <project-config> git2mo\n\t'
              + thisscriptcalledas + ' <project-config> debug.dumpwjdb <target-folder>\n\t'
              + thisscriptcalledas + ' <project-config> debug.modsizes\n'
              )
