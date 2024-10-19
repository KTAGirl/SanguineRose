import os
import py7zr
import zipfile

def extract(archive,list_of_files,targetpath):
    # list_of_files is a list of paths in the same format as in archiveEntries!
    ext = os.path.splitext(archive)[1].lower()
    if ext == '.7z':
        sevenz = py7zr.SevenZipFile(archive)
        names = sevenz.namelist()
        lof_normalized = []
        for f in list_of_files:
            normf = f.replace('\\','/')
            lof_normalized.append(normf)
            if normf not in names:
                print('WARNING: '+f+' NOT FOUND in '+archive)
        print('Extracting from '+archive+'...')
        sevenz.extract(path=targetpath,targets=lof_normalized)
        out = []
        for f in list_of_files:
            if os.path.isfile(targetpath+f):
                out.append(targetpath+f)
            else:
                print('WARNING: '+f+' NOT EXTRACTED from '+archive)
                out.append(None)
        print('Extraction done')
        sevenz.close()
        return out
    elif ext == '.zip':
        z = zipfile.ZipFile(archive)
        names = z.namelist()
        lof_normalized = []
        for f in list_of_files:
            normf = f.replace('\\','/')
            lof_normalized.append(normf)
            if normf not in names:
                print('WARNING: '+f+' NOT FOUND in '+archive)
        print('Extracting from '+archive+'...')
        out = []
        for f in lof_normalized:
            z.extract(f,path=targetpath)
            if os.path.isfile(targetpath+f):
                out.append(targetpath+f)
            else:
                print('WARNING: '+f+' NOT EXTRACTED from '+archive)
                out.append(None)
        print('Extraction done')
        z.close()
        return out
       