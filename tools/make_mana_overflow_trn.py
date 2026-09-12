"""Authoring tool for the mana-overflow globe asset (X\\other\\ManaOvfl.trn).

The mage mana globe can hold more than max mana.  The first filling of the globe is the
normal mana liquid; every point of mana above max fills the globe a second time, in a
darker tone.  The darker tone is produced by running the liquid pixels of the panel
graphic through a colour translation table (a .trn - the same 256-byte remap asset the
game already uses for spell icons), so the second fill is the very same globe artwork,
only darker.

The table maps every palette entry to the palette entry closest to `entry * FACTOR`.
Targets are limited to palette indices 128..255, which are identical in every level
palette (verified for town + L1..L6), so the recoloured globe looks the same everywhere.

usage: python tools/make_mana_overflow_trn.py <town.pal> <out.trn> [preview-dir] [panel.cel ...]
"""
import os
import struct
import sys

FACTOR = 0.45           # how dark the second (overflow) filling is
STABLE_FIRST = 128      # palette entries below this differ from level to level


def load_pal(path):
    d = open(path, 'rb').read()
    return [tuple(d[i * 3:i * 3 + 3]) for i in range(256)]


def nearest(pal, rgb):
    best, bestd = STABLE_FIRST, None
    for i in range(STABLE_FIRST, 256):
        pr, pg, pb = pal[i]
        d = (pr - rgb[0]) ** 2 + (pg - rgb[1]) ** 2 + (pb - rgb[2]) ** 2
        if bestd is None or d < bestd:
            best, bestd = i, d
    return best


def build_trn(pal):
    out = bytearray(256)
    for i in range(256):
        r, g, b = pal[i]
        out[i] = nearest(pal, (r * FACTOR, g * FACTOR, b * FACTOR))
    out[0] = 0  # index 0 marks "not liquid" in the overflow globe buffer - keep it untouched
    return bytes(out)


# --- preview rendering -------------------------------------------------------
# Mirrors what the engine does: the globe area of the panel is the full liquid, the
# P8Bulbs frame is the empty globe, and a pixel belongs to the liquid exactly where the
# two differ.  See DrawManaGlobeBottom / BuildManaOverflowGlobe in src\Panel.cpp.

def parse_cel(data, frame, width, height):
    nframes = struct.unpack_from('<I', data, 0)[0]
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


def write_png(path, rows, pal, scale=3, bg=(255, 0, 255)):
    import zlib
    raw = bytearray()
    for row in rows:
        line = bytearray()
        for px in row:
            line += bytes(bg if px is None else pal[px]) * scale
        raw += (b'\x00' + line) * scale

    def chunk(t, d):
        c = t + d
        return struct.pack('>I', len(d)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

    w, h = len(rows[0]) * scale, len(rows) * scale
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(bytes(raw), 9))
    png += chunk(b'IEND', b'')
    open(path, 'wb').write(png)


def preview(panel_cel, bulbs_cel, pal, trn, out_dir, name):
    panel = parse_cel(open(panel_cel, 'rb').read(), 1, 640, 144)
    bulb = parse_cel(open(bulbs_cel, 'rb').read(), 2, 88, 88)
    globe = [row[464:552] for row in panel][:88]
    for ratio in (0, 25, 50, 69):
        rows = [list(r) for r in globe]
        for r in range(86 - ratio, 86):
            for x in range(88):
                if globe[r][x] != bulb[r][x] and globe[r][x] is not None:
                    rows[r][x] = trn[globe[r][x]]
        write_png(os.path.join(out_dir, 'preview_%s_%d.png' % (name, ratio)), rows, pal)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    pal = load_pal(sys.argv[1])
    trn = build_trn(pal)
    open(sys.argv[2], 'wb').write(trn)
    print('wrote %s (%d bytes, factor %.2f)' % (sys.argv[2], len(trn), FACTOR))
    for i in (0, 134, 135, 189, 190, 191, 239, 253, 254):
        print('  %3d %-14s -> %3d %s' % (i, pal[i], trn[i], pal[trn[i]]))
    if len(sys.argv) > 4:
        out_dir = sys.argv[3]
        bulbs = os.path.join(os.path.dirname(sys.argv[4]), 'P8Bulbs.CEL')
        for panel in sys.argv[4:]:
            preview(panel, bulbs, pal, trn, out_dir, os.path.splitext(os.path.basename(panel))[0])
    return 0


if __name__ == '__main__':
    sys.exit(main())
