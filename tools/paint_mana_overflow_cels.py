"""Paints the three overflow mana globes (X\\panel\\front_panel_mana_ovf1..3.cel, 13cirlces.MPQ).

A Master Caster can carry mana above his maximum, and each further full bar refills the globe in a
different liquid.  Those three fillings used to be the main globe recoloured through a .trn; they
are now globes in their own right, painted by the same light as the main one (the shading model is
imported from tools/paint_mana_globe_cel.py, so all four are the same sphere) but in their own
colours, and each carries three more sparkles than the one below it.

  ovf1  100-200%   midnight, the main globe's blue sinking into dark blue-grey
  ovf2  200-300%   bright azure, the blue made lighter and glowing, with a bright lower-left rim
  ovf3  300-400%   gold, the colour of the rejuvenation potion's liquid, with a soft halo rim

The sparkles are cumulative: ovf1 is the main globe's twelve plus three small new ones, ovf2 keeps
all fifteen of those and adds three, ovf3 keeps all eighteen and adds three more.  Each pass runs
tools/make_mana_globe_stars_cel.py with the placement masked by the untouched original panel, so
the twelve inherited ones land exactly where they do on the main globe.

THE PALETTE HAS NO IN-BETWEEN HUES.  Entries 128-255, the only ones panel art may use, hold blue,
red, yellow, orange, rose-brown, blue-grey, gold-tan, orange-tan, pink-red and grey ramps - no
violet, green or cyan.  A colour that falls between ramps has to be mixed on the screen rather than
chosen: the quantiser below searches every *pair* of candidate entries for the blend that best
matches the target colour and dithers between the two.  Midnight uses it to sink the
blue ramp into the dark blue-grey.  (ovf1 used to be a violet mixed from blue and red; up close
that dither read as noise, which is why it became a darker blue-grey.)  That is also why this file
cannot reuse the main painter's matcher, which walks a single ordered ramp and assumes its
neighbours are the nearest colours.

usage: python tools/paint_mana_overflow_cels.py <panel.cel> <P8Bulbs.CEL> <palette.pal> <out-dir> [png-dir]
"""
import contextlib
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_mana_globe_stars_cel as stars
import paint_mana_globe_cel as orb

PANEL_W, PANEL_H = 640, 144
GLOBE_X, GLOBE_W, GLOBE_H = 464, 88, 88
FRAME = 1

# The engine fills the globe from a 88x88 window at GLOBE_X, but the panel art's globe is a pixel
# wider than that: column 463 carries its left rim for rows 41-51.  The main globe never notices,
# because that column is blue there and so is the liquid; an overflow filling that stops at 464
# leaves it behind as a blue sliver down the left.  So the painting window starts one column early.
PAINT_X = GLOBE_X - 1
PAINT_W = GLOBE_W + 1
BLUE_RAMP = range(128, 136)

# The globe shape is taken from the panel the engine actually loads (ModManaGlobePanelCel in
# Panel.cpp), not from the panel being painted over.  The engine cuts each overflow globe out along
# the shape it finds in that panel; front_panel_mana_blue.cel paints much of its liquid in the
# blue-grey ramp, so a shape found there is smaller and would leave slivers of the blue globe showing.
SHAPE_PANEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir,
                           'res', '13cirlces', 'X', 'panel', 'front_panel_mana_stars.cel')

# The sparkle scatter the main globe ships with, reproduced here so the inherited twelve match it.
BASE_STAR_SEED = 2
BASE_STAR_CELL = 15.0

# Each overflow level adds three sparkles.  A separate seed per level, and a finer grid so there
# are enough candidate cells left once the ones already taken are excluded.
EXTRA_SEEDS = [21, 22, 23]
EXTRA_CELL = 8.0
EXTRA_PER_LEVEL = 3

#   key     name                       exposure  the families the quantiser may mix
TONES = [
    ('ovf1', 'midnight', dict(
        # The first bar of overflow is a new mechanic, so it stays close to the blue liquid of the
        # main globe - the blue sinking into the dark end of the blue-grey ramp, darker and greyer,
        # which is enough to read as "more mana than the globe holds".  Only the darker blue
        # entries are offered, so the quantiser cannot pull it back to plain blue.  Violet was
        # tried first; this palette has no violet, and the blue/red dither it had to be mixed from
        # looked like noise next to the blue.
        tint=(0.08, 0.10, 0.58), glow=(0.20, 0.26, 0.72), exposure=0.80,
        palette=list(range(130, 136)) + list(range(184, 192)),
        star_levels=[255, 240, 241, 128, 176, 129],
        dither=0.60, pair_penalty=0.012,
    )),
    ('ovf2', 'bright azure', dict(
        # The same blue again, now lighter and glowing: it climbs out of the dark midnight below
        # it, so the step reads as the liquid charging up rather than changing substance.  The
        # pale end of the blue-grey ramp is mixed in for the glow, since the blue ramp's own light
        # entries are too few to carry it.
        # Its glass also catches far more light than the other globes: a thick bright rim hugging
        # the lower-left limb, the side facing away from the key, to balance the glare coils the
        # key light already draws in the upper right.
        light=dict(RIM=1.30, RIM_POW=2.0, RIM_BIAS=0.95, BOUNCE=0.22),
        tint=(0.10, 0.22, 1.00), glow=(0.55, 0.62, 1.00), exposure=1.10,
        palette=list(range(128, 136)) + list(range(176, 180)),
        star_levels=[255, 240, 241, 242, 176, 128],
        dither=0.60, pair_penalty=0.012,
    )),
    ('ovf3', 'gold', dict(
        # the yellow ramp 144-151, which is what the rejuvenation potion's own liquid is painted in
        # A softer relative of the azure's glass rim, running all round the glass instead of only
        # the lower left, so the last globe reads as a glowing golden bubble.
        light=dict(RIM=0.95, RIM_POW=2.5, RIM_BIAS=0.45, BOUNCE=0.22),
        tint=(1.00, 0.94, 0.10), glow=(1.00, 0.90, 0.35), exposure=1.05,
        palette=list(range(144, 152)) + list(range(192, 208)) + list(range(152, 160)),
        star_levels=[144, 145, 146, 147, 148, 149],
        dither=0.60, pair_penalty=0.014,
    )),
]

# How far the nacre hue swings, and how fast it cycles around and across the globe.
IRIDESCENCE = 0.80
IRIDESCENCE_TURNS = 1.60
IRIDESCENCE_RADIAL = 2.40

DITHER_JITTER = 16.0


def weighted(a, b):
    return 2.0 * (a[0] - b[0]) ** 2 + 4.0 * (a[1] - b[1]) ** 2 + 3.0 * (a[2] - b[2]) ** 2


class PairMatcher:
    """Finds the two palette entries whose blend best matches a colour, and how to mix them.

    Returns (index_a, index_b, share_of_b).  Results are cached on the target rounded to 4 units,
    because the search is O(pairs) and the globe asks for the same colours over and over.
    """

    def __init__(self, pal, palette, penalty):
        self.pal = pal
        self.entries = [(i, pal[i]) for i in palette]
        self.penalty = penalty
        self.cache = {}

    def __call__(self, want):
        key = (int(want[0]) >> 2, int(want[1]) >> 2, int(want[2]) >> 2)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        best, bestd = None, None
        for ai, (ia, ca) in enumerate(self.entries):
            for ib, cb in self.entries[ai:]:
                seg = (cb[0] - ca[0], cb[1] - ca[1], cb[2] - ca[2])
                span = seg[0] ** 2 + seg[1] ** 2 + seg[2] ** 2
                if span:
                    t = ((want[0] - ca[0]) * seg[0] + (want[1] - ca[1]) * seg[1]
                         + (want[2] - ca[2]) * seg[2]) / span
                    t = max(0.0, min(1.0, t))
                else:
                    t = 0.0
                mix = (ca[0] + seg[0] * t, ca[1] + seg[1] * t, ca[2] + seg[2] * t)
                d = weighted(mix, want)
                # A mix of two very different colours only averages out at a distance; up close it
                # is visible as speckle.  This penalty leans toward pairs that sit near each other,
                # and has to be small for any tone whose whole point is mixing across the wheel.
                d += self.penalty * span * t * (1.0 - t)
                if bestd is None or d < bestd:
                    best, bestd = (ia, ib, t), d
        self.cache[key] = best
        return best


@contextlib.contextmanager
def lighting(overrides):
    """Overrides the shading constants of paint_mana_globe_cel (RIM, BOUNCE, ...) for one tone.

    All four globes share that lighting model, so a tone that wants its own light sets a `light`
    dict in its TONES entry and gets it only while it is being painted.
    """
    for name in overrides:
        if not hasattr(orb, name):
            raise KeyError('paint_mana_globe_cel has no lighting constant %s' % name)
    saved = {name: getattr(orb, name) for name in overrides}
    for name, value in overrides.items():
        setattr(orb, name, value)
    try:
        yield
    finally:
        for name, value in saved.items():
            setattr(orb, name, value)


def hue_shift(rgb, turn, amount):
    """Rotate a colour's hue, cheaply, around the grey axis - enough for a nacre sheen."""
    r, g, b = rgb
    grey = (r + g + b) / 3.0
    cos, sin = math.cos(turn), math.sin(turn)
    # rotation of the (r,g,b) vector about (1,1,1), linearised
    k = 1.0 / 3.0 * (1.0 - cos)
    s = sin / math.sqrt(3.0)
    m = ((cos + k, k - s, k + s), (k + s, cos + k, k - s), (k - s, k + s, cos + k))
    out = [sum(m[i][j] * (rgb[j] - grey) for j in range(3)) + grey for i in range(3)]
    return [rgb[i] + (out[i] - rgb[i]) * amount for i in range(3)]


def globe_shape(globe):
    """Which pixels of the painting window are the round globe rather than the frame around it.

    Differing from the empty bulb is not enough: P8Bulbs.CEL carries Diablo's own frame, and where
    this panel's frame differs from it - most of the bottom right corner - that test calls the frame
    liquid, and the corner came out painted as a square of liquid.  The same rule as
    BuildManaGlobeShape in Panel.cpp: the largest 4-connected patch of the blue ramp, widened to
    everything between its outermost pixels along both the row and the column, which closes the holes
    left by sparkles and the figure while stray blue specks in the frame stay outside.
    """
    h, w = len(globe), len(globe[0])
    patch = [[0] * w for _ in range(h)]
    best, best_size, patches = 0, 0, 0
    for sy in range(h):
        for sx in range(w):
            if patch[sy][sx] or globe[sy][sx] not in BLUE_RAMP:
                continue
            patches += 1
            patch[sy][sx] = patches
            pending, size = [(sy, sx)], 0
            while pending:
                y, x = pending.pop()
                size += 1
                for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if (0 <= ny < h and 0 <= nx < w and not patch[ny][nx]
                            and globe[ny][nx] in BLUE_RAMP):
                        patch[ny][nx] = patches
                        pending.append((ny, nx))
            if size > best_size:
                best, best_size = patches, size
    rows = [[x for x in range(w) if patch[y][x] == best] for y in range(h)]
    cols = [[y for y in range(h) if patch[y][x] == best] for x in range(w)]
    return [[bool(rows[y] and cols[x] and rows[y][0] <= x <= rows[y][-1]
                  and cols[x][0] <= y <= cols[x][-1]) for x in range(w)] for y in range(h)]


def paint(panel_path, bulbs_path, pal_path, out_path, spec, shape):
    pal = orb.load_pal(pal_path)
    data = bytearray(open(panel_path, 'rb').read())
    panel, pos = orb.parse_cel(bytes(data), FRAME, PANEL_W, PANEL_H)
    bulb, _ = orb.parse_cel(open(bulbs_path, 'rb').read(), 2, GLOBE_W, GLOBE_H)

    # Painting window coordinates: x is an offset from PAINT_X, so x-1 indexes the 88-wide bulb.
    globe = [[panel[y][x + PAINT_X] for x in range(PAINT_W)] for y in range(GLOBE_H)]

    def is_liquid(y, x):
        v = globe[y][x]
        if v is None or not v or not shape[y][x]:
            return False
        if x == 0:                      # the extra rim column, which the bulb graphic does not reach
            return v in BLUE_RAMP
        # A handful of pixels near the figure at the bottom of the globe are painted in exactly the
        # colour the empty bulb has there, so the usual "differs from the bulb" test drops them and
        # they would stay blue.  They are globe art all the same - being on the blue ramp says so.
        return v != bulb[y][x - 1] or v in BLUE_RAMP

    liquid = [(y, x) for y in range(GLOBE_H) for x in range(PAINT_W) if is_liquid(y, x)]

    cy, cx, radius = (GLOBE_H - 1) / 2.0, (GLOBE_W - 1) / 2.0 + 1.0, GLOBE_W / 2.0
    match = PairMatcher(pal, spec['palette'], spec.get('pair_penalty', 0.012))
    dither = spec.get('dither', 0.6)
    tint, glow, exposure = spec['tint'], spec['glow'], spec['exposure']

    # Every pixel of the liquid mask gets painted, with no exceptions.  The main globe's painter
    # may leave a pixel alone, because the panel underneath it is that same globe; here the panel
    # underneath is the *blue* globe and an overflow filling is drawn on top of it, so anything
    # left unpainted shows up as blue sticking out past the edge of the overflow liquid.
    patched, clamped, collisions, used = 0, 0, 0, {}
    for y, x in liquid:
        nx, ny = (x - cx) / radius, (y - cy) / radius
        r = math.hypot(nx, ny)
        if r > 1.0:             # the joint with the stone frame - shaded as if on the limb
            clamped += 1
            r = 1.0
        lit, reflect = orb.shade(nx, ny, r)

        want = [255.0 * exposure * lit * (tint[c] + glow[c] * lit) for c in range(3)]
        if spec.get('iridescent'):
            turn = (math.atan2(ny, nx) * IRIDESCENCE_TURNS + r * IRIDESCENCE_RADIAL)
            want = hue_shift(want, turn, IRIDESCENCE)
        for c in range(3):
            want[c] += 255.0 * reflect
        want = [max(0.0, min(255.0, v)) for v in want]

        ia, ib, share = match(want)
        hard = 1.0 if share > 0.5 else 0.0
        share = hard + (share - hard) * dither
        t = (orb.BAYER8[y & 7][x & 7] + 0.5
             + (orb.rnd(x, y, 31) - 0.5) * DITHER_JITTER) / 64.0
        new = ib if share > t else ia

        under = bulb[y][x - 1] if x else None
        if new == under:
            # This index would make the engine stop counting the pixel as liquid and the globe
            # would show a hole. Take the other half of the dither pair, or failing that the
            # closest entry in this tone that is not the bulb's colour - never leave it unpainted.
            alt = ib if new == ia else ia
            if alt == under:
                alt = min((i for i in spec['palette'] if i != under),
                          key=lambda i: weighted(pal[i], want))
            new = alt
            collisions += 1
        used[new] = used.get(new, 0) + 1
        if new != globe[y][x]:
            data[pos[y][x + PAINT_X]] = new
            patched += 1

    open(out_path, 'wb').write(bytes(data))
    top = sorted(used.items(), key=lambda kv: -kv[1])[:6]
    print('  painted %d of %d liquid px (%d on the frame joint, %d bulb clashes resolved)'
          % (patched, len(liquid), clamped, collisions))
    print('  top tones %s' % ', '.join('%d x%d' % kv for kv in top))
    return len(liquid)


def scatter(panel_path, bulbs_path, pal_path, out_path, mask_path, seed, cell,
            levels, limit=0, exclude=(), force_kind=None):
    """One sparkle pass over an already painted globe.  Returns the placements it made."""
    stars.REPAINT_BODY = False
    stars.STAR_SEED = seed
    stars.STAR_CELL = cell
    stars.STAR_LEVELS = levels
    stars.STAR_LIMIT = limit
    stars.STAR_EXCLUDE = list(exclude)
    stars.STAR_FORCE_KIND = force_kind
    argv = sys.argv
    sys.argv = ['x', panel_path, bulbs_path, pal_path, out_path, mask_path]
    try:
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            stars.main()
    finally:
        sys.argv = argv
        stars.STAR_LIMIT, stars.STAR_EXCLUDE, stars.STAR_FORCE_KIND = 0, [], None
    return list(stars.LAST_PLACEMENTS)


def render(cel_path, pal_path, png_dir, key, label):
    from PIL import Image, ImageDraw
    pal = orb.load_pal(pal_path)
    rows, _ = orb.parse_cel(open(cel_path, 'rb').read(), FRAME, PANEL_W, PANEL_H)
    tile = Image.new('RGB', (GLOBE_W, GLOBE_H), (0, 0, 0))
    px = tile.load()
    for y in range(GLOBE_H):
        for x in range(GLOBE_W):
            v = rows[y][x + GLOBE_X]
            px[x, y] = (0, 0, 0) if v is None else pal[v]
    os.makedirs(png_dir, exist_ok=True)
    scales = (1, 2, 4)
    ims = [tile.resize((GLOBE_W * s, GLOBE_H * s), Image.NEAREST) for s in scales]
    pad, lbl = 10, 16
    sheet = Image.new('RGB', (pad + sum(im.width + pad for im in ims),
                              lbl + max(im.height for im in ims) + pad), (22, 22, 26))
    draw = ImageDraw.Draw(sheet)
    draw.text((pad, 3), '%s - %s   1x / 2x / 4x' % (key, label), fill=(205, 205, 215))
    at = pad
    for im in ims:
        sheet.paste(im, (at, lbl + 4))
        at += im.width + pad
    sheet.save(os.path.join(png_dir, '%s_%s.png' % (key, label.replace('-', '_'))))
    ims[-1].save(os.path.join(png_dir, '%s.png' % key))
    return tile


def main():
    if len(sys.argv) not in (5, 6):
        print(__doc__)
        return 1
    panel_path, bulbs_path, pal_path, out_dir = sys.argv[1:5]
    png_dir = sys.argv[5] if len(sys.argv) == 6 else None
    os.makedirs(out_dir, exist_ok=True)
    shape_panel, _ = orb.parse_cel(open(SHAPE_PANEL, 'rb').read(), FRAME, PANEL_W, PANEL_H)
    shape = globe_shape([[shape_panel[y][x + PAINT_X] for x in range(PAINT_W)]
                         for y in range(GLOBE_H)])

    # Every sparkle pass ever run, as (seed, cell, limit, keep-away list, forced size).  Each
    # overflow level repaints its globe from scratch, so it replays all of them in its own colours
    # before adding its own - which is what makes the inherited sparkles land in identical places.
    passes = [(BASE_STAR_SEED, BASE_STAR_CELL, 0, [], None)]
    tiles = []
    for level, (key, label, spec) in enumerate(TONES):
        out = os.path.join(out_dir, 'front_panel_mana_%s.cel' % key)
        print('%s  %s' % (key, label))
        with lighting(spec.get('light', {})):
            paint(panel_path, bulbs_path, pal_path, out, spec, shape)

        positions = []
        for seed, cell, limit, exclude, kind in passes:
            got = scatter(out, bulbs_path, pal_path, out, panel_path, seed, cell,
                          spec['star_levels'], limit, exclude, kind)
            positions += [(y, x) for y, x, _kind in got]
        print('  %d sparkles carried over' % len(positions))

        fresh = (EXTRA_SEEDS[level], EXTRA_CELL, EXTRA_PER_LEVEL, list(positions),
                 'small' if level == 0 else None)
        got = scatter(out, bulbs_path, pal_path, out, panel_path, fresh[0], fresh[1],
                      spec['star_levels'], fresh[2], fresh[3], fresh[4])
        passes.append(fresh)
        positions += [(y, x) for y, x, _kind in got]
        print('  +%d new -> %d sparkles total' % (len(got), len(positions)))

        if png_dir:
            tiles.append((key, label, render(out, pal_path, png_dir, key, label)))

    if png_dir and tiles:
        from PIL import Image, ImageDraw
        s, pad, lbl = 4, 10, 16
        sheet = Image.new('RGB', (pad + len(tiles) * (GLOBE_W * s + pad),
                                  lbl + GLOBE_H * s + pad + lbl), (22, 22, 26))
        draw = ImageDraw.Draw(sheet)
        draw.text((pad, 3), 'mana globe overflow levels, 4x', fill=(205, 205, 215))
        for i, (key, label, tile) in enumerate(tiles):
            at = pad + i * (GLOBE_W * s + pad)
            sheet.paste(tile.resize((GLOBE_W * s, GLOBE_H * s), Image.NEAREST), (at, lbl + 4))
            draw.text((at, lbl + 8 + GLOBE_H * s), '%s  %s' % (key, label), fill=(235, 235, 235))
        sheet.save(os.path.join(png_dir, 'sheet_overflow_levels.png'))
        print('\nwrote PNGs to %s' % png_dir)
    return 0


if __name__ == '__main__':
    sys.exit(main())
