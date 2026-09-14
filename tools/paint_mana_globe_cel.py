"""Paints the mana globe for the panel from scratch (X\\panel\\front_panel_mana_orb.cel).

This is not tools\\make_mana_globe_stars_cel.py.  That one takes Diablo's globe and filters it -
averages the checkerboard out, lifts it, matches it back - so it inherits everything about the
original, including the fact that the whole sphere is drawn in about four tones.  This one samples
none of the source art.  It paints a glass sphere full of dark blue liquid, lit the way the panel
implies, and every value below is an art decision rather than something measured off the original:

  KEY         where the light comes from.  Diablo's globes are lit from above and to the right and
              the stone frame around the panel is shaded to match, so the key sits there.
  DIFFUSE     the broad falloff around the sphere, the main thing that makes it read as round.
  SPECULAR    the hot little reflection of the light source in the glass.  Tight and very bright -
              on a polished sphere it is nearly a point, and its size is what tells the eye the
              surface is glass and not stone.
  RIM         the whole edge of the glass catches light, brightest where it faces away from the
              key.  This is the single most important cue that the orb is transparent: without it
              a shaded circle just reads as a ball.
  BOUNCE      light that has gone through the liquid, hit the far inside of the glass and come
              back - a soft crescent inside the lower-left edge.  It is what keeps the dark side
              from going flat and dead, which is exactly what the filtered versions could not fix.
  DEPTH       the liquid is darkest where you look through most of it, so the middle sits deeper
              than a plain diffuse term would put it.

Because the shading is designed rather than inherited, it can be spread across six tones of the
blue ramp instead of the original's four, which is most of why it comes out smoother.  The rest is
a light ordered dither, only where two ramp entries meet.

The globe is painted into the panel in place, respecting the liquid mask: only pixels the original
already treats as liquid are touched, and never with a value equal to the empty-bulb graphic
underneath (see BuildManaOverflowGlobe in src\\Panel.cpp).

usage: python tools/paint_mana_globe_cel.py <panel.cel> <P8Bulbs.CEL> <palette.pal> <out.cel>
"""
import math
import os
import struct
import sys

PANEL_W, PANEL_H = 640, 144
GLOBE_X, GLOBE_W, GLOBE_H = 464, 88, 88
FRAME = 1

# Every pixel of the liquid mask is repainted, the original's own highlight and rim shading
# included.  The filtering tool leaves those alone because it is touching up Diablo's art; here
# they are painted too, or the old highlight shows through the new one.

# --- the light ------------------------------------------------------------------------------
KEY = (0.42, -0.30, 0.85)   # direction to the key light: right, up, toward the viewer
AMBIENT = 0.080             # how much light reaches the shadow side at all
DIFFUSE = 0.50              # strength of the broad round falloff
DIFFUSE_POW = 1.70          # >1 tightens the lit side and widens the terminator

SPECULAR = 1.00             # strength of the hot reflection
SPECULAR_TIGHT = 900.0      # higher = smaller, harder highlight.  Together with the bloom
                            # below this is sized to match the original's glare: 5x5 px above a
                            # luminance of 100, against the original's 16 px in the same 5x5.
SPECULAR_BLOOM = 0.050       # a wide, faint halo around it, the way glass scatters
SPECULAR_BLOOM_TIGHT = 260.0

RIM = 0.20                  # brightness of the lit edge of the glass
RIM_POW = 4.0               # how tightly the rim hugs the limb
RIM_BIAS = 0.55             # 0 = even all round, 1 = only on the side facing away from the key

BOUNCE = 0.14               # light returning off the far inside of the glass
BOUNCE_AT = 0.76            # how far out the crescent sits, in radii
BOUNCE_WIDTH = 0.20

DEPTH = 0.30                # how much the liquid darkens where you look through most of it

EDGE_DARK = 0.55            # the glass wall itself, a thin dark line right at the limb
EDGE_AT = 0.955

# --- the paint ------------------------------------------------------------------------------
LIQUID = (0.02, 0.06, 1.00)     # the hue of the mana itself, deep blue with a trace of green
GLOW = (0.34, 0.40, 1.00)       # the colour light takes on its way back out of the liquid
BODY_PALETTE = list(range(128, 136))
SPEC_PALETTE = [240, 241, 242, 243, 244, 176, 177, 178, 179, 180] + list(range(128, 136))
SPEC_CUT = 0.60                 # above this the pixel is painted as reflection, not as liquid.
                                # Set it low and the highlight's faint halo reaches the pale
                                # blue-greys too, which paints a flat blocky patch beside the
                                # core; the halo belongs in the blue ramp with the rest.

EXPOSURE = 0.83                 # overall brightness of the finished orb
DITHER = 0.60                   # share of the gradient carried by the ordered dither
DITHER_JITTER = 16.0

BAYER8 = [[0, 32, 8, 40, 2, 34, 10, 42],
          [48, 16, 56, 24, 50, 18, 58, 26],
          [12, 44, 4, 36, 14, 46, 6, 38],
          [60, 28, 52, 20, 62, 30, 54, 22],
          [3, 35, 11, 43, 1, 33, 9, 41],
          [51, 19, 59, 27, 49, 17, 57, 25],
          [15, 47, 7, 39, 13, 45, 5, 37],
          [63, 31, 55, 23, 61, 29, 53, 21]]


def parse_cel(data, frame, width, height):
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


def rnd(a, b, salt):
    h = (a * 73856093) ^ (b * 19349663) ^ (salt * 83492791)
    h &= 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 1274126177) & 0xFFFFFFFF
    h ^= h >> 16
    return h / 0x100000000


def load_pal(path):
    d = open(path, 'rb').read()
    return [tuple(d[i * 3:i * 3 + 3]) for i in range(256)]


def norm(v):
    m = math.sqrt(sum(c * c for c in v))
    return tuple(c / m for c in v)


def shade(nx, ny, r):
    """Light at one point on the sphere.  Returns (liquid brightness, reflection brightness)."""
    key = norm(KEY)
    z = math.sqrt(max(0.0, 1.0 - min(r, 1.0) ** 2))

    diffuse = max(0.0, nx * key[0] + ny * key[1] + z * key[2]) ** DIFFUSE_POW

    # half vector between the key and the viewer, who is straight on
    half = norm((key[0], key[1], key[2] + 1.0))
    align = max(0.0, nx * half[0] + ny * half[1] + z * half[2])
    spec = align ** SPECULAR_TIGHT
    bloom = align ** SPECULAR_BLOOM_TIGHT

    # the glass edge: brightest where it turns away from us, and more so away from the key
    facing = 1.0 - z
    away = 0.5 - 0.5 * (nx * key[0] + ny * key[1]) / max(1e-6, math.hypot(key[0], key[1]))
    rim = (facing ** RIM_POW) * (1.0 - RIM_BIAS + RIM_BIAS * away)

    # light that crossed the liquid and came back off the far wall
    bounce = math.exp(-(((r - BOUNCE_AT) / BOUNCE_WIDTH) ** 2)) * max(0.0, away - 0.15)

    # you see through more liquid toward the middle, so the middle goes deeper
    depth = 1.0 - DEPTH * z

    body = (AMBIENT + DIFFUSE * diffuse + BOUNCE * bounce) * depth + RIM * rim
    if r > EDGE_AT:                             # the wall of the glass itself
        body *= 1.0 - EDGE_DARK * (r - EDGE_AT) / (1.0 - EDGE_AT)
    return body, SPECULAR * spec + SPECULAR_BLOOM * bloom


def match(pal, palette, want, y, x, dither):
    """Nearest two entries, dithered between them by where the colour falls in the gap."""
    def dist(i):
        e = pal[i]
        return 2.0 * (e[0] - want[0]) ** 2 + 4.0 * (e[1] - want[1]) ** 2 + 3.0 * (e[2] - want[2]) ** 2

    order = sorted(range(len(palette)), key=lambda j: dist(palette[j]))
    j0 = order[0]
    j1 = min((j for j in (j0 - 1, j0 + 1) if 0 <= j < len(palette)), key=lambda j: dist(palette[j]),
             default=j0)
    a, b = pal[palette[j0]], pal[palette[j1]]
    seg = [b[i] - a[i] for i in range(3)]
    span = sum(v * v for v in seg)
    share = sum((want[i] - a[i]) * seg[i] for i in range(3)) / span if span else 0.0
    share = max(0.0, min(1.0, share))
    hard = 1.0 if share > 0.5 else 0.0
    share = hard + (share - hard) * dither
    t = (BAYER8[y & 7][x & 7] + 0.5 + (rnd(x, y, 31) - 0.5) * DITHER_JITTER) / 64.0
    return palette[j1] if share > t else palette[j0]


def main():
    if len(sys.argv) != 5:
        print(__doc__)
        return 1
    panel_path, bulbs_path, pal_path, out_path = sys.argv[1:5]
    pal = load_pal(pal_path)

    data = bytearray(open(panel_path, 'rb').read())
    panel, pos = parse_cel(bytes(data), FRAME, PANEL_W, PANEL_H)
    bulb, _ = parse_cel(open(bulbs_path, 'rb').read(), 2, GLOBE_W, GLOBE_H)

    globe = [[panel[y][x + GLOBE_X] for x in range(GLOBE_W)] for y in range(GLOBE_H)]
    liquid = [(y, x) for y in range(GLOBE_H) for x in range(GLOBE_W)
              if globe[y][x] is not None and globe[y][x] != bulb[y][x]]
    body = liquid

    # The globe is drawn to fill its 88x88 tile, so the sphere is the tile's inscribed circle.
    # Fitting it to the mask instead pulls the centre off, because the mask also picks up a few
    # stray pixels down where the glass meets the panel's stone frame.
    cy, cx, radius = (GLOBE_H - 1) / 2.0, (GLOBE_W - 1) / 2.0, GLOBE_W / 2.0
    print('painting a sphere at (%.1f,%.1f) r=%.1f over %d liquid px' % (cy, cx, radius, len(liquid)))

    patched, blocked, outside, used = 0, 0, 0, {}
    for y, x in body:
        nx, ny = (x - cx) / radius, (y - cy) / radius
        r = math.hypot(nx, ny)
        if r > 1.0:         # outside the glass: where it meets the frame, left as Diablo drew it
            outside += 1
            continue
        lit, reflect = shade(nx, ny, r)

        want = [255.0 * EXPOSURE * lit * (LIQUID[c] + GLOW[c] * lit) for c in range(3)]
        if reflect > SPEC_CUT:
            for c in range(3):
                want[c] += 255.0 * min(1.0, reflect)
            palette = SPEC_PALETTE
        else:
            for c in range(3):
                want[c] += 255.0 * reflect * (0.45 + 0.55 * GLOW[c])
            palette = BODY_PALETTE
        want = [max(0.0, min(255.0, v)) for v in want]

        new = match(pal, palette, want, y, x, DITHER)
        if new == bulb[y][x]:       # would stop counting as liquid
            blocked += 1
            continue
        used[new] = used.get(new, 0) + 1
        if new != globe[y][x]:
            data[pos[y][x + GLOBE_X]] = new
            patched += 1

    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    open(out_path, 'wb').write(bytes(data))
    print('wrote %s (%d bytes)' % (out_path, len(data)))
    print('  mask %d px, repainted %d, %d left outside the glass, %d skipped (bulb clash)'
          % (len(body), patched, outside, blocked))
    print('  tones used: %s' % ', '.join('%d x%d' % kv for kv in sorted(used.items())))

    check, _ = parse_cel(bytes(data), FRAME, PANEL_W, PANEL_H)
    still = [(y, x) for y in range(GLOBE_H) for x in range(GLOBE_W)
             if check[y][x + GLOBE_X] is not None and check[y][x + GLOBE_X] != bulb[y][x]]
    print('  verify: liquid mask %d px (was %d) - %s'
          % (len(still), len(liquid), 'OK' if len(still) == len(liquid) else 'CHANGED, check this'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
