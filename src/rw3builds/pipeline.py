"""Run every record through extraction, calibrate the positional rule, classify, dedupe."""
from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass

from .catalog import Catalog
from .extract import POSITIONAL_MIN_ACCURACY, extract
from .models import RecordParse
from .normalize import Normalizer
from .records import Record

log = logging.getLogger(__name__)


@dataclass
class Calibration:
    checks: int
    correct: int
    threshold: float

    @property
    def accuracy(self) -> float | None:
        return self.correct / self.checks if self.checks else None

    @property
    def positional_enabled(self) -> bool:
        return self.accuracy is not None and self.accuracy >= self.threshold


def _safe_extract(rec: Record, cat: Catalog, norm: Normalizer, allow_positional: bool) -> RecordParse:
    try:
        return extract(rec, cat, norm, allow_positional=allow_positional)
    except Exception as exc:  # keep the record, mark it failed, never abort the run
        log.exception("record %s failed", rec.record_id)
        out = RecordParse(record_id=rec.record_id, header_line_no=rec.header_line_no, outcome=None,
                          outcome_raw=None, realm=None, turns_game=None, turns_level=None, hp=None,
                          hp_max=None, sp=None, sh=None)
        out.parse_status = "failed"
        out.error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        return out


def run(records: list[Record], cat: Catalog) -> tuple[list[RecordParse], Calibration]:
    norm = Normalizer(cat)
    # Pass 1 (positional disabled) only measures how often "nearest preceding spell" agrees
    # with the catalog where the catalog already knows the answer.
    first = [_safe_extract(r, cat, norm, allow_positional=False) for r in records]
    checks = [c for p in first for c in p.positional_checks]
    cal = Calibration(len(checks), sum(c["correct"] for c in checks), POSITIONAL_MIN_ACCURACY)
    log.info("positional calibration: %s/%s = %s (enabled=%s)", cal.correct, cal.checks,
             f"{cal.accuracy:.3f}" if cal.accuracy is not None else "n/a", cal.positional_enabled)
    parses = first if not cal.positional_enabled else [
        _safe_extract(r, cat, norm, allow_positional=True) for r in records]
    for p in parses:
        if p.parse_status != "failed":
            classify(p)
    from .dedupe import mark_duplicates
    mark_duplicates(parses)
    return parses, cal


REVIEW_FLAG_PREFIXES = ("missing_", "fuzzy_match:", "spell_only_in_hotkey_list:", "spell_inferred_from_upgrade:",
                        "ambiguous_column_kind:", "ambiguous_trial_or_companion:", "possible_missed_spell_column_item:",
                        "turns_game_from_ocr", "wrap_fragment_unconfirmed:", "spell_only_from_wrapped_lines:")
# risky_upgrade_name_held_back is not a review trigger: the item is already safely unresolved.


def classify(p: RecordParse) -> None:
    has_anchors = p.anchors.get("spell_window") is not None or p.anchors.get("equipment_window") is not None
    if p.outcome is None and not has_anchors:
        p.parse_status = "excluded"
        p.flags.append("excluded:not_a_character_sheet")
        return
    if p.outcome is not None and p.outcome != "VICTORY":
        p.parse_status = "excluded"
        p.flags.append(f"excluded:outcome_{p.outcome}")
        return
    if p.outcome is None:
        p.flags.append("missing_outcome")
    if not p.spells:
        p.flags.append("no_spells_extracted")
    uncertain = p.unresolved_upgrades or any(
        u.association != "verified" for s in p.spells for u in s.upgrades) or any(
        s.status != "owned" for s in p.spells)
    review = any(f.startswith(REVIEW_FLAG_PREFIXES) for f in p.flags) or not p.spells
    if review:
        p.parse_status = "needs_review"
    elif uncertain:
        p.parse_status = "partial"
    else:
        p.parse_status = "validated"
