# we have reasons to have our own Json writer:
#  1. major. we need very specific gitdiff-friendly format
#  2. minor. we want to keep these files as small as feasible (while keeping it more or less readable),
#            hence JSON5 quote-less names, and path and elements "compression". It was seen to save 3.8x (2x for default pcompression=0), for a 50M file it is quite a bit

import base64
import urllib.parse as urlparse

from mo2gitlib.common import *


def to_json_hash(h: int) -> str:
    assert (isinstance(h, int))
    assert (h >= 0)
    assert (h < 2 ** 64)
    # print(h)
    b = h.to_bytes(8, 'little', signed=False)
    b64 = base64.b64encode(b).decode('ascii')
    # print(b64)
    s = b64.rstrip('=')
    # assert from_json_hash(s) == h
    return s


def from_json_hash(s: str) -> int:
    ntopad = (3 - (len(s) % 3)) % 3
    # print(ntopad)
    s += '=='[:ntopad]
    # print(s)
    b = base64.b64decode(s)
    h = int.from_bytes(b, byteorder='little')
    return h


def to_json_fpath(fpath: str) -> str:
    return urlparse.quote(fpath, safe=" /+()'&#$[];,!@")


def from_json_fpath(fpath: str) -> str:
    return urlparse.unquote(fpath)


def compress_json_path(prevn: Val | None, prevpath: Val | None, path: str, level: int = 2):
    assert '/' not in path
    # assert('>' not in path)
    path = path.replace('\\', '/')
    if level == 0:
        path = '"' + to_json_fpath(path) + '"'
        assert ('"' not in path[1:-1])
        return path

    spl = path.split('/')
    # print(prevpath.val)
    # print(spl)
    nmatch = 0
    for i in range(min(len(prevpath.val), len(spl))):
        if spl[i] == prevpath.val[i]:
            nmatch = i + 1
        else:
            break
    assert nmatch >= 0
    if level == 2 or (level == 1 and prevn.val <= nmatch):
        if nmatch <= 9:
            path = '"' + str(nmatch)
        else:
            assert (nmatch <= 35)
            path = '"' + chr(nmatch - 10 + 65)
        needslash = False
        for i in range(nmatch, len(spl)):
            if needslash:
                path += '/'
            else:
                needslash = True
            path += to_json_fpath(spl[i])
    else:  # skipping compression because of level restrictions
        path = '"0' + to_json_fpath(path)
    prevpath.val = spl
    if prevn is not None:
        prevn.val = nmatch
    assert ('"' not in path[1:])
    return path + '"'


def decompress_json_path(prevpath: Val, path: str, level: int = 2):
    path = from_json_fpath(path)
    if level == 0:
        return path.replace('/', '\\')

    p0 = path[0]
    if '0' <= p0 <= '9':
        nmatch = int(p0)
    elif 'A' <= p0 <= 'Z':
        nmatch = ord(p0) - 65 + 10
    else:
        assert False
    out = ''

    # print(prevpath)
    # print(nmatch)
    for i in range(nmatch):
        if i > 0:
            out += '/'
        out += prevpath.val[i]
    if out != '':
        out += '/'
    out += path[1:]
    prevpath.val = out.split('/')
    return out.replace('/', '\\')


def int_json_param(name: str, prev: Val, new: int) -> str:
    if prev.val == new:
        return ''
    prev.val = new
    return ',' + name + ':' + str(new)


def str_json_param(name: str, prev: Val, new: str) -> str:
    if prev.val == new:
        return ''
    prev.val = new
    return ',' + name + ':"' + new + '"'
