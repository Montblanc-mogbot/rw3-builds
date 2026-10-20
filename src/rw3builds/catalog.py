"""Canonical game-data catalog built from hpp3/rw3 compendium snapshots.

The union of the dataset-period snapshots defines what names exist. Each entry remembers the
snapshots it was seen in, so a name that only existed in an older build is still canonical for
this dataset. The *live* snapshot is used only for stable ids (guide links) and never adds names.

Kinds:
  spell      - a learnable spell (central Spells column)
  upgrade    - a spell upgrade; ``parents`` lists every spell that defines an upgrade by this name
  equipment  - craftable equipment (central Equipment column)
  companion  - a Tavern companion (units with ``is_companion``; appears in the Equipment column)
  tome       - a school tome, ``<School> Tome`` where School is a spell tag (pattern rule; these
               are generated in-game and absent from the compendium)
  component  - crafting components (diagnostic only, never build content)
  trial      - a run modifier ("Limited Spellbook", "Oner", ...), from the localization string
               table's Mutators.py trial list. Run metadata, never build content.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .fetch import CATALOG_SNAPSHOTS

BUILD_KINDS_SPELL_COLUMN = frozenset({"spell", "upgrade"})
BUILD_KINDS_EQUIPMENT_COLUMN = frozenset({"equipment", "companion", "tome"})


@dataclass
class Entry:
    name: str
    kind: str
    snapshots: set[str] = field(default_factory=set)
    parents: set[str] = field(default_factory=set)      # upgrades only
    slot: str | None = None                              # equipment only
    level: int | None = None                             # spells / upgrades (first seen)
    tags: tuple[str, ...] = ()
    source: str = "hpp3/rw3"                             # or "pattern:school_tome"


@dataclass
class Catalog:
    # (kind, name) -> Entry. A name can in principle have several kinds; lookups return all.
    entries: dict[tuple[str, str], Entry]
    spell_tags: frozenset[str]
    sp_ids: dict[str, int]          # "Spell" / "Spell::Upgrade" -> stable id (live)
    equipment_ids: dict[str, int]   # equipment name -> stable id (live)
    snapshot_dates: tuple[str, ...]
    stat_labels: frozenset[str] = frozenset()   # "Radius", "Shields", ... (compendium stat_meta)

    def kinds_of(self, name: str) -> list[Entry]:
        return [e for (k, n), e in self.entries.items() if n == name]

    def get(self, kind: str, name: str) -> Entry | None:
        return self.entries.get((kind, name))

    def names(self) -> set[str]:
        return {n for (_, n) in self.entries}

    def upgrade_parents(self, name: str) -> set[str]:
        e = self.entries.get(("upgrade", name))
        return set(e.parents) if e else set()

    def spells(self) -> list[Entry]:
        return sorted((e for e in self.entries.values() if e.kind == "spell"), key=lambda e: e.name)


def _as_list(v):
    # A few live-snapshot fields are serialized as Python-repr strings; we only need tags.
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v.startswith("["):
        import ast
        try:
            return ast.literal_eval(v)
        except (ValueError, SyntaxError):
            return []
    return []


def load_catalog(cache_dir: Path) -> Catalog:
    entries: dict[tuple[str, str], Entry] = {}
    spell_tags: set[str] = set()
    stat_labels: set[str] = {"Bonus"}   # generic stat-upgrade word not in stat_meta

    def add(kind: str, name: str, snap: str, **kw) -> Entry:
        e = entries.get((kind, name))
        if e is None:
            e = entries[(kind, name)] = Entry(name=name, kind=kind)
        e.snapshots.add(snap)
        for k, v in kw.items():
            if v is not None and getattr(e, k) in (None, ()):
                setattr(e, k, v)
        return e

    for date in CATALOG_SNAPSHOTS:
        data = json.loads((cache_dir / f"catalog_{date}.json").read_text(encoding="utf-8"))
        stat_labels.update(v for v in (data.get("stat_meta") or {}).values() if isinstance(v, str))
        for s in data["spells"]:
            tags = tuple(_as_list(s.get("tags")))
            spell_tags.update(tags)
            add("spell", s["name"], date, level=s.get("level"), tags=tags)
            for u in s.get("upgrades", []):
                e = add("upgrade", u["name"], date, level=u.get("level"))
                e.parents.add(s["name"])
        for eq in data["equipment"]:
            add("equipment", eq["name"], date, slot=eq.get("slot"), tags=tuple(_as_list(eq.get("tags"))))
        for c in data["components"]:
            add("component", c["name"], date)
        for name, unit in (data.get("units") or {}).items():
            if str(unit.get("is_companion")) == "True":
                add("companion", unit.get("name", name), date)

    for tag in sorted(spell_tags):
        e = add("tome", f"{tag} Tome", "pattern")
        e.source = "pattern:school_tome"

    for name in load_trial_names(cache_dir):
        e = add("trial", name, "localization")
        e.source = "localization:Mutators.py"

    ids = json.loads((cache_dir / "ids_live.json").read_text(encoding="utf-8"))
    return Catalog(
        entries=entries,
        spell_tags=frozenset(spell_tags),
        sp_ids=dict(ids.get("sp", {})),
        equipment_ids=dict(ids.get("equipment", {})),
        snapshot_dates=tuple(CATALOG_SNAPSHOTS),
        stat_labels=frozenset(stat_labels),
    )


# The trial table is one contiguous block of string literals in Mutators.py (lines ~1852-1873 in
# the pinned build: "Limited Spellbook" .. "Mordred's Vengeance"). We take the block that
# contains "Limited Spellbook" and stop at the first gap, rather than hard-coding the names.
TRIAL_ANCHOR = "Limited Spellbook"


def load_trial_names(cache_dir: Path) -> list[str]:
    path = cache_dir / "loc_keys.json"
    if not path.exists():
        return []
    rows: dict[int, str] = {}
    for k in json.loads(path.read_text(encoding="utf-8")):
        for o in k["orig"]:
            f, _, ln = o.partition(":")
            if f == "Mutators.py" and ln.isdigit():
                rows.setdefault(int(ln), k["k"])
    start = next((ln for ln, n in rows.items() if n == TRIAL_ANCHOR), None)
    if start is None:
        return []
    names, ln = [], start
    while ln in rows:
        names.append(rows[ln])
        ln += 1
    return names


def catalog_summary(cat: Catalog) -> dict:
    by_kind: dict[str, int] = defaultdict(int)
    for (k, _), _e in cat.entries.items():
        by_kind[k] += 1
    shared = {e.name: sorted(e.parents) for e in cat.entries.values() if e.kind == "upgrade" and len(e.parents) > 1}
    multi = defaultdict(list)
    for (k, n) in cat.entries:
        multi[n].append(k)
    return {
        "by_kind": dict(sorted(by_kind.items())),
        "shared_upgrade_names": dict(sorted(shared.items())),
        "multi_kind_names": {n: sorted(ks) for n, ks in sorted(multi.items()) if len(ks) > 1},
    }
