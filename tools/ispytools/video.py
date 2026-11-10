"""Bink video -> Ogg Theora (Godot-playable) via ffmpeg when available."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def convert_bink(src: Path, dest: Path, quality: int = 7) -> bool:
    exe = ffmpeg_path()
    if not exe:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [exe, "-y", "-loglevel", "error", "-i", str(src),
           "-c:v", "libtheora", "-q:v", str(quality),
           "-c:a", "libvorbis", "-q:a", "5", str(dest)]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=1800)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    return dest.exists() and dest.stat().st_size > 0
