"""Frame labels (VWLB) and score sprite channels (VWSC) for Director 5+ movies."""
from __future__ import annotations

from dataclasses import dataclass, field

from .stream import Stream


@dataclass
class Sprite:
    channel: int
    sprite_type: int = 0
    ink: int = 0
    cast_lib: int = 0
    member: int = 0
    script_lib: int = 0
    script_member: int = 0
    fore: int = 0
    back: int = 0
    y: int = 0
    x: int = 0
    height: int = 0
    width: int = 0
    flags: int = 0
    blend: int = 0

    @property
    def visible(self) -> bool:
        return self.member != 0 and (self.width > 0 or self.height > 0 or self.sprite_type != 0)

    def rect(self) -> tuple[int, int, int, int]:
        """left, top, right, bottom in stage coords (sprite loc is the registration point)."""
        return self.x, self.y, self.x + self.width, self.y + self.height

    def to_dict(self) -> dict:
        return {
            "channel": self.channel, "type": self.sprite_type, "ink": self.ink,
            "castLib": self.cast_lib, "member": self.member,
            "x": self.x, "y": self.y, "w": self.width, "h": self.height,
            "scriptLib": self.script_lib, "scriptMember": self.script_member,
        }


@dataclass
class Frame:
    index: int  # 1-based
    sprites: dict[int, Sprite] = field(default_factory=dict)
    script_lib: int = 0
    script_member: int = 0
    tempo: int = 0
    sound1: int = 0
    sound2: int = 0
    palette: int = 0
    transition: int = 0


def parse_labels(data: bytes, big: bool = True) -> dict[int, str]:
    """VWLB: {frame: label}"""
    s = Stream(data, big)
    count = s.u16()
    entries = []
    for _ in range(count):
        frame = s.u16()
        offset = s.u16()
        entries.append((frame, offset))
    text_len = s.u32()
    base = s.pos
    labels: dict[int, str] = {}
    for i, (frame, off) in enumerate(entries):
        end = entries[i + 1][1] if i + 1 < len(entries) else text_len
        labels[frame] = data[base + off: base + end].decode("cp1252", "replace")
    return labels


def parse_score(data: bytes, big: bool = True) -> list[Frame]:
    """Decode frame deltas into a per-frame channel snapshot."""
    s = Stream(data, big)
    s.u32()  # total size
    s.u32()  # -3 / header length
    frame_count = s.u32()
    version = s.u16()
    record_size = s.u16()
    channel_count = s.u16()
    if version > 13:
        s.u16()  # channels displayed
    else:
        s.u16()
    if record_size == 0:
        record_size = 24
    if channel_count == 0:
        channel_count = 122
    buf = bytearray(record_size * (channel_count + 2))
    frames: list[Frame] = []
    frame_idx = 0
    main_size = record_size * 2  # two frame-level channel records precede sprite channels

    while not s.eof() and frame_idx < max(frame_count, 1) + 2:
        if s.remaining() < 2:
            break
        frame_len = s.u16()
        if frame_len < 2:
            break
        end = s.pos + frame_len - 2
        if end > len(data):
            end = len(data)
        while s.pos + 4 <= end:
            size = s.u16()
            offset = s.u16()
            chunk = s.read(size)
            if offset + size <= len(buf):
                buf[offset:offset + size] = chunk
        s.seek(end)
        frame_idx += 1
        frames.append(_snapshot(frame_idx, bytes(buf), record_size, channel_count, main_size, big))
    return frames


def _snapshot(index: int, buf: bytes, rec: int, channels: int, main_size: int, big: bool) -> Frame:
    f = Frame(index=index)
    m = Stream(buf, big)
    # main channel record (D6+ layout): script id at 0, sound1 4, sound2 ..; be forgiving
    try:
        m.seek(0)
        m.u8()  # action flags
        f.transition = m.u8()
        m.seek(4)
        f.tempo = m.u8()
    except Exception:
        pass
    for ch in range(1, channels + 1):
        off = main_size + (ch - 1) * rec
        if off + 24 > len(buf):
            break
        st = Stream(buf, big, off)
        sp = Sprite(channel=ch)
        sp.sprite_type = st.u8()
        sp.ink = st.u8()
        sp.cast_lib = st.u16()
        sp.member = st.u16()
        sp.script_lib = st.u16()
        sp.script_member = st.u16()
        sp.fore = st.u8()
        sp.back = st.u8()
        sp.y = st.i16()
        sp.x = st.i16()
        sp.height = st.i16()
        sp.width = st.i16()
        sp.flags = st.u8()
        sp.blend = st.u8()
        if sp.member or sp.sprite_type:
            f.sprites[ch] = sp
    return f
