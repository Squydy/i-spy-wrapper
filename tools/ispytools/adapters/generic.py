"""Fallback scene builder: one scene per cast file with its largest bitmap as background.
Used as the base for the game-specific adapters before they refine hotspots/riddles."""
from __future__ import annotations

from pathlib import Path

from .common import Log, largest_bitmap, members_of, write_json

SKIP_CASTS = {"MAIN", "BHP", "SIGNIN", "EXTERNAL", "DEFAULT", "CREDIT", "BUMP", "OP"}


def generic_scenes(pack: Path, casts: dict, log: Log) -> list[dict]:
    scenes = []
    for label in casts["casts"]:
        if label in SKIP_CASTS:
            continue
        members = members_of(casts, label)
        bg = largest_bitmap(members)
        if not bg:
            continue
        scene = {
            "id": label.lower(),
            "title": label,
            "cast": label,
            "background": bg["image"],
            "width": bg["w"],
            "height": bg["h"],
            "hotspots": [],
            "riddles": [],
            "kind": "scene",
        }
        write_json(pack / "scenes" / f"{scene['id']}.json", scene)
        scenes.append({"id": scene["id"], "title": scene["title"], "kind": "scene"})
    return scenes
