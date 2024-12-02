import zipfile

from sanguine.pluginhandler import ArchivePluginBase

class ZipArchivePlugin(ArchivePluginBase):
    def extensions(self):
        return ['.zip']
        
    def extract(self,archive,list_of_files,targetpath):
        print('Extracting from '+archive+'...')
        z = zipfile.ZipFile(archive)
        names = z.namelist()
        lof_normalized = []
        for f in list_of_files:
            normf = f.replace('\\','/')
            lof_normalized.append(normf)
            if normf not in names:
                print('WARNING: '+f+' NOT FOUND in '+archive)
        out = []
        for f in lof_normalized:
            z.extract(f,path=targetpath)
            if os.path.isfile(targetpath+f):
                out.append(targetpath+f)
            else:
                print('WARNING: '+f+' NOT EXTRACTED from '+archive)
                out.append(None)
        z.close()
        print('Extraction done')
        return out
        
    def extract_all(self, archive, targetpath):
        print('Extracting from '+archive+'...')
        z = zipfile.ZipFile(archive)
        z.extractall(targetpath)
        z.close()
        print('Extraction done')