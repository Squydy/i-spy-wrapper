"""Endian-aware byte stream helpers."""
from __future__ import annotations

import struct


class Stream:
    __slots__ = ("data", "pos", "big")

    def __init__(self, data: bytes, big_endian: bool = True, pos: int = 0):
        self.data = data
        self.pos = pos
        self.big = big_endian

    # -- positioning -----------------------------------------------------
    def __len__(self) -> int:
        return len(self.data)

    def eof(self) -> bool:
        return self.pos >= len(self.data)

    def remaining(self) -> int:
        return len(self.data) - self.pos

    def seek(self, pos: int) -> None:
        self.pos = pos

    def skip(self, n: int) -> None:
        self.pos += n

    # -- primitives ------------------------------------------------------
    def _fmt(self, code: str) -> str:
        return (">" if self.big else "<") + code

    def read(self, n: int) -> bytes:
        b = self.data[self.pos:self.pos + n]
        self.pos += n
        return b

    def u8(self) -> int:
        v = self.data[self.pos]
        self.pos += 1
        return v

    def i8(self) -> int:
        v = struct.unpack_from("b", self.data, self.pos)[0]
        self.pos += 1
        return v

    def u16(self) -> int:
        v = struct.unpack_from(self._fmt("H"), self.data, self.pos)[0]
        self.pos += 2
        return v

    def i16(self) -> int:
        v = struct.unpack_from(self._fmt("h"), self.data, self.pos)[0]
        self.pos += 2
        return v

    def u32(self) -> int:
        v = struct.unpack_from(self._fmt("I"), self.data, self.pos)[0]
        self.pos += 4
        return v

    def i32(self) -> int:
        v = struct.unpack_from(self._fmt("i"), self.data, self.pos)[0]
        self.pos += 4
        return v

    def fourcc(self) -> str:
        """Read a FourCC, honouring file endianness (little-endian files store them reversed)."""
        raw = self.read(4)
        if not self.big:
            raw = raw[::-1]
        return raw.decode("latin-1")

    def varint(self) -> int:
        """Afterburner variable-length integer (7 bits per byte, MSB first)."""
        val = 0
        while True:
            b = self.u8()
            val = (val << 7) | (b & 0x7F)
            if not (b & 0x80):
                return val

    def pstring(self) -> str:
        n = self.u8()
        return self.read(n).decode("latin-1")

    def cstring(self) -> str:
        end = self.data.index(b"\x00", self.pos)
        s = self.data[self.pos:end].decode("latin-1")
        self.pos = end + 1
        return s

    def rect(self) -> tuple[int, int, int, int]:
        """Director rect order: top, left, bottom, right."""
        top, left, bottom, right = self.i16(), self.i16(), self.i16(), self.i16()
        return top, left, bottom, right
