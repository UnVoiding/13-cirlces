"""Authoring tool for the mana-overflow globe assets (X\\other\\ManaOvfl.trn and friends).

A character who knows Master Caster can hold more than his maximum mana.  The first filling
of the globe is the normal mana liquid; every further full bar of mana above max fills the
globe again, a shade darker each time.  Each darker tone is produced by running the liquid
pixels of the panel graphic through a colour translation table (a .trn - the same 256-byte
remap asset the game already uses for spell icons), so every filling is the very same globe
artwork, only darker.

Three tones are generated, one per overflow bar (see ManaOverflowTones in src\\enums.h):

    ManaOvfl.trn   100-200% of max mana   darker, still neutral grey
    ManaOvf2.trn   200-300% of max mana   darker again, and cold - it leans into the blue
                                          ramp, which reaches further down than the grey one
    ManaOvf3.trn   300%+ of max mana      near black

The grey ramp the black panel's globe is drawn in bottoms out at palette entry 254
(17,17,17), so plain darkening runs out of room after the first tone.  The deeper tones
therefore also tint towards blue, which lets them land on the blue-grey ramp (176..191,
bottoming out at 5,7,12) and on the pure blue ramp (135 = 0,0,25) and stay distinguishable.

Targets are limited to palette indices 128..255, which are identical in every level palette
(verified for town + L1..L6), so the recoloured globe looks the same everywhere.

usage: python tools/make_mana_overflow_trn.py <town.pal> <out-dir> [preview-dir] [panel.cel ...]
"""
import os
import struct
import sys

STABLE_FIRST = 128      # palette entries below this differ from level to level

# one entry per overflow bar: output file, how much of the original brightness survives,
# and a per-channel tint applied on top of that (1,1,1 = keep the original hue)
TONES = [
    ('ManaOvfl.trn', 0.45, (1.00, 1.00, 1.00)),
    ('ManaOvf2.trn', 0.40, (0.40, 0.55, 1.00)),
    ('ManaOvf3.trn', 0.40, (1.00, 0.22, 0.22)),
]


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


def build_trn(pal, factor, tint):
    out = bytearray(256)
    for i in range(256):
        r, g, b = pal[i]
        out[i] = nearest(pal, (r * factor * tint[0], g * factor * tint[1], b * factor * tint[2]))
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


def preview(panel_cel, bulbs_cel, pal, trns, out_dir, name):
    """One PNG per (overflow bar, fill level), painted the way the engine stacks the
    fillings: the bar below the topmost one covers the whole globe in its tone, the
    topmost one rises from the bottom in the next tone down."""
    panel = parse_cel(open(panel_cel, 'rb').read(), 1, 640, 144)
    bulb = parse_cel(open(bulbs_cel, 'rb').read(), 2, 88, 88)
    globe = [row[464:552] for row in panel][:88]
    liquid = [[globe[y][x] is not None and globe[y][x] != bulb[y][x] for x in range(88)] for y in range(88)]

    def paint(rows, trn, height):
        for r in range(86 - height, 86):
            for x in range(88):
                if liquid[r][x]:
                    rows[r][x] = trn[globe[r][x]]

    for fills in range(len(trns) + 1):
        for ratio in (0, 25, 50, 86):
            if fills == 0 and ratio:
                continue    # the plain globe has nothing on top of it
            rows = [list(r) for r in globe]
            if fills >= 2:
                paint(rows, trns[fills - 2], 86)
            if fills >= 1:
                paint(rows, trns[fills - 1], ratio)
            write_png(os.path.join(out_dir, 'preview_%s_bar%d_%d.png' % (name, fills, ratio)), rows, pal)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    pal = load_pal(sys.argv[1])
    out_dir = sys.argv[2]
    trns = []
    for name, factor, tint in TONES:
        trn = build_trn(pal, factor, tint)
        trns.append(trn)
        open(os.path.join(out_dir, name), 'wb').write(trn)
        print('wrote %s (%d bytes, factor %.2f, tint %.2f/%.2f/%.2f)'
              % (os.path.join(out_dir, name), len(trn), factor, tint[0], tint[1], tint[2]))
        for i in (241, 245, 248, 251, 254, 175, 191):
            print('  %3d %-14s -> %3d %s' % (i, pal[i], trn[i], pal[trn[i]]))
    if len(sys.argv) > 4:
        preview_dir = sys.argv[3]
        bulbs = os.path.join(os.path.dirname(sys.argv[4]), 'P8Bulbs.CEL')
        for panel in sys.argv[4:]:
            preview(panel, bulbs, pal, trns, preview_dir, os.path.splitext(os.path.basename(panel))[0])
    return 0


if __name__ == '__main__':
    sys.exit(main())
