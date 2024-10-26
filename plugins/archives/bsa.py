from bethesda_structs.archive import BSAArchive

from wj2git.pluginhandler import ArchivePluginBase

class BsaArchivePlugin(ArchivePluginBase):
    def extensions(self):
        return ['.bsa']
        
    def extract(self,archive,list_of_files,targetpath):
        bsa = BSAArchive.parse_file(archive)
        # names = bsa.container.file_names
        # print(names)
        print('Extracting from '+archive+'...')
        bsa.extract(targetpath)
        out = []
        for f in list_of_files:
            if os.path.isfile(targetpath+f):
                out.append(targetpath+f)
            else:
                print('WARNING: '+f+' NOT EXTRACTED from '+archive)
                out.append(None)
        print('Extraction done')
        return out