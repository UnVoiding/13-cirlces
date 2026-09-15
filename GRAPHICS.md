# GRAPHICS.md

This file provides guidance to Claude Code (claude.ai/code) when working with graphics, palettes, CEL files, etc.

## CEL and palette facts

- A CEL frame is a run-length stream: a byte `< 0x80` starts a literal run of that many raw palette
  indices; a byte `>= 0x80` skips `256 - byte` transparent pixels. Rows are stored bottom-up.
- Palette entries **128-255 are identical across 1084 of the 1113 `.pal` files** (29 differ, of which
  only `l0_dark04.pal` is a real level palette). Interface art uses only that upper half, which is why
  a single `.trn` or panel edit works on every level.
- The panel's mana globe occupies x 464-551, y 0-87 of frame 1, and the engine decides what counts as
  liquid by comparing the panel against `P8Bulbs.CEL` — so a repainted pixel must never equal the
  empty-bulb pixel underneath it or it silently drops out of the globe (`BuildManaOverflowGlobe`,
  `Panel.cpp`).
- "Differs from the bulb" alone also catches the stone frame, because `P8Bulbs.CEL` carries Diablo's
  own frame and this panel's differs from it (most of the bottom-right corner). Liquid is therefore
  also limited to the round globe shape found from the blue ramp (`BuildManaGlobeShape`, and
  `globe_shape` in `paint_mana_overflow_cels.py`), and the empty bulb's frame outside that shape is
  overwritten with the panel's so the corner no longer changes as mana drains.


## Panels

The mana globe panel has two authoring tools with different jobs:
`make_mana_globe_stars_cel.py` filters an existing globe and scatters sparkles over it, while
`paint_mana_globe_cel.py` paints a lit glass sphere from scratch. Both patch CEL bytes in place
rather than re-encoding — a CEL literal run stores raw palette indices, so overwriting one changes no
run lengths and no frame offsets.
