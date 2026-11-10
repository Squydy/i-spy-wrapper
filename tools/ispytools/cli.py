"""Command line entry point: python -m ispytools <command>."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ispytools", description="I SPY disc installer / extractor")
    ap.add_argument("--games", help="games root directory (default: <repo>/games)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("detect", help="identify a disc image or folder")
    p.add_argument("src")

    p = sub.add_parser("install", help="install disc(s) into the games directory")
    p.add_argument("src", nargs="+", help="ISO files or disc folders")
    p.add_argument("--no-video", action="store_true", help="skip Bink -> Ogg conversion")
    p.add_argument("--no-audio", action="store_true", help="skip AIFF -> WAV conversion")
    p.add_argument("--no-extract", action="store_true", help="do not run asset extraction after install")
    p.add_argument("--force", action="store_true", help="reinstall over an existing pack")

    p = sub.add_parser("extract", help="(re)build images/data/scenes for an installed game")
    p.add_argument("game", nargs="*", help="game ids (default: all installed)")
    p.add_argument("--no-images", action="store_true", help="skip bitmap decoding")
    p.add_argument("--force", action="store_true", help="rewrite already extracted images")

    p = sub.add_parser("scenes", help="rebuild scenes/*.json from cached extraction data (fast)")
    p.add_argument("game", nargs="*", help="game ids (default: all installed)")

    p = sub.add_parser("list", help="list installed games")

    p = sub.add_parser("inspect", help="dump a Director file's structure")
    p.add_argument("file")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--limit", type=int, default=60)

    args = ap.parse_args(argv)
    from .install import games_root, install, list_installed
    root = games_root(args.games)

    if args.cmd == "detect":
        from .detect import detect
        r = detect(Path(args.src))
        if not r:
            print("unrecognised")
            return 1
        print(f"{r[0].id}\t{r[0].title}\tdata={r[1]!r}")
        return 0

    if args.cmd == "install":
        from .extract import extract_game
        for src in args.src:
            dest = install(Path(src), root, with_video=not args.no_video,
                           with_audio=not args.no_audio, force=args.force)
            if not args.no_extract:
                extract_game(dest)
        return 0

    if args.cmd == "extract":
        from .extract import extract_game
        ids = args.game or [m["id"] for m in list_installed(root)]
        for gid in ids:
            extract_game(root / gid, images=not args.no_images, force=args.force)
        return 0

    if args.cmd == "scenes":
        from .extract import rebuild_scenes
        ids = args.game or [m["id"] for m in list_installed(root)]
        for gid in ids:
            rebuild_scenes(root / gid)
        return 0

    if args.cmd == "list":
        for m in list_installed(root):
            flag = "extracted" if m.get("extracted") else "installed"
            print(f"{m['id']:<16} {m['title']:<32} {flag}")
        return 0

    if args.cmd == "inspect":
        from .director import DirectorFile
        from .director.dump import describe
        df = DirectorFile(args.file)
        print(describe(df, verbose=args.verbose, limit=args.limit))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
