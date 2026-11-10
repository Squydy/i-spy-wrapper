"""Turn an installed pack's Director sources into engine-friendly data:
images/<cast>/<member>.png, data/casts.json, data/scripts.json, data/score.json,
then hand off to the per-game adapter to build scenes/riddles."""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Callable

from .audio import write_wav
from .director import DirectorFile
from .director.bitmap import decode_bitd
from .director.members import CastMember
from .director.palette import builtin, parse_clut
from .director.score import parse_labels, parse_score
from .director.script import parse_lnam, parse_lscr
from .director.sound import parse_snd, parse_sndh
from .director.text import parse_stxt
from .lingo import decompile_scripts

Log = Callable[[str], None]
_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def safe_name(s: str, limit: int = 48) -> str:
    s = _SAFE.sub("_", s).strip("_")
    return s[:limit] or "member"


class CastBundle:
    """One Director file (main movie or external cast) with its parsed members."""

    def __init__(self, path: Path, label: str):
        self.path = path
        self.label = label
        self.df = DirectorFile(path)
        self.members = self.df.members()
        self.palettes: dict[int, list] = {}
        lnam = self.df.first_chunk("Lnam")
        self.names = parse_lnam(self.df.read_chunk(lnam)) if lnam is not None else []

    def all(self) -> list[CastMember]:
        return [m for lib in self.members.values() for m in lib.values()]

    def palette(self, pid: int) -> list | None:
        if pid <= 0:
            return builtin(pid)
        if pid in self.palettes:
            return self.palettes[pid]
        for lib in self.members.values():
            m = lib.get(pid)
            if m and m.type == 4:
                for k in m.resources(self.df, "CLUT"):
                    pal = parse_clut(self.df.read_chunk(k.section_id))
                    self.palettes[pid] = pal
                    return pal
        return None


def extract_game(pack: Path, images: bool = True, log: Log = print, force: bool = False) -> None:
    mf_path = pack / "manifest.json"
    manifest = json.loads(mf_path.read_text())
    gid = manifest["id"]
    t0 = time.time()
    log(f"[{gid}] extracting assets" + (" (forced rewrite)" if force else ""))
    if force:
        # rewriting bitmaps invalidates the matte bookkeeping and decompiled scripts
        for stale in (pack / "data" / "matted.json",):
            if stale.exists():
                stale.unlink()
        if (pack / "data" / "lingo").exists():
            shutil.rmtree(pack / "data" / "lingo")
    src = pack / "source"
    casts_dir = src / "casts"
    main_path = pack / manifest["source"]["mainMovie"]
    bundles: list[CastBundle] = []
    main = CastBundle(main_path, "MAIN")
    bundles.append(main)
    for cf in sorted(casts_dir.iterdir()):
        if cf.suffix.lower() in (".cxt", ".cct", ".cst"):
            try:
                bundles.append(CastBundle(cf, cf.stem.upper()))
            except Exception as exc:
                log(f"  ! {cf.name}: {exc}")

    # stage size from the main movie
    r = main.df.config.stage_rect
    if r[3] - r[1] > 0 and r[2] - r[0] > 0:
        manifest["stage"] = {"width": r[3] - r[1], "height": r[2] - r[0]}

    data_dir = pack / "data"
    data_dir.mkdir(exist_ok=True)
    img_root = pack / "images"

    casts_json: dict = {"castLibs": [], "casts": {}}
    for lib in main.df.cast_libs:
        casts_json["castLibs"].append({
            "index": lib.index, "name": lib.name, "path": lib.path,
            "minMember": lib.min_member, "maxMember": lib.max_member,
        })
    scripts_json: dict = {}
    texts_json: dict = {}
    lingo_json: dict = {}
    image_count = 0
    fail_count = 0
    sound_count = 0
    snd_root = pack / "audio" / "members"

    for b in bundles:
        entries = []
        bundle_scripts = []
        for m in sorted(b.all(), key=lambda m: m.number):
            e = {"n": m.number, "type": m.type_name, "name": m.name}
            if m.filename:
                e["file"] = m.filename
            if m.type == 6:
                out = snd_root / b.label / f"{m.number}_{safe_name(m.name)}.wav"
                if out.exists() or _write_sound(b, m, out):
                    e["audio"] = str(out.relative_to(pack)).replace("\\", "/")
                    sound_count += 1
            if m.bitmap:
                bm = m.bitmap
                e.update({"w": bm.width, "h": bm.height, "regX": bm.reg_x, "regY": bm.reg_y,
                          "bpp": bm.bpp, "palette": bm.palette_id})
                if images and bm.width > 0 and bm.height > 0:
                    out = img_root / b.label / f"{m.number}_{safe_name(m.name)}.png"
                    if force or not out.exists():
                        ok = _write_bitmap(b, m, out)
                        if ok:
                            image_count += 1
                        else:
                            fail_count += 1
                    e["image"] = str(out.relative_to(pack)).replace("\\", "/")
            if m.type in (3, 12):
                txt = _member_text(b, m)
                if txt is not None:
                    e["text"] = txt
                    texts_json[f"{b.label}:{m.number}"] = txt
            if m.type == 11:
                e["scriptType"] = m.script_type
                lscr_ids = [k.section_id for k in m.resources(b.df, "Lscr")]
                ctx_id = b.df.script_chunk(m.script_id) if m.script_id else None
                if ctx_id is not None and ctx_id not in lscr_ids:
                    lscr_ids.append(ctx_id)
                for sid in lscr_ids:
                    info = parse_lscr(b.df.read_chunk(sid), b.names, True, b.df.version, sid)
                    bundle_scripts.append({
                        "member": m.number, "name": m.name, "scriptType": m.script_type,
                        "handlers": info.handlers, "strings": info.strings,
                        "properties": info.properties, "globals": info.globals_,
                    })
            entries.append(e)
        casts_json["casts"][b.label] = {
            "file": str(b.path.relative_to(pack)).replace("\\", "/"),
            "version": b.df.version,
            "members": entries,
        }
        if bundle_scripts:
            scripts_json[b.label] = bundle_scripts
            # full Lingo source via ProjectorRays (needed for the data-driven screen tables)
            lingo_dir = data_dir / "lingo" / b.label
            if lingo_dir.exists() and any(lingo_dir.glob("*.ls")):
                lingo_json[b.label] = {p.stem: p.read_text(encoding="utf-8", errors="replace")
                                       for p in lingo_dir.glob("*.ls")}
            else:
                lingo_json[b.label] = decompile_scripts(b.path, lingo_dir, log)

    (data_dir / "casts.json").write_text(json.dumps(casts_json, indent=1))
    (data_dir / "scripts.json").write_text(json.dumps(scripts_json, indent=1))
    (data_dir / "texts.json").write_text(json.dumps(texts_json, indent=1))

    score = _score_json(main)
    (data_dir / "score.json").write_text(json.dumps(score, indent=1))

    log(f"  casts: {len(bundles)} files, images: {image_count} written, {fail_count} failed, "
        f"sounds: {sound_count}, lingo scripts: {sum(len(v) for v in lingo_json.values())}, "
        f"labels: {len(score['labels'])}")

    # per-game adapter builds scenes/riddles
    from .adapters import build_scenes
    summary = build_scenes(pack, manifest, casts_json, scripts_json, texts_json, score, log, lingo_json)

    manifest["extracted"] = True
    manifest["extractedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    manifest["scenes"] = summary
    mf_path.write_text(json.dumps(manifest, indent=2))
    log(f"[{gid}] extraction done in {time.time() - t0:.1f}s")


def rebuild_scenes(pack: Path, log: Log = print) -> None:
    """Re-run only the adapter using the cached data/*.json and data/lingo/ output."""
    mf_path = pack / "manifest.json"
    manifest = json.loads(mf_path.read_text())
    data_dir = pack / "data"
    casts_json = json.loads((data_dir / "casts.json").read_text())
    scripts_json = json.loads((data_dir / "scripts.json").read_text())
    texts_json = json.loads((data_dir / "texts.json").read_text())
    score = json.loads((data_dir / "score.json").read_text())
    lingo_json: dict = {}
    lingo_root = data_dir / "lingo"
    if lingo_root.exists():
        for d in lingo_root.iterdir():
            if d.is_dir():
                lingo_json[d.name] = {p.stem: p.read_text(encoding="utf-8", errors="replace")
                                      for p in d.glob("*.ls")}
    t0 = time.time()
    log(f"[{manifest['id']}] rebuilding scenes")
    from .adapters import build_scenes
    manifest["scenes"] = build_scenes(pack, manifest, casts_json, scripts_json, texts_json, score, log, lingo_json)
    mf_path.write_text(json.dumps(manifest, indent=2))
    log(f"[{manifest['id']}] scenes rebuilt in {time.time() - t0:.1f}s")


def _member_text(b: CastBundle, m: CastMember) -> str | None:
    for k in m.resources(b.df, "STXT"):
        return parse_stxt(b.df.read_chunk(k.section_id))
    for k in m.resources(b.df, "XMED"):
        raw = b.df.read_chunk(k.section_id)
        txt = _xmed_text(raw)
        if txt:
            return txt
    return None


def _xmed_text(raw: bytes) -> str:
    """Rich-text (XMED) members embed RTF-ish text; pull printable runs."""
    try:
        s = raw.decode("latin-1")
    except Exception:
        return ""
    if "\\rtf" in s:
        body = re.sub(r"\\[a-z]+-?\d* ?", " ", s)
        body = re.sub(r"[{}]", "", body)
        return re.sub(r"\s+", " ", body).strip()[:2000]
    return ""


def _write_sound(b: CastBundle, m: CastMember, out: Path) -> bool:
    # KEY* may reference chunks that are absent from the Afterburner map; only use present ones
    res = {k.fourcc: k.section_id for k in m.resources(b.df) if k.section_id in b.df.chunks}
    pcm = None
    try:
        if "sndH" in res and "sndS" in res:
            pcm = parse_sndh(b.df.read_chunk(res["sndH"]), b.df.read_chunk(res["sndS"]))
        elif "snd " in res and b.df.chunks[res["snd "]].length > 0:
            pcm = parse_snd(b.df.read_chunk(res["snd "]))
    except Exception:
        pcm = None
    if pcm is None or not pcm.data:
        return False
    write_wav(out, pcm.channels, pcm.rate, pcm.bits, pcm.data)
    return True


def _write_bitmap(b: CastBundle, m: CastMember, out: Path) -> bool:
    try:
        from PIL import Image
    except ImportError:
        return False
    bitd = m.resources(b.df, "BITD")
    if not bitd:
        return False
    bm = m.bitmap
    assert bm is not None
    data = b.df.read_chunk(bitd[0].section_id)
    pal = b.palette(bm.palette_id) if bm.bpp <= 8 else None
    try:
        w, h, rgba = decode_bitd(data, bm, pal)
    except Exception:
        return False
    if w == 0:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.frombytes("RGBA", (w, h), rgba).save(out, optimize=False)
    return True


def _score_json(main: CastBundle) -> dict:
    df = main.df
    labels: dict[int, str] = {}
    lid = df.first_chunk("VWLB")
    if lid is not None:
        try:
            labels = parse_labels(df.read_chunk(lid))
        except Exception:
            labels = {}
    frames = []
    sid = df.first_chunk("VWSC")
    if sid is not None:
        try:
            frames = parse_score(df.read_chunk(sid))
        except Exception:
            frames = []
    out_frames = []
    for f in frames:
        sprites = [sp.to_dict() for sp in f.sprites.values() if sp.member]
        if sprites or f.index in labels:
            out_frames.append({"frame": f.index, "sprites": sprites})
    return {
        "labels": {str(k): v for k, v in sorted(labels.items())},
        "frameCount": len(frames),
        "frames": out_frames,
    }
