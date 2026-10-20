"""Turn classified tokens into one structured build (spells+upgrades nested, equipment)."""
from __future__ import annotations

import re
from collections import OrderedDict

from .catalog import BUILD_KINDS_EQUIPMENT_COLUMN, Catalog
from .models import (EquipmentOut, Mention, Provenance, RecordParse, SpellOut, UnknownToken,
                     UnresolvedUpgrade, UpgradeOut)
from .normalize import Normalizer
from .records import Record
from .segment import NAME_LIKE, Token, Windows, assign_panes, classify_lines, find_windows

# Positional parent assignment is only trusted if calibration on catalog-unique upgrades clears
# this bar (see associate_positional_accuracy in report.py); the pipeline passes the decision in.
POSITIONAL_MIN_ACCURACY = 0.95

_OUTCOME = re.compile(r"^Outco\w*\s*[:;]\s*(?P<v>\w+)")
_REALM_TURN = re.compile(r"^Real\w*\s+(?P<r>\d+)\s*[,.]\s*Turn", re.I)
_REALM = re.compile(r"^Real\w*\s+(?P<r>\d+)\s*$", re.I)
_TURNS = re.compile(r"^(?P<n>\d+)\s*\((?P<k>[A-Za-z0-9])\)?\s*$")
_HP = re.compile(r"^HP\s*(?P<a>\d+)\s*/\s*(?P<b>\d+)")
_SP = re.compile(r"^SP\s*(?P<v>\d+)\s*$")
_SH = re.compile(r"^SH\s*(?P<v>\d+)\s*$")


def _prov(tk: Token) -> Provenance:
    m = tk.match
    raw = tk.line.text if not tk.joined_lines else "\n".join([tk.line.text, *(l.text for l in tk.joined_lines)])
    return Provenance(line_no=tk.line.no, raw_text=raw, matched_text=m.core_text, normalization=m.method,
                      pane=tk.pane, rule=tk.rule, fuzzy_score=m.score)


def normalize_outcome(raw: str) -> str:
    """"VICTORY" also when the OCR garbled it by at most 2 edits ("VICTORI", "VIGTCRY"). Any
    other word is kept verbatim (upper-cased) so it can be excluded explicitly."""
    from rapidfuzz.distance import Levenshtein
    v = raw.upper()
    if v.startswith("VICTOR") or Levenshtein.distance(v, "VICTORY") <= 2:
        return "VICTORY"
    return v


def parse_meta(rec: Record, out: RecordParse) -> None:
    texts = [l.text.strip() for l in rec.lines]
    for t in texts:
        if out.outcome_raw is None and (m := _OUTCOME.match(t)):
            out.outcome_raw = m.group("v")
            out.outcome = normalize_outcome(m.group("v"))
            if out.outcome == "VICTORY" and not m.group("v").upper().startswith("VICTOR"):
                out.flags.append(f"outcome_ocr_corrected:{m.group('v')}")
        if out.realm is None and (m := _REALM_TURN.match(t)):
            out.realm = int(m.group("r"))
        if out.hp is None and (m := _HP.match(t)):
            out.hp, out.hp_max = int(m.group("a")), int(m.group("b"))
        if out.sp is None and (m := _SP.match(t)):
            out.sp = int(m.group("v"))
        if out.sh is None and (m := _SH.match(t)):
            out.sh = int(m.group("v"))
    if out.realm is None:
        out.realm = next((int(m.group("r")) for t in texts if (m := _REALM.match(t))), None)
    # "Turns taken:" is followed (interleaved) by "<n> (L)" = turns this realm and
    # "<n> (G)" = whole game. Only accept the explicit (L)/(G) markers; OCR'd "(6)" for "(G)"
    # is accepted only when (G) itself is absent and the value is not the (L) value.
    for t in texts:
        if (m := _TURNS.match(t)):
            k = m.group("k").upper()
            if k == "G" and out.turns_game is None:
                out.turns_game = int(m.group("n"))
            elif k == "L" and out.turns_level is None:
                out.turns_level = int(m.group("n"))
    if out.turns_game is None:
        sixes = [int(m.group("n")) for t in texts if (m := _TURNS.match(t)) and m.group("k") == "6"]
        if len(sixes) == 1:
            out.turns_game = sixes[0]
            out.flags.append("turns_game_from_ocr_variant_(6)")


def extract(rec: Record, cat: Catalog, norm: Normalizer, *, allow_positional: bool) -> RecordParse:
    out = RecordParse(record_id=rec.record_id, header_line_no=rec.header_line_no, outcome=None,
                      outcome_raw=None, realm=None, turns_game=None, turns_level=None, hp=None,
                      hp_max=None, sp=None, sh=None)
    parse_meta(rec, out)
    win = find_windows(rec)
    out.flags.extend(win.flags)
    out.anchors = {"spell_window": win.spell, "equipment_window": win.equipment,
                   **{k: v for k, v in win.positions.items() if v}}
    toks = classify_lines(rec, norm, win)
    assign_panes(toks, win, norm)

    spells: "OrderedDict[str, SpellOut]" = OrderedDict()
    equipment: "OrderedDict[str, EquipmentOut]" = OrderedDict()
    upgrade_toks: list[Token] = []
    central_seq: list[tuple[int, str, str]] = []      # (idx, kind, name) in central spell column
    left_only_spells: dict[str, list[Provenance]] = {}

    for tk in toks:
        idx = tk.line.idx
        if tk.kind == "notice":
            if win.in_spell(idx):
                central_seq.append((idx, "notice", str(tk.notice_count)))
            continue
        if tk.kind == "junk":
            t = tk.line.text.strip()
            zone = win.zone(idx)
            if zone != "outside":
                out.unknown_tokens.append(UnknownToken(tk.line.no, tk.line.text, zone, bool(NAME_LIKE.match(t))))
            continue
        if tk.kind != "name":
            continue
        m = tk.match
        kinds = set(m.kinds)
        if "trial" in kinds:
            out.trials.append({"name": m.name, "line_no": tk.line.no, "raw_text": tk.line.text,
                               "normalization": m.method, "source": "localization:Mutators.py"})
            if kinds & BUILD_KINDS_EQUIPMENT_COLUMN and tk.pane == "central" and win.in_equipment(idx):
                out.flags.append(f"ambiguous_trial_or_companion:{m.name}")
            continue
        if "component" in kinds and not (kinds - {"component"}):
            if tk.pane == "central":
                out.components.append(m.name)
            continue
        prov = _prov(tk)

        spell_col = kinds & {"spell", "upgrade"}
        equip_col = kinds & BUILD_KINDS_EQUIPMENT_COLUMN
        in_scope_spell = tk.pane == "central" and win.in_spell(idx) and spell_col
        in_scope_equip = tk.pane == "central" and win.in_equipment(idx) and equip_col
        if in_scope_spell or in_scope_equip:
            # Weak-identity flags only matter for items that enter the build.
            if m.method.startswith("fuzzy"):
                out.flags.append(f"fuzzy_match:{m.name}")
            if m.method.endswith("complement_missing"):
                out.flags.append(f"wrap_fragment_unconfirmed:{m.name}")
        if in_scope_spell and in_scope_equip:
            # A name that is both a spell-column and an equipment-column kind, inside both
            # windows: no line-level evidence decides. Keep it out and say so.
            out.flags.append(f"ambiguous_column_kind:{m.name}")
            out.out_of_scope_mentions.append(Mention(m.name, "/".join(sorted(kinds)), prov))
            continue
        if in_scope_spell:
            kind = next(iter(spell_col)) if len(spell_col) == 1 else "ambiguous"
            if kind == "spell":
                sp = spells.setdefault(m.name, SpellOut(m.name, "owned"))
                sp.provenance.append(prov)
                central_seq.append((idx, "spell", m.name))
            elif kind == "upgrade":
                upgrade_toks.append(tk)
                central_seq.append((idx, "upgrade", m.name))
            continue
        if in_scope_equip:
            kind = next(iter(equip_col))
            e = equipment.setdefault(m.name, EquipmentOut(m.name, kind, _slot(cat, m.name)))
            e.provenance.append(prov)
            continue
        # Out of scope: hotkey list, right pane, desired list, outside both windows.
        for k in sorted(kinds):
            out.out_of_scope_mentions.append(Mention(m.name, k, prov))
        if "spell" in kinds and tk.pane == "left":
            left_only_spells.setdefault(m.name, []).append(prov)

    for name in left_only_spells:
        if name not in spells:
            out.flags.append(f"spell_only_in_hotkey_list:{name}")

    _attach_notices(central_seq, spells)
    loose_words = {" ".join(t.line.text.split()).strip("'\"`").casefold() for t in toks if t.kind == "junk"}
    upgrade_toks = _hold_back_risky_names(upgrade_toks, cat, norm, loose_words, spells, out)
    _associate(upgrade_toks, central_seq, spells, cat, out, allow_positional=allow_positional)
    out.spells = list(spells.values())
    out.equipment = list(equipment.values())
    for sp in out.spells:
        if sp.status == "owned" and not sp.upgrades and sp.provenance and \
                all("line_join" in pr.normalization for pr in sp.provenance):
            # Only evidence: two adjacent lines joined, and no upgrade corroborates it. The hotkey
            # and casts panes also wrap spell names, so this deserves a human look.
            out.flags.append(f"spell_only_from_wrapped_lines:{sp.name}")
    _flag_possible_misses(out, norm)
    return out


def _flag_possible_misses(out: RecordParse, norm: Normalizer) -> None:
    """An unmatched word inside a build column that could only be part of names NOT in the build
    means an item may have been lost (wrapped/garbled). If any completion is already present the
    word is almost always the narrow hotkey pane wrapping its copy of that item (measured:
    "Savage" beside "Savage Spree", "Eye of" beside "Floating Eye"), so it is not flagged."""
    have_spell_col = {s.name for s in out.spells} | {u.name for s in out.spells for u in s.upgrades}
    have_equip = {e.name for e in out.equipment}
    for u in out.unknown_tokens:
        if not u.name_like:
            continue
        if u.zone in ("spell_window", "both"):
            cands = norm.fragment_candidates(u.raw_text, {"spell", "upgrade"})
            if cands and not set(cands) & have_spell_col:
                out.flags.append(f"possible_missed_spell_column_item:{u.raw_text.strip()}")
        if u.zone in ("equipment_window", "both"):
            cands = norm.fragment_candidates(u.raw_text, set(BUILD_KINDS_EQUIPMENT_COLUMN))
            if cands and not set(cands) & have_equip:
                out.flags.append(f"possible_missed_equipment:{u.raw_text.strip()}")


def _hold_back_risky_names(upgrade_toks, cat: Catalog, norm: Normalizer, loose_words: set[str],
                           spells, out: RecordParse) -> list:
    """One-word upgrade names whose bare line is not reliable evidence of that upgrade:
      * stat labels ("Radius", "Shields", "Bonus") - indistinguishable from stat/UI text and from
        the tail of a wrapped "Sonic Shields"; always held back.
      * a word that is also part of a longer catalog name ("Meteor" / "Meteor Shower",
        "Cascade" / "Cantrip Cascade") - held back only if that longer name's other half is
        present in the record as an unmatched line.
    Held-back names go to unresolved_upgrades with the reason; nothing is guessed."""
    keep = []
    for tk in upgrade_toks:
        name = tk.match.name
        reason = None
        if " " not in name and tk.match.method == "exact":
            if name in cat.stat_labels:
                reason = "generic stat-word upgrade name (also a UI stat label / tail of a wrapped name)"
            else:
                for longer in norm.fragment_candidates(name, {"spell", "upgrade", "equipment", "companion", "tome"}):
                    if longer == name:
                        continue
                    rest = longer.casefold().replace(name.casefold(), "", 1).strip()
                    if rest in loose_words:
                        reason = f"could be half of '{longer}' (its other half '{rest}' is in the record)"
                        break
        if reason is None:
            keep.append(tk)
            continue
        parents = sorted(cat.upgrade_parents(name))
        owned = [p for p in parents if p in spells and spells[p].status == "owned"]
        out.unresolved_upgrades.append(UnresolvedUpgrade(name, parents, owned, reason, [_prov(tk)]))
        out.flags.append(f"risky_upgrade_name_held_back:{name}")
    return keep


def _slot(cat: Catalog, name: str) -> str | None:
    e = cat.get("equipment", name)
    return e.slot if e else None


def _attach_notices(seq, spells) -> None:
    """'N Upgrades Available' sits under its spell in the UI; attach it to the nearest preceding
    central spell, labelled positional. It is never an upgrade."""
    last_spell = None
    for idx, kind, name in sorted(seq):
        if kind == "spell":
            last_spell = name
        elif kind == "notice" and last_spell is not None:
            spells[last_spell].notices.append({"available": None if name == "None" else int(name),
                                               "association": "positional", "line_idx": idx})


def nearest_preceding_spell(seq, idx: int, among: set[str] | None = None) -> str | None:
    best = None
    for i, kind, name in sorted(seq):
        if i >= idx:
            break
        if kind == "spell" and (among is None or name in among):
            best = name
    return best


def _weak_identity(pr: Provenance) -> bool:
    return pr.normalization.startswith("fuzzy") or pr.normalization.endswith("complement_missing")


def _associate(upgrade_toks, seq, spells, cat: Catalog, out: RecordParse, *, allow_positional: bool) -> None:
    by_name: "OrderedDict[str, list[Token]]" = OrderedDict()
    for tk in upgrade_toks:
        by_name.setdefault(tk.match.name, []).append(tk)
    for name, tks in by_name.items():
        provs = [_prov(t) for t in tks]
        parents = cat.upgrade_parents(name)
        owned = sorted(p for p in parents if p in spells and spells[p].status == "owned")
        if len(parents) == 1 and owned:
            spells[owned[0]].upgrades.append(UpgradeOut(name, "verified", "catalog_unique", provs))
            owned_all = {n for n, s in spells.items() if s.status == "owned"}
            guess = nearest_preceding_spell(seq, tks[0].line.idx, among=owned_all)
            out.positional_checks.append({"upgrade": name, "parent": owned[0], "positional_guess": guess,
                                          "correct": guess == owned[0]})
        elif len(parents) > 1 and len(owned) == 1:
            spells[owned[0]].upgrades.append(UpgradeOut(name, "verified", "catalog_build_disambiguated", provs))
        elif len(parents) > 1 and len(owned) > 1:
            guess = nearest_preceding_spell(seq, tks[0].line.idx, among=set(owned))
            if allow_positional and guess:
                spells[guess].upgrades.append(UpgradeOut(name, "probable", "positional", provs))
            else:
                out.unresolved_upgrades.append(UnresolvedUpgrade(
                    name, sorted(parents), owned,
                    "several candidate parent spells owned" + ("" if allow_positional else "; positional rule disabled by calibration"),
                    provs))
        elif len(parents) == 1 and not all(_weak_identity(p) for p in provs):
            parent = next(iter(parents))
            sp = spells.setdefault(parent, SpellOut(parent, "inferred_from_upgrade"))
            sp.upgrades.append(UpgradeOut(name, "inferred", "implied_parent", provs))
            out.flags.append(f"spell_inferred_from_upgrade:{parent}")
        elif len(parents) == 1:
            out.unresolved_upgrades.append(UnresolvedUpgrade(
                name, sorted(parents), [], "parent spell not in the build and the upgrade line itself is a weak "
                "match (fragment without its other half, or fuzzy) - not used to imply the spell", provs))
        else:
            out.unresolved_upgrades.append(UnresolvedUpgrade(
                name, sorted(parents), [], "no candidate parent spell detected in the build", provs))
