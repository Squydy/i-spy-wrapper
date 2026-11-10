"""Director 'matte' ink emulation: make the exterior white region of a bitmap transparent.

Uses a scanline flood fill from the image border over near-white pixels, so interior
white pixels (eyes, teeth, labels) stay opaque, like Director's matte ink."""
from __future__ import annotations

from pathlib import Path

WHITE_THRESHOLD = 250


def apply_matte_file(path: Path, mode: str = "matte") -> bool:
    """mode 'matte' = flood fill from border; 'bgtransparent' = every white pixel transparent."""
    try:
        from PIL import Image
    except ImportError:
        return False
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    px = bytearray(img.tobytes())
    # white mask
    mask = bytearray(w * h)
    t = WHITE_THRESHOLD
    for i in range(w * h):
        o = i * 4
        if px[o] >= t and px[o + 1] >= t and px[o + 2] >= t:
            mask[i] = 1
    if mode == "bgtransparent":
        for i in range(w * h):
            if mask[i]:
                px[i * 4 + 3] = 0
    else:
        visited = _flood_from_border(mask, w, h)
        for i in range(w * h):
            if visited[i]:
                px[i * 4 + 3] = 0
    Image.frombytes("RGBA", (w, h), bytes(px)).save(path)
    return True


def _flood_from_border(mask: bytearray, w: int, h: int) -> bytearray:
    """Scanline flood fill over mask==1 pixels reachable from any border pixel."""
    visited = bytearray(w * h)
    stack: list[tuple[int, int]] = []
    for x in range(w):
        if mask[x]:
            stack.append((x, 0))
        if mask[(h - 1) * w + x]:
            stack.append((x, h - 1))
    for y in range(h):
        if mask[y * w]:
            stack.append((0, y))
        if mask[y * w + w - 1]:
            stack.append((w - 1, y))
    while stack:
        x, y = stack.pop()
        row = y * w
        if visited[row + x] or not mask[row + x]:
            continue
        # expand span
        x0 = x
        while x0 > 0 and mask[row + x0 - 1] and not visited[row + x0 - 1]:
            x0 -= 1
        x1 = x
        while x1 < w - 1 and mask[row + x1 + 1] and not visited[row + x1 + 1]:
            x1 += 1
        for xx in range(x0, x1 + 1):
            visited[row + xx] = 1
        for ny in (y - 1, y + 1):
            if 0 <= ny < h:
                nrow = ny * w
                xx = x0
                while xx <= x1:
                    if mask[nrow + xx] and not visited[nrow + xx]:
                        stack.append((xx, ny))
                        # skip the rest of this run
                        while xx <= x1 and mask[nrow + xx]:
                            xx += 1
                    else:
                        xx += 1
    return visited
