from bethesda_structs.archive import BSAArchive

from mo2gitlib.pluginhandler import ArchivePluginBase

class BsaArchivePlugin(ArchivePluginBase):
    def extensions(self):
        return ['.bsa']
        
    def extract(self,archive,list_of_files,targetpath):
        print('Extracting from '+archive+'...')
        bsa = BSAArchive.parse_file(archive)
        # names = bsa.container.file_names
        # print(names)
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
        
    def extractAll(self,archive,targetpath):
        print('Extracting from '+archive+'...')
        bsa = BSAArchive.parse_file(archive)
        bsa.extract(targetpath)
        print('Extraction done')
