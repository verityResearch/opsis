#!/usr/bin/env python3
"""ROAM/1 opsis — time laid out as space.

A format for showing a language model what changed across a span of time, as one
tiled image plus a plain-text manifest.

Standalone by design: standard library only. No engine, no imaging package, no
build step. It takes raw pixel buffers and metadata and writes a PNG; it does not
know or care where the frames came from. Adapters for particular sources
(a game engine, a camera, a screen recorder) live outside this file.

Why it is shaped this way
-------------------------
The reader is a language model, and a model receives a rendered image through a
vision encoder. Spatial layout survives that stage intact; exact values do not.
You can show it an arrangement and it will read the arrangement. You cannot hide
a number in the pixels and expect it back.

A model also has no continuous present. It cannot watch. So frames-over-time is
the wrong medium twice over: unwatchable, and ~1,500 tokens per image whether the
image carries much or little.

Hence: lay time out AS SPACE. One image, tiled in reading order, one tile per
moment. A 2x2 sheet of 320x180 tiles is exactly the pixel budget of one 640x360
look — one look's worth of attention, spent on four moments instead of one.

Three rules, each earned by getting it wrong first
--------------------------------------------------
1. Nothing is encoded into pixels. An earlier version marked unmeasurable frames
   by dimming and cross-ruling them, destroying image content to carry one bit
   that was already in the manifest. Data in pixels is invisible to this reader
   by construction. Frames appear unaltered or not at all.

2. Sampled by travel, not by time. On a real walk — 4.9 m covered, then two
   seconds standing still — an even time sample produced two informative tiles
   and seven identical ones. `select_by_travel` stops at roughly equal
   displacement instead.

3. A span that did not move composes NO sheet. A grid of identical tiles looks
   like evidence. Declining is the honest output.
"""

from __future__ import annotations

import math
import struct
import zlib
from dataclasses import dataclass, field
from typing import Iterable, Sequence

__all__ = [
    "Tile", "Opsis", "select_by_travel", "grid_for", "compose", "write_png", "self_test",
]

VERSION = "ROAM/1"
RULE_PX = 2                     # separator thickness between tiles
RULE_RGB = (90, 90, 96)
MISSING_RGB = (24, 24, 28)      # a tile with no frame


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #

@dataclass
class Tile:
    """One moment. `pixels` is raw RGB, 3 bytes per pixel, row-major, TOP row first.

    Top-first is stated because it is the single convention most likely to be got
    backwards, and getting it backwards silently reverses time.
    """
    pixels: bytes | None
    width: int
    height: int
    elapsed: float = 0.0                    # seconds from span start
    pos: tuple[float, float, float] = (0.0, 0.0, 0.0)
    heading: float = 0.0                    # degrees
    note: str = ""


@dataclass
class Opsis:
    png: bytes
    manifest: str
    cols: int
    rows: int
    tile_w: int
    tile_h: int
    composed: bool = True
    reason: str = ""


# --------------------------------------------------------------------------- #
# selection
# --------------------------------------------------------------------------- #

def _dist(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def select_by_travel(positions: Sequence[Sequence[float]], max_tiles: int,
                     min_step: float = 0.15) -> list[int]:
    """Indices sampled at roughly equal DISPLACEMENT along the path.

    Equal-time sampling wastes the budget whenever the observer pauses: a span
    that walked then stopped yields a run of identical tiles. Equal-travel
    sampling spends tiles where something actually changed, and returns a single
    index when nothing moved at all — which callers should treat as "do not
    compose".
    """
    if not positions:
        return []
    chosen = [0]
    if len(positions) == 1 or max_tiles <= 1:
        return chosen

    total = sum(_dist(positions[i - 1], positions[i]) for i in range(1, len(positions)))
    if total < min_step:
        return chosen                                   # never really moved

    target = total / (max_tiles - 1)
    since = 0.0
    for i in range(1, len(positions)):
        if len(chosen) >= max_tiles:
            break
        since += _dist(positions[i - 1], positions[i])
        last = (i == len(positions) - 1)
        if since >= target - 1e-6 or (last and since >= min_step):
            chosen.append(i)
            since = 0.0
    return chosen


def grid_for(n: int) -> tuple[int, int]:
    """Reading-shaped, never a long strip: a 1xN row scales down to unreadable."""
    if n <= 1:
        return 1, 1
    if n == 2:
        return 2, 1
    cols = min(3, math.ceil(math.sqrt(n)))
    return cols, math.ceil(n / cols)


# --------------------------------------------------------------------------- #
# PNG, written by hand so nothing is imported
# --------------------------------------------------------------------------- #

def _chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def write_png(width: int, height: int, rgb: bytes, level: int = 6) -> bytes:
    """Minimal truecolour PNG. `rgb` is 3 bytes/px, row-major, top row first."""
    if len(rgb) != width * height * 3:
        raise ValueError(f"expected {width * height * 3} bytes, got {len(rgb)}")
    stride = width * 3
    raw = bytearray()
    for y in range(height):
        raw.append(0)                                   # filter: none
        raw += rgb[y * stride:(y + 1) * stride]
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(bytes(raw), level))
            + _chunk(b"IEND", b""))


# --------------------------------------------------------------------------- #
# composition
# --------------------------------------------------------------------------- #

def _blit(dst: bytearray, W: int, H: int, tile: Tile, x0: int, y0: int,
          tw: int, th: int) -> None:
    src, sw, sh = tile.pixels, tile.width, tile.height
    for y in range(th):
        for x in range(tw):
            if src is None:
                r, g, b = MISSING_RGB
            else:
                sx = x if sw == tw else min(sw - 1, x * sw // tw)
                sy = y if sh == th else min(sh - 1, y * sh // th)
                o = (sy * sw + sx) * 3
                r, g, b = src[o], src[o + 1], src[o + 2]
            d = ((y0 + y) * W + (x0 + x)) * 3
            dst[d], dst[d + 1], dst[d + 2] = r, g, b


def compose(tiles: Sequence[Tile], tile_w: int = 320, tile_h: int = 180,
            turn_threshold: float = 8.0) -> Opsis:
    """Build the sheet and the manifest that must travel with it."""
    if not tiles:
        return Opsis(b"", f"{VERSION}  opsis\n  unavailable: no frames",
                     0, 0, tile_w, tile_h, composed=False, reason="no frames")
    if len(tiles) == 1:
        msg = (f"{VERSION}  opsis\n  not composed: only one distinct position in this "
               "span — nothing changed to have a shape.")
        return Opsis(b"", msg, 0, 0, tile_w, tile_h, composed=False,
                     reason="single position")

    cols, rows = grid_for(len(tiles))
    W = cols * tile_w + (cols - 1) * RULE_PX
    H = rows * tile_h + (rows - 1) * RULE_PX

    buf = bytearray(bytes(RULE_RGB) * (W * H))          # rules show through the gaps
    for i, t in enumerate(tiles):
        c, r = i % cols, i // cols
        _blit(buf, W, H, t, c * (tile_w + RULE_PX), r * (tile_h + RULE_PX), tile_w, tile_h)

    png = write_png(W, H, bytes(buf))
    return Opsis(png, _manifest(tiles, cols, rows, tile_w, tile_h, len(png), turn_threshold),
                 cols, rows, tile_w, tile_h)


def _manifest(tiles: Sequence[Tile], cols: int, rows: int, tw: int, th: int,
              nbytes: int, turn_threshold: float) -> str:
    span = tiles[-1].elapsed - tiles[0].elapsed
    dist = sum(_dist(tiles[i - 1].pos, tiles[i].pos) for i in range(1, len(tiles)))
    max_turn = max((abs((tiles[i].heading - tiles[i - 1].heading + 180) % 360 - 180)
                    for i in range(1, len(tiles))), default=0.0)

    L = [f"{VERSION}  opsis   (the shape of what happened — NOT a substitute for looking)",
         f"grid {cols}x{rows}  tiles {tw}x{th}  {len(tiles)} frames  {nbytes // 1024} KB",
         "reading order: left to right, top to bottom — the layout IS the ordering.",
         "frames are UNALTERED; every qualification is here in text, never in pixels.",
         "sampled at equal TRAVEL, so tiles are not equally spaced in time.",
         f"span {span:.2f} s, {dist:.2f} m travelled"
         + (f", ~{dist / (len(tiles) - 1):.2f} m per tile" if len(tiles) > 1 else "")]

    for i, t in enumerate(tiles):
        step = f"+{_dist(tiles[i - 1].pos, t.pos):.2f}m" if i else " start "
        L.append(f"  tile {i:>2}  +{t.elapsed:.2f}s  {step}  "
                 f"({t.pos[0]:.2f},{t.pos[1]:.2f},{t.pos[2]:.2f})  "
                 f"heading {t.heading:>3.0f}" + (f"  {t.note}" if t.note else ""))

    if max_turn > turn_threshold:
        L.append(f"** the observer TURNED up to {max_turn:.0f} deg between marks — tiles show")
        L.append("   different directions, so apparent movement across them is partly the")
        L.append("   observer's own pivot, not the world's.")
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# self-test: the format proves itself without any source of frames
# --------------------------------------------------------------------------- #

def _synth(motion: str, i: int, n: int, w: int, h: int) -> bytes:
    f = i / max(1, n - 1)
    buf = bytearray(w * h * 3)
    shift = int(f * 120) if motion == "sweep" else 0
    for y in range(h):
        base = 70 if ((0 + shift) // 26) % 2 == 0 else 105
        for x in range(w):
            band = ((x + shift) // 26) % 2
            g = min(255, (70 if band == 0 else 105) + y * 40 // h)
            o = (y * w + x) * 3
            buf[o], buf[o + 1], buf[o + 2] = g, min(255, g + 12), min(255, g + 4)
    if motion == "crossing":
        _disc(buf, w, h, int(34 + f * (w - 78)), h // 2, 18)
    elif motion == "approach":
        _disc(buf, w, h, w // 2, h // 2, int(7 + f * 52))
    return bytes(buf)


def _disc(buf: bytearray, w: int, h: int, cx: int, cy: int, r: int) -> None:
    for y in range(max(0, cy - r), min(h, cy + r + 1)):
        for x in range(max(0, cx - r), min(w, cx + r + 1)):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                o = (y * w + x) * 3
                buf[o], buf[o + 1], buf[o + 2] = 230, 215, 120


def self_test(motion: str = "crossing", frames: int = 4,
              w: int = 320, h: int = 180) -> Opsis:
    """Synthesise one of: crossing, sweep, approach, still.

    If these four are not distinguishable by eye in the output, the format has
    failed at the only job it has.
    """
    tiles = [Tile(pixels=_synth(motion, i, frames, w, h), width=w, height=h,
                  elapsed=i * 0.45, pos=(i * 0.5, 0.75, 0.0),
                  # 12 deg/step, deliberately clear of the 8 deg warning threshold:
                  # the synthetic sweep stepped exactly 8 and sat on the boundary, so
                  # the one test built to exercise the turn warning never tripped it.
                  heading=320 + i * 12 if motion == "sweep" else 355)
             for i in range(frames)]
    return compose(tiles)


if __name__ == "__main__":
    import sys
    which = sys.argv[1] if len(sys.argv) > 1 else "crossing"
    out = self_test(which)
    if out.composed:
        path = f"opsis-{which}.png"
        with open(path, "wb") as fh:
            fh.write(out.png)
        print(out.manifest)
        print(f"written: {path}")
    else:
        print(out.manifest)
