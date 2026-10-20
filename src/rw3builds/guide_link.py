"""Build a hpp3.github.io/rw3 Guide link (``?g=``) for one parsed build.

Format (site/app.js ``encodeGuide``, pinned in fetch.CATALOG_LIVE_COMMIT):
    g = VER _ <equipment track> _ <sp track> _ <title>
    track   = section*;  section = HEADING item ('.' item)*;  item = id ('-' id)*  (OR-group)
    ids are lowercase base36; HEADING is one uppercase letter (C = Core, M = Maybe, ...)
The SP track is one combined namespace: "Spell" and "Spell::Upgrade" -> stable ids. The site
drops an upgrade whose spell is not in a strictly earlier item, so each spell is emitted before
its upgrades.

Only items whose identity AND (for upgrades) parent link are verified go in the Core section.
Inferred spells/upgrades go in a "Maybe" section, so the link never presents a guess as fact.
"""
from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

from .catalog import Catalog
from .models import RecordParse

SITE = "https://hpp3.github.io/rw3/"
CORE, MAYBE = "C", "M"
TITLE_MAX = 40


def read_guide_constants(app_js: Path) -> dict:
    """Read GUIDE_VER / GUIDE_SEP / GUIDE_PARAM from the pinned app.js so a format change in
    the site shows up as a loud failure rather than silently broken links."""
    src = app_js.read_text(encoding="utf-8")
    out = {}
    for key in ("GUIDE_VER", "GUIDE_SEP", "GUIDE_PARAM"):
        m = re.search(rf"const {key} = '([^']*)';", src)
        if not m:
            raise ValueError(f"{key} not found in {app_js}")
        out[key] = m.group(1)
    return out


def _b36(n: int) -> str:
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    if n == 0:
        return "0"
    s = ""
    while n:
        n, r = divmod(n, 36)
        s = chars[r] + s
    return s


def encode_track(sections: list[tuple[str, list[list[int]]]]) -> str:
    return "".join(h + ".".join("-".join(_b36(i) for i in item) for item in items)
                   for h, items in sections if items)


def build_link(p: RecordParse, cat: Catalog, consts: dict) -> tuple[str | None, list[str]]:
    """Return (url, names_missing_an_id). Names without a stable id are left out and reported."""
    core_sp: list[list[int]] = []
    maybe_sp: list[list[int]] = []
    missing: list[str] = []
    for s in p.spells:
        sid = cat.sp_ids.get(s.name)
        if sid is None:
            missing.append(s.name)
            continue
        target = core_sp if s.status == "owned" else maybe_sp
        target.append([sid])
        for u in s.upgrades:
            uid = cat.sp_ids.get(f"{s.name}::{u.name}")
            if uid is None:
                missing.append(f"{s.name}::{u.name}")
                continue
            (core_sp if (u.association == "verified" and s.status == "owned") else maybe_sp).append([uid])
    eq: list[list[int]] = []
    for e in p.equipment:
        eid = cat.equipment_ids.get(e.name)
        if eid is None:
            if e.kind == "equipment":
                missing.append(e.name)
            continue                      # companions/tomes have no compendium equipment id
        eq.append([eid])
    if not core_sp and not eq:
        return None, missing
    # An upgrade in MAYBE whose spell is in CORE still decodes (CORE precedes MAYBE).
    sp_track = encode_track([(CORE, core_sp), (MAYBE, maybe_sp)])
    eq_track = encode_track([(CORE, eq)])
    title = re.sub(r"[^A-Za-z0-9 ._-]", "", f"Win {p.record_id}")[:TITLE_MAX]
    g = consts["GUIDE_SEP"].join([consts["GUIDE_VER"], eq_track, sp_track, title])
    return SITE + "?" + urllib.parse.urlencode({consts["GUIDE_PARAM"]: g}), missing


def decode_track(s: str) -> list[tuple[str, list[list[int]]]]:
    """Python port of app.js parseTrack (fixed headings only), used to round-trip test links."""
    secs: list[tuple[str, list[list[int]]]] = []
    item: list[int] = []
    tok = ""

    def flush_tok():
        nonlocal tok
        if tok:
            item.append(int(tok, 36))
            tok = ""

    def flush_item():
        nonlocal item
        flush_tok()
        if secs and item:
            secs[-1][1].append(item)
        item = []

    for ch in s:
        if "A" <= ch <= "Z":
            flush_item()
            secs.append((ch, []))
        elif ch == ".":
            flush_item()
        elif ch == "-":
            flush_tok()
        else:
            tok += ch
    flush_item()
    return [(h, items) for h, items in secs if items]
