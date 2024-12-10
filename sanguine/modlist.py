from sanguine.common import *


class ModList:
    modlist: list[str] | None

    def __init__(self, dirpath: str) -> None:
        assert is_normalized_dir_path(dirpath)
        fname = dirpath + 'modlist.txt'
        self.modlist = None
        with open_3rdparty_txt_file(fname) as rf:
            self.modlist = [line.rstrip() for line in rf]
        self.modlist = list(filter(lambda s: s.endswith('_separator') or not s.startswith('-'), self.modlist))
        self.modlist.reverse()  # 'natural' order

    def write(self, path: str) -> None:
        fname = path + 'modlist.txt'
        with open_3rdparty_txt_file_w(fname) as wfile:
            wfile.write("# This file was automatically modified by sanguine-rose.\n")
            for line in reversed(self.modlist):
                wfile.write(line + '\n')

    def write_disabling_if(self, path: str, f: Callable[[str], bool]) -> None:
        fname = path + 'modlist.txt'
        with open_3rdparty_txt_file_w(fname) as wfile:
            wfile.write("# This file was automatically modified by sanguine-rose.\n")
            for mod0 in reversed(self.modlist):
                if mod0[0] == '+':
                    mod = mod0[1:]
                    if f(mod):
                        wfile.write('-' + mod + '\n')
                    else:
                        wfile.write(mod0 + '\n')
                else:
                    wfile.write(mod0 + '\n')

    def all_enabled(self) -> Generator[str]:
        for mod in self.modlist:
            if mod[0] == '+':
                yield mod[1:]

    @staticmethod
    def is_separator(modname: str) -> str | None:  # returns separator name if applicable
        if modname.endswith('_separator'):
            return modname[:len(modname) - len('_separator')]
        return None
