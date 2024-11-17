# def trace_reader(x):
#    # print("'"+str(x)+"'")
#    pass


class BinaryReader:
    contents: bytes
    offset: int

    def __init__(self, contents:bytes) -> None:
        self.contents = contents
        self.offset = 0

    def read_string(self) -> str:
        l = int(self.contents[self.offset])
        self.offset += 1
        # trace_reader('len=' + str(l))
        if l & 0x80:
            l = l & 0x7F
            len2 = int(self.contents[self.offset])
            self.offset += 1
            # trace_reader('len2=' + str(len2))
            assert (len2 & 0x80 == 0)
            l += len2 << 7
        # print(len)
        b = self.contents[self.offset:self.offset + l]
        self.offset += l
        s = b.decode('cp1252', 'replace')
        # trace_reader(str(l) + ":" + s)
        return s

    def read_int16(self) -> int:
        b = self.contents[self.offset:self.offset + 2]
        self.offset += 2
        i = int.from_bytes(b, byteorder='little', signed=True)
        # trace_reader(i)
        return i

    def read_uint16(self) -> int:
        b = self.contents[self.offset:self.offset + 2]
        self.offset += 2
        i = int.from_bytes(b, byteorder='little', signed=False)
        # trace_reader(i)
        return i

    def read_int32(self) -> int:
        b = self.contents[self.offset:self.offset + 4]
        self.offset += 4
        i = int.from_bytes(b, byteorder='little', signed=True)
        # trace_reader(i)
        return i

    def read_uint32(self) -> int:
        b = self.contents[self.offset:self.offset + 4]
        self.offset += 4
        i = int.from_bytes(b, byteorder='little', signed=False)
        # trace_reader(i)
        return i

    def read_int64(self) -> int:
        b = self.contents[self.offset:self.offset + 8]
        self.offset += 8
        i = int.from_bytes(b, byteorder='little', signed=True)
        # trace_reader(i)
        return i

    def read_uint64(self) -> int:
        b = self.contents[self.offset:self.offset + 8]
        self.offset += 8
        i = int.from_bytes(b, byteorder='little', signed=False)
        # trace_reader(i)
        return i

    def read_boolean(self) -> bool:
        b = self.contents[self.offset]
        self.offset += 1
        # trace_reader(b)
        return bool(b)

    def read_byte(self) -> int:
        b = self.contents[self.offset]
        self.offset += 1
        # trace_reader(b)
        return b

    def read_bytes(self, n) -> bytes:
        b = self.contents[self.offset:self.offset + n]
        self.offset += n
        # trace_reader(b)
        return b

    def is_eof(self) -> bool:
        return self.offset == len(self.contents)

    # def dbg(self):
    #    print(self.contents[self.offset:])
