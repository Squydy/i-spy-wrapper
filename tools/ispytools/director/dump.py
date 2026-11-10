"""Human-readable inspection of a Director file (used by `ispytools inspect`)."""
from __future__ import annotations

from .file import DirectorFile
from .script import parse_lnam, parse_lscr
from .text import parse_stxt


def describe(df: DirectorFile, verbose: bool = False, limit: int = 60) -> str:
    out = [df.describe()]
    members = df.members()
    for owner, lib in members.items():
        out.append(f"  cast owner {owner}: {len(lib)} members")
        counts: dict[str, int] = {}
        for m in lib.values():
            counts[m.type_name] = counts.get(m.type_name, 0) + 1
        out.append("    " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        if verbose:
            for i, m in enumerate(sorted(lib.values(), key=lambda m: m.number)):
                if i >= limit:
                    out.append(f"    ... {len(lib) - limit} more")
                    break
                extra = ""
                if m.bitmap:
                    b = m.bitmap
                    extra = f" {b.width}x{b.height} bpp={b.bpp} pal={b.palette_id} reg=({b.reg_x},{b.reg_y})"
                if m.filename:
                    extra += f" file={m.filename!r}"
                out.append(f"    #{m.number:<5} {m.type_name:<9} {m.name!r}{extra}")
    lnam_ids = df.chunk_ids("Lnam")
    lscr_ids = df.chunk_ids("Lscr")
    out.append(f"  scripts: {len(lscr_ids)} Lscr, {len(lnam_ids)} Lnam")
    if verbose and lnam_ids:
        names = parse_lnam(df.read_chunk(lnam_ids[0]))
        for cid in lscr_ids[:limit]:
            info = parse_lscr(df.read_chunk(cid), names, True, df.version, cid)
            out.append(f"    Lscr {cid}: handlers={info.handlers[:12]} strings={len(info.strings)}")
            for sx in info.strings[:6]:
                out.append("       " + repr(sx[:100]))
    stxt = df.chunk_ids("STXT")
    out.append(f"  texts: {len(stxt)} STXT")
    if verbose:
        for cid in stxt[:limit]:
            txt = parse_stxt(df.read_chunk(cid))
            if txt.strip():
                out.append("    " + repr(txt[:120]))
    return "\n".join(out)
