"""Identify which I SPY title a disc image or folder contains."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .iso9660 import IsoImage, is_iso


@dataclass(frozen=True)
class GameDef:
    id: str
    title: str
    short: str
    main_movie: str          # relative to DATA
    casts_dir: str           # relative to DATA
    audio_dir: str           # relative to DATA
    video_dir: str | None    # relative to DATA
    cast_ext: str
    director: int            # marketing version
    stage: tuple[int, int] = (640, 480)


GAMES: dict[str, GameDef] = {
    "treasure_hunt": GameDef("treasure_hunt", "I SPY Treasure Hunt", "Treasure Hunt",
                             "ISPYMAIN6.dxr", "casts", "AIFF", None, ".cxt", 700),
    "fantasy": GameDef("fantasy", "I SPY Fantasy", "Fantasy",
                       "ISPYMAIN7.dxr", "CASTS", "AIFF", "BINK", ".cxt", 850),
    "spooky_deluxe": GameDef("spooky_deluxe", "I SPY Spooky Mansion Deluxe", "Spooky Mansion Deluxe",
                             "ISPYMAIN8.dxr", "CASTS", "AIFF", "BINK", ".cxt", 850),
    "mystery": GameDef("mystery", "I SPY Mystery", "Mystery",
                       "ISPYMAIN9.dcr", "CASTS", "AUDIO", "BINK", ".cct", 1000),
}

# main-movie filename (lowercase) -> game id
_FINGERPRINTS = {g.main_movie.lower(): g.id for g in GAMES.values()}


class SourceTree:
    """Uniform read access over either an ISO image or an already-copied folder."""

    def __init__(self, src: Path):
        self.src = Path(src)
        self.iso: IsoImage | None = IsoImage(self.src) if is_iso(self.src) else None

    def close(self) -> None:
        if self.iso:
            self.iso.close()

    def _names(self, rel: str) -> list[tuple[str, bool, int]]:
        """(name, is_dir, size) for children of rel"""
        if self.iso:
            return [(e.name, e.is_dir, e.size) for e in self.iso.listdir(rel)]
        p = self.src / rel if rel else self.src
        if not p.is_dir():
            return []
        return [(c.name, c.is_dir(), c.stat().st_size if c.is_file() else 0) for c in p.iterdir()]

    def find_dir(self, parent: str, name: str) -> str | None:
        """Case-insensitive directory lookup; returns the real relative path."""
        for n, is_dir, _ in self._names(parent):
            if is_dir and n.lower() == name.lower():
                return f"{parent}/{n}" if parent else n
        return None

    def find_file(self, parent: str, name: str) -> str | None:
        for n, is_dir, _ in self._names(parent):
            if not is_dir and n.lower() == name.lower():
                return f"{parent}/{n}" if parent else n
        return None

    def list_files(self, rel: str) -> list[tuple[str, int]]:
        return [(f"{rel}/{n}" if rel else n, size) for n, is_dir, size in self._names(rel) if not is_dir]

    def read(self, rel: str) -> bytes:
        if self.iso:
            return self.iso.read(rel)
        return (self.src / rel).read_bytes()

    def copy(self, rel: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if self.iso:
            entry = self.iso.get(rel)
            if entry is None:
                raise FileNotFoundError(rel)
            self.iso.extract(entry, dest)
        else:
            import shutil
            shutil.copy2(self.src / rel, dest)


def detect(src: Path) -> tuple[GameDef, str] | None:
    """Return (game, data_dir_relpath) or None. Accepts an ISO, a disc root folder,
    or a DATA folder directly."""
    tree = SourceTree(src)
    try:
        candidates = []
        data = tree.find_dir("", "DATA")
        if data:
            candidates.append(data)
        candidates.append("")  # maybe src *is* DATA
        for data_dir in candidates:
            for name, is_dir, _ in tree._names(data_dir):
                if not is_dir and name.lower() in _FINGERPRINTS:
                    return GAMES[_FINGERPRINTS[name.lower()]], data_dir
        return None
    finally:
        tree.close()
