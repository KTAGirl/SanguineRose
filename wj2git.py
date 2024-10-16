import sqlite3
import os
import gzip

def traceReader(x):
    # print("'"+str(x)+"'")
    pass

class BinaryReader:
    def __init__(self,contents):
        self.contents = contents
        self.offset = 0

    def ReadString(self):
        len = int(self.contents[self.offset])
        self.offset += 1
        # print(len)
        bytes = contents[self.offset:self.offset+len]
        self.offset += len
        s = bytes.decode('cp1252')
        traceReader(s)
        return s

    def ReadInt16(self):
        bytes = self.contents[self.offset:self.offset+2]
        self.offset += 2
        i = int.from_bytes(bytes,byteorder='little',signed=True)
        traceReader(i)
        return i
        
    def ReadUint16(self):
        bytes = self.contents[self.offset:self.offset+2]
        self.offset += 2
        i = int.from_bytes(bytes,byteorder='little',signed=False)
        traceReader(i)
        return i
        
    def ReadInt32(self):
        bytes = self.contents[self.offset:self.offset+4]
        self.offset += 4
        i = int.from_bytes(bytes,byteorder='little',signed=True)
        traceReader(i)
        return i

    def ReadUint32(self):
        bytes = self.contents[self.offset:self.offset+4]
        self.offset += 4
        i = int.from_bytes(bytes,byteorder='little',signed=False)
        traceReader(i)
        return i

    def ReadInt64(self):
        bytes = self.contents[self.offset:self.offset+8]
        self.offset += 8
        i = int.from_bytes(bytes,byteorder='little',signed=True)
        traceReader(i)
        return i

    def ReadUint64(self):
        bytes = self.contents[self.offset:self.offset+8]
        self.offset += 8
        i = int.from_bytes(bytes,byteorder='little',signed=False)
        traceReader(i)
        return i
        
    def ReadBoolean(self):
        b = self.contents[self.offset]
        self.offset += 1
        traceReader(b)
        return bool(b)

    def ReadByte(self):
        b = self.contents[self.offset]
        self.offset += 1
        traceReader(b)
        return b

    def ReadBytes(self,n):
        bytes = self.contents[self.offset:self.offset+n]
        self.offset += n
        traceReader(bytes)
        return bytes
        
    def isEOF(self):
        return self.offset == len(self.contents)
        
    def dbg(self):
        print(self.contents[self.offset:])
        
class Img:
    def __init__(self,br):
        traceReader('Img:')
        self.w = br.ReadUint16()
        self.h = br.ReadUint16()
        self.mip = br.ReadByte()
        self.fmt = br.ReadByte()
        self.phash = br.ReadBytes(40)
        
    def dbg(self):
        return '{ w='+str(self.w)+' h='+str(self.h)+' mip='+str(self.mip)+' fmt='+str(self.fmt)+' phash=['+str(len(self.phash))+']}'
 
class HashedFile:
    def __init__(self,br):
        traceReader('HashedFile:')
        self.name = br.ReadString()
        self.hash = br.ReadUint64()
        if br.ReadBoolean():
            self.img = Img(br)
            # print(self.img.__dict__)
            # br.dbg()
        else:
            self.img = None
        self.size = br.ReadInt64()
        assert(self.size>=0)
        n = br.ReadInt32()
        assert(n>=0)
        self.children = []
        for i in range(0,n):
            self.children.append(HashedFile(br))
            
    def dbg(self):
        s = '{ name='+self.name+' hash='+str(self.hash)
        if self.img:
            s += ' img=' + self.img.dbg()
        if len(self.children):
            s += ' children=['
            ci = 0
            for child in self.children:
                if ci:
                    s += ','
                s += child.dbg()
                ci += 1
            s += ']'
        s += ' }'
        return s

home_dir = os.path.expanduser("~")
con = sqlite3.connect(home_dir+'/AppData/Local/Wabbajack/GlobalVFSCache5.sqlite')
cur = con.cursor()
rowi = -1
nn = 0
nx = 0
for row in cur.execute('SELECT Hash,Contents FROM VFSCache'): # WHERE Hash=-8778729428874073019"):
    rowi += 1
    # print(row)
    # print(row[0])
    contents = row[1]
    # print(contents)
    # with open('gzipped', 'wb') as wfile:
    #    wfile.write(contents)
    contents = gzip.decompress(contents)
    # print(contents)
    # print(rowi)
    # print(contents)
    try:
        nn += 1
        br = BinaryReader(contents)
        
        hf = HashedFile(br)
        assert(br.isEOF())
        # print(br.contents[br.offset:])
        print(str(row[0])+':'+hf.dbg())
    except Exception as e:
        print(e)
        nx += 1
print('nn='+str(nn)+' nx='+str(nx))