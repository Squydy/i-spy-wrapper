# ispytools

Python 3.12 command line tools that turn an original I SPY disc (ISO or copied disc folder)
into a normalized game pack under `games/<id>/` that the Godot engine in `engine/` can run.

Supported titles (Macromedia Director 7 / 8.5 / 10):

| id              | title                        | fingerprint     | Director |
|-----------------|------------------------------|-----------------|----------|
| `treasure_hunt` | I SPY Treasure Hunt          | `ISPYMAIN6.dxr` | 7        |
| `fantasy`       | I SPY Fantasy                | `ISPYMAIN7.dxr` | 8.5      |
| `spooky_deluxe` | I SPY Spooky Mansion Deluxe  | `ISPYMAIN8.dxr` | 8.5      |
| `mystery`       | I SPY Mystery                | `ISPYMAIN9.dcr` | 10 (Afterburner) |

## Requirements

- Python 3.12 with Pillow (`pip install pillow`)
- `ffmpeg` on `PATH` (or `C:\FFmpeg\ffmpeg.exe`) for Bink -> Ogg Theora video conversion
- [ProjectorRays](https://github.com/ProjectorRays/ProjectorRays) for Lingo decompilation; it is
  downloaded into `../.tools/` automatically on first use

## Usage

```
cd tools
python -m ispytools detect  "..\I SPY Treasure Hunt.ISO"
python -m ispytools install "..\I SPY Treasure Hunt.ISO"        # copy + convert + extract
python -m ispytools install "..\I Spy Fantasy.iso" --no-extract --no-video
python -m ispytools extract treasure_hunt [--force] [--no-images]
python -m ispytools list
python -m ispytools inspect ..\games\treasure_hunt\source\casts\BHP.cxt -v
```

`--games <dir>` overrides the pack root (default `<repo>/games`). The Godot launcher invokes the
same commands for "Install from ISO..." and "Re-extract assets".

## Pack layout

```
games/<id>/
  manifest.json        id, title, director, stage, source, extracted, scenes summary
  source/              main movie + cast files copied from the disc (+ original .bik videos)
  images/<CAST>/       decoded bitmaps  <n>_<name>.png (matte alpha applied to sprites)
  audio/               external AIFF -> WAV      audio/members/<CAST>/ embedded sounds -> WAV
  video/               Bink -> Ogg Theora
  data/casts.json      every cast member (type, name, size, registration point, file refs)
  data/scripts.json    Lingo handler names / string literals per script member
  data/lingo/<CAST>/   full decompiled Lingo source (ProjectorRays)
  data/texts.json, score.json
  scenes/index.json    entry screen + screen list;  scenes/<ID>.json  per-screen data
```

## Modules

- `director/` — RIFX/XFIR/Afterburner container, cast members, bitmaps (1/2/4/8/16/32 bpp,
  PackBits), palettes, sounds (`snd `/`sndH`), text, score, Lingo name tables
- `iso9660.py` — pure Python ISO 9660 / Joliet reader (no mounting required)
- `detect.py`, `install.py` — title fingerprinting and disc -> pack copy/convert
- `extract.py` — cast walk: images, sounds, data json, Lingo decompile, then the adapter
- `lingo.py`, `lingo_literals.py` — ProjectorRays driver and a parser for Lingo property-list literals
- `adapters/` — per-title translation of the game's data tables into screen JSON
  - `treasure_hunt.py` — Black Hammer "BHP" declarative screen tables (nav + riddle screens)
  - `blackhammer.py` — SCREENDADDY framework titles (Fantasy, Spooky Deluxe, Mystery)
  - `generic.py` — fallback: one viewable scene per cast background
