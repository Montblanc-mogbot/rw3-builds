"""Score parser output against hand-annotated gold records (tests/gold/*.yaml).

Gold files list what a careful human reading of the SAME OCR text (plus the catalog) concludes
is in the central character sheet. Items the annotator could not decide go under ``uncertain``
and are removed from both sides before scoring. The gold set therefore measures the parser's
reading of the OCR, not the OCR's fidelity to the original screenshot.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .models import RecordParse


@dataclass
class Gold:
    record_id: str
    split: str
    spells: dict[str, list[str]]
    equipment: list[str]
    uncertain_spells: set[str]
    uncertain_equipment: set[str]
    uncertain_pairs: set[tuple[str, str]]
    notes: str


def load_gold(gold_dir: Path) -> list[Gold]:
    out = []
    for p in sorted(gold_dir.glob("*.yaml")):
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        unc = d.get("uncertain") or {}
        out.append(Gold(
            record_id=d["record_id"], split=d["split"],
            spells={k: list(v or []) for k, v in (d.get("spells") or {}).items()},
            equipment=list(d.get("equipment") or []),
            uncertain_spells=set(unc.get("spells") or []),
            uncertain_equipment=set(unc.get("equipment") or []),
            uncertain_pairs={tuple(x.split("::", 1)) for x in (unc.get("pairs") or [])},
            notes=d.get("notes", ""),
        ))
    return out


@dataclass
class PR:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def add(self, pred: set, gold: set):
        self.tp += len(pred & gold)
        self.fp += len(pred - gold)
        self.fn += len(gold - pred)

    @property
    def precision(self):
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self):
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None


def predicted_sets(p: RecordParse):
    spells = {s.name for s in p.spells}
    pairs = {(s.name, u.name) for s in p.spells for u in s.upgrades}
    equipment = {e.name for e in p.equipment}
    return spells, pairs, equipment


def evaluate(parses: list[RecordParse], gold: list[Gold]) -> dict:
    by_id = {p.record_id: p for p in parses}
    results: dict[str, dict] = {}
    errors: list[dict] = []
    for split in ("dev", "heldout", "all"):
        sp, eq, pa = PR(), PR(), PR()
        n = 0
        for g in gold:
            if split != "all" and g.split != split:
                continue
            p = by_id.get(g.record_id)
            if p is None:
                continue
            n += 1
            ps, pp, pe = predicted_sets(p)
            gs = set(g.spells)
            gp = {(s, u) for s, ups in g.spells.items() for u in ups}
            ge = set(g.equipment)
            ps, gs = ps - g.uncertain_spells, gs - g.uncertain_spells
            pe, ge = pe - g.uncertain_equipment, ge - g.uncertain_equipment
            pp = {x for x in pp if x not in g.uncertain_pairs and x[0] not in g.uncertain_spells}
            gp = {x for x in gp if x not in g.uncertain_pairs and x[0] not in g.uncertain_spells}
            sp.add(ps, gs)
            eq.add(pe, ge)
            pa.add(pp, gp)
            if split == "all":
                for kind, pred, gl in (("spell", ps, gs), ("equipment", pe, ge), ("pair", pp, gp)):
                    for x in sorted(pred - gl, key=str):
                        errors.append({"record_id": g.record_id, "split": g.split, "kind": kind, "error": "false_positive", "item": x})
                    for x in sorted(gl - pred, key=str):
                        errors.append({"record_id": g.record_id, "split": g.split, "kind": kind, "error": "false_negative", "item": x})
        results[split] = {"records": n, "spells": sp, "equipment": eq, "spell_upgrade_pairs": pa}
    return {"by_split": results, "errors": errors}
