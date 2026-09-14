"""Authoring tool for the mana globe panel asset (X\\panel\\front_panel_mana_blue.cel).

The mod's own panel art (CtrlPan\\front_panel_mana_blue.cel in TH4data.mor) recoloured the mana
liquid into the palette's pure blue ramp, which reads brighter and flatter than Diablo's original
globe.  The original (CtrlPan\\Panel8.cel in DIABDAT.MPQ) paints the same globe out of the
desaturated blue-grey ramp instead:

    mod 135 (0,0,25)  -> original 190 (13,17,27)  and  191 (5,7,12)
    mod 134 (0,0,87)  -> original 189 (25,30,45)
    mod 133 (0,0,138) -> original 188 (37,43,65)

Note the first line: one mod colour maps to two different original ones, so this cannot be undone
with a .trn colour table - the pixels have to be copied across one by one.  That is all this script
does: it takes the mod panel, and inside the 88x88 mana globe rectangle only, replaces every pixel
with the one the original panel has there.  Everything else in the panel - the mod's own buttons,
frame and layout - is left exactly as it was.

The output is written as a byte-level patch of the mod .cel rather than a re-encode.  A CEL frame is
a run-length stream in which a byte < 0x80 starts a run of that many raw palette indices and a byte
>= 0x80 skips (256 - byte) transparent pixels, so overwriting an index inside a literal run changes
no lengths and no frame offsets.  Every pixel this script touches is a literal in both panels
(verified on write), so the file stays structurally identical to the one the game already reads.

usage: python tools/make_mana_globe_cel.py <original Panel8.cel> <mod front_panel_mana_blue.cel> <out.cel>
"""
import os
import struct
import sys

PANEL_W, PANEL_H = 640, 144
GLOBE_X, GLOBE_W, GLOBE_H = 464, 88, 88   # the mana globe rect inside the panel, see ManaGlobeLeft
FRAME = 1                                 # the panel image itself


def parse_cel(data, frame, width, height):
    """Decode one frame to (pixels, offsets); offsets[y][x] is where that pixel's palette index
    lives in `data`, or None for a transparent pixel that has no byte of its own."""
    nframes = struct.unpack_from('<I', data, 0)[0]
    offs = struct.unpack_from('<%dI' % (nframes + 2), data, 0)
    start, end = offs[frame], offs[frame + 1]
    cel = data[start:end]
    img = [[None] * width for _ in range(height)]
    pos = [[None] * width for _ in range(height)]
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
                        pos[y][x] = start + p + i
                    x += 1
                p += b
        y -= 1
    return img, pos


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        return 1
    orig_path, mod_path, out_path = sys.argv[1:4]
    orig, _ = parse_cel(open(orig_path, 'rb').read(), FRAME, PANEL_W, PANEL_H)
    mod_data = bytearray(open(mod_path, 'rb').read())
    mod, mod_pos = parse_cel(bytes(mod_data), FRAME, PANEL_W, PANEL_H)

    patched, skipped = 0, []
    for y in range(GLOBE_H):
        for x in range(GLOBE_X, GLOBE_X + GLOBE_W):
            want, have = orig[y][x], mod[y][x]
            if want == have:
                continue
            if want is None or mod_pos[y][x] is None:
                # one of the two is transparent here: fixing it would mean re-encoding the run
                skipped.append((y, x, have, want))
                continue
            mod_data[mod_pos[y][x]] = want
            patched += 1

    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    open(out_path, 'wb').write(bytes(mod_data))
    print('wrote %s (%d bytes, %d pixels taken from %s)'
          % (out_path, len(mod_data), patched, os.path.basename(orig_path)))
    if skipped:
        print('  %d pixel(s) left alone - transparent on one side, would need a re-encode:' % len(skipped))
        for y, x, have, want in skipped[:8]:
            print('    globe (%d,%d): %s -> %s' % (y, x - GLOBE_X, have, want))

    check, _ = parse_cel(bytes(mod_data), FRAME, PANEL_W, PANEL_H)
    bad = [(y, x) for y in range(PANEL_H) for x in range(PANEL_W)
           if check[y][x] != (orig[y][x] if (y < GLOBE_H and GLOBE_X <= x < GLOBE_X + GLOBE_W
                                             and (y, x, mod[y][x], orig[y][x]) not in skipped)
                              else mod[y][x])]
    print('  verify: %s' % ('OK - decodes to the mod panel with the original globe' if not bad
                            else '%d pixel(s) wrong, e.g. %s' % (len(bad), bad[:5])))
    return 0 if not bad else 2


if __name__ == '__main__':
    sys.exit(main())
