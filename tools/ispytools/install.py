"""Install a disc (ISO or folder) into games/<id>/."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from . import __version__
from .audio import convert_aiff
from .detect import GameDef, SourceTree, detect
from .video import convert_bink, ffmpeg_path

Log = Callable[[str], None]


def games_root(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit)
    # tools/ispytools/install.py -> repo root / games
    return Path(__file__).resolve().parents[2] / "games"


def _dedupe_largest(files: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Hybrid Mac/PC discs expose resource-fork twins with identical names; keep the largest."""
    best: dict[str, tuple[str, int]] = {}
    for rel, size in files:
        key = rel.lower()
        if key not in best or size > best[key][1]:
            best[key] = (rel, size)
    return list(best.values())


def install(src: Path, root: Path, log: Log = print, with_video: bool = True,
            with_audio: bool = True, force: bool = False) -> Path:
    found = detect(src)
    if not found:
        raise SystemExit(f"{src}: not a recognised I SPY disc (expected DATA/ISPYMAIN*.dxr|dcr)")
    game, data_dir = found
    dest = root / game.id
    log(f"[{game.id}] {game.title} <- {src}")
    if dest.exists() and (dest / "manifest.json").exists() and not force:
        log(f"[{game.id}] already installed at {dest} (use --force to reinstall)")
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    tree = SourceTree(src)
    t0 = time.time()
    try:
        _copy_source(tree, data_dir, game, dest, log)
        audio_count = _convert_audio(tree, data_dir, game, dest, log) if with_audio else 0
        video_info = _convert_video(tree, data_dir, game, dest, log, with_video)
    finally:
        tree.close()
    manifest = {
        "schema": 1,
        "id": game.id,
        "title": game.title,
        "shortTitle": game.short,
        "director": game.director,
        "stage": {"width": game.stage[0], "height": game.stage[1]},
        "source": {
            "disc": str(src),
            "mainMovie": f"source/{game.main_movie}",
            "casts": "source/casts",
            "castExt": game.cast_ext,
        },
        "audio": {"dir": "audio", "count": audio_count},
        "video": video_info,
        "extracted": False,
        "installedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "toolsVersion": __version__,
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2))
    log(f"[{game.id}] installed in {time.time() - t0:.1f}s -> {dest}")
    return dest


def _copy_source(tree: SourceTree, data_dir: str, game: GameDef, dest: Path, log: Log) -> None:
    src_dir = dest / "source"
    casts_dir = src_dir / "casts"
    casts_dir.mkdir(parents=True, exist_ok=True)
    movie = tree.find_file(data_dir, game.main_movie)
    if movie is None:
        raise SystemExit(f"main movie {game.main_movie} missing")
    # the movie may appear twice on hybrid discs; pick the biggest copy
    movie_entries = [(rel, size) for rel, size in tree.list_files(data_dir)
                     if rel.lower().endswith("/" + game.main_movie.lower()) or rel.lower() == game.main_movie.lower()]
    movie_rel = max(movie_entries, key=lambda e: e[1])[0] if movie_entries else movie
    log(f"  copying {game.main_movie}")
    tree.copy(movie_rel, src_dir / game.main_movie)
    # loose casts at DATA level (DEFAULT.cct, EXTERNAL.cxt)
    for rel, size in _dedupe_largest(tree.list_files(data_dir)):
        name = rel.split("/")[-1]
        if name.lower().endswith((".cxt", ".cct", ".cst")) and size > 0:
            tree.copy(rel, casts_dir / name)
    casts_rel = tree.find_dir(data_dir, game.casts_dir)
    if casts_rel:
        files = _dedupe_largest(tree.list_files(casts_rel))
        log(f"  copying {len(files)} cast files")
        for rel, size in files:
            name = rel.split("/")[-1]
            if size <= 0 or name.startswith("."):
                continue
            tree.copy(rel, casts_dir / name)


def _convert_audio(tree: SourceTree, data_dir: str, game: GameDef, dest: Path, log: Log) -> int:
    audio_rel = tree.find_dir(data_dir, game.audio_dir)
    if not audio_rel:
        log("  no audio folder found")
        return 0
    out_dir = dest / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    skipped = 0
    # audio folders may contain subfolders (Treasure Hunt: AIFF/RIDDLES etc.)
    stack = [audio_rel]
    while stack:
        cur = stack.pop()
        for name, is_dir, size in tree._names(cur):
            rel = f"{cur}/{name}"
            if is_dir:
                stack.append(rel)
                continue
            if name.startswith(".") or size <= 0:
                continue
            low = name.lower()
            stem = Path(name).stem
            if low.endswith((".aif", ".aiff", ".aifc")):
                data = tree.read(rel)
                if convert_aiff(data, out_dir / f"{stem.upper()}.wav"):
                    count += 1
                else:
                    skipped += 1
            elif low.endswith((".wav", ".mp3", ".ogg")):
                tree.copy(rel, out_dir / name.upper())
                count += 1
    log(f"  audio: {count} converted, {skipped} skipped")
    return count


def _convert_video(tree: SourceTree, data_dir: str, game: GameDef, dest: Path, log: Log,
                   with_video: bool) -> dict:
    info: dict = {"dir": "video", "count": 0, "converted": 0, "format": "ogv"}
    if not game.video_dir:
        return info
    video_rel = tree.find_dir(data_dir, game.video_dir)
    if not video_rel:
        return info
    raw_dir = dest / "source" / "video"
    out_dir = dest / "video"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = [(rel, size) for rel, size in _dedupe_largest(tree.list_files(video_rel))
             if rel.lower().endswith(".bik") and size > 0 and not rel.split("/")[-1].startswith(".")]
    info["count"] = len(files)
    log(f"  copying {len(files)} Bink videos")
    for rel, _ in files:
        tree.copy(rel, raw_dir / rel.split("/")[-1])
    if not with_video:
        return info
    if not ffmpeg_path():
        log("  ffmpeg not found: videos kept as .bik only (engine will skip them)")
        return info
    log("  converting videos to Ogg Theora (this can take a few minutes)")
    for i, (rel, _) in enumerate(files, 1):
        name = rel.split("/")[-1]
        ogv = out_dir / (Path(name).stem.upper() + ".ogv")
        if ogv.exists():
            info["converted"] += 1
            continue
        if convert_bink(raw_dir / name, ogv):
            info["converted"] += 1
        if i % 10 == 0:
            log(f"    {i}/{len(files)}")
    log(f"  video: {info['converted']}/{len(files)} converted")
    return info


def list_installed(root: Path) -> list[dict]:
    out = []
    if not root.exists():
        return out
    for d in sorted(root.iterdir()):
        mf = d / "manifest.json"
        if mf.exists():
            try:
                out.append(json.loads(mf.read_text()))
            except json.JSONDecodeError:
                pass
    return out
