"""Renders a Diablo .cel frame to a PNG so it can be looked at outside the game.

CEL is the game's own sprite format - a run-length stream of palette indices - so a palette is
needed to turn it into colours. Any level palette will do for interface art, which only uses
entries 128..255 (identical in every level palette); Levels\\TownData\\Town.pal out of TH4data.mor
is the usual choice. Transparent pixels come out fully transparent in the PNG.

usage: python tools/cel_to_png.py <file.cel> <palette.pal> <out.png> [frame] [width] [height] [scale]
       frame defaults to 1, width/height to 640x144 (the main panel), scale to 1

No external modules are needed - the PNG is written by hand.
"""
import os
import struct
import sys
import zlib


def load_pal(path):
    d = open(path, 'rb').read()
    return [tuple(d[i * 3:i * 3 + 3]) for i in range(256)]


def parse_cel(data, frame, width, height):
    nframes = struct.unpack_from('<I', data, 0)[0]
    if not 1 <= frame <= nframes:
        raise SystemExit('frame %d out of range, the file has %d' % (frame, nframes))
    offs = struct.unpack_from('<%dI' % (nframes + 2), data, 0)
    cel = data[offs[frame]:offs[frame + 1]]
    img = [[None] * width for _ in range(height)]
    y, p = height - 1, 0
    while p < len(cel) and y >= 0:
        x = 0
        while x < width and p < len(cel):
            b = cel[p]
            p += 1
            if b >= 0x80:
                x += 256 - b
            else:
                for i in range(b):
                    if x < width:
                        img[y][x] = cel[p + i]
                    x += 1
                p += b
        y -= 1
    return img


def write_png(path, rows, pal, scale=1):
    """32-bit RGBA, so transparent CEL pixels stay transparent."""
    raw = bytearray()
    for row in rows:
        line = bytearray()
        for px in row:
            rgba = (0, 0, 0, 0) if px is None else (pal[px][0], pal[px][1], pal[px][2], 255)
            line += bytes(rgba) * scale
        raw += (b'\x00' + line) * scale

    def chunk(tag, data):
        body = tag + data
        return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)

    w, h = len(rows[0]) * scale, len(rows) * scale
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))   # 6 = truecolour + alpha
    png += chunk(b'IDAT', zlib.compress(bytes(raw), 9))
    png += chunk(b'IEND', b'')
    open(path, 'wb').write(png)
    return w, h


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 1
    cel_path, pal_path, out_path = sys.argv[1:4]
    frame = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    width = int(sys.argv[5]) if len(sys.argv) > 5 else 640
    height = int(sys.argv[6]) if len(sys.argv) > 6 else 144
    scale = int(sys.argv[7]) if len(sys.argv) > 7 else 1

    rows = parse_cel(open(cel_path, 'rb').read(), frame, width, height)
    w, h = write_png(out_path, rows, load_pal(pal_path), scale)
    opaque = sum(1 for r in rows for p in r if p is not None)
    print('wrote %s (%dx%d, frame %d of %s, %d opaque of %d pixels)'
          % (out_path, w, h, frame, os.path.basename(cel_path), opaque, width * height))
    return 0


if __name__ == '__main__':
    sys.exit(main())
