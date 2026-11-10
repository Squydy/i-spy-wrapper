"""Decompile Lingo with ProjectorRays (MPL-2.0, downloaded on demand into .tools/)."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable

PR_URL = "https://github.com/ProjectorRays/ProjectorRays/releases/download/v0.2.0/projectorrays-0.2.0.exe"
Log = Callable[[str], None]


def tools_dir() -> Path:
    return Path(__file__).resolve().parents[2] / ".tools"


def projectorrays_path(log: Log = print, allow_download: bool = True) -> Path | None:
    exe = tools_dir() / ("projectorrays.exe" if sys.platform == "win32" else "projectorrays")
    if exe.exists():
        return exe
    found = shutil.which("projectorrays")
    if found:
        return Path(found)
    if not allow_download or sys.platform != "win32":
        return None
    try:
        exe.parent.mkdir(parents=True, exist_ok=True)
        log("  downloading ProjectorRays (Lingo decompiler)...")
        urllib.request.urlretrieve(PR_URL, exe)
        return exe
    except Exception as exc:  # network issues etc.
        log(f"  ! could not download ProjectorRays: {exc}")
        return None


def decompile_scripts(director_file: Path, out_dir: Path, log: Log = print) -> dict[str, str]:
    """Decompile every script in a Director file. Returns {script label: source}.
    Also stores .ls files under out_dir."""
    exe = projectorrays_path(log)
    if exe is None:
        return {}
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="ispy_pr_") as tmp:
        try:
            subprocess.run([str(exe), "decompile", str(director_file), "-o", tmp, "--dump-scripts"],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
        except (OSError, subprocess.TimeoutExpired) as exc:
            log(f"  ! projectorrays failed on {director_file.name}: {exc}")
            return {}
        for ls in Path(tmp).rglob("*.ls"):
            try:
                text = ls.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if not text.strip():
                continue
            label = ls.stem
            result[label] = text
            (out_dir / ls.name).write_text(text, encoding="utf-8")
    return result
