"""Shared helpers for adapters."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

Log = Callable[[str], None]


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1))


def members_of(casts: dict, label: str) -> list[dict]:
    c = casts["casts"].get(label)
    return c["members"] if c else []


def bitmaps_of(casts: dict, label: str) -> list[dict]:
    return [m for m in members_of(casts, label) if m.get("type") == "bitmap" and m.get("image")]


def largest_bitmap(members: list[dict], min_w: int = 400) -> dict | None:
    best = None
    for m in members:
        if m.get("type") != "bitmap" or not m.get("image"):
            continue
        area = m.get("w", 0) * m.get("h", 0)
        if m.get("w", 0) >= min_w and (best is None or area > best["w"] * best["h"]):
            best = m
    return best


def audio_index(pack: Path) -> dict[str, str]:
    """UPPERCASE stem -> relative wav path"""
    out = {}
    adir = pack / "audio"
    if adir.exists():
        for f in adir.iterdir():
            if f.suffix.lower() in (".wav", ".ogg", ".mp3"):
                out[f.stem.upper()] = f"audio/{f.name}"
    return out


def video_index(pack: Path) -> dict[str, str]:
    out = {}
    vdir = pack / "video"
    if vdir.exists():
        for f in vdir.iterdir():
            if f.suffix.lower() == ".ogv":
                out[f.stem.upper()] = f"video/{f.name}"
    return out
