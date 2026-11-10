"""'snd ' resources (classic Mac sound format) -> PCM."""
from __future__ import annotations

import struct
from dataclasses import dataclass

from .stream import Stream


@dataclass
class PCM:
    rate: int
    channels: int
    bits: int
    data: bytes  # little-endian signed (16-bit) or unsigned (8-bit) interleaved


def parse_sndh(header: bytes, samples: bytes) -> PCM | None:
    """Director 6+ 'sndH' header + 'sndS' sample chunk (big-endian PCM)."""
    if len(header) < 80:
        return None
    w = struct.unpack(">20I", header[:80])
    nbytes = w[1] or w[8] or len(samples)
    rate = w[11] or 22050
    bits = w[17] or 16
    channels = w[19] or 1
    pcm = samples[:nbytes]
    if bits == 16:
        count = len(pcm) // 2
        pcm = struct.pack("<%dh" % count, *struct.unpack(">%dh" % count, pcm[:count * 2]))
    elif bits == 8:
        # Director stores 8-bit as unsigned already (Mac convention); keep as is
        pass
    else:
        return None
    return PCM(rate, channels, bits, pcm)


def parse_snd(data: bytes) -> PCM | None:
    s = Stream(data, True)
    if len(data) < 20:
        return None
    fmt = s.u16()
    if fmt == 1:
        n = s.u16()
        s.skip(n * 6)
    elif fmt == 2:
        s.u16()
    else:
        return None
    ncmd = s.u16()
    header_off = None
    for _ in range(ncmd):
        cmd = s.u16()
        s.u16()
        param2 = s.u32()
        if cmd & 0x7FFF in (0x51, 0x50):  # bufferCmd / soundCmd
            header_off = param2
    if header_off is None or header_off + 22 > len(data):
        return None
    s.seek(header_off)
    s.u32()  # samplePtr
    length_or_channels = s.u32()
    rate = s.u32() >> 16
    s.u32()  # loop start
    s.u32()  # loop end
    encode = s.u8()
    s.u8()  # base frequency
    if encode == 0x00:  # standard: 8-bit mono
        pcm = s.read(length_or_channels)
        return PCM(rate or 22050, 1, 8, pcm)
    if encode in (0xFF, 0xFE):  # extended / compressed header
        channels = length_or_channels or 1
        frames = s.u32()
        s.read(10)  # AIFF 80-bit sample rate
        s.u32()  # marker chunk
        if encode == 0xFF:
            s.u32()  # instrument chunks
            s.u32()  # AES recording
            bits = s.u16()
            s.read(14)
        else:
            s.read(4)  # format
            s.u32()  # future use
            s.u32()  # state vars
            s.u32()  # left over samples
            comp_id = s.i16()
            s.u16()  # packet size
            s.u16()  # synth id
            bits = s.u16()
            if comp_id != 0 and comp_id != -1:
                return None  # MACE/IMA not supported here
        bits = bits or 8
        nbytes = frames * channels * (bits // 8)
        pcm = s.read(nbytes)
        if bits == 16:
            # big-endian -> little-endian
            count = len(pcm) // 2
            pcm = struct.pack("<%dh" % count, *struct.unpack(">%dh" % count, pcm[:count * 2]))
        return PCM(rate or 22050, channels, bits, pcm)
    return None
