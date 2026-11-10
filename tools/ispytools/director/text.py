"""STXT text chunks."""
from __future__ import annotations

from .stream import Stream


def parse_stxt(data: bytes, big: bool = True) -> str:
    s = Stream(data, big)
    if len(data) < 12:
        return data.decode("latin-1", "replace")
    offset = s.u32()
    text_len = s.u32()
    s.u32()  # style length
    s.seek(offset)
    raw = s.read(text_len)
    return raw.decode("cp1252", "replace").replace("\r", "\n")
