"""Lingo script metadata: handler names and string literals (no bytecode decompilation)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .stream import Stream


@dataclass
class ScriptInfo:
    chunk_id: int
    cast_id: int
    handlers: list[str] = field(default_factory=list)
    properties: list[str] = field(default_factory=list)
    globals_: list[str] = field(default_factory=list)
    strings: list[str] = field(default_factory=list)
    numbers: list[float] = field(default_factory=list)


def parse_lnam(data: bytes, big: bool = True) -> list[str]:
    s = Stream(data, big)
    s.u32()
    s.u32()
    s.u32()
    s.u32()
    names_offset = s.u16()
    count = s.u16()
    s.seek(names_offset)
    names = []
    for _ in range(count):
        if s.eof():
            break
        names.append(s.pstring())
    return names


def parse_lscr(data: bytes, names: list[str], big: bool = True, version: int = 700,
               chunk_id: int = 0) -> ScriptInfo:
    s = Stream(data, big)
    info = ScriptInfo(chunk_id=chunk_id, cast_id=0)
    if len(data) < 92:
        return info
    s.seek(44)
    info.cast_id = s.i32()
    s.i16()  # factory name id
    s.u16()  # handler vectors count
    s.u32()
    s.u32()
    props_count = s.u16()
    props_offset = s.u32()
    globals_count = s.u16()
    globals_offset = s.u32()
    handlers_count = s.u16()
    handlers_offset = s.u32()
    literals_count = s.u16()
    literals_offset = s.u32()
    s.u32()  # literals data count
    literals_data_offset = s.u32()

    def name(i: int) -> str:
        return names[i] if 0 <= i < len(names) else f"<name{i}>"

    try:
        s.seek(props_offset)
        info.properties = [name(s.i16()) for _ in range(props_count)]
        s.seek(globals_offset)
        info.globals_ = [name(s.i16()) for _ in range(globals_count)]
    except Exception:
        pass

    rec = 46 if version >= 850 else 42
    for i in range(handlers_count):
        off = handlers_offset + i * rec
        if off + 2 > len(data):
            break
        s.seek(off)
        info.handlers.append(name(s.i16()))

    for i in range(literals_count):
        off = literals_offset + i * 8
        if off + 8 > len(data):
            break
        s.seek(off)
        ltype = s.u32()
        loff = s.u32()
        pos = literals_data_offset + loff
        if pos + 4 > len(data):
            continue
        s.seek(pos)
        if ltype == 1:  # string
            n = s.u32()
            raw = s.read(n)
            txt = raw.rstrip(b"\x00").decode("cp1252", "replace").replace("\r", "\n")
            info.strings.append(txt)
        elif ltype == 4:  # int
            n = s.u32()
            if n >= 4:
                info.numbers.append(s.i32())
        elif ltype == 9:  # float
            n = s.u32()
            raw = s.read(n)
            try:
                import struct
                if n == 8:
                    info.numbers.append(struct.unpack(">d" if big else "<d", raw)[0])
                elif n == 10:
                    info.numbers.append(_ext80(raw))
            except Exception:
                pass
    return info


def _ext80(raw: bytes) -> float:
    import struct
    exp = struct.unpack(">H", raw[:2])[0]
    mant = struct.unpack(">Q", raw[2:10])[0]
    sign = -1 if exp & 0x8000 else 1
    exp &= 0x7FFF
    if exp == 0 and mant == 0:
        return 0.0
    return sign * mant * 2.0 ** (exp - 16383 - 63)
