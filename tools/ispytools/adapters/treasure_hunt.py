"""I SPY Treasure Hunt (Director 7, Black Hammer 2001) adapter.

The game is fully data-driven: BHP.cxt movie scripts return Lingo property lists that
describe every screen (backgrounds, nav buttons, riddle objects, word strips, sounds).
We decompile them with ProjectorRays, parse the literals and emit engine screens.

Member numbering: values >= 65536 encode (castLib << 16) | member. castLib 1 = the main
movie's internal cast ("MAIN"), castLib 2 = BHP code cast, castLib 3 = the per-screen media
cast swapped in from casts/<CODE>.cxt. Plain values < 65536 are MAIN members."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..lingo_literals import Point, Rect, Symbol, find_assignments
from ..matte import apply_matte_file
from .common import Log, write_json

STAGE_W, STAGE_H = 640, 480
LOC = (320, 240)

# handler -> screen code
RIDDLE_HANDLERS = {
    "getGeneralStoreRiddleArea": "GS", "getIceCreamRiddleArea": "IC", "getTackleBoxRiddleArea": "TB",
    "getShipWreckRiddleArea": "SW", "getToyWindowRiddleArea": "TW", "getDuckPondRiddleArea": "DP",
    "getBarnRiddleArea": "BN", "getPaintingRiddleArea": "PT", "getLighthouseRiddleArea": "LV",
    "getExhibitRiddleArea": "EX", "getToolCabinetRiddleArea": "TC", "getPicnicRiddleArea": "PN",
    "getDisplayRiddleArea": "DC", "getDungeonRiddleArea": "DU", "getBoatLoftRiddleArea": "BL",
    "getFortBinocularsRiddleArea": "FB", "getBulletinBoardRiddleArea": "BB", "getRuinsRiddleArea": "RU",
    "getNatureRiddleArea": "NT", "getWellRiddleArea": "WL",
}

BUTTON_ACTIONS = {
    "GLHELP": "help", "MHELP": "help", "GLBACK": "back", "MBACK": "back", "GLMAP": "map", "MMAP": "map",
    "MNEWGAME": "newgame", "MSSTOP": "quit", "GL_EAR": "readriddle",
}


def _title_from_handler(name: str) -> str:
    core = name[len("get"):-len("RiddleArea")] if name.endswith("RiddleArea") else name
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", core)


class Resolver:
    def __init__(self, pack: Path, casts: dict, log: Log):
        self.pack = pack
        self.casts = casts
        self.log = log
        self.by_label: dict[str, dict[int, dict]] = {}
        for label, c in casts["casts"].items():
            self.by_label[label] = {m["n"]: m for m in c["members"]}
        self.media = "MAIN"
        self.matted: set[str] = set()
        matted_file = pack / "data" / "matted.json"
        if matted_file.exists():
            import json
            self.matted = set(json.loads(matted_file.read_text()))
        self.audio_files = {}
        adir = pack / "audio"
        if adir.exists():
            for f in adir.glob("*.wav"):
                self.audio_files[f.stem.upper()] = f"audio/{f.name}"

    def save(self) -> None:
        import json
        (self.pack / "data" / "matted.json").write_text(json.dumps(sorted(self.matted)))

    # ---- members
    def member(self, value: Any) -> dict | None:
        if not isinstance(value, int) or value <= 0:
            return None
        lib, n = (value >> 16, value & 0xFFFF) if value >= 65536 else (1, value)
        if lib == 1:
            label = "MAIN"
        elif lib == 2:
            label = "BHP"
        else:
            label = self.media
        m = self.by_label.get(label, {}).get(n)
        if m is None and lib == 3:
            # some screens reference the previous media cast; search everywhere as a fallback
            for lbl, table in self.by_label.items():
                if n in table and table[n].get("type") == "bitmap" and lbl not in ("MAIN", "BHP"):
                    return table[n]
        return m

    def sprite(self, value: Any, loc: tuple[int, int] = LOC, matte: bool = True) -> dict | None:
        """Bitmap member placed at loc using its registration point -> {image, rect}."""
        m = self.member(value)
        if not m or m.get("type") != "bitmap" or not m.get("image"):
            return None
        left = loc[0] - m.get("regX", 0)
        top = loc[1] - m.get("regY", 0)
        if matte:
            self._matte(m["image"])
        return {"image": m["image"], "rect": [left, top, left + m["w"], top + m["h"]], "member": m["n"],
                "name": m.get("name", "")}

    def frames(self, values: Any, loc: tuple[int, int] = LOC) -> list[dict]:
        if not isinstance(values, list):
            return []
        out = []
        for v in values:
            s = self.sprite(v, loc)
            if s:
                out.append(s)
        return out

    def _matte(self, rel: str) -> None:
        if rel in self.matted:
            return
        path = self.pack / rel
        if path.exists():
            try:
                apply_matte_file(path, "matte")
            except Exception as exc:
                self.log(f"  ! matte failed for {rel}: {exc}")
        self.matted.add(rel)

    # ---- sounds
    def sound(self, value: Any) -> str | None:
        if isinstance(value, list) and value:
            name = value[-1]
            if isinstance(name, str):
                stem = Path(name).stem.upper()
                return self.audio_files.get(stem)
            return None
        m = self.member(value)
        if m and m.get("type") == "sound":
            return m.get("audio")
        return None


def _rect(v: Any) -> list[int] | None:
    return v.as_list() if isinstance(v, Rect) else None


def _screen_ref(v: Any) -> str:
    """Screen codes appear as strings or symbols (#EN); normalise to an upper-case code."""
    return _sym(v).lstrip("#").upper() if v is not None else ""


def _sym(v: Any) -> str:
    if isinstance(v, Symbol):
        return v.name
    return str(v) if v is not None else ""


def _button(r: Resolver, d: dict, default_action: str | None = None) -> dict | None:
    neut = r.sprite(d.get("pNeutMember", d.get("pMember")))
    if not neut:
        return None
    name = _sym(d.get("pName")).upper()
    btn = {
        "id": name.lower(),
        "action": BUTTON_ACTIONS.get(name, default_action or name.lower()),
        "image": neut["image"], "rect": neut["rect"],
        "rollImage": (r.sprite(d.get("pRollMember")) or {}).get("image"),
        "downImage": (r.sprite(d.get("pDownMember")) or {}).get("image"),
        "disabledImage": (r.sprite(d.get("pDisMember")) or {}).get("image"),
        "downSound": r.sound(d.get("pDownSound")),
        "upSound": r.sound(d.get("pUpSound")),
        "rollSound": r.sound(d.get("pRollSound")),
    }
    return btn


def _anim_object(r: Resolver, d: dict) -> dict | None:
    """ANIMPL_RIDDLE_* objects (clickable riddle items)."""
    loc = d.get("pLoc")
    loc_t = (loc.x, loc.y) if isinstance(loc, Point) else LOC
    base = r.sprite(d.get("pMember"), loc_t)
    if not base:
        return None
    frames = r.frames(d.get("pAnimMembers"), loc_t)
    multi = d.get("pMultiMember", 0)
    rest_after = r.sprite(multi, loc_t) if isinstance(multi, int) and multi else None
    found = None
    if d.get("pStateChange"):
        # state-change objects stay on their final frame (or an explicit replacement member) once found
        found = rest_after or (frames[-1] if frames else None)
    return {
        "id": _sym(d.get("pName")),
        "image": base["image"], "rect": base["rect"],
        "frames": [f["image"] for f in frames],
        "frameRects": [f["rect"] for f in frames],
        "fps": d.get("pSpeed", 10) or 10,
        "sound": r.sound(d.get("pAnimSound")),
        "stateChange": bool(d.get("pStateChange", 0)),
        "hotspot": _rect(d.get("pInitRect")) if d.get("pHotSpotExist") else None,
        "foundHotspot": _rect(d.get("pNewHotSpotRect")) if d.get("pRectChange") else None,
        "foundImage": found["image"] if found else None,
        "foundRect": found["rect"] if found else None,
    }


def _riddle_variant(r: Resolver, d: dict) -> dict:
    riddle = d.get("pRiddle", {}) or {}
    strip = riddle.get("pRiddleStrip", {}) or {}

    def prop(key: str, default: Any = None) -> Any:
        """Riddle-level properties may sit on the area or inside pRiddle depending on the screen."""
        if key in riddle:
            return riddle[key]
        return d.get(key, default)
    objects = []
    for od in riddle.get("pRiddleObjectList", []) or []:
        if not isinstance(od, dict):
            continue
        if "pClickAnimObjList" in od:  # multi-part object
            parts = [p for p in (_anim_object(r, pd) for pd in od["pClickAnimObjList"]) if p]
            objects.append({
                "id": _sym(od.get("pName")),
                "multi": True,
                "parts": parts,
                "clickSounds": [r.sound(s) for s in od.get("pClickedSoundList", []) or []],
                "allFoundSound": r.sound(od.get("pAllFoundAudio")),
            })
        else:
            o = _anim_object(r, od)
            if o:
                objects.append(o)

    words = []
    rect_list = [x for x in (riddle.get("pRiddleWordRectList") or []) if isinstance(x, dict)]
    used = set()
    for wd in strip.get("pRiddleWordList", []) or []:
        if not isinstance(wd, dict):
            continue
        found = r.sprite(wd.get("pFoundMember"))
        click_snd = wd.get("pClickSound")
        rect = None
        for i, rd in enumerate(rect_list):
            if i not in used and rd.get("pClickSound") == click_snd:
                rect = _rect(rd.get("pRect"))
                used.add(i)
                break
        words.append({
            "id": _sym(wd.get("pName")),
            "foundImage": found["image"] if found else None,
            "foundRect": found["rect"] if found else None,
            "rect": rect,
            "sound": r.sound(click_snd),
        })
    extra_words = []
    for i, rd in enumerate(rect_list):
        if i not in used:
            extra_words.append({"rect": _rect(rd.get("pRect")), "sound": r.sound(rd.get("pClickSound"))})

    paper = r.sprite(strip.get("pBackMember"))
    full = r.sprite(strip.get("pFullRiddle"))
    ear = _button(r, strip.get("pEarButton") or {}, "readriddle") if isinstance(strip.get("pEarButton"), dict) else None

    end = prop("pEndAniObject") or {}
    end_frames = r.frames(end.get("pAnimMembers")) if isinstance(end, dict) else []
    end_obj = None
    if isinstance(end, dict) and end_frames:
        base = r.sprite(end.get("pMember")) or end_frames[0]
        end_obj = {
            "image": base["image"], "rect": base["rect"],
            "frames": [f["image"] for f in end_frames], "frameRects": [f["rect"] for f in end_frames],
            "fps": end.get("pSpeed", 10) or 10,
            "sound": r.sound(end.get("pAnimSound")),
            "clickRect": _rect(end.get("pClickRect")),
        }

    mp = prop("pMapRiddleStrip") or {}
    map_strip = None
    if isinstance(mp, dict):
        mpaper = r.sprite(mp.get("pMapRiddlePaper"))
        mtext = r.sprite(mp.get("pMapRiddle"))
        map_strip = {
            "paperImage": mpaper["image"] if mpaper else None,
            "paperRect": mpaper["rect"] if mpaper else None,
            "image": mtext["image"] if mtext else None,
            "rect": mtext["rect"] if mtext else None,
            "audio": r.sound(mp.get("pMapRiddleAudio")),
        }

    return {
        "background": (r.sprite(d.get("pBGMember"), matte=False) or {}).get("image"),
        "ambient": r.sound(d.get("pAmbientAudio")),
        "introAudio": r.sound(prop("pIntroAudio")),
        "congratsAudio": r.sound(prop("pCongratsAudio")),
        "mapGoneAudio": r.sound(prop("pMapGoneAudio")),
        "back": _screen_ref(d.get("pMyBackButtScreen")) or None,
        "strip": {
            "paperImage": paper["image"] if paper else None,
            "paperRect": paper["rect"] if paper else None,
            "riddleImage": full["image"] if full else None,
            "riddleRect": full["rect"] if full else None,
            "riddleAudio": r.sound(strip.get("pFullRiddleAudio")),
            "ear": ear,
        },
        "words": words,
        "extraWords": extra_words,
        "objects": objects,
        "endAnim": end_obj,
        "mapStrip": map_strip,
        "buttons": [b for b in (_button(r, bd) for bd in d.get("pButtList", []) or [] if isinstance(bd, dict)) if b],
    }


def _nav_screen(r: Resolver, d: dict) -> dict | None:
    bg = r.sprite(d.get("pScreen"), matte=False)
    if not bg:
        return None
    code = str(_sym(d.get("pScreenName"))).upper()
    navs = []
    for nd in d.get("pNavButts", []) or []:
        if not isinstance(nd, dict):
            continue
        neut = r.sprite(nd.get("pNeutMember"))
        if not neut:
            continue
        navs.append({
            "id": _sym(nd.get("pName")),
            "dest": _screen_ref(nd.get("pDestination")),
            "image": neut["image"], "rect": neut["rect"],
            "frames": [f["image"] for f in r.frames(nd.get("pAnimList"))],
            "frameRects": [f["rect"] for f in r.frames(nd.get("pAnimList"))],
            "endFrames": [f["image"] for f in r.frames(nd.get("pAnimEndList"))],
            "endFrameRects": [f["rect"] for f in r.frames(nd.get("pAnimEndList"))],
            "fps": nd.get("pSpeed", 8) or 8,
            "rollSound": r.sound(nd.get("pRollOnSound")),
            "downSound": r.sound(nd.get("pDownSound")),
        })
    sides = []
    for sd in d.get("pRectButtList", []) or []:
        if not isinstance(sd, dict):
            continue
        name = _sym(sd.get("pName")).lower()
        dest = d.get("pLeftScreen") if "left" in name else d.get("pRightScreen")
        rect = _rect(sd.get("pBeforeShape"))
        if rect and dest:
            sides.append({"id": name, "dest": _screen_ref(dest), "rect": rect,
                          "downSound": r.sound(sd.get("pDownSound")), "rollSound": r.sound(sd.get("pRollSound"))})
    return {
        "id": code, "kind": "nav", "title": code,
        "background": bg["image"],
        "ambient": r.sound(d.get("pAmbientAudio")),
        "back": _screen_ref(d.get("pMyBackButtScreen")) or None,
        "navs": navs,
        "sideNavs": sides,
        "buttons": [b for b in (_button(r, bd) for bd in d.get("pButtList", []) or [] if isinstance(bd, dict)) if b],
    }


def build(pack: Path, manifest: dict, casts: dict, scripts: dict, texts: dict, score: dict, log: Log,
          lingo: dict) -> dict:
    src = lingo.get("BHP", {})
    if not src:
        log("  ! no decompiled BHP scripts; falling back to generic scenes")
        from .generic import generic_scenes
        scenes = generic_scenes(pack, casts, log)
        write_json(pack / "scenes" / "index.json", {"entry": scenes[0]["id"] if scenes else None, "screens": scenes})
        return {"count": len(scenes), "index": "scenes/index.json"}

    r = Resolver(pack, casts, log)
    screens: list[dict] = []

    # --- navigation screens
    nav_src = next((t for k, t in src.items() if "getAllScreenNavs" in k), "")
    nav_lists = find_assignments(nav_src, "dalist")
    nav_count = 0
    for _, value in nav_lists:
        if isinstance(value, list):
            for d in value:
                if isinstance(d, dict):
                    r.media = "MAIN"
                    s = _nav_screen(r, d)
                    if s:
                        screens.append(s)
                        nav_count += 1
    log(f"  nav screens: {nav_count}")

    # --- riddle screens (three hunts A/B/C each)
    riddle_count = 0
    for handler, code in RIDDLE_HANDLERS.items():
        text = next((t for k, t in src.items() if handler in k), None)
        if not text:
            log(f"  ! missing script for {handler}")
            continue
        r.media = code
        variants = {}
        for label, value in find_assignments(text, "dalist"):
            if isinstance(value, dict) and label:
                try:
                    variants[label] = _riddle_variant(r, value)
                except Exception as exc:
                    log(f"  ! {handler} hunt {label}: {exc}")
        if not variants:
            continue
        first = next(iter(variants.values()))
        screens.append({
            "id": code, "kind": "riddle",
            "title": _title_from_handler(handler),
            "cast": code,
            "background": first.get("background"),
            "back": first.get("back"),
            "variants": variants,
        })
        riddle_count += 1
    log(f"  riddle screens: {riddle_count} ({sum(len(s.get('variants', {})) for s in screens)} variants)")

    r.save()
    index_entries = []
    for s in screens:
        write_json(pack / "scenes" / f"{s['id']}.json", s)
        index_entries.append({"id": s["id"], "kind": s["kind"], "title": s["title"]})
    entry = "FO" if any(s["id"] == "FO" for s in screens) else (screens[0]["id"] if screens else None)
    index = {"entry": entry, "hunts": ["A", "B", "C"], "screens": index_entries,
             "stage": {"width": STAGE_W, "height": STAGE_H}}
    write_json(pack / "scenes" / "index.json", index)
    return {"count": len(screens), "index": "scenes/index.json", "entry": entry}
