"""CASt member records (Director 5+ layout)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .stream import Stream

if TYPE_CHECKING:
    from .file import DirectorFile

TYPE_NAMES = {
    0: "null", 1: "bitmap", 2: "filmloop", 3: "text", 4: "palette", 5: "picture", 6: "sound",
    7: "button", 8: "shape", 9: "movie", 10: "video", 11: "script", 12: "richtext", 13: "ole",
    14: "transition", 15: "xtra",
}

SCRIPT_TYPES = {1: "behavior", 3: "movie", 7: "parent"}


@dataclass
class BitmapInfo:
    pitch: int = 0
    rect: tuple[int, int, int, int] = (0, 0, 0, 0)  # top,left,bottom,right
    reg_y: int = 0
    reg_x: int = 0
    bpp: int = 8
    palette_lib: int = 0
    palette_id: int = 0  # <=0 built-in palettes
    flags: int = 0

    @property
    def width(self) -> int:
        return self.rect[3] - self.rect[1]

    @property
    def height(self) -> int:
        return self.rect[2] - self.rect[0]


@dataclass
class CastMember:
    number: int
    chunk_id: int
    type: int
    name: str = ""
    lib_owner: int = 1024
    filename: str = ""          # external linked media path (as authored)
    script_text: str = ""
    script_id: int = 0
    flags: int = 0
    specific: bytes = b""
    info_items: list[bytes] = field(default_factory=list)
    bitmap: BitmapInfo | None = None
    script_type: int = 0

    @property
    def type_name(self) -> str:
        return TYPE_NAMES.get(self.type, f"type{self.type}")

    def resources(self, df: "DirectorFile", fourcc: str | None = None):
        return df.owned(self.chunk_id, fourcc)


def _parse_info(s: Stream, m: CastMember) -> None:
    """CastInfo list chunk: header + offset table + items."""
    start = s.pos
    data_offset = s.u32()
    s.u32()  # unk1
    s.u32()  # unk2
    m.flags = s.u32()
    m.script_id = s.u32()
    s.seek(start + data_offset)
    count = s.u16()
    offsets = [s.u32() for _ in range(count)]
    items_len = s.u32()
    base = s.pos
    offsets.append(items_len)
    items: list[bytes] = []
    for i in range(count):
        a, b = offsets[i], offsets[i + 1]
        items.append(s.data[base + a: base + b])
    m.info_items = items
    if len(items) > 0 and items[0]:
        m.script_text = items[0].decode("latin-1", "replace")
    if len(items) > 1 and items[1]:
        n = items[1][0]
        m.name = items[1][1:1 + n].decode("latin-1", "replace")
    if len(items) > 2 and items[2]:
        n = items[2][0]
        m.filename = items[2][1:1 + n].decode("latin-1", "replace")
    if len(items) > 3 and items[3] and not m.filename:
        n = items[3][0]
        m.filename = items[3][1:1 + n].decode("latin-1", "replace")


def _parse_bitmap(spec: bytes, big: bool) -> BitmapInfo:
    s = Stream(spec, big)
    b = BitmapInfo()
    if len(spec) < 2 + 8:
        return b
    raw_pitch = s.u16()
    b.pitch = raw_pitch & 0x7FFF
    b.flags = raw_pitch & 0x8000
    b.rect = s.rect()
    if s.remaining() >= 8:
        s.rect()  # bounding rect
    if s.remaining() >= 4:
        b.reg_y = s.i16()
        b.reg_x = s.i16()
    if s.remaining() >= 2:
        s.u8()  # flags2
        b.bpp = s.u8()
    if s.remaining() >= 4:
        b.palette_lib = s.i16()
        b.palette_id = s.i16()
    elif s.remaining() >= 2:
        b.palette_id = s.i16()
    if b.bpp == 0:
        b.bpp = 1
    # sanity: derive bpp from pitch if the stored value disagrees badly
    w = max(b.width, 1)
    if b.pitch and not (b.pitch * 8 >= w * b.bpp and b.pitch * 8 < (w + 32) * b.bpp + 64):
        for cand in (1, 2, 4, 8, 16, 32):
            if (w * cand + 15) // 16 * 2 == b.pitch or (w * cand + 7) // 8 == b.pitch:
                b.bpp = cand
                break
    return b


def parse_cast_member(df: "DirectorFile", chunk_id: int, number: int, owner: int) -> CastMember:
    s = df.stream(chunk_id)
    mtype = s.u32()
    info_len = s.u32()
    spec_len = s.u32()
    m = CastMember(number=number, chunk_id=chunk_id, type=mtype, lib_owner=owner)
    if info_len:
        info = Stream(s.read(info_len), True)
        try:
            _parse_info(info, m)
        except Exception:
            pass
    m.specific = s.read(spec_len)
    if mtype == 1:
        m.bitmap = _parse_bitmap(m.specific, True)
    elif mtype == 11 and len(m.specific) >= 2:
        m.script_type = Stream(m.specific, True).u16()
    return m
