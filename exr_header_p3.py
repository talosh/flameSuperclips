import os
import sys
import atexit
import base64
import collections
import fnmatch
import re
import shutil
import socket
import subprocess
import threading
import time

from xml.dom import minidom
from datetime import datetime, timedelta
from struct import unpack
from pprint import pprint, pformat

def read_exr_header(path):
    exr = None
    try:
        exr = open(path, 'rb')
    except:
        print('unable to open exr file\n%s:' % path)
        return None

    MAGIC = 0x01312f76

    COMPRESSION = ['NO','RLE','ZIPS','ZIP','PIZ','PXR24','B44','B44A', 'DWAA', 'DWAB']
    LINEORDER = ['INCRESING Y','DECREASING Y','RANDOM Y']
    PIXELTYPE = ['UINT','HALF','FLOAT']

    header = {}

    id = unpack('I', exr.read(4))[0]
    ver = unpack('I', exr.read(4))[0]
    if id != MAGIC:
        return False

    str = []
    d = exr.read(1).decode()
    while d != '\x00':
        str.append(d)
        d = exr.read(1).decode()
    cn = ''.join(str)

    pprint (cn)

    while len(cn):
        str = []
        d = exr.read(1).decode()
        while d != '\x00':
            str.append(d)
            d = (exr.read(1)).decode()
        name = ''.join(str)
        size = unpack('I', exr.read(4))[0]
        data = exr.read(size)

        result = ""
        if name == 'int':
            result = unpack('i', data)[0]
        elif name == 'float':
            result = unpack('f', data)[0]
        elif name == 'double':
            result = unpack('d', data)[0]
        elif name == 'string':
            result = "%s" % data
        elif name == 'box2i':
            result = unpack('4i', data)
        elif name == 'v2i':
            result = unpack('2i', data)
        elif name == 'v2f':
            result = unpack('2f', data)
        elif name == 'v3i':
            result = unpack('3i', data)
        elif name == 'v3f':
            result = unpack('3f', data)
        elif name == 'compression':
            if unpack('B', data)[0] > (len(COMPRESSION)-1):
                result = 'UNKNOWN, INDEX: %s' % unpack('B', data)[0]
            else:
                result = COMPRESSION[ unpack('B', data)[0] ]
        elif name == 'chlist':
            str_data = data.decode()
            chld = {}
            cid = 0
            while cid < (size-1):
                str = []
                while str_data[cid] != '\x00':
                    str.append((str_data)[cid])
                    cid = cid + 1
                idx = ''.join(str)
                cid = cid + 1
                ch = unpack('iiii', data[cid:cid+16])
                cid = cid + 16
                chld[idx] = {'pixeltype':PIXELTYPE[ch[0]], 'sampling x':ch[2], 'sampling y':ch[3] }
            result = chld
        elif name == 'lineOrder':
            result = LINEORDER[ unpack('B', data)[0] ]
        else:
            if size == 8:
                result = unpack('2i', data)
            else:
                result = unpack('%dB' % size, data)

        header[ cn ] = { name:result }

        str = []
        d = exr.read(1).decode()
        while d != '\x00':
            str.append(d)
            d = (exr.read(1)).decode()
        cn = ''.join(str)

    exr.close()
    return header


path = sys.argv[1]
header = read_exr_header(path)
pprint (header)