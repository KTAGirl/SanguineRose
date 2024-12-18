import glob
import importlib
import inspect

from sanguine.common import *


def load_plugins(plugindir: str, basecls: any, found: Callable[[any], None]) -> None:
    # plugindir is relative to the path of this very file
    thisdir = os.path.split(os.path.abspath(__file__))[0] + '\\..\\'
    # print(thisdir)
    sortedpys = sorted([py for py in glob.glob(thisdir + plugindir + '*.py')])
    for py in sortedpys:
        # print(py)
        modulename = os.path.splitext(os.path.split(py)[1])[0]
        if modulename == '__init__' or modulename.startswith('_'):
            continue
        # print(modulename)
        module = importlib.import_module('sanguine.' + plugindir.replace('/', '.') + modulename)
        ok = False
        for name, obj in inspect.getmembers(module):
            if inspect.isclass(obj):
                cls = obj
                mro = inspect.getmro(cls)
                if len(mro) >= 2:
                    parent = mro[1]
                    if parent is basecls:
                        plugin = cls()
                        found(plugin)
                        ok = True
        if not ok:
            warn('no class derived from ' + str(basecls) + ' found in ' + py)
