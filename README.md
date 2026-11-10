# I SPY Engine *AI Project*

A modern desktop engine for the four Scholastic **I SPY** games that shipped as Macromedia Director titles. You install a disc into `games/`; launching the engine lists the installed games and plays them from the original art, sound, and screen data, scaled to whatever window size you use.

Supported discs:

| Pack id | Title | Director |
|---|---|---|
| `treasure_hunt` | I SPY Treasure Hunt | 7 |
| `fantasy` | I SPY Fantasy | 8.5 |
| `spooky_deluxe` | I SPY Spooky Mansion Deluxe | 8.5 |
| `mystery` | I SPY Mystery | 10 (Afterburner) |

**Treasure Hunt is playable**: the launcher, any-resolution stage, navigation screens, and the riddle loop (find the objects, hear the words, finish the picture, collect the map clue). Fantasy, Spooky Mansion Deluxe, and Mystery install from ISO and extract their assets; their screen adapters are in progress.

Game discs and installed packs stay on your machine. They are gitignored. This repo is the engine and the tools only.

## Requirements

- Windows
- [Godot 4.3](https://godotengine.org/) (a portable copy in `.tools/` works; that folder is gitignored)
- Python 3.12 and [Pillow](https://pypi.org/project/pillow/) (`pip install pillow`)
- [ffmpeg](https://ffmpeg.org/) on `PATH`, or `C:\FFmpeg\ffmpeg.exe`, if you want Bink video converted (Fantasy, Spooky, Mystery)
- Your own ISO or a copied disc folder for each game

The extractor downloads [ProjectorRays](https://github.com/ProjectorRays/ProjectorRays) into `.tools/` the first time it needs to decompile Lingo.

## Quick start

From the repo root:

```
cd tools
pip install pillow
python -m ispytools install "..\I SPY Treasure Hunt.ISO"
```

Then open `engine/project.godot` in Godot 4.3 and press Play, or from the repo root:

```
.\.tools\Godot_v4.3-stable_win64.exe --path engine
```

The library lists every pack under `games/`. **Play** launches an extracted game. **Install from ISO...** and **Re-extract assets** call the same Python tools.

Useful flags while testing:

```
.\.tools\Godot_v4.3-stable_win64.exe --path engine -- --play=treasure_hunt --screen=IC --hunt=A
```

`--play` needs a `--` in front of it so Godot treats it as a user argument.

## Playing

The original 640×480 stage is scaled to the window and letterboxed. Mouse clicks are mapped back into stage coordinates, so hit testing stays on the original art.

| Key | Action |
|---|---|
| Esc | Pause menu (hunt A/B/C, scaling, reset, library) |
| F11 | Fullscreen |
| F3 | Draw hotspot rectangles |
| Backspace | Previous screen |

Pause menu also switches **smooth** and **integer** scaling. Progress (found objects, solved riddles, current screen, hunt) is saved per game under Godot's user data folder.

## Tools

```
cd tools
python -m ispytools detect  "..\I Spy Fantasy.iso"
python -m ispytools install "..\I Spy Fantasy.iso"          # copy, convert audio/video, extract
python -m ispytools install "..\Spooky DLX.iso" --no-video  # skip the slow Bink conversion
python -m ispytools extract treasure_hunt                   # rebuild images, audio, scenes
python -m ispytools extract treasure_hunt --force           # rewrite bitmaps already on disk
python -m ispytools scenes  fantasy                         # rebuild scenes only, from cached data
python -m ispytools list
python -m ispytools inspect games\treasure_hunt\source\casts\BHP.cxt -v
```

`--games <dir>` overrides the pack root (default is `<repo>/games`).

Details of the Director parser and the pack schema are in [`tools/README.md`](tools/README.md).

## Layout

```
engine/     Godot 4 project: library, stage, scene player, audio, saves
tools/      Python installer and Director extractor (python -m ispytools)
games/      Installed packs (gitignored except this folder's README)
.tools/     Local Godot and ProjectorRays binaries (gitignored)
```

An installed pack looks like this:

```
games/treasure_hunt/
  manifest.json
  source/            main movie and cast files copied from the disc
  images/<CAST>/     bitmaps as PNG
  audio/             WAV (disc AIFF and embedded Director sounds)
  video/             Ogg Theora, when Bink was converted
  data/              cast index, decompiled Lingo, score dump
  scenes/<ID>.json   one file per screen, plus scenes/index.json
```

## What v1 does

- Install a disc (ISO or folder) without mounting it
- Decode Director bitmaps, sounds, and the Lingo tables that describe each screen
- Launch any installed pack from a library screen
- Draw the original stage at any window size, smooth or integer, with letterboxing
- Play Treasure Hunt navigation and riddle screens, including hunts A, B, and C
- Remember finds and solved riddles

Later, on purpose: zoom and pan, hint highlights, a richer help sequence, intro skipping, controller support, and the Fantasy / Spooky / Mystery minigames (rocket, ghost hunt, dungeon, case-file puzzles). The scene JSON and the pause menu are where those hook in.
