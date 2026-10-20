"""Flag records that are the same winning build posted more than once."""
from __future__ import annotations

from .models import RecordParse


def fingerprint(p: RecordParse) -> tuple:
    spells = tuple(sorted((s.name, tuple(sorted(u.name for u in s.upgrades))) for s in p.spells))
    equip = tuple(sorted(e.name for e in p.equipment))
    return (spells, equip, p.turns_game, p.hp_max, p.realm)


def mark_duplicates(parses: list[RecordParse]) -> None:
    """Same spells+upgrades+equipment+game turns+max HP+realm => a re-post of one win.
    The earliest record in file order is the canonical copy; later ones point at it and are
    excluded from frequency denominators. Records with no extracted spells are never matched
    (an empty fingerprint would merge unrelated failures)."""
    seen: dict[tuple, str] = {}
    for p in parses:
        p.is_countable = p.parse_status in ("validated", "partial", "needs_review") and p.outcome == "VICTORY" \
            and bool(p.spells)
        if not p.spells or p.parse_status in ("excluded", "failed"):
            continue
        fp = fingerprint(p)
        if fp in seen:
            p.duplicate_of = seen[fp]
            p.is_countable = False
            p.flags.append(f"duplicate_of:{seen[fp]}")
        else:
            seen[fp] = p.record_id
