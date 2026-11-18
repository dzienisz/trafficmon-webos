#!/usr/bin/env python3
"""Generate app/icon.png: simple bar-chart glyph on dark background."""
import struct
import zlib

W = H = 160
px = [[(0, 0, 0, 0)] * W for _ in range(H)]


def rect(x0, y0, x1, y1, c):
    for y in range(max(0, y0), min(H, y1)):
        for x in range(max(0, x0), min(W, x1)):
            px[y][x] = c


# rounded-ish dark tile
rect(4, 4, 156, 156, (13, 13, 18, 255))
# bars: tx orange, rx blue
rect(30, 90, 55, 140, (255, 166, 87, 255))
rect(65, 55, 90, 140, (121, 192, 255, 255))
rect(100, 30, 125, 140, (126, 231, 135, 255))

raw = b''.join(b'\x00' + b''.join(struct.pack('4B', *p) for p in row) for row in px)


def chunk(typ, data):
    c = struct.pack('>I', len(data)) + typ + data
    return c + struct.pack('>I', zlib.crc32(typ + data) & 0xffffffff)


png = (b'\x89PNG\r\n\x1a\n'
       + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 6, 0, 0, 0))
       + chunk(b'IDAT', zlib.compress(raw, 9))
       + chunk(b'IEND', b''))
with open('app/icon.png', 'wb') as f:
    f.write(png)
print('wrote app/icon.png')
