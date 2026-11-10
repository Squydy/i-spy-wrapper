"""AIFF/AIFF-C -> WAV (PCM) conversion without the deprecated aifc module."""
from __future__ import annotations

import struct
import wave
from pathlib import Path


class AiffError(Exception):
    pass


def _ext80_to_int(raw: bytes) -> int:
    exp = struct.unpack(">H", raw[:2])[0]
    mant = struct.unpack(">Q", raw[2:10])[0]
    exp &= 0x7FFF
    if exp == 0 and mant == 0:
        return 0
    return int(round(mant * 2.0 ** (exp - 16383 - 63)))


def aiff_to_pcm(data: bytes) -> tuple[int, int, int, bytes]:
    """Return (channels, sample_rate, bits, little-endian pcm)."""
    if data[:4] != b"FORM":
        raise AiffError("not an AIFF file")
    form = data[8:12]
    pos = 12
    channels = rate = bits = 0
    frames = 0
    comp = b"NONE"
    ssnd = b""
    while pos + 8 <= len(data):
        cid = data[pos:pos + 4]
        clen = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + clen]
        if cid == b"COMM":
            channels, frames, bits = struct.unpack(">hIh", body[:8])
            rate = _ext80_to_int(body[8:18])
            if form == b"AIFC" and len(body) >= 22:
                comp = body[18:22]
        elif cid == b"SSND":
            offset = struct.unpack(">I", body[:4])[0]
            ssnd = body[8 + offset:]
        pos += 8 + clen + (clen & 1)
    if not channels or not ssnd:
        raise AiffError("missing COMM/SSND")
    if comp not in (b"NONE", b"twos", b"sowt", b"raw ", b"in16", b"in32"):
        raise AiffError(f"compressed AIFF-C ({comp!r})")
    if bits <= 8:
        # AIFF 8-bit is signed; WAV 8-bit is unsigned
        pcm = bytes((b + 128) & 0xFF for b in ssnd)
        bits = 8
    elif bits <= 16:
        count = len(ssnd) // 2
        if comp == b"sowt":
            pcm = ssnd[:count * 2]
        else:
            pcm = struct.pack("<%dh" % count, *struct.unpack(">%dh" % count, ssnd[:count * 2]))
        bits = 16
    elif bits <= 24:
        # downconvert 24-bit to 16-bit
        out = bytearray()
        for i in range(0, len(ssnd) - 2, 3):
            out += ssnd[i:i + 2][::-1] if comp != b"sowt" else ssnd[i + 1:i + 3]
        pcm = bytes(out)
        bits = 16
    else:
        count = len(ssnd) // 4
        samples = struct.unpack(">%di" % count, ssnd[:count * 4])
        pcm = struct.pack("<%dh" % count, *(s >> 16 for s in samples))
        bits = 16
    return channels, rate or 22050, bits, pcm


def write_wav(dest: Path, channels: int, rate: int, bits: int, pcm: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(bits // 8)
        w.setframerate(rate)
        w.writeframes(pcm)


def convert_aiff(data: bytes, dest: Path) -> bool:
    try:
        ch, rate, bits, pcm = aiff_to_pcm(data)
    except AiffError:
        return False
    write_wav(dest, ch, rate, bits, pcm)
    return True
