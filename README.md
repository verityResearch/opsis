# opsis

**Time laid out as space, for a reader that perceives images but cannot parse them.**

`ROAM/1 opsis` is a format for showing a language model what changed across a span of
time — as one tiled image plus a plain-text manifest.

It exists because of a specific, measurable property of its reader. A model receives a
rendered image through a vision encoder: spatial layout survives that stage intact,
while exact values do not. You can show it a picture and it will read the arrangement;
you cannot hide a number in the pixels and expect it back.

That constraint rules out most of how machine-readable imagery is normally done, and it
suggests something else instead.

## The idea

A model has no continuous present. It cannot watch. Frames over time are therefore the
wrong medium twice over — expensive (each image costs ~1,500 tokens whether it carries
much or little) and unwatchable.

So instead of frames over time, lay **time out as space**: one image, tiled in reading
order, one tile per moment.

|  | cost | what it answers |
|---|---|---|
| 8 stereo pairs of a span | ~24,000 tokens | everything, unwatchably |
| one 2×2 opsis | ~1,500 tokens | *what changed, and in what shape* |

A 2×2 sheet of 320×180 tiles is exactly the pixel budget of a single 640×360 look. That
makes the trade legible: **one look's worth of attention, spent on four moments instead
of one.**

## What it makes visible

Four things that are near-indistinguishable as tables of numbers, and obvious at a glance
as a sheet:

- **a mover crossing** — a streak walking across tiles
- **the observer turning** — the whole field sliding, nothing moving against it
- **approach** — something growing in place
- **a static span** — tiles differing only by parallax

`examples/approach-L.jpg` is a real four-mark walk: a tree small and off-centre in the
first tile, dominating the frame by the fourth, while the mound behind it holds constant.
That is approach, read without a single number.

## What it is *not*

**Not a substitute for looking.** Two full-resolution looks cost ~3,000 tokens and carry
bark grain and leaf veins. A four-tile sheet costs ~1,500 and carries none of that — each
tile arrives at a quarter of a look's resolution before the encoder even sees it. Reaching
for an opsis to *see* a place is the wrong tool. It answers one question: what changed.

## Three rules, each one earned

**1. Nothing is encoded into pixels.**
An earlier version marked unmeasurable frames by dimming and cross-ruling them —
destroying frame content to carry one bit that was already in the manifest. Data in
pixels is invisible to this reader by construction. Frames are shown unaltered or not
shown at all; every qualification lives in the text.

**2. Sampled by travel, not by time.**
On a real walk — 4.9 m covered, then two seconds standing still — an even time sample
produced two informative tiles and seven identical ones. Seven-ninths of the budget spent
on a stationary body. `SelectByTravel` walks the path's arc length and stops at roughly
equal displacement, so a span that did not move produces **no sheet at all**:

> *not composed: only one distinct position in this span — nothing changed to have a
> shape.*

Declining to compose is a feature. A sheet of identical tiles looks like evidence.

**3. Ordering is the layout.**
Reading order, stated in the manifest — no burned-in ordinals, because a wrong glyph is
worse than a stated convention.

## Rotation

If the observer turned between marks, consecutive tiles show *different parts of the
world*, and apparent movement across them is partly the observer's own pivot. The
manifest says so explicitly above 8° rather than letting the sheet imply the world moved.

## Manifest

```
ROAM/1  opsis   (the shape of what happened — NOT a substitute for looking)
grid 2x2  tiles 320x180  4 frames  55 KB
reading order: left to right, top to bottom — the layout IS the ordering.
frames are UNALTERED; every qualification is here in text, never in pixels.
sampled at equal TRAVEL, so tiles are not equally spaced in time.
span 7.00 world-s, 5.98 m travelled, ~1.99 m per tile
  tile  0  +0.00s   start   (18.62,1.53,32.91)  yaw 150
  tile  1  +2.37s  +2.00m   (19.62,1.66,31.19)  yaw 150
  tile  2  +4.68s  +2.00m   (20.61,1.68,29.45)  yaw 150
  tile  3  +7.00s  +1.99m   (21.60,1.84,27.73)  yaw 150
```

## Usage

`opsis.py` is the format, and it is **standalone**: Python standard library only. No
engine, no imaging package, no build step. It writes the PNG by hand with `zlib`, takes
raw RGB buffers, and knows nothing about where frames came from.

```python
import opsis

tiles = [opsis.Tile(pixels=rgb_bytes, width=320, height=180,
                    elapsed=t, pos=(x, y, z), heading=deg)
         for ...]

out = opsis.compose(tiles)
if out.composed:
    open("opsis.png", "wb").write(out.png)
print(out.manifest)
```

Choose which frames to use first — sampled by travel, not time:

```python
keep = opsis.select_by_travel([t.pos for t in all_frames], max_tiles=4)
```

If it returns a single index, the observer never moved: **do not compose.** A grid of
identical tiles looks like evidence.

Prove it without any source of frames:

```
python3 opsis.py crossing     # also: sweep, approach, still
```

If those four are not distinguishable by eye in the output, the format has failed at the
only job it has. `examples/` holds two of them.

### Adapters

`adapters/` holds the original Unity implementation — the same format expressed against
`UnityEngine`, plus `OpsisCapture` for taking stereo marks during a walk. Adapters are
optional and none of them are the format. Anything that can produce raw RGB and a
position can drive `opsis.py` directly.

## Provenance

Built 2026-09-09/10 by cairn, in conversation with Tony, while giving a language model a
body to walk around in. The name is Greek: a **stigme** (στιγμή) is a point without
extension — one look; a **kairos** (καιρός) is a span of time as lived; an **opsis**
(ὄψις) is the *seeing* of it, Aristotle's word for the spectacle of a drama as distinct
from its structure.

The rest of that rig measured depth. This is the only part that showed *change* rather
than reporting it, which is why it survived.
