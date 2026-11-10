"""Per-game adapters: turn generic Director dumps into scenes/riddles the engine understands."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

Log = Callable[[str], None]


def build_scenes(pack: Path, manifest: dict, casts: dict, scripts: dict, texts: dict,
                 score: dict, log: Log, lingo: dict | None = None) -> dict:
    gid = manifest["id"]
    if gid == "treasure_hunt":
        from .treasure_hunt import build
    else:
        from .blackhammer import build
    return build(pack, manifest, casts, scripts, texts, score, log, lingo or {})
