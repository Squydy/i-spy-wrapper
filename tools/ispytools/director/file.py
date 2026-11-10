"""Director container: RIFX/XFIR memory-mapped files and Afterburner (.dcr/.cct)."""
from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .stream import Stream
from . import members as _members

MOVIE_CODECS = {"MV93", "MC95"}
AFTERBURNER_CODECS = {"FGDM", "FGDC"}


@dataclass
class ChunkInfo:
    id: int
    fourcc: str
    offset: int          # absolute offset of chunk *data* (plain) or FGEI-relative (afterburner)
    length: int          # stored length
    uncompressed: int = -1
    compression: int = -1  # afterburner codec index, -1 = none


@dataclass
class KeyEntry:
    section_id: int
    cast_id: int
    fourcc: str


@dataclass
class CastLibInfo:
    name: str
    path: str
    min_member: int
    max_member: int
    lib_id: int
    index: int


@dataclass
class Config:
    file_version: int = 0
    stage_rect: tuple[int, int, int, int] = (0, 0, 0, 0)
    min_member: int = 1
    max_member: int = 0
    director_version: int = 0
    palette_id: int = 0
    stage_color: int = 0


def human_version(ver: int) -> int:
    """Map Director's internal fileVersion to a 'marketing' version (e.g. 700, 850, 1000)."""
    table = [(1951, 1200), (1922, 1150), (1921, 1100), (1851, 1000), (1700, 850), (1410, 800),
             (1224, 700), (1218, 600), (1201, 500), (1117, 404), (1115, 400), (1029, 310), (1028, 300)]
    for threshold, hv in table:
        if ver >= threshold:
            return hv
    return 200


class DirectorFile:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        self.big_endian = True
        self.codec = ""
        self.afterburner = False
        self.chunks: dict[int, ChunkInfo] = {}
        self._ils_cache: dict[int, bytes] = {}
        self._fgei_base = 0
        self.keys: list[KeyEntry] = []
        self.config = Config()
        self.version = 0  # human version
        self.cast_libs: list[CastLibInfo] = []
        self._members_cache: dict[int, dict[int, _members.CastMember]] | None = None
        self._script_sections: dict[int, int] | None = None
        self._read_header()
        self._read_keys()
        self._read_config()
        self._read_cast_list()

    # ------------------------------------------------------------------ container
    def _read_header(self) -> None:
        magic = self.data[:4]
        if magic == b"RIFX":
            self.big_endian = True
        elif magic == b"XFIR":
            self.big_endian = False
        else:
            raise ValueError(f"{self.path}: not a Director file (magic {magic!r})")
        s = Stream(self.data, self.big_endian, 4)
        s.u32()  # file length
        self.codec = s.fourcc()
        if self.codec in AFTERBURNER_CODECS:
            self.afterburner = True
            self._read_afterburner(s)
        elif self.codec in MOVIE_CODECS:
            self._read_mmap(s)
        else:
            raise ValueError(f"{self.path}: unsupported codec {self.codec}")

    def _read_mmap(self, s: Stream) -> None:
        # imap chunk directly follows the header
        if s.fourcc() != "imap":
            raise ValueError("imap chunk missing")
        s.u32()  # imap length
        s.u32()  # mmap count
        mmap_offset = s.u32()
        s.seek(mmap_offset)
        if s.fourcc() != "mmap":
            raise ValueError("mmap chunk missing")
        s.u32()  # mmap length
        header_len = s.u16()
        entry_len = s.u16()
        s.u32()  # chunkCountMax
        count_used = s.u32()
        s.skip(header_len - 12)
        base = s.pos
        for i in range(count_used):
            s.seek(base + i * entry_len)
            fourcc = s.fourcc()
            length = s.u32()
            offset = s.u32()
            if fourcc in ("free", "junk") or offset == 0 and fourcc != "RIFX":
                continue
            self.chunks[i] = ChunkInfo(i, fourcc, offset + 8, length)

    def _read_afterburner(self, s: Stream) -> None:
        if s.fourcc() != "Fver":
            raise ValueError("Fver chunk missing")
        fver_len = s.varint()
        s.skip(fver_len)
        if s.fourcc() != "Fcdr":
            raise ValueError("Fcdr chunk missing")
        fcdr_len = s.varint()
        s.skip(fcdr_len)
        if s.fourcc() != "ABMP":
            raise ValueError("ABMP chunk missing")
        abmp_len = s.varint()
        abmp_end = s.pos + abmp_len
        s.varint()  # compression type
        s.varint()  # uncompressed length
        abmp = Stream(zlib.decompress(self.data[s.pos:abmp_end]), self.big_endian)
        s.seek(abmp_end)
        abmp.varint()
        abmp.varint()
        res_count = abmp.varint()
        for _ in range(res_count):
            rid = abmp.varint()
            offset = abmp.varint()
            comp_size = abmp.varint()
            uncomp_size = abmp.varint()
            comp_type = abmp.varint()
            fourcc = abmp.fourcc()
            self.chunks[rid] = ChunkInfo(rid, fourcc, offset, comp_size, uncomp_size, comp_type)
        if s.fourcc() != "FGEI":
            raise ValueError("FGEI chunk missing")
        s.varint()
        self._fgei_base = s.pos
        # Initial Load Segment: small resources packed together, zlib-compressed
        ils = next((c for c in self.chunks.values() if c.fourcc == "ILS "), None)
        if ils is not None:
            raw = self.data[self._fgei_base + ils.offset:self._fgei_base + ils.offset + ils.length]
            body = Stream(zlib.decompress(raw), self.big_endian)
            while not body.eof():
                rid = body.varint()
                info = self.chunks.get(rid)
                if info is None:
                    break
                self._ils_cache[rid] = body.read(info.length)

    # ------------------------------------------------------------------ chunk access
    def chunk_ids(self, fourcc: str) -> list[int]:
        return [cid for cid, c in self.chunks.items() if c.fourcc == fourcc]

    def read_chunk(self, cid: int) -> bytes:
        info = self.chunks[cid]
        if not self.afterburner:
            return self.data[info.offset:info.offset + info.length]
        if cid in self._ils_cache:
            return self._ils_cache[cid]
        start = self._fgei_base + info.offset
        raw = self.data[start:start + info.length]
        if info.uncompressed >= 0 and info.uncompressed != info.length:
            try:
                return zlib.decompress(raw)
            except zlib.error:
                return raw
        return raw

    def stream(self, cid: int, big: bool = True) -> Stream:
        """Chunk *contents* are big-endian in every Director file; only the container
        (imap/mmap/KEY*/Afterburner map) follows the file byte order."""
        return Stream(self.read_chunk(cid), big)

    def first_chunk(self, fourcc: str) -> int | None:
        ids = self.chunk_ids(fourcc)
        return ids[0] if ids else None

    # ------------------------------------------------------------------ KEY*
    def _read_keys(self) -> None:
        kid = self.first_chunk("KEY*")
        if kid is None:
            return
        s = self.stream(kid, self.big_endian)
        s.u16()  # header size
        s.u16()  # entry size
        s.u32()  # max
        used = s.u32()
        for _ in range(used):
            if s.remaining() < 12:
                break
            section = s.u32()
            cast = s.u32()
            fourcc = s.fourcc()
            self.keys.append(KeyEntry(section, cast, fourcc))

    def owned(self, cast_id: int, fourcc: str | None = None) -> list[KeyEntry]:
        return [k for k in self.keys if k.cast_id == cast_id and (fourcc is None or k.fourcc == fourcc)]

    # ------------------------------------------------------------------ Lctx
    def script_sections(self) -> dict[int, int]:
        """{scriptId (1-based, from CastInfo): Lscr chunk id} from the script context (Lctx/LctX)."""
        if self._script_sections is not None:
            return self._script_sections
        out: dict[int, int] = {}
        cid = self.first_chunk("Lctx")
        if cid is None:
            cid = self.first_chunk("LctX")
        if cid is not None:
            s = self.stream(cid, True)
            s.u32(); s.u32()                 # unknown0, unknown1
            count = s.u32()
            s.u32()                          # count2
            entries_offset = s.u16()
            s.seek(entries_offset)
            for i in range(count):
                if s.remaining() < 12:
                    break
                s.u32()                      # unknown
                section = s.i32()
                s.u16(); s.u16()
                if section > 0:
                    out[i + 1] = section
        self._script_sections = out
        return out

    def script_chunk(self, script_id: int) -> int | None:
        return self.script_sections().get(script_id)

    # ------------------------------------------------------------------ config
    def _read_config(self) -> None:
        cid = self.first_chunk("DRCF")
        if cid is None:
            cid = self.first_chunk("VWCF")
        if cid is None:
            return
        s = self.stream(cid)
        cfg = Config()
        s.u16()  # length
        cfg.file_version = s.u16()
        cfg.stage_rect = s.rect()
        cfg.min_member = s.i16()
        cfg.max_member = s.i16()
        # offsets after this differ by version; director version lives at 36
        if len(s) >= 38:
            s.seek(36)
            cfg.director_version = s.u16()
        if len(s) >= 0x58:
            s.seek(0x4E)
            cfg.palette_id = s.i16()
        self.config = cfg
        self.version = human_version(cfg.director_version or cfg.file_version)

    # ------------------------------------------------------------------ MCsL
    def _read_cast_list(self) -> None:
        cid = self.first_chunk("MCsL")
        if cid is None:
            return
        s = self.stream(cid)
        s.u32()  # dataOffset
        s.u32()
        cast_count = s.u32()
        items_per = s.u16()
        s.u32()
        table_len = s.u16()
        offsets = [s.u32() for _ in range(table_len)]
        s.u32()  # items length
        items_base = s.pos
        offsets.append(len(s) - items_base)

        def item(i: int) -> bytes:
            if i + 1 >= len(offsets):
                return b""
            return s.data[items_base + offsets[i]: items_base + offsets[i + 1]]

        for ci in range(cast_count):
            base = ci * items_per
            name_raw = item(base)
            path_raw = item(base + 1)
            meta = item(base + 3)
            name = name_raw[1:1 + name_raw[0]].decode("latin-1") if name_raw else ""
            path = path_raw[1:1 + path_raw[0]].decode("latin-1") if path_raw else ""
            mn = mx = 0
            lib_id = 0
            if len(meta) >= 8:
                ms = Stream(meta, True)
                mn = ms.u16()
                mx = ms.u16()
                lib_id = ms.u32()
            self.cast_libs.append(CastLibInfo(name, path, mn, mx, lib_id, ci + 1))

    # ------------------------------------------------------------------ members
    def cast_tables(self) -> dict[int, list[int]]:
        """Return {castLibOwnerId: [CASt chunk id per slot (0 = empty)]} from every CAS* chunk."""
        tables: dict[int, list[int]] = {}
        for cas_id in self.chunk_ids("CAS*"):
            owner = next((k.cast_id for k in self.keys if k.section_id == cas_id), 1024)
            # CAS* is always big-endian
            s = Stream(self.read_chunk(cas_id), True)
            slots = [s.u32() for _ in range(len(s) // 4)]
            tables[owner] = slots
        return tables

    def members(self) -> dict[int, dict[int, _members.CastMember]]:
        """{castLibOwnerId: {memberNumber: CastMember}}"""
        if self._members_cache is not None:
            return self._members_cache
        out: dict[int, dict[int, _members.CastMember]] = {}
        min_member = self.config.min_member or 1
        for owner, slots in self.cast_tables().items():
            lib: dict[int, _members.CastMember] = {}
            for i, cid in enumerate(slots):
                if cid == 0 or cid not in self.chunks or self.chunks[cid].fourcc != "CASt":
                    continue
                try:
                    m = _members.parse_cast_member(self, cid, min_member + i, owner)
                except Exception as exc:  # keep going on odd members
                    m = _members.CastMember(number=min_member + i, chunk_id=cid, type=0, name=f"<error {exc}>")
                lib[m.number] = m
            out[owner] = lib
        self._members_cache = out
        return out

    def all_members(self) -> Iterable[_members.CastMember]:
        for lib in self.members().values():
            yield from lib.values()

    # ------------------------------------------------------------------ misc
    def describe(self) -> str:
        counts: dict[str, int] = {}
        for c in self.chunks.values():
            counts[c.fourcc] = counts.get(c.fourcc, 0) + 1
        lines = [f"{self.path.name}: codec={self.codec} endian={'BE' if self.big_endian else 'LE'} "
                 f"afterburner={self.afterburner} version={self.version} stage={self.config.stage_rect} "
                 f"members={self.config.min_member}-{self.config.max_member}"]
        lines.append("  chunks: " + ", ".join(f"{k}:{v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])))
        for lib in self.cast_libs:
            lines.append(f"  castlib {lib.index}: {lib.name!r} path={lib.path!r} members {lib.min_member}-{lib.max_member} id={lib.lib_id}")
        return "\n".join(lines)
