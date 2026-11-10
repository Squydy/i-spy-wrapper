"""Parse Lingo literal expressions from decompiled (.ls) source.

Handles: integers, floats, strings, symbols (#name), VOID, linear lists [a, b],
property lists [#k: v, ...] and [:], point(x, y), rect(l, t, r, b), rgb(...).
Everything else (identifiers, calls) becomes a Ref(text) so callers can decide."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<float>-?\d+\.\d+)
  | (?P<int>-?\d+)
  | (?P<str>"(?:[^"\\]|\\.)*")
  | (?P<sym>\#[A-Za-z_][A-Za-z0-9_]*)
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<punct>[\[\]\(\):,])
  | (?P<other>.)
""", re.VERBOSE)


@dataclass(frozen=True)
class Symbol:
    name: str

    def __str__(self) -> str:
        return "#" + self.name


@dataclass(frozen=True)
class Point:
    x: int
    y: int


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    def as_list(self) -> list[int]:
        return [self.left, self.top, self.right, self.bottom]


@dataclass(frozen=True)
class Ref:
    text: str


VOID = None


class LingoParseError(ValueError):
    pass


class _Parser:
    def __init__(self, text: str):
        self.toks: list[tuple[str, str]] = []
        for m in _TOKEN.finditer(text):
            kind = m.lastgroup
            if kind == "ws":
                continue
            self.toks.append((kind, m.group()))
        self.i = 0

    def peek(self) -> tuple[str, str] | None:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def next(self) -> tuple[str, str]:
        t = self.toks[self.i]
        self.i += 1
        return t

    def expect(self, val: str) -> None:
        t = self.next()
        if t[1] != val:
            raise LingoParseError(f"expected {val!r} got {t[1]!r} at {self.i}")

    def value(self) -> Any:
        t = self.peek()
        if t is None:
            raise LingoParseError("unexpected end")
        kind, text = t
        if kind == "int":
            self.next()
            return int(text)
        if kind == "float":
            self.next()
            return float(text)
        if kind == "str":
            self.next()
            return bytes(text[1:-1], "utf-8").decode("unicode_escape")
        if kind == "sym":
            self.next()
            return Symbol(text[1:])
        if text == "[":
            return self.list()
        if kind == "ident":
            self.next()
            low = text.lower()
            if low == "void":
                return VOID
            if low in ("true", "false"):
                return 1 if low == "true" else 0
            if self.peek() and self.peek()[1] == "(":
                args = self.args()
                if low == "point" and len(args) == 2:
                    return Point(int(args[0]), int(args[1]))
                if low == "rect" and len(args) == 4:
                    return Rect(*(int(a) for a in args))
                if low == "symbol" and len(args) == 1:
                    return Symbol(str(args[0]))
                return Ref(f"{text}({', '.join(repr(a) for a in args)})")
            return Ref(text)
        if text == "-":
            self.next()
            v = self.value()
            return -v
        raise LingoParseError(f"unexpected token {text!r}")

    def args(self) -> list[Any]:
        self.expect("(")
        out = []
        while True:
            t = self.peek()
            if t is None:
                raise LingoParseError("unterminated call")
            if t[1] == ")":
                self.next()
                return out
            out.append(self.value())
            if self.peek() and self.peek()[1] == ",":
                self.next()

    def list(self) -> Any:
        self.expect("[")
        t = self.peek()
        if t and t[1] == ":":
            self.next()
            self.expect("]")
            return {}
        if t and t[1] == "]":
            self.next()
            return []
        first = self.value()
        if self.peek() and self.peek()[1] == ":":
            # property list
            self.next()
            d: dict = {}
            key = first.name if isinstance(first, Symbol) else first
            d[key] = self.value()
            while True:
                t = self.peek()
                if t is None:
                    raise LingoParseError("unterminated proplist")
                if t[1] == "]":
                    self.next()
                    return d
                if t[1] == ",":
                    self.next()
                k = self.value()
                self.expect(":")
                key = k.name if isinstance(k, Symbol) else k
                d[key] = self.value()
        items = [first]
        while True:
            t = self.peek()
            if t is None:
                raise LingoParseError("unterminated list")
            if t[1] == "]":
                self.next()
                return items
            if t[1] == ",":
                self.next()
            items.append(self.value())


def parse_literal(text: str) -> Any:
    p = _Parser(text)
    v = p.value()
    return v


def find_assignments(source: str, var: str) -> list[tuple[str | None, Any]]:
    """Return [(case_label, value)] for every `var = <literal>` in a handler body.
    case_label is the preceding `"X":` case label if any."""
    out = []
    case_label = None
    pat = re.compile(rf"^\s*{re.escape(var)}\s*=\s*(.+)$")
    case_pat = re.compile(r'^\s*"([^"]*)"\s*:\s*$')
    for line in source.splitlines():
        cm = case_pat.match(line)
        if cm:
            case_label = cm.group(1)
            continue
        m = pat.match(line)
        if m:
            try:
                out.append((case_label, parse_literal(m.group(1))))
            except LingoParseError:
                continue
    return out


def to_plain(v: Any) -> Any:
    """Convert parsed values to JSON-friendly structures."""
    if isinstance(v, Symbol):
        return "#" + v.name
    if isinstance(v, Point):
        return {"x": v.x, "y": v.y}
    if isinstance(v, Rect):
        return {"l": v.left, "t": v.top, "r": v.right, "b": v.bottom}
    if isinstance(v, Ref):
        return {"$ref": v.text}
    if isinstance(v, dict):
        return {str(k): to_plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [to_plain(x) for x in v]
    return v
