import py7zr

from mo2git.pluginhandler import ArchivePluginBase

class SevenzArchivePlugin(ArchivePluginBase):
    def extensions(self):
        return ['.7z']
        
    def extract(self,archive,list_of_files,targetpath):
        print('Extracting from '+archive+'...')
        sevenz = py7zr.SevenZipFile(archive)
        names = sevenz.namelist()
        lof_normalized = []
        for f in list_of_files:
            normf = f.replace('\\','/')
            lof_normalized.append(normf)
            if normf not in names:
                print('WARNING: '+f+' NOT FOUND in '+archive)
        sevenz.extract(path=targetpath,targets=lof_normalized)
        out = []
        for f in list_of_files:
            if os.path.isfile(targetpath+f):
                out.append(targetpath+f)
            else:
                print('WARNING: '+f+' NOT EXTRACTED from '+archive)
                out.append(None)
        sevenz.close()
        print('Extraction done')
        return out
        
    def extractAll(self,archive,targetpath):
        print('Extracting from '+archive+'...')
        sevenz = py7zr.SevenZipFile(archive)
        sevenz.extractall(path=targetpath)
        sevenz.close()
        print('Extraction done')
