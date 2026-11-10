"""Tiny read-only ISO 9660 / Joliet reader (enough for CD-ROM game discs)."""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterator

SECTOR = 2048


@dataclass
class IsoEntry:
    path: str            # posix-style path inside the image, no leading slash
    name: str
    is_dir: bool
    lba: int
    size: int
    children: list["IsoEntry"] = field(default_factory=list)


class IsoImage:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._fh = open(self.path, "rb")
        self._raw_sector = SECTOR
        self._raw_offset = 0
        self._detect_sector_layout()
        self.root = self._read_volume()
        self._index: dict[str, IsoEntry] = {}
        self._build_index(self.root)

    # ------------------------------------------------------------------ low level
    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> "IsoImage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _detect_sector_layout(self) -> None:
        """Handle raw 2352-byte sector images (.bin) as well as plain 2048-byte .iso."""
        self._fh.seek(0)
        head = self._fh.read(16)
        if head[:12] == b"\x00\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\x00":
            self._raw_sector = 2352
            mode = head[15]
            self._raw_offset = 16 if mode == 1 else 24

    def _sector(self, lba: int, count: int = 1) -> bytes:
        out = bytearray()
        for i in range(count):
            self._fh.seek((lba + i) * self._raw_sector + self._raw_offset)
            out.extend(self._fh.read(SECTOR))
        return bytes(out)

    def read_extent(self, lba: int, size: int) -> bytes:
        if self._raw_sector == SECTOR:
            self._fh.seek(lba * SECTOR)
            return self._fh.read(size)
        sectors = (size + SECTOR - 1) // SECTOR
        return self._sector(lba, sectors)[:size]

    def iter_extent(self, lba: int, size: int, chunk_sectors: int = 512) -> Iterator[bytes]:
        remaining = size
        cur = lba
        while remaining > 0:
            n = min(chunk_sectors, (remaining + SECTOR - 1) // SECTOR)
            data = self._sector(cur, n) if self._raw_sector != SECTOR else self._read_plain(cur, n)
            take = min(remaining, len(data))
            yield data[:take]
            remaining -= take
            cur += n

    def _read_plain(self, lba: int, n: int) -> bytes:
        self._fh.seek(lba * SECTOR)
        return self._fh.read(n * SECTOR)

    # ------------------------------------------------------------------ volume descriptors
    def _read_volume(self) -> IsoEntry:
        joliet_root = None
        primary_root = None
        lba = 16
        while True:
            vd = self._sector(lba)
            vtype = vd[0]
            if vd[1:6] != b"CD001":
                break
            if vtype == 255:
                break
            if vtype == 1 and primary_root is None:
                primary_root = (vd[156:190], False)
            elif vtype == 2:
                esc = vd[88:120]
                if b"%/@" in esc or b"%/C" in esc or b"%/E" in esc:
                    joliet_root = (vd[156:190], True)
            lba += 1
        rec, joliet = joliet_root or primary_root
        if rec is None:
            raise ValueError(f"{self.path}: no ISO9660 volume descriptor")
        self._joliet = joliet
        root_lba = struct.unpack_from("<I", rec, 2)[0]
        root_size = struct.unpack_from("<I", rec, 10)[0]
        root = IsoEntry("", "", True, root_lba, root_size)
        self._read_dir(root)
        return root

    def _read_dir(self, d: IsoEntry) -> None:
        data = self.read_extent(d.lba, d.size)
        pos = 0
        while pos < len(data):
            rec_len = data[pos]
            if rec_len == 0:
                # skip to next sector boundary
                pos = (pos // SECTOR + 1) * SECTOR
                continue
            rec = data[pos:pos + rec_len]
            pos += rec_len
            lba = struct.unpack_from("<I", rec, 2)[0]
            size = struct.unpack_from("<I", rec, 10)[0]
            flags = rec[25]
            name_len = rec[32]
            raw_name = rec[33:33 + name_len]
            if raw_name in (b"\x00", b"\x01"):
                continue
            if self._joliet:
                name = raw_name.decode("utf-16-be", "replace")
            else:
                name = raw_name.decode("latin-1")
            if ";" in name:
                name = name.split(";")[0]
            if name.endswith("."):
                name = name[:-1]
            is_dir = bool(flags & 2)
            child = IsoEntry(f"{d.path}/{name}" if d.path else name, name, is_dir, lba, size)
            d.children.append(child)
            if is_dir:
                self._read_dir(child)

    def _build_index(self, d: IsoEntry) -> None:
        for c in d.children:
            self._index[c.path.lower()] = c
            if c.is_dir:
                self._build_index(c)

    # ------------------------------------------------------------------ public API
    def walk(self) -> Iterator[IsoEntry]:
        yield from self._index.values()

    def files(self) -> list[IsoEntry]:
        return [e for e in self._index.values() if not e.is_dir]

    def get(self, path: str) -> IsoEntry | None:
        return self._index.get(path.replace("\\", "/").strip("/").lower())

    def exists(self, path: str) -> bool:
        return self.get(path) is not None

    def listdir(self, path: str) -> list[IsoEntry]:
        if path in ("", "/"):
            return self.root.children
        e = self.get(path)
        return e.children if e and e.is_dir else []

    def read(self, path: str) -> bytes:
        e = self.get(path)
        if e is None or e.is_dir:
            raise FileNotFoundError(path)
        return self.read_extent(e.lba, e.size)

    def extract(self, entry: IsoEntry, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as out:
            for chunk in self.iter_extent(entry.lba, entry.size):
                out.write(chunk)

    def top_level_names(self) -> list[str]:
        return [c.name for c in self.root.children]


def is_iso(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in (".iso", ".bin", ".img")


def rel_name(p: str) -> str:
    return PurePosixPath(p).name
