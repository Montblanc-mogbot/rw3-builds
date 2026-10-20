"""Map one OCR line to a canonical catalog name, recording exactly how.

Tiers run strictest-first and stop at the first unique hit. Every tier above ``exact`` only
fires when the transformed key identifies exactly one catalog name; a key that collides with
two names is never used (it is reported as ambiguous instead of guessed).

Prefixes/suffixes that are stripped are returned, because they are pane evidence: a central
character-sheet line never carries numbers, so ``68 Blink`` (hotkey charges) or
``4313 Chain Lightning`` (combat stats) is out of scope by construction.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from .catalog import Catalog

FUZZY_MIN_SCORE = 92.0
FUZZY_MIN_MARGIN = 4.0
FUZZY_MIN_LEN = 6
FRAGMENT_MIN_LEN = 6

# Leading numbers ("68 Blink", "13, Rain of Thunderbolts", '"0 Flame Burst') and a lone glyph
# that is really a spell icon ("M Pillar of Fire").
_NUM_PREFIX = re.compile(
    r"""^(?P<p>[^A-Za-z]{0,3}\d[^A-Za-z\s]*\s*(?:[a-z][^A-Za-z\s]*\s+)?)(?P<rest>[A-Z].*)$""")
# A glyph that is really an icon: "M Pillar of Fire", "X! Word of Chaos", "T} Word of Beauty".
_GLYPH_PREFIX = re.compile(r"^(?P<p>[A-Za-z]?[^\w\s]+\s*|[A-Za-z]\s+)(?P<rest>[A-Z].*)$")
# Combat-stat multiplicity ("Fire Wyrm Spirit Armor x81") and purchase counts ("Darkness (5)").
_COUNT_SUFFIX = re.compile(r"^(?P<rest>.*\S)\s+(?P<s>[xX×]\d+|\(\d+\))$")


def nospace_key(s: str) -> str:
    return re.sub(r"[^0-9a-z]", "", s.casefold())


def confusion_key(s: str) -> str:
    """Collapse the OCR confusions observed in this dataset onto one representative."""
    k = nospace_key(s)
    k = k.replace("m", "n")                             # Storn/Forn/Arnor/Wyrn/Conprehensive
    k = re.sub(r"[il1|!]", "l", k)                      # I/l/1/| confusion
    k = k.replace("0", "o").replace("vv", "w")
    return k


@dataclass(frozen=True)
class Match:
    name: str
    kinds: tuple[str, ...]
    method: str            # exact | casefold_nospace | ocr_confusion | fuzzy (+ "+prefix_strip"...)
    core_text: str         # the text that matched, after stripping
    prefix: str = ""       # stripped leading text (pane evidence)
    suffix: str = ""       # stripped trailing text (pane evidence)
    score: float | None = None

    @property
    def has_number_affix(self) -> bool:
        return bool(re.search(r"\d", self.prefix + self.suffix))


class Normalizer:
    def __init__(self, cat: Catalog, *, allow_fuzzy: bool = True):
        self.cat = cat
        self.allow_fuzzy = allow_fuzzy
        self.kinds: dict[str, tuple[str, ...]] = defaultdict(tuple)
        for (kind, name) in cat.entries:
            self.kinds[name] = tuple(sorted(set(self.kinds[name]) | {kind}))
        self.by_nospace = self._unique_index(nospace_key)
        self.by_confusion = self._unique_index(confusion_key)
        self._fuzzy_keys = {nospace_key(n): n for n in self.kinds}
        self._cache: dict[str, Match | None] = {}

    def _unique_index(self, keyfn) -> dict[str, str | None]:
        idx: dict[str, str | None] = {}
        for name in self.kinds:
            k = keyfn(name)
            idx[k] = None if (k in idx and idx[k] != name) else name   # None marks a collision
        return idx

    def collisions(self) -> dict[str, list[str]]:
        """Catalog names that share a confusion key (never auto-corrected to)."""
        out = defaultdict(list)
        for name in self.kinds:
            k = confusion_key(name)
            if self.by_confusion.get(k) is None:
                out[k].append(name)
        return {k: sorted(v) for k, v in out.items()}

    # -- core lookup without affix handling ---------------------------------------------------
    def _lookup(self, text: str, *, fuzzy: bool = False) -> tuple[str, str, float | None] | None:
        if text in self.kinds:
            return text, "exact", None
        k = nospace_key(text)
        if len(k) < 3:
            return None
        hit = self.by_nospace.get(k)
        if hit:
            return hit, "casefold_nospace", None
        hit = self.by_confusion.get(confusion_key(text))
        if hit:
            return hit, "ocr_confusion", None
        if fuzzy and self.allow_fuzzy and len(k) >= FUZZY_MIN_LEN:
            res = process.extract(k, self._fuzzy_keys.keys(), scorer=fuzz.ratio, limit=2)
            if res and res[0][1] >= FUZZY_MIN_SCORE:
                runner = res[1][1] if len(res) > 1 else 0.0
                if res[0][1] - runner >= FUZZY_MIN_MARGIN:
                    return self._fuzzy_keys[res[0][0]], "fuzzy", float(res[0][1])
        return None

    def match(self, raw: str) -> Match | None:
        if raw in self._cache:
            return self._cache[raw]
        m = self._match(raw)
        self._cache[raw] = m
        return m

    def _match(self, raw: str) -> Match | None:
        text = raw.strip()
        if not text or not re.search(r"[A-Za-z]{2}", text):
            return None
        hit = self._lookup(text)
        if hit:
            return Match(hit[0], self.kinds[hit[0]], hit[1], text)
        # Strip a count suffix and/or a numeric / glyph prefix, then retry. Done before fuzzy
        # matching so the affix (pane evidence) is never absorbed into a fuzzy score.
        prefix = suffix = ""
        core = text
        m = _COUNT_SUFFIX.match(core)
        if m:
            core, suffix = m.group("rest"), m.group("s")
        m = _NUM_PREFIX.match(core) or _GLYPH_PREFIX.match(core)
        if m:
            core, prefix = m.group("rest"), m.group("p").strip()
        affix = ("+prefix_strip" if prefix else "") + ("+suffix_strip" if suffix else "")
        if core != text:
            hit = self._lookup(core)
            if hit:
                return Match(hit[0], self.kinds[hit[0]], hit[1] + affix, core, prefix, suffix)
        hit = self._lookup(core, fuzzy=True)
        if hit:
            return Match(hit[0], self.kinds[hit[0]], hit[1] + affix, core, prefix, suffix, hit[2])
        return None

    def match_fragment(self, text: str) -> tuple[Match, str] | None:
        """A name the UI wrapped onto two lines whose halves the OCR did not keep together
        (``Flagellant's`` ... ``Cup``). The fragment must be whole leading or trailing words of
        exactly ONE catalog name of any kind, and at least FRAGMENT_MIN_LEN characters.
        Returns the match and the missing complement text."""
        frag = " ".join(text.split())
        if len(frag) < FRAGMENT_MIN_LEN or frag in self.kinds or frag in self.cat.stat_labels:
            return None          # "Damage" is a stat label, not half of "Damage Assimilation"
        f = frag.casefold()
        hits = []
        for name in self.kinds:
            n = name.casefold()
            if n.startswith(f + " "):
                hits.append((name, "prefix", name[len(frag) + 1:]))
            elif n.endswith(" " + f):
                hits.append((name, "suffix", name[: len(name) - len(frag) - 1]))
        if len(hits) != 1:
            return None
        name, side, complement = hits[0]
        return Match(name, self.kinds[name], f"wrap_fragment_{side}", frag), complement

    def fragment_candidates(self, text: str, kinds: set[str]) -> list[str]:
        """Every name of ``kinds`` that the fragment could be whole leading/trailing words of."""
        f = " ".join(text.split()).casefold()
        if len(f) < 3:
            return []
        return sorted(n for n, ks in self.kinds.items() if set(ks) & kinds and (
            n.casefold().startswith(f + " ") or n.casefold().endswith(" " + f)))

    def match_join(self, parts: list[str]) -> Match | None:
        """A name wrapped across lines (``Flagellant's`` / ``Cup``). Exact/nospace/confusion only."""
        joined = " ".join(p.strip() for p in parts)
        hit = self._lookup(joined)
        if not hit:
            return None
        return Match(hit[0], self.kinds[hit[0]], hit[1] + "+line_join", joined)
