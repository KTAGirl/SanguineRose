from mo2gitlib.common import *
from mo2gitlib.files import ArchiveEntry

def _dictOfArEntriesFromJsonFile(path):
    out = {}
    with open_3rdparty_txt_file(path) as rfile:
        for line in rfile:
            ae = ArchiveEntry.from_json(line)
            # print(ar.__dict__)
            out[ae.calculate_file_hash] = ae
    return out

def _dictOfArEntriesToJsonFile(path,aes):
    with open_3rdparty_txt_file_w(path) as wfile:
        for key in sorted(aes):
            ae = aes[key]
            wfile.write(ArchiveEntry.to_json(ae) + '\n')

class ArchiveEntriesCache:
    def __init__(self):
        self.archiveentries = {}
