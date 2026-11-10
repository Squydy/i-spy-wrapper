"""Palettes: CLUT chunks and approximations of Director's built-in palettes."""
from __future__ import annotations

from .stream import Stream

Palette = list[tuple[int, int, int]]


def parse_clut(data: bytes, big: bool = True) -> Palette:
    """CLUT chunk: 16-bit RGB triplets (high byte significant)."""
    s = Stream(data, big)
    pal: Palette = []
    while s.remaining() >= 6:
        r = s.u16() >> 8
        g = s.u16() >> 8
        b = s.u16() >> 8
        pal.append((r, g, b))
    return pal


def _mac_system() -> Palette:
    """Classic Mac OS 8-bit system palette (index 0 = white ... 255 = black)."""
    pal: Palette = []
    levels = [0xFF, 0xCC, 0x99, 0x66, 0x33, 0x00]
    for r in levels:
        for g in levels:
            for b in levels:
                pal.append((r, g, b))
    # 10 extra ramps: red, green, blue, gray (each skipping the cube values)
    ramp = [0xEE, 0xDD, 0xBB, 0xAA, 0x88, 0x77, 0x55, 0x44, 0x22, 0x11]
    for v in ramp:
        pal.append((v, 0, 0))
    for v in ramp:
        pal.append((0, v, 0))
    for v in ramp:
        pal.append((0, 0, v))
    for v in ramp:
        pal.append((v, v, v))
    return pal[:256]


def _win_system() -> Palette:
    """Approximation of Director's 'System - Win' palette (Windows halftone layout)."""
    pal: Palette = [
        (0, 0, 0), (128, 0, 0), (0, 128, 0), (128, 128, 0), (0, 0, 128), (128, 0, 128),
        (0, 128, 128), (192, 192, 192), (192, 220, 192), (166, 202, 240),
    ]
    levels = [0, 51, 102, 153, 204, 255]
    cube: Palette = []
    for b in levels:
        for g in levels:
            for r in levels:
                cube.append((r, g, b))
    # remove the 20 static colours that appear in the cube to keep 236 unique entries
    body = cube[:]
    grays = [(v, v, v) for v in (0x08, 0x10, 0x18, 0x20, 0x28, 0x30, 0x38, 0x40, 0x48, 0x50, 0x58, 0x60,
                                 0x68, 0x70, 0x78, 0x80, 0x88, 0x90, 0x98, 0xA0)]
    pal.extend(body)
    pal.extend(grays)
    tail = [(255, 251, 240), (160, 160, 164), (128, 128, 128), (255, 0, 0), (0, 255, 0), (255, 255, 0),
            (0, 0, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255)]
    pal = pal[:246] + tail
    return pal[:256]


def _grayscale() -> Palette:
    return [(255 - i, 255 - i, 255 - i) for i in range(256)]


_BUILTIN: dict[int, Palette] = {}


def builtin(palette_id: int) -> Palette:
    """Director built-in palette ids: -1 mac system, -101 win system, -3 grayscale, others -> mac."""
    if not _BUILTIN:
        _BUILTIN[-1] = _mac_system()
        _BUILTIN[-3] = _grayscale()
        _BUILTIN[-101] = _win_system()
        _BUILTIN[-102] = _win_system()
    return _BUILTIN.get(palette_id, _BUILTIN[-101] if palette_id <= -100 else _BUILTIN[-1])


def normalise(pal: Palette) -> Palette:
    if len(pal) >= 256:
        return pal[:256]
    return pal + [(0, 0, 0)] * (256 - len(pal))
