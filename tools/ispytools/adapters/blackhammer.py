"""Adapter for the Black Hammer "SCREENDADDY" framework titles:
I SPY Fantasy (D8.5), I SPY Spooky Mansion Deluxe (D8.5) and I SPY Mystery (D10 Afterburner).

All three describe their screens with Lingo property lists returned by movie scripts in the
code cast (BHP.cxt / CODE.cct). Every object carries a #pType = (2 << 16) | scriptMember, so
we resolve types through the code cast's member names (SCREEN_RIDDLE, BUTT_MAIN, ...), which
keeps one adapter working across the three titles even though the member numbers differ.

Member references encode (castLib << 16) | member:
  castLib 1 = main movie cast (MAIN)     castLib 2 = code cast
  castLib 3 = "game" cast (Fantasy: S/B/D; Spooky/Mystery: the screen's own cast)
  castLib 4 = riddle cast (Fantasy only: casts/<SCREEN>.cxt)
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..lingo_literals import Point, Rect, Symbol, find_assignments
from ..matte import apply_matte_file
from .common import Log, write_json

STAGE_W, STAGE_H = 640, 480
LOC = (320, 240)

NAV_SCREEN_TYPES = {
    "SCREEN_MAIN", "SCREEN_MASTER", "SCREEN_NAV", "SCREEN_MYSTERY", "SCREEN_DOOR", "SCREEN_STUDY",
    "SCREEN_KITCHEN", "SCREEN_MM", "SCREEN_CC", "SCREEN_IWORKSHOP", "SCREEN_SMESSAGE", "SCREEN_DUNGEON",
    "SCREEN_WIZLAB", "SCREEN_ROCKET", "SCREEN_CP", "SCREEN_BOOK", "SCREEN_TEMPMYSTERY", "SCREEN_TEMPMYSTERY2",
}
RIDDLE_SCREEN_TYPES = {"SCREEN_RIDDLE", "SCREEN_RIDDLE_MAG", "SCREEN_RIDDLE_MICRO"}
SKIP_SCREEN_TYPES = {"SCREEN_BUMP", "SCREEN_SIGNIN", "SCREEN_CREDIT"}
MINIGAME_TYPES = {
    "SCREEN_DUNGEON", "SCREEN_WIZLAB", "SCREEN_ROCKET", "SCREEN_CP", "SCREEN_BOOK", "SCREEN_STUDY",
    "SCREEN_KITCHEN", "SCREEN_MM", "SCREEN_CC", "SCREEN_IWORKSHOP", "SCREEN_SMESSAGE",
    "SCREEN_TEMPMYSTERY", "SCREEN_TEMPMYSTERY2",
}
BUTTON_ACTIONS = {
    "HELP": "help", "BACK": "back", "HOME": "home", "MAIN": "home", "EXIT": "quit", "QUIT": "quit",
    "EAR": "readriddle", "LIPS": "readriddle", "TURN": "back",
}


def _sym(v: Any) -> str:
    if isinstance(v, Symbol):
        return v.name
    return str(v) if v is not None else ""


def _code(v: Any) -> str:
    """Screen / destination codes: symbols or strings, normalised to upper case without '#'."""
    return _sym(v).lstrip("#").upper()


def _rect(v: Any, scale: float = 1.0) -> list[int] | None:
    if isinstance(v, Rect):
        if scale != 1.0:
            return [round(v.left * scale), round(v.top * scale), round(v.right * scale), round(v.bottom * scale)]
        return v.as_list()
    return None


def _name_action(name: str) -> str | None:
    n = name.upper()
    for key, action in BUTTON_ACTIONS.items():
        if n.endswith("_" + key) or n == key or n == "GL_" + key or n.endswith(key + "BUTTON"):
            return action
    return None


class Resolver:
    def __init__(self, pack: Path, casts: dict, log: Log, code_label: str):
        self.pack = pack
        self.log = log
        self.code_label = code_label
        self.by_label: dict[str, dict[int, dict]] = {}
        self.by_name: dict[str, dict[str, dict]] = {}
        for label, c in casts["casts"].items():
            self.by_label[label] = {m["n"]: m for m in c["members"]}
            self.by_name[label] = {m["name"].upper(): m for m in c["members"] if m.get("name")}
        self.script_names = {n: m["name"] for n, m in self.by_label.get(code_label, {}).items()
                             if m.get("type") == "script"}
        # castLib 3 / 4 bindings for the screen being built
        self.game_cast: str | None = None
        self.screen_cast: str | None = None
        self.matted: set[str] = set()
        mf = pack / "data" / "matted.json"
        if mf.exists():
            self.matted = set(json.loads(mf.read_text()))
        self.audio_files: dict[str, str] = {}
        adir = pack / "audio"
        if adir.exists():
            for f in adir.glob("*.wav"):
                self.audio_files[f.stem.upper()] = f"audio/{f.name}"
        self.videos: dict[str, str] = {}
        vdir = pack / "video"
        if vdir.exists():
            for f in vdir.glob("*.ogv"):
                self.videos[f.stem.upper()] = f"video/{f.name}"
        self.missing: set[str] = set()

    def save(self) -> None:
        (self.pack / "data" / "matted.json").write_text(json.dumps(sorted(self.matted)))

    # ---- types
    def type_name(self, d: Any) -> str:
        if not isinstance(d, dict):
            return ""
        t = d.get("pType")
        if isinstance(t, int) and t >= 65536:
            return self.script_names.get(t & 0xFFFF, "")
        return ""

    # ---- members
    def _lib_labels(self, lib: int) -> list[str]:
        if lib == 1:
            return ["MAIN"]
        if lib == 2:
            return [self.code_label]
        if lib == 3:
            return [x for x in (self.game_cast, self.screen_cast) if x]
        return [x for x in (self.screen_cast, self.game_cast) if x]

    def member(self, value: Any) -> dict | None:
        if not isinstance(value, int) or value <= 0:
            return None
        lib, n = (value >> 16, value & 0xFFFF) if value >= 65536 else (1, value)
        for label in self._lib_labels(lib):
            m = self.by_label.get(label, {}).get(n)
            if m is not None:
                return m
        key = f"{lib}:{n}"
        if key not in self.missing:
            self.missing.add(key)
        return None

    def member_by_name(self, name: str) -> dict | None:
        for label in [x for x in (self.screen_cast, self.game_cast, "MAIN") if x]:
            m = self.by_name.get(label, {}).get(name.upper())
            if m:
                return m
        return None

    def sprite(self, value: Any, loc: tuple[int, int] = LOC, matte: bool = True, ink: int | None = None) -> dict | None:
        m = self.member(value) if not isinstance(value, dict) else value
        if not m or m.get("type") != "bitmap" or not m.get("image"):
            return None
        left = loc[0] - m.get("regX", 0)
        top = loc[1] - m.get("regY", 0)
        if matte and ink != 0:
            self._matte(m["image"], "bgtransparent" if ink == 36 else "matte")
        return {"image": m["image"], "rect": [left, top, left + m["w"], top + m["h"]], "member": m["n"],
                "name": m.get("name", "")}

    def frames(self, values: Any, loc: tuple[int, int] = LOC, ink: int | None = None) -> list[dict]:
        if not isinstance(values, list):
            return []
        out = []
        for v in values:
            s = self.sprite(v, loc, ink=ink)
            if s:
                out.append(s)
        return out

    def _matte(self, rel: str, mode: str) -> None:
        if rel in self.matted:
            return
        path = self.pack / rel
        if path.exists():
            try:
                apply_matte_file(path, mode)
            except Exception as exc:
                self.log(f"  ! matte failed for {rel}: {exc}")
        self.matted.add(rel)

    # ---- sounds / video
    def sound(self, value: Any) -> str | None:
        if isinstance(value, str):
            stem = Path(value.replace("\\", "/")).stem.upper()
            return self.audio_files.get(stem)
        if isinstance(value, list) and value:
            return self.sound(value[-1])
        m = self.member(value)
        if m and m.get("type") == "sound":
            return m.get("audio")
        return None

    def video(self, value: Any) -> str | None:
        if isinstance(value, str):
            return self.videos.get(Path(value).stem.upper())
        return None


# --------------------------------------------------------------------------- pieces
def _loc(d: dict) -> tuple[int, int]:
    loc = d.get("pLoc")
    return (loc.x, loc.y) if isinstance(loc, Point) else LOC


def _anim_frames(r: Resolver, d: dict, ink: int | None = None) -> list[dict]:
    loc = _loc(d)
    return r.frames(d.get("pAnimMembers") or d.get("pAnimList"), loc, ink=ink)


def _button(r: Resolver, d: dict, action: str | None = None, dest: str | None = None) -> dict | None:
    """BUTT_ROLL_UP / BUTT_ROLL_DOWN / BUTT_SIMPLE style buttons (neutral/roll/down members)."""
    if not isinstance(d, dict):
        return None
    neut = r.sprite(d.get("pNeutMember", d.get("pMember")), _loc(d), ink=d.get("pInk"))
    if not neut:
        return None
    name = _sym(d.get("pName"))
    out = {
        "id": name.lower(),
        "action": action or _name_action(name) or "none",
        "image": neut["image"], "rect": neut["rect"],
        "rollImage": (r.sprite(d.get("pRollMember"), _loc(d)) or {}).get("image"),
        "downImage": (r.sprite(d.get("pDownMember"), _loc(d)) or {}).get("image"),
        "disabledImage": (r.sprite(d.get("pDisMember"), _loc(d)) or {}).get("image"),
        "downSound": r.sound(d.get("pDownSound")),
        "upSound": r.sound(d.get("pUpSound")),
        "rollSound": r.sound(d.get("pRollSound")),
    }
    if dest:
        out["dest"] = dest
    return out


def _nav_from_button(r: Resolver, d: dict, dest: str) -> dict | None:
    """Turn any button object with a destination into a nav entry (animated or static)."""
    loc = _loc(d)
    ink = d.get("pInk")
    neut = r.sprite(d.get("pNeutMember", d.get("pMember")), loc, ink=ink)
    if not neut:
        return None
    nav = {"id": _sym(d.get("pName")), "dest": dest, "image": neut["image"], "rect": neut["rect"],
           "frames": [], "frameRects": [], "endFrames": [], "endFrameRects": [], "fps": 8,
           "rollSound": None, "downSound": None}
    roll_on = d.get("pRollOnAnimObject")
    if isinstance(roll_on, dict):  # BUTT_MAIN
        fr = _anim_frames(r, roll_on, ink)
        nav["frames"] = [neut["image"]] + [f["image"] for f in fr]
        nav["frameRects"] = [neut["rect"]] + [f["rect"] for f in fr]
        nav["rollSound"] = r.sound(roll_on.get("pAnimSound"))
        nav["fps"] = roll_on.get("pSpeed") or 8
        down = d.get("pDownAnimObject")
        if isinstance(down, dict):
            fr = _anim_frames(r, down, ink)
            nav["endFrames"] = [f["image"] for f in fr]
            nav["endFrameRects"] = [f["rect"] for f in fr]
            nav["downSound"] = r.sound(down.get("pAnimSound"))
    else:
        roll = r.sprite(d.get("pRollMember"), loc, ink=ink)
        down = r.sprite(d.get("pDownMember"), loc, ink=ink)
        if roll:
            nav["frames"] = [roll["image"]]
            nav["frameRects"] = [roll["rect"]]
        if down:
            nav["endFrames"] = [down["image"]]
            nav["endFrameRects"] = [down["rect"]]
        nav["rollSound"] = r.sound(d.get("pRollSound"))
        nav["downSound"] = r.sound(d.get("pDownSound"))
    return nav


# --------------------------------------------------------------------------- screens
class GameBuilder:
    def __init__(self, pack: Path, manifest: dict, casts: dict, lingo: dict, log: Log):
        self.pack = pack
        self.manifest = manifest
        self.log = log
        self.gid = manifest["id"]
        self.code_label = "BHP" if "BHP" in casts["casts"] else "CODE"
        self.src: dict[str, str] = lingo.get(self.code_label, {})
        self.r = Resolver(pack, casts, log, self.code_label)
        self.screens: dict[str, dict] = {}
        self.order: list[str] = []
        self.entry: str | None = None
        self.game_roots: dict[str, str] = {}   # game symbol -> first screen id (Fantasy)
        self.globals: dict = {}                # game-level strip/buttons for the current game

    # ---- data access
    def _assign(self, handler: str) -> Any:
        text = next((t for k, t in self.src.items() if handler.lower() in k.lower()), None)
        if not text:
            return None
        for var in ("daList", "dalist"):
            assigns = find_assignments(text, var)
            if assigns:
                return assigns[0][1]
        return None

    def _handlers(self, pattern: str) -> list[tuple[str, Any]]:
        rx = re.compile(pattern)
        out = []
        for k, text in self.src.items():
            for m in re.finditer(r"^on\s+(\w+)", text, re.M):
                if rx.match(m.group(1)):
                    assigns = find_assignments(text, "daList") or find_assignments(text, "dalist")
                    if assigns:
                        out.append((m.group(1), assigns[0][1]))
        return out

    # ---- cast binding per screen
    def _bind_casts(self, screen_name: str, game: str | None) -> None:
        labels = self.r.by_label
        self.r.game_cast = game.upper() if game and game.upper() in labels else None
        cand = screen_name.upper()
        self.r.screen_cast = None
        for c in (cand, re.sub(r"_[ABC]$", "", cand)):
            if c in labels and c not in ("MAIN", self.code_label):
                self.r.screen_cast = c
                break

    # ---- public
    def build(self) -> dict:
        if self.gid == "fantasy":
            self._build_fantasy()
        elif self.gid == "spooky_deluxe":
            self._build_spooky()
        else:
            self._build_mystery()
        self.r.save()
        if self.r.missing:
            self.log(f"  ! {len(self.r.missing)} unresolved member refs (e.g. {sorted(self.r.missing)[:5]})")
        return self._write()

    def _write(self) -> dict:
        sdir = self.pack / "scenes"
        sdir.mkdir(exist_ok=True)
        for old in sdir.glob("*.json"):
            old.unlink()
        entries = []
        hunts: set[str] = set()
        for sid in self.order:
            s = self.screens[sid]
            write_json(sdir / f"{sid}.json", s)
            entries.append({"id": sid, "kind": s["kind"], "title": s.get("title", sid)})
            if s["kind"] == "riddle":
                hunts.update(s.get("variants", {}).keys())
        index = {"entry": self.entry, "hunts": sorted(hunts) or ["A"], "screens": entries,
                 "stage": {"width": STAGE_W, "height": STAGE_H}}
        write_json(sdir / "index.json", index)
        nav = sum(1 for s in self.screens.values() if s["kind"] == "nav")
        rid = sum(1 for s in self.screens.values() if s["kind"] == "riddle")
        self.log(f"  nav screens: {nav}, riddle screens: {rid} "
                 f"({sum(len(s.get('variants', {})) for s in self.screens.values())} variants), entry {self.entry}")
        return {"count": len(self.screens), "index": "scenes/index.json", "entry": self.entry}

    def _add(self, screen: dict) -> None:
        sid = screen["id"]
        if sid not in self.screens:
            self.order.append(sid)
        self.screens[sid] = screen

    # ---- per-title drivers
    def _build_fantasy(self) -> None:
        daddy = self._assign("getGameDaddy")
        hunts = {"A": "_A", "B": "_B", "C": "_C"}
        games = {"S": "getSandCastle", "B": "getBlast", "D": "getDeep"}
        # per-game data: hunt A for layout, B/C for riddle variants
        for gsym, handler in games.items():
            data = {h: self._assign(handler + suffix) for h, suffix in hunts.items()}
            base = data.get("A") or next((d for d in data.values() if d), None)
            if not isinstance(base, dict):
                self.log(f"  ! no data for {handler}")
                continue
            self.globals = base
            screens = (base.get("ancestor") or {}).get("pScreenList") or base.get("pScreenList") or []
            first = None
            for sd in screens:
                if not isinstance(sd, dict):
                    continue
                name = _code(sd.get("pName"))
                tname = self.r.type_name(sd)
                if first is None and tname not in SKIP_SCREEN_TYPES:
                    first = name
                self._bind_casts(name, gsym)
                if tname in RIDDLE_SCREEN_TYPES:
                    variants = {}
                    for h, d in data.items():
                        if not isinstance(d, dict):
                            continue
                        scr = (d.get("ancestor") or {}).get("pScreenList") or []
                        match = next((x for x in scr if isinstance(x, dict) and _code(x.get("pName")) == name), None)
                        if match:
                            self.globals = d
                            variants[h] = self._riddle_variant(match)
                    self.globals = base
                    self._add({"id": name, "kind": "riddle", "title": name, "cast": self.r.screen_cast,
                               "background": next(iter(variants.values()))["background"] if variants else None,
                               "back": None, "variants": variants})
                elif tname not in SKIP_SCREEN_TYPES:
                    s = self._nav_screen(sd, tname)
                    if s:
                        self._add(s)
            if first:
                self.game_roots[gsym] = first
        # the MAIN game: title menu with the three game buttons
        if isinstance(daddy, dict):
            self.globals = {}
            for g in daddy.get("pGameList", []):
                if not isinstance(g, dict) or _code(g.get("pName")) != "MAIN":
                    continue
                for sd in g.get("pScreenList", []):
                    if not isinstance(sd, dict):
                        continue
                    tname = self.r.type_name(sd)
                    if tname in SKIP_SCREEN_TYPES:
                        continue
                    self._bind_casts("MAIN", None)
                    s = self._nav_screen(sd, tname)
                    if s:
                        s["id"] = "MAIN"
                        for nav in s["navs"]:
                            nav["dest"] = self.game_roots.get(nav["dest"], nav["dest"])
                        open_anim = sd.get("pOpenAnim")
                        if isinstance(open_anim, dict) and open_anim.get("pFileName"):
                            s["introVideo"] = self.r.video(open_anim["pFileName"])
                        self._add(s)
        self.entry = "MAIN" if "MAIN" in self.screens else (self.order[0] if self.order else None)
        # game main screens go "back" to the title menu
        for root in self.game_roots.values():
            if root in self.screens and not self.screens[root].get("back"):
                self.screens[root]["back"] = "MAIN"
        self._fill_back_links()

    def _build_spooky(self) -> None:
        data = {h: self._assign(f"getSpookyData_{h}") for h in "ABC"}
        base = data.get("A") or next((d for d in data.values() if d), None)
        if not isinstance(base, dict):
            self.log("  ! no spooky data")
            return
        self.globals = base
        for sd in base.get("pLevelScreenList", []):
            if not isinstance(sd, dict):
                continue
            name = _code(sd.get("pName"))
            tname = self.r.type_name(sd)
            self._bind_casts(name, None)
            if tname in RIDDLE_SCREEN_TYPES:
                variants = {}
                for h, d in data.items():
                    if not isinstance(d, dict):
                        continue
                    match = next((x for x in d.get("pLevelScreenList", [])
                                  if isinstance(x, dict) and _code(x.get("pName")) == name), None)
                    if match:
                        self.globals = d
                        variants[h] = self._riddle_variant(match)
                self.globals = base
                self._add({"id": name, "kind": "riddle", "title": name, "cast": self.r.screen_cast,
                           "background": next(iter(variants.values()))["background"] if variants else None,
                           "back": None, "variants": variants})
            elif tname not in SKIP_SCREEN_TYPES:
                s = self._nav_screen(sd, tname)
                if s:
                    if tname == "SCREEN_DOOR":
                        # the front door opens onto the foyer
                        s["navs"].append({"id": "door", "dest": "FOYER", "image": s["background"],
                                          "rect": [200, 60, 440, 420], "frames": [], "frameRects": [],
                                          "endFrames": [], "endFrameRects": [], "fps": 8,
                                          "rollSound": None, "downSound": r_sound(self.r, sd.get("pKnobButt"))})
                    self._add(s)
        self.entry = "MAIN" if "MAIN" in self.screens else (self.order[0] if self.order else None)
        self._fill_back_links()

    def _build_mystery(self) -> None:
        root = self._assign("getGlobalGameData")
        if not isinstance(root, dict):
            self.log("  ! no mystery data")
            return
        self.globals = root
        screens = (root.get("ancestor") or {}).get("pScreenList") or []
        mysteries = {_code(m.get("pName")): m for m in root.get("pMysteryList", []) if isinstance(m, dict)}
        riddle_parent: dict[str, str] = {}
        for mid, m in mysteries.items():
            for rsym in m.get("pRiddleList", []) or []:
                riddle_parent[_code(rsym)] = mid
        for sd in screens:
            if not isinstance(sd, dict):
                continue
            name = _code(sd.get("pName"))
            tname = self.r.type_name(sd)
            if tname in SKIP_SCREEN_TYPES or not name:
                continue
            self._bind_casts(name, None)
            if tname in RIDDLE_SCREEN_TYPES:
                var = self._riddle_variant(sd)
                var["back"] = riddle_parent.get(name)
                self._add({"id": name, "kind": "riddle", "title": name, "cast": self.r.screen_cast,
                           "background": var["background"], "back": riddle_parent.get(name),
                           "variants": {"A": var}})
            elif tname == "SCREEN_MAIN":
                self._add(self._mystery_main(sd))
            else:
                s = self._nav_screen(sd, tname)
                if s:
                    if tname == "SCREEN_MYSTERY":
                        s["back"] = "MAIN"
                    self._add(s)
        self.entry = "MAIN" if "MAIN" in self.screens else (self.order[0] if self.order else None)
        self._fill_back_links()

    def _mystery_main(self, sd: dict) -> dict:
        """The case map: a 640x480 overview whose click rects are given in 1280x960 space."""
        bg = self.r.sprite(sd.get("pBGMember"), matte=False)
        scale = 1.0 / float(sd.get("pMagOffset") or 2)
        sides = []
        for cd in sd.get("pClickDefList", []) or []:
            if not isinstance(cd, dict):
                continue
            dest = _code(cd.get("pNav"))
            rect = _rect(cd.get("pClickRect"), scale)
            if not dest or not rect or dest == "CREDIT":
                continue
            sides.append({"id": dest.lower(), "dest": dest, "rect": rect,
                          "downSound": self.r.sound(cd.get("pClickSound")), "rollSound": None})
        return {"id": "MAIN", "kind": "nav", "title": "Case map",
                "background": bg["image"] if bg else None,
                "ambient": self.r.sound(sd.get("pAmbientAudio")), "back": None,
                "navs": [], "sideNavs": sides, "buttons": self._global_buttons(include_back=False)}

    # ---- shared pieces
    def _fill_back_links(self) -> None:
        """Screens reached from exactly one nav screen go back to it."""
        parents: dict[str, set[str]] = {}
        for sid, s in self.screens.items():
            if s["kind"] != "nav":
                continue
            for nav in s.get("navs", []) + s.get("sideNavs", []):
                parents.setdefault(nav["dest"], set()).add(sid)
        for sid, s in self.screens.items():
            if s.get("back"):
                continue
            ps = parents.get(sid, set()) - {sid}
            if len(ps) == 1:
                s["back"] = next(iter(ps))
            elif ps:
                s["back"] = sorted(ps, key=lambda p: self.order.index(p))[0]
            elif sid != self.entry:
                s["back"] = self.entry

    def _global_buttons(self, include_back: bool = True) -> list[dict]:
        out = []
        for key, action in (("pHelpButton", "help"), ("pBackButton", "back"), ("pHomeButton", "home"),
                            ("pQuitButton", "quit")):
            if not include_back and action == "back":
                continue
            d = self.globals.get(key)
            if isinstance(d, dict):
                b = _button(self.r, d, action)
                if b:
                    out.append(b)
        return out

    def _nav_screen(self, sd: dict, tname: str) -> dict | None:
        bg = self.r.sprite(sd.get("pBGMember", sd.get("pBackMember")), matte=False)
        if not bg:
            self.log(f"  ! no background for screen {_code(sd.get('pName'))} ({tname})")
            return None
        navs = []
        buttons = []
        for bd in sd.get("pButtList", []) or []:
            if not isinstance(bd, dict):
                continue
            dest = _code(bd.get("pDestination"))
            if dest in ("QUIT",):
                b = _button(self.r, bd, "quit")
                if b:
                    buttons.append(b)
            elif dest and dest != "0":
                nav = _nav_from_button(self.r, bd, dest)
                if nav:
                    navs.append(nav)
            else:
                b = _button(self.r, bd)
                if b and b["action"] != "none":
                    buttons.append(b)
        # typed buttons on special screens that lead somewhere
        for key in ("pWizardNavButton", "pPrincessDoorButton", "pCreditButton"):
            bd = sd.get(key)
            if isinstance(bd, dict):
                dest = _code(bd.get("pDestination"))
                if dest and dest != "0" and dest != "CREDIT":
                    nav = _nav_from_button(self.r, bd, dest)
                    if nav:
                        navs.append(nav)
        for key, action in (("pStopButt", "quit"), ("pBackButton", "back"), ("pTurnAroundButton", "back"),
                            ("pHelpButton", "help")):
            bd = sd.get(key)
            if isinstance(bd, dict):
                b = _button(self.r, bd, action)
                if b:
                    buttons.append(b)
        screen = {
            "id": _code(sd.get("pName")), "kind": "nav", "title": _code(sd.get("pName")),
            "background": bg["image"],
            "ambient": self.r.sound(sd.get("pAmbientAudio")),
            "back": None,
            "navs": navs, "sideNavs": [], "buttons": buttons,
        }
        if sd.get("pIntroAudio"):
            screen["introAudio"] = self.r.sound(sd["pIntroAudio"])
        if tname in MINIGAME_TYPES:
            screen["minigame"] = tname
        intro = sd.get("pIntroBink")
        if isinstance(intro, dict) and intro.get("pFileName"):
            screen["introVideo"] = self.r.video(intro["pFileName"])
        return screen

    def _riddle_variant(self, sd: dict) -> dict:
        r = self.r
        bg = r.sprite(sd.get("pBGMember"), matte=False)
        objects_raw = [o for o in (sd.get("pRiddleObjectList") or []) if isinstance(o, dict)]
        by_name = {_sym(o.get("pName")).upper(): o for o in objects_raw}
        consumed: set[str] = set()
        objects = []
        # multi objects first so their parts are consumed
        for od in objects_raw:
            if r.type_name(od) == "RIDDLE_MULTI" or "pClickAnimObjList" in od:
                parts = []
                for ref in od.get("pClickAnimObjList", []) or []:
                    pd = by_name.get(_sym(ref).upper()) if not isinstance(ref, dict) else ref
                    if isinstance(pd, dict):
                        consumed.add(_sym(pd.get("pName")).upper())
                        p = self._anim_object(pd)
                        if p:
                            parts.append(p)
                objects.append({
                    "id": _sym(od.get("pName")), "multi": True, "parts": parts,
                    "clickSounds": [], "allFoundSound": r.sound(od.get("pAllFoundAudio")),
                    "wordRect": _rect(od.get("pWordRect")),
                })
                consumed.add(_sym(od.get("pName")).upper())
        for od in objects_raw:
            if _sym(od.get("pName")).upper() in consumed:
                continue
            o = self._anim_object(od)
            if o:
                objects.append(o)

        words, extra = [], []
        for wd in sd.get("pRiddleWordRectList") or []:
            if not isinstance(wd, dict):
                continue
            rect = _rect(wd.get("prect", wd.get("pRect")))
            snd = r.sound(wd.get("pClickSound"))
            found = r.sprite(wd.get("pMember")) if wd.get("pMember") else None
            wid = _sym(wd.get("pName"))
            if r.type_name(wd) == "RIDDLEWORD_RECT" or wid.upper() in by_name:
                words.append({"id": wid, "foundImage": found["image"] if found else None,
                              "foundRect": found["rect"] if found else None, "rect": rect, "sound": snd})
            else:
                extra.append({"rect": rect, "sound": snd})
        # multi objects whose word highlight is given by name rather than in the rect list
        known = {w["id"].upper() for w in words}
        for o in objects:
            if o.get("multi") and o["id"].upper() not in known:
                src = by_name.get(o["id"].upper(), {})
                wm = src.get("pWordMember")
                found = r.sprite(r.member_by_name(wm)) if isinstance(wm, str) else None
                words.append({"id": o["id"], "foundImage": found["image"] if found else None,
                              "foundRect": found["rect"] if found else None,
                              "rect": o.get("wordRect"), "sound": None})
        # the word list must only contain words that have a clickable object
        object_ids = {o["id"].upper() for o in objects}
        words = [w for w in words if w["id"].upper() in object_ids]

        strip_obj = self.globals.get("pRiddleStripObject") or {}
        paper = r.sprite(strip_obj.get("pBackMember")) if isinstance(strip_obj, dict) else None
        riddle_img = r.sprite(sd.get("pRiddleStripMember"))
        ear_src = strip_obj.get("pEarButton") if isinstance(strip_obj, dict) else None
        if not isinstance(ear_src, dict):
            ear_src = self.globals.get("pLipsButton")
        ear = _button(r, ear_src, "readriddle") if isinstance(ear_src, dict) else None

        end_obj = None
        end = sd.get("pEndAniObject") or sd.get("pSkellyAniObjectA")
        if isinstance(end, dict):
            fr = _anim_frames(r, end, end.get("pInk"))
            if fr:
                end_obj = {"image": fr[0]["image"], "rect": fr[0]["rect"],
                           "frames": [f["image"] for f in fr], "frameRects": [f["rect"] for f in fr],
                           "fps": end.get("pSpeed") or 10, "sound": r.sound(end.get("pAnimSound")),
                           "clickRect": _rect(end.get("pEndClickRect")) or _rect(end.get("pClickRect"))}

        clue_obj = self.globals.get("pClueStripObject") or {}
        map_strip = None
        if sd.get("pClueStripMember"):
            cpaper = r.sprite(clue_obj.get("pBackMember")) if isinstance(clue_obj, dict) else None
            ctext = r.sprite(sd.get("pClueStripMember"))
            map_strip = {"paperImage": cpaper["image"] if cpaper else None,
                         "paperRect": cpaper["rect"] if cpaper else None,
                         "image": ctext["image"] if ctext else None, "rect": ctext["rect"] if ctext else None,
                         "audio": r.sound(sd.get("pClueAudio"))}

        return {
            "background": bg["image"] if bg else None,
            "ambient": r.sound(sd.get("pAmbientAudio")),
            "introAudio": None,
            "congratsAudio": r.sound(sd.get("pCongratsAudio")) or r.sound(self.globals.get("pCongratsAudio")),
            "mapGoneAudio": None,
            "back": None,
            "strip": {
                "paperImage": paper["image"] if paper else None,
                "paperRect": paper["rect"] if paper else None,
                "riddleImage": riddle_img["image"] if riddle_img else None,
                "riddleRect": riddle_img["rect"] if riddle_img else None,
                "riddleAudio": r.sound(sd.get("pFullRiddleAudio")),
                "ear": ear,
            },
            "words": words,
            "extraWords": extra,
            "objects": objects,
            "endAnim": end_obj,
            "mapStrip": map_strip,
            "buttons": self._global_buttons(),
        }

    def _anim_object(self, d: dict) -> dict | None:
        r = self.r
        loc = _loc(d)
        ink = d.get("pInk")
        tname = r.type_name(d)
        base = r.sprite(d.get("pMember"), loc, ink=ink)
        frames = r.frames(d.get("pAnimMembers"), loc, ink=ink)
        if not base and frames:
            base = frames[0]
        if not base:
            return None
        state_change = tname in ("RIDDLE_SC", "RIDDLE_WIG_SC", "ANIM_SC")
        found = frames[-1] if (state_change and frames) else None
        hot = _rect(d.get("pClickRect")) if isinstance(d.get("pClickRect"), Rect) else None
        found_hot = _rect(d.get("pEndClickRect")) if isinstance(d.get("pEndClickRect"), Rect) else None
        return {
            "id": _sym(d.get("pName")),
            "image": base["image"], "rect": base["rect"],
            "frames": [f["image"] for f in frames], "frameRects": [f["rect"] for f in frames],
            "fps": d.get("pSpeed") or 10,
            "sound": r.sound(d.get("pWordSound")),
            "animSound": r.sound(d.get("pAnimSound")),
            "stateChange": state_change,
            "hotspot": hot, "foundHotspot": found_hot,
            "foundImage": found["image"] if found else None,
            "foundRect": found["rect"] if found else None,
            "type": tname,
        }


def r_sound(r: Resolver, d: Any) -> str | None:
    return r.sound(d.get("pDownSound")) if isinstance(d, dict) else None


def build(pack: Path, manifest: dict, casts: dict, scripts: dict, texts: dict, score: dict, log: Log,
          lingo: dict | None = None) -> dict:
    code_label = "BHP" if "BHP" in casts["casts"] else "CODE"
    if not lingo or not lingo.get(code_label):
        log("  ! no decompiled code scripts; falling back to generic scenes")
        from .generic import generic_scenes
        scenes = generic_scenes(pack, casts, log)
        write_json(pack / "scenes" / "index.json", {"entry": scenes[0]["id"] if scenes else None, "screens": scenes})
        return {"count": len(scenes), "index": "scenes/index.json"}
    return GameBuilder(pack, manifest, casts, lingo, log).build()
