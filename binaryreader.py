from w2gdebug import DEBUG
from w2gdebug import dbgWait

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
        traceReader("len="+str(len))
        if len & 0x80:
            len = len & 0x7F
            len2 = int(self.contents[self.offset])
            self.offset += 1
            traceReader("len2="+str(len2))
            assert(len2&0x80==0)
            len += len2 << 7
        # print(len)
        bytes = self.contents[self.offset:self.offset+len]
        self.offset += len
        s = bytes.decode('cp1252','replace')
        traceReader(str(len)+":"+s)
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
        