"""BITD bitmap decoding to RGBA bytes."""
from __future__ import annotations

from .members import BitmapInfo
from .palette import Palette, normalise

_LUT16: list[bytes] | None = None
_OPAQUE_ROW_CACHE: dict[int, bytes] = {}


def _lut16() -> list[bytes]:
    global _LUT16
    if _LUT16 is None:
        lut = []
        for v in range(65536):
            r = (v >> 10) & 0x1F
            g = (v >> 5) & 0x1F
            b = v & 0x1F
            lut.append(bytes(((r << 3) | (r >> 2), (g << 3) | (g >> 2), (b << 3) | (b >> 2), 255)))
        _LUT16 = lut
    return _LUT16


def unpack_bits(data: bytes, expected: int) -> bytes:
    """PackBits RLE as used by Director."""
    out = bytearray()
    i = 0
    n = len(data)
    while i < n and len(out) < expected:
        c = data[i]
        i += 1
        if c & 0x80:
            run = 257 - c
            if i < n:
                out.extend(data[i:i + 1] * run)
                i += 1
        else:
            run = c + 1
            out.extend(data[i:i + run])
            i += run
    if len(out) < expected:
        out.extend(b"\x00" * (expected - len(out)))
    return bytes(out)


def decode_bitd(data: bytes, info: BitmapInfo, palette: Palette | None = None) -> tuple[int, int, bytes]:
    """Return (width, height, rgba bytes)."""
    w, h = info.width, info.height
    if w <= 0 or h <= 0:
        return 0, 0, b""
    bpp = info.bpp
    pitch = info.pitch
    if pitch <= 0:
        pitch = ((w * bpp + 15) // 16) * 2
    total = pitch * h
    # Compressed (PackBits) 16/32-bit rows are stored as byte planes; uncompressed data is
    # stored as plain interleaved pixels.
    compressed = len(data) != total
    raw = unpack_bits(data, total) if compressed else data

    rows: list[bytes] = []
    opaque = _OPAQUE_ROW_CACHE.get(w)
    if opaque is None:
        opaque = b"\xff" * w
        _OPAQUE_ROW_CACHE[w] = opaque

    if bpp == 32:
        for y in range(h):
            row = raw[y * pitch:(y + 1) * pitch]
            if len(row) < 4 * w:
                row = row + b"\x00" * (4 * w - len(row))
            out = bytearray(w * 4)
            if compressed:   # planes: A, R, G, B
                out[0::4] = row[w:2 * w]
                out[1::4] = row[2 * w:3 * w]
                out[2::4] = row[3 * w:4 * w]
            else:            # interleaved ARGB pixels
                out[0::4] = row[1:4 * w:4]
                out[1::4] = row[2:4 * w:4]
                out[2::4] = row[3:4 * w:4]
            out[3::4] = opaque
            rows.append(bytes(out))
    elif bpp == 16:
        lut = _lut16()
        for y in range(h):
            row = raw[y * pitch:(y + 1) * pitch]
            if len(row) < 2 * w:
                row = row + b"\x00" * (2 * w - len(row))
            if compressed:   # hi-byte plane then lo-byte plane
                hi = row[0:w]
                lo = row[w:2 * w]
            else:            # interleaved big-endian RGB555 pixels
                hi = row[0:2 * w:2]
                lo = row[1:2 * w:2]
            rows.append(b"".join([lut[(hi[x] << 8) | lo[x]] for x in range(w)]))
    elif bpp == 8:
        pal = normalise(palette or [])
        pal_bytes = [bytes((r, g, b, 255)) for r, g, b in pal]
        for y in range(h):
            row = raw[y * pitch:y * pitch + w]
            if len(row) < w:
                row = row + b"\x00" * (w - len(row))
            rows.append(b"".join(map(pal_bytes.__getitem__, row)))
    elif bpp in (1, 2, 4):
        per_byte = 8 // bpp
        mask = (1 << bpp) - 1
        pal = normalise(palette or [])
        step = 256 // (1 << bpp)
        if bpp == 1:
            table = [bytes((255, 255, 255, 255)), bytes((0, 0, 0, 255))]
        else:
            table = [bytes((*pal[i * step], 255)) for i in range(1 << bpp)]
        for y in range(h):
            row = raw[y * pitch:(y + 1) * pitch]
            px = []
            for x in range(w):
                bi = x // per_byte
                byte = row[bi] if bi < len(row) else 0
                shift = (per_byte - 1 - (x % per_byte)) * bpp
                px.append(table[(byte >> shift) & mask])
            rows.append(b"".join(px))
    else:
        raise ValueError(f"unsupported bpp {bpp}")
    return w, h, b"".join(rows)
