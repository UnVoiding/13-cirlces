"""Authoring tool for the alternative mana globe panel (X\\panel\\front_panel_mana_stars.cel).

Both the stock globes paint their shading as a 50/50 checkerboard dither between two palette
entries, which at 1x reads as a constant fizz over the whole sphere.  This script dissolves that
checkerboard - every body pixel is averaged with its neighbours in RGB, lifted a little, and
matched back to the palette - and then scatters a handful of pale blue sparkles through the
result: a bright core with four short rays fading out from it, the way a star glint looks.

The sparkles are placed on a jittered grid rather than by rolling a die per pixel.  Independent
per-pixel chance gives a Poisson distribution, which clumps in places and leaves bald patches
elsewhere; one sparkle per grid cell, nudged off the cell centre by STAR_JITTER, keeps them evenly
spread while still looking scattered.  Each one takes a size from STAR_KINDS, so a few are bigger
than the rest.

Only the body of the liquid is touched - pixels currently painted in BODY_INDICES.  The globe's
own specular glint, the rim shading and everything outside the globe are left exactly as they are.

Like tools\\make_mana_globe_cel.py this writes a byte-level patch of the source .cel rather than a
re-encode: a CEL literal run stores raw palette indices, so overwriting one changes no run lengths
and no frame offsets.  The script also refuses to write a pixel whose new index would equal the
empty-bulb graphic underneath it, because the engine decides what counts as liquid by comparing
the two (see BuildManaOverflowGlobe in src\\Panel.cpp) and such a pixel would silently drop out of
the mana globe.

Set REPAINT_BODY to False to leave the panel's liquid exactly as it is and only scatter sparkles
over it - which is how sparkles go onto a globe that tools/paint_mana_globe_cel.py has already
painted.  An optional fifth argument names a panel whose liquid decides where sparkles may land;
without it that comes from the panel being written.  Passing the untouched original there is what
reproduces a scatter that was chosen on the original, pixel for pixel, on top of a new globe.

usage: python tools/make_mana_globe_stars_cel.py <front_panel.cel> <P8Bulbs.CEL> <palette.pal> <out.cel> [mask.cel]
"""
import os
import struct
import sys

PANEL_W, PANEL_H = 640, 144
GLOBE_X, GLOBE_W, GLOBE_H = 464, 88, 88
FRAME = 1

# The body of the liquid - every index here gets repainted.  The mod's own panel shades the globe
# in the blue ramp alone; Diablo's original shades it as a checkerboard between the blue ramp and
# the desaturated blue-greys 188-191, so both families have to be listed for the tool to work on
# either base panel.  Anything not listed (the specular highlight, the rim) is left alone.
BODY_INDICES = {133, 134, 135, 188, 189, 190, 191}

# --- the body ------------------------------------------------------------------------------
# The body is not repainted from a ramp of our choosing: it is repainted from its own colours.
# Each body pixel is averaged with its neighbours in RGB, which dissolves the checkerboard, then
# brightened a little and matched back to the nearest palette entry.  Doing it this way preserves
# the original shading and, more importantly, its hue - the globe is a dither of pure blue against
# desaturated blue-grey, and a gradient over the blue ramp alone comes out far bluer and brighter
# than the art it replaces, however carefully the luminance is matched.
# The blue-greys are deliberately left out of the match.  They are in the source art, but they sit
# close enough to the blue ramp in the globe's darker half that the nearest-entry match flips
# between the two families there and leaves a hard-edged slate blotch down the left side.
BODY_PALETTE = list(range(128, 136))    # the blue ramp, as the mana potion sprite uses
BODY_BLUR = 2.6         # radius in px the smoothing averages over; this is what kills the fizz
BODY_GAIN = 1.12        # overall brightness multiplier, 1.0 = as dark as the original
BODY_BLUE = 1.12        # extra multiplier on the blue channel alone, for a more potion-like tint
# How far each pixel is pushed away from the body's mean colour before the match, which is what
# controls how pronounced the shading is.  1.0 leaves the original's shading alone.  The two sides
# are separate because they do different jobs: SHADOW deepens the dark bottom-left and makes the
# sphere read as round, while LIT brightens the side under the highlight and quickly starts to
# look like a different, bluer globe.
BODY_CONTRAST_SHADOW = 1.90
BODY_CONTRAST_LIT = 1.10
BODY_CONTRAST_BAND = 14.0   # luminance width the two factors cross over in.  Switching between
                            # them at the mean leaves a visible seam across the sphere wherever
                            # they differ much, so they are blended over a band instead.
# How much of the gradient is carried by dithering, 0 = none, 1 = fully dithered.  The blue ramp
# is coarse at its dark end - 135 is (0,0,25) and 134 is (0,0,87), with nothing between - so
# matching each pixel to its single nearest entry paints the globe's dark side as one large flat
# plateau with a hard contour where it steps.  Dithering between the two entries that bracket the
# target, at a density that follows the gradient, is what makes that side read as liquid instead.
# It is nothing like the fizz in the source art: Diablo's globe is a 50/50 checkerboard everywhere,
# the worst possible case, while here the mix is only near 50/50 in the middle of a band and falls
# to nothing at either end, where almost every pixel is the same colour as its neighbours.
BODY_DITHER = 0.40
BODY_DITHER_JITTER = 16.0   # how far each threshold may be nudged, out of the matrix's 64 levels.
                            # A pure Bayer matrix lays the dithered pixels out on a regular grid,
                            # which the eye picks up as a screen door; jittering the thresholds
                            # keeps the same density but scatters them.  Past about 24 it stops
                            # being a scatter and starts clumping, which looks like grain.

# --- the sparkles --------------------------------------------------------------------------
# The top of the liquid's own blue ramp, brightest first.  Nothing whiter than 128 (159,159,255)
# belongs here: the near-white palette entries (240/241, or even the pale blue-grey 176) read as
# specks stuck on the glass rather than as glints inside the mana, and the globe already has one
# white highlight of its own.  Against a body painted in 134/135 a 128 core is still an enormous
# step up, so the sparkle stays legible while staying blue.  The tail runs down the same ramp,
# which lets the rays fade into the body instead of stopping dead against it.
STAR_LEVELS = [128, 129, 130, 131, 132, 133]
# most cores sit on 129 (87,87,255), which is unmistakably blue; the occasional 128 core is what
# keeps the field from looking like ten copies of the same star
STAR_CORE = [(0, 0.30), (1, 0.45), (2, 0.25)]   # index into STAR_LEVELS for the core -> share

REPAINT_BODY = True     # False leaves the liquid alone and only lays the sparkles over it
STAR_SEED = 1           # change this for a different scatter at the same density and sizes
STAR_CELL = 13.8        # grid spacing in px; smaller = more sparkles, evenly spread.  Count does
                        # not go as 1/cell^2 - cells rejected by EDGE_CLEAR and GLINT_CLEAR do not
                        # scale the same way - so this was measured rather than derived: averaged
                        # over seeds 6-10, 15.0 gives 9.8 sparkles and 13.8 gives 11.2
STAR_JITTER = 0.80      # how far off its cell centre a sparkle may sit, 0 = a rigid grid
STAR_SKIP = 0.14        # share of cells left empty, so the grid never shows through
STAR_KINDS = [('small', 0.40), ('medium', 0.35), ('large', 0.25)]
GLINT_CLEAR = 12.0      # keep sparkles this far away from the globe's own specular highlight
EDGE_CLEAR = 0.70       # sparkle centres stay inside this share of the globe radius, so that no
                        # star is cut in half by the rim or crowds the panel's stone frame

# 8x8 rather than 4x4: 64 thresholds instead of 16, so the dither density can follow the gradient
# closely enough that no repeat of the pattern is visible at the size the globe is drawn
BAYER8 = [[0, 32, 8, 40, 2, 34, 10, 42],
          [48, 16, 56, 24, 50, 18, 58, 26],
          [12, 44, 4, 36, 14, 46, 6, 38],
          [60, 28, 52, 20, 62, 30, 54, 22],
          [3, 35, 11, 43, 1, 33, 9, 41],
          [51, 19, 59, 27, 49, 17, 57, 25],
          [15, 47, 7, 39, 13, 45, 5, 37],
          [63, 31, 55, 23, 61, 29, 53, 21]]

# What a sparkle is made of: (dy, dx, dim), dim being steps down STAR_LEVELS from the core.
# A bright centre with four short rays fading out from it - the shape of a star glint rather than
# a round dot.  All three sizes are small: at 1x the globe is 88 px across, so a star wider than
# five pixels stops reading as a glint in the liquid and starts reading as a drawn object.  The
# difference between the sizes is mostly how far the rays fade out, not how far they reach.
SHAPES = {
    'small': [      # 5px cross, one pixel of ray each way
        [           (-1, 0, 2),
         (0, -1, 2), (0, 0, 0), (0, 1, 2),
                    (1, 0, 2)],
    ],
    'medium': [     # the same cross with its arms one step brighter, so it carries a little more
        [           (-1, 0, 1),
         (0, -1, 1), (0, 0, 0), (0, 1, 1),
                    (1, 0, 1)],
    ],
    'large': [      # 9px cross; the outer ray pixel is dimmed almost to the body, so it reads as
                    # a faint halo on a five-pixel star rather than as a nine-pixel one
        [           (-2, 0, 5),
                    (-1, 0, 1),
         (0, -2, 5), (0, -1, 1), (0, 0, 0), (0, 1, 1), (0, 2, 5),
                    (1, 0, 1),
                    (2, 0, 5)],
    ],
}


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
    """Deterministic noise in [0,1), so the asset rebuilds byte for byte."""
    h = (a * 73856093) ^ (b * 19349663) ^ (salt * 83492791)
    h &= 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 1274126177) & 0xFFFFFFFF
    h ^= h >> 16
    return h / 0x100000000


def pick(table, roll):
    """Choose from [(value, share), ...] with a roll in [0,1)."""
    acc = 0.0
    for value, share in table:
        acc += share
        if roll < acc:
            return value
    return table[-1][0]


def weighted_dist(entry, r, g, b):
    """Palette distance weighted to match the way the eye reads these colours, not raw RGB."""
    return 2.0 * (entry[0] - r) ** 2 + 4.0 * (entry[1] - g) ** 2 + 3.0 * (entry[2] - b) ** 2


def load_pal(path):
    d = open(path, 'rb').read()
    return [tuple(d[i * 3:i * 3 + 3]) for i in range(256)]


def main():
    if len(sys.argv) not in (5, 6):
        print(__doc__)
        return 1
    panel_path, bulbs_path, pal_path, out_path = sys.argv[1:5]
    mask_path = sys.argv[5] if len(sys.argv) == 6 else None
    pal = load_pal(pal_path)

    def lum(i):
        r, g, b = pal[i]
        return 0.299 * r + 0.587 * g + 0.114 * b

    data = bytearray(open(panel_path, 'rb').read())
    panel, pos = parse_cel(bytes(data), FRAME, PANEL_W, PANEL_H)
    bulb, _ = parse_cel(open(bulbs_path, 'rb').read(), 2, GLOBE_W, GLOBE_H)

    globe = [[panel[y][x + GLOBE_X] for x in range(GLOBE_W)] for y in range(GLOBE_H)]
    liquid = [(y, x) for y in range(GLOBE_H) for x in range(GLOBE_W)
              if globe[y][x] is not None and globe[y][x] != bulb[y][x]]
    # Everything that decides *where* a sparkle may go comes from one panel, so that a scatter
    # chosen on one globe reproduces pixel for pixel on another.  That is the mask panel when one
    # is given, and the panel being written otherwise.
    if mask_path:
        mpanel, _ = parse_cel(open(mask_path, 'rb').read(), FRAME, PANEL_W, PANEL_H)
        place = [[mpanel[y][x + GLOBE_X] for x in range(GLOBE_W)] for y in range(GLOBE_H)]
        print('sparkle placement masked by %s' % os.path.basename(mask_path))
    else:
        place = globe
    place_liquid = [(y, x) for y in range(GLOBE_H) for x in range(GLOBE_W)
                    if place[y][x] is not None and place[y][x] != bulb[y][x]]
    body = set((y, x) for y, x in place_liquid if place[y][x] in BODY_INDICES)

    cx, cy, radius = (GLOBE_W - 1) / 2.0, (GLOBE_H - 1) / 2.0, GLOBE_W / 2.0
    # the globe's own specular highlight: the brightest liquid pixels well inside the globe (the
    # rim is excluded because the panel's stone frame bleeds into the mask there)
    glint = [(y, x) for y, x in place_liquid
             if lum(place[y][x]) > 100 and ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 < radius * 0.6]
    if not glint:
        raise SystemExit('could not find the specular highlight - check BODY_INDICES / the panel')
    gy = sum(y for y, x in glint) / len(glint)
    gx = sum(x for y, x in glint) / len(glint)
    print('globe centre (%.1f,%.1f) r=%.1f, highlight at (%.1f,%.1f) from %d px'
          % (cy, cx, radius, gy, gx, len(glint)))

    # --- the body: its own colours, blurred, lifted, matched back to the palette ---
    # only body pixels feed the average, so neither the specular highlight nor the stone frame
    # bleeds into the liquid
    level = {}
    if not REPAINT_BODY:
        # The liquid is already how it should be - painted by tools/paint_mana_globe_cel.py, most
        # likely.  level[] is then only what the sparkles measure themselves against, so that no
        # ray comes out darker than the paint it crosses.
        for y, x in body:
            level[(y, x)] = globe[y][x]
    reach = int(BODY_BLUR) + 1
    taps = [(dy, dx) for dy in range(-reach, reach + 1) for dx in range(-reach, reach + 1)
            if (dy * dy + dx * dx) ** 0.5 <= BODY_BLUR]
    # the body's own mean colour, which BODY_CONTRAST pushes every pixel away from
    mean = [sum(pal[globe[y][x]][c] for y, x in body) / float(len(body)) for c in range(3)]
    meanlum = 0.299 * mean[0] + 0.587 * mean[1] + 0.114 * mean[2]
    for y, x in (body if REPAINT_BODY else ()):
        r = g = b = 0.0
        n = 0
        for dy, dx in taps:
            p = (y + dy, x + dx)
            if p in body:
                pr, pg, pb = pal[globe[p[0]][p[1]]]
                r += pr
                g += pg
                b += pb
                n += 1
        r, g, b = r / n, g / n, b / n
        # one factor for the whole pixel, blended on luminance, so the push never shifts the hue
        t = (0.299 * r + 0.587 * g + 0.114 * b - meanlum) / BODY_CONTRAST_BAND + 0.5
        t = max(0.0, min(1.0, t))
        t = t * t * (3.0 - 2.0 * t)     # smoothstep, so the crossover has no corners in it
        k = BODY_CONTRAST_SHADOW + (BODY_CONTRAST_LIT - BODY_CONTRAST_SHADOW) * t
        r = mean[0] + (r - mean[0]) * k
        g = mean[1] + (g - mean[1]) * k
        b = mean[2] + (b - mean[2]) * k
        r, g, b = max(0.0, r) * BODY_GAIN, max(0.0, g) * BODY_GAIN, max(0.0, b) * BODY_GAIN * BODY_BLUE
        # Find the entry nearest the target and then its better-placed neighbour on the ramp, and
        # work out where between the two the target actually falls.  That fraction is the share of
        # pixels the darker of the pair should take, which the ordered threshold then delivers.
        ranked = sorted(range(len(BODY_PALETTE)), key=lambda j: weighted_dist(pal[BODY_PALETTE[j]],
                                                                             r, g, b))
        j0 = ranked[0]
        j1 = min((j for j in (j0 - 1, j0 + 1) if 0 <= j < len(BODY_PALETTE)),
                 key=lambda j: weighted_dist(pal[BODY_PALETTE[j]], r, g, b), default=j0)
        a, c = pal[BODY_PALETTE[j0]], pal[BODY_PALETTE[j1]]
        seg = [c[i] - a[i] for i in range(3)]
        span = sum(v * v for v in seg)
        if span:
            share = ((r - a[0]) * seg[0] + (g - a[1]) * seg[1] + (b - a[2]) * seg[2]) / span
        else:
            share = 0.0
        share = max(0.0, min(1.0, share))
        # crossfade between a hard match (flat bands) and a fully dithered one
        hard = 1.0 if share > 0.5 else 0.0
        share = hard + (share - hard) * BODY_DITHER
        threshold = (BAYER8[y & 7][x & 7] + 0.5 + (rnd(x, y, 31) - 0.5) * BODY_DITHER_JITTER) / 64.0
        level[(y, x)] = BODY_PALETTE[j1] if share > threshold else BODY_PALETTE[j0]

    # --- the sparkles: one per jittered grid cell ---
    def sr(a, b, salt):
        return rnd(a, b, salt + STAR_SEED * 1009)

    stars = {}
    placed, kinds_used = 0, {}
    for gyi in range(int(GLOBE_H / STAR_CELL) + 1):
        for gxi in range(int(GLOBE_W / STAR_CELL) + 1):
            if sr(gxi, gyi, 7) < STAR_SKIP:
                continue
            jy = (sr(gxi, gyi, 11) - 0.5) * STAR_JITTER * STAR_CELL
            jx = (sr(gxi, gyi, 13) - 0.5) * STAR_JITTER * STAR_CELL
            sy = int(round((gyi + 0.5) * STAR_CELL + jy))
            sx = int(round((gxi + 0.5) * STAR_CELL + jx))
            if (sy, sx) not in body:
                continue
            if ((sx - gx) ** 2 + (sy - gy) ** 2) ** 0.5 <= GLINT_CLEAR:
                continue
            # measured from the globe's geometric centre, not the highlight, so the margin the
            # sparkles keep from the rim is even all the way round
            if ((sx - cx) ** 2 + (sy - cy) ** 2) ** 0.5 > radius * EDGE_CLEAR:
                continue
            kind = pick(STAR_KINDS, sr(gxi, gyi, 17))
            shape = SHAPES[kind][int(sr(gxi, gyi, 19) * len(SHAPES[kind])) % len(SHAPES[kind])]
            core = pick(STAR_CORE, sr(gxi, gyi, 23))
            drawn = 0
            for oy, ox, dim in shape:
                p = (sy + oy, sx + ox)
                if p not in body:
                    continue
                want = STAR_LEVELS[min(core + dim, len(STAR_LEVELS) - 1)]
                # a ray must never come out darker than the liquid it crosses
                if lum(want) <= lum(level[p]):
                    continue
                if p not in stars or lum(want) > lum(stars[p]):
                    stars[p] = want
                drawn += 1
            if drawn:
                placed += 1
                kinds_used[kind] = kinds_used.get(kind, 0) + 1

    # --- write ---
    patched, blocked = 0, 0
    for p in body:
        y, x = p
        if not REPAINT_BODY and p not in stars:
            continue
        new = stars.get(p, level[p])
        if new == bulb[y][x]:       # would stop counting as liquid - leave the pixel alone
            blocked += 1
            continue
        if new != globe[y][x]:
            data[pos[y][x + GLOBE_X]] = new
            patched += 1

    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    open(out_path, 'wb').write(bytes(data))
    print('wrote %s (%d bytes)' % (out_path, len(data)))
    print('  body %d px, repainted %d, skipped %d (would clash with the bulb)'
          % (len(body), patched, blocked))
    print('  %d sparkles over %d px (%.1f%% of the body), %s'
          % (placed, len(stars), 100.0 * len(stars) / len(body),
             ', '.join('%s x%d' % (k, n) for k, n in sorted(kinds_used.items()))))

    check, _ = parse_cel(bytes(data), FRAME, PANEL_W, PANEL_H)
    still = [(y, x) for y in range(GLOBE_H) for x in range(GLOBE_W)
             if check[y][x + GLOBE_X] is not None and check[y][x + GLOBE_X] != bulb[y][x]]
    print('  verify: liquid mask %d px (was %d) - %s'
          % (len(still), len(liquid), 'OK' if len(still) == len(liquid) else 'CHANGED, check this'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
