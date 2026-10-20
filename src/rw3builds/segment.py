"""Anchors, column windows, and per-line classification.

The build lives only in the central character-sheet pane:
  * Spells column:    bare ``Spells`` header  ..  ``Learn a Spell (S)``
  * Equipment column: bare ``Equipment`` header .. ``Craft Equipment (E)``
EasyOCR emitted boxes roughly top-to-bottom, so inside those windows the central lines are
interleaved with the left pane (``Spells (S)`` hotkey list) and the right pane (run summary,
``Purchases:``, combat stats). Line shape separates them: central lines never carry numbers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .normalize import Match, Normalizer
from .records import Line, Record

ANCHORS = {
    "spells_header": re.compile(r"^Spells:?$"),
    "equipment_header": re.compile(r"^Equip\w{3,7}$"),
    "left_spells_header": re.compile(r"^Spells\s*[\(\{]"),
    "left_equipment_header": re.compile(r"^Equip\w*\s*[\(\{I]"),
    "craft_equipment": re.compile(r"^Craft\s+Equip"),
    "learn_spell": re.compile(r"^Learn\b"),
    "outcome": re.compile(r"^Outco\w*\s*[:;]"),
    "purchases": re.compile(r"^Purchases\s*[:;]"),
    "desired": re.compile(r"^Desired$"),
    "components": re.compile(r"^Co[mn]+ponents$"),
    "resistances": re.compile(r"^Resistances$"),
    "spell_casts": re.compile(r"^(Spell\s+)?Casts\s*:"),
    "damage_to_enemies": re.compile(r"^Damage to Enem"),
    "damage_to_wizard": re.compile(r"^Damage to Wiz"),
    "status_effects": re.compile(r"^Status Effects"),
    "view_combat": re.compile(r"^View Combat"),
    "menu": re.compile(r"^Menu\s*\("),
}
# Fallback ends for a column whose end anchor was cropped away, in preference order.
SPELL_END_FALLBACK = ("resistances", "view_combat", "menu")

UI_LINE = re.compile(
    r"^(Turns taken:?|Rift Wizard( 3)?|Character Sheet.*|How to( Play)?.*|Log|Play|X|\(\w?\)|"
    r"View Combat.*|Menu.*|Spell Casts:?|Casts:?|Damage to .*|Status Effects|Resistances|Components|"
    r"Desired|Purchases[:;]?|Spell|Learn.*|Craft.*|Spells.*|Equip\w*.*|Outco\w*.*|Real\w* \d+.*|"
    r"HP \d.*|SP \d.*|SH \d.*)$"
)
NOTICE = re.compile(r"^\W*(?P<n>\d+)?\s*Upgrades?\s+Ava\w*", re.I)
NUMBER_LINE = re.compile(r"^[^\w]*\d{1,4}[^\w]*$|^\d+\s*\(\w\)$")
RECIPE_LINE = re.compile(r"^[A-Z0-9?]*\*{2,}\W*$")
RESIST_LINE = re.compile(r"^\d+[%7]?\s*Resist\b")
ESSENCE_LINE = re.compile(r"(\b[A-Z0-9][:;.][\w?]\b.*){2,}")
COLON_FORM = re.compile(r"^(?P<left>[^:]+?)\s*:\s*(?P<right>.*)$")
NAME_LIKE = re.compile(r"^[A-Z][A-Za-z']+(?:[ -][A-Za-z'][a-z']*)*$")


@dataclass
class Windows:
    spell: tuple[int, int] | None
    equipment: tuple[int, int] | None
    positions: dict[str, list[int]]
    flags: list[str] = field(default_factory=list)

    def in_spell(self, idx: int) -> bool:
        return self.spell is not None and self.spell[0] < idx < self.spell[1]

    def in_equipment(self, idx: int) -> bool:
        return self.equipment is not None and self.equipment[0] < idx < self.equipment[1]

    def zone(self, idx: int) -> str:
        s, e = self.in_spell(idx), self.in_equipment(idx)
        return "both" if s and e else "spell_window" if s else "equipment_window" if e else "outside"


def find_windows(rec: Record) -> Windows:
    pos: dict[str, list[int]] = {k: [] for k in ANCHORS}
    for ln in rec.lines:
        t = ln.text.strip()
        for k, rx in ANCHORS.items():
            if rx.match(t):
                pos[k].append(ln.idx)
    flags: list[str] = []
    n = len(rec.lines)

    def first_after(key: str, after: int) -> int | None:
        return next((i for i in pos[key] if i > after), None)

    spell = equip = None
    if pos["spells_header"]:
        s = pos["spells_header"][0]
        e = first_after("learn_spell", s)
        if e is None:
            flags.append("missing_learn_spell_anchor")
            e = next((x for k in SPELL_END_FALLBACK if (x := first_after(k, s)) is not None), n)
        spell = (s, e)
    else:
        flags.append("missing_spells_header")
    if pos["equipment_header"]:
        s = pos["equipment_header"][0]
        e = first_after("craft_equipment", s)
        if e is None:
            flags.append("missing_craft_equipment_anchor")
            e = spell[1] if spell else n
        equip = (s, e)
    else:
        flags.append("missing_equipment_header")
    return Windows(spell, equip, pos, flags)


@dataclass
class Token:
    line: Line
    kind: str                      # name | notice | number | ui | recipe | resist | essence | colon | junk | blank
    match: Match | None = None
    joined_lines: tuple[Line, ...] = ()
    pane: str = "other"
    rule: str = ""
    notice_count: int | None = None
    colon_spell: str | None = None
    colon_rest: str = ""


def _is_number(t: str) -> bool:
    return bool(NUMBER_LINE.match(t))


def classify_lines(rec: Record, norm: Normalizer, win: "Windows | None" = None) -> list[Token]:
    toks: list[Token] = []
    for ln in rec.lines:
        t = ln.text.strip()
        if not t:
            toks.append(Token(ln, "blank"))
        elif NOTICE.match(t):
            m = NOTICE.match(t)
            toks.append(Token(ln, "notice", notice_count=int(m.group("n")) if m.group("n") else None))
        elif _is_number(t):
            toks.append(Token(ln, "number"))
        elif RECIPE_LINE.match(t):
            toks.append(Token(ln, "recipe"))
        elif RESIST_LINE.match(t):
            toks.append(Token(ln, "resist"))
        elif ESSENCE_LINE.search(t) and not norm.match(t):
            toks.append(Token(ln, "essence"))
        elif UI_LINE.match(t) and not norm.match(t):
            toks.append(Token(ln, "ui"))
        else:
            cm = COLON_FORM.match(t)
            if cm:
                left = norm.match(cm.group("left"))
                if left and "spell" in left.kinds:
                    toks.append(Token(ln, "colon", colon_spell=left.name, colon_rest=cm.group("right").strip()))
                    continue
            m = norm.match(t)
            toks.append(Token(ln, "name", match=m) if m else Token(ln, "junk"))
    _merge_split_notices(toks)
    _join_wrapped_names(toks, norm)
    _pair_separated_halves(toks, norm, win)
    _complete_fragments(toks, norm)
    return toks


def _merge_split_notices(toks: list[Token]) -> None:
    """"2" / "Upgrades Available" is one notice the OCR split; the number is not a hotkey index."""
    for a, b in zip(toks, toks[1:]):
        if a.kind == "number" and b.kind == "notice" and b.notice_count is None:
            digits = re.sub(r"\D", "", a.line.text)
            if digits and len(digits) <= 2:
                b.notice_count, a.kind, a.rule = int(digits), "notice_count", f"count of notice on line {b.line.no}"


def _join_wrapped_names(toks: list[Token], norm: Normalizer) -> None:
    """Join a name the UI wrapped onto two lines. Only between two adjacent, individually
    unmatched, letters-only lines - never across a matched or numeric line."""
    i = 0
    while i < len(toks) - 1:
        a, b = toks[i], toks[i + 1]
        if a.kind == "junk" and b.kind == "junk" and NAME_LIKE.match(a.line.text.strip()) \
                and NAME_LIKE.match(b.line.text.strip()):
            m = norm.match_join([a.line.text, b.line.text])
            if m:
                a.kind, a.match, a.joined_lines = "name", m, (b.line,)
                b.kind, b.rule = "joined_into_previous", f"joined into line {a.line.no}"
                i += 2
                continue
        i += 1


def _clean_half(t: str) -> str:
    return t.strip().strip("'\"`").strip()


PAIRABLE_KINDS = frozenset({"upgrade", "equipment", "companion", "tome"})
FRAGMENT_SOLO_MIN_LEN = 8   # single-word fragment whose other half is missing


def _pair_separated_halves(toks: list[Token], norm: Normalizer, win: "Windows | None") -> None:
    """Both halves of a wrapped name present but not adjacent ("Robe of" ... "'Agony",
    "Echo" ... "Mage"): the columns interleave, so line 2 of a wrap lands several lines later.
    Accepted only when (a) both lines are unmatched letters-only text, (b) the first half comes
    BEFORE the second (a wrap's first line is above its second), and (c) "first second" is a
    catalog name by exact / case-and-space / OCR-confusion match - never fuzzy. The nearest
    qualifying second half is used, and each line is used once.

    Spells are deliberately NOT paired: the narrow hotkey pane wraps its copies of spell names
    ("Twili"/"Gaze"), and a spell must only enter the build from the central column. Both halves
    must also sit inside the same column window as the resulting kind."""
    junk = [t for t in toks if t.kind == "junk" and NAME_LIKE.match(_clean_half(t.line.text))]
    used: set[int] = set()
    for i, a in enumerate(junk):
        if id(a) in used:
            continue
        for b in junk[i + 1:]:
            if id(b) in used:
                continue
            m = norm.match_join([_clean_half(a.line.text), _clean_half(b.line.text)])
            if m and not set(m.kinds) & PAIRABLE_KINDS:
                continue
            if m and win is not None:
                spell_side = bool(set(m.kinds) & {"upgrade"})
                inside = win.in_spell if spell_side else win.in_equipment
                if not (inside(a.line.idx) and inside(b.line.idx)):
                    continue
            if m:
                a.kind, a.joined_lines = "name", (b.line,)
                a.match = Match(m.name, m.kinds, m.method.replace("line_join", "wrap_pair_nonadjacent"), m.core_text)
                b.kind, b.rule = "joined_into_previous", f"second half of wrapped name on line {a.line.no}"
                used.update((id(a), id(b)))
                break


def _complete_fragments(toks: list[Token], norm: Normalizer) -> None:
    """Complete a wrapped-name fragment to its unique catalog name. If the complement line is
    present anywhere in the record it is consumed and the method says so."""
    for tk in toks:
        if tk.kind != "junk" or not NAME_LIKE.match(tk.line.text.strip()):
            continue
        hit = norm.match_fragment(tk.line.text)
        if not hit:
            continue
        m, complement = hit
        if not set(m.kinds) & PAIRABLE_KINDS:
            continue          # spells only from full central lines (hotkey/casts panes wrap theirs)
        # If the complement was itself read as a catalog name ("Meteor" ... "Shower"), the two
        # readings conflict (Meteor + stray word vs. a wrapped Meteor Shower). Pick neither.
        if any(o.kind == "name" and o.match.core_text.casefold() == complement.casefold() for o in toks):
            tk.rule = f"fragment_conflicts_with_matched_line:{complement}"
            continue
        partner = next((o for o in toks if o.kind == "junk" and o is not tk
                        and " ".join(o.line.text.split()).casefold() == complement.casefold()), None)
        if partner is not None:
            partner.kind, partner.rule = "joined_into_previous", f"wrap complement of line {tk.line.no}"
            m = Match(m.name, m.kinds, m.method + "+complement_found", m.core_text)
            tk.joined_lines = (partner.line,)
        else:
            frag = m.core_text
            if " " not in frag and len(frag) < FRAGMENT_SOLO_MIN_LEN:
                continue      # a short single word ("Knight", "Triple") alone is not evidence
            m = Match(m.name, m.kinds, m.method + "+complement_missing", m.core_text)
        tk.kind, tk.match = "name", m


def _neighbor(toks: list[Token], i: int, step: int) -> Token | None:
    j = i + step
    while 0 <= j < len(toks):
        if toks[j].kind not in ("blank", "joined_into_previous"):
            return toks[j]
        j += step
    return None


def assign_panes(toks: list[Token], win: Windows, norm: Normalizer) -> None:
    """Decide central vs. left/right/other for every name token, recording the rule."""
    # Purchase-log wraps: "Lightning Spire: Resistance" + "Penetration". The continuation line
    # (and the colon line) are right-pane, so the fragment can never become a central upgrade.
    for i, tk in enumerate(toks):
        if tk.kind != "colon":
            continue
        tk.pane, tk.rule = "right", "purchase_log_spell_colon_form"
        for step in (1, 2, 3):
            if i + step >= len(toks):
                break
            nxt = toks[i + step]
            if nxt.kind in ("name", "junk"):
                cont = norm.match_join([tk.colon_rest, nxt.line.text]) if tk.colon_rest else None
                if cont and "upgrade" in cont.kinds and tk.colon_spell in norm.cat.upgrade_parents(cont.name):
                    nxt.pane, nxt.rule = "right", f"purchase_log_wrap_of_line_{tk.line.no}"
                    nxt.kind = "purchase_wrap"
                    break

    for i, tk in enumerate(toks):
        if tk.kind != "name" or tk.rule:
            continue
        m = tk.match
        prev, nxt = _neighbor(toks, i, -1), _neighbor(toks, i, +1)
        if m.has_number_affix:
            tk.pane, tk.rule = "left_or_right", "numeric_affix"          # hotkey charges / combat stats
        elif m.prefix and set(m.kinds) & {"spell", "upgrade"}:
            # Measured: all 41 glyph-prefixed spell lines in the dataset had a clean duplicate -
            # the glyph is the hotkey list's spell icon.
            tk.pane, tk.rule = "left", "hotkey_icon_glyph_prefix"
        elif prev is not None and nxt is not None and prev.kind == "number" and nxt.kind == "number":
            tk.pane, tk.rule = "left", "hotkey_signature_number_both_sides"
        elif nxt is not None and nxt.kind == "recipe":
            tk.pane, tk.rule = "other", "desired_list_recipe_follows"
        else:
            tk.pane, tk.rule = "central", "no_out_of_pane_signature"
