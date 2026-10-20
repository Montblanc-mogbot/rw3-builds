"""Whole-dataset checks, real records, gold-set accuracy, exports and determinism."""
import json
import sqlite3
from pathlib import Path

from conftest import ROOT

from rw3builds.evaluate import evaluate, load_gold
from rw3builds.guide_link import build_link, decode_track, read_guide_constants

GOLD = ROOT / "tests" / "gold"
OUT = ROOT / "out"


def test_every_record_is_parsed_and_none_fail(parsed, records):
    by_id, _ = parsed
    assert len(by_id) == len(records) == 595
    assert not [p for p in by_id.values() if p.parse_status == "failed"]


def test_positional_rule_stays_disabled_unless_calibrated(parsed):
    _, cal = parsed
    assert cal.checks > 1000
    assert cal.positional_enabled == (cal.accuracy >= 0.95)


def test_no_unresolved_upgrade_was_silently_attached(parsed):
    by_id, _ = parsed
    for p in by_id.values():
        for u in p.unresolved_upgrades:
            assert all(u.name not in [x.name for x in s.upgrades] for s in p.spells if s.name in u.owned_candidates)


def test_every_attached_upgrade_belongs_to_its_spell_in_the_catalog(parsed, cat):
    by_id, _ = parsed
    for p in by_id.values():
        for s in p.spells:
            for u in s.upgrades:
                assert s.name in cat.upgrade_parents(u.name), (p.record_id, s.name, u.name)


def test_every_build_item_has_provenance(parsed):
    by_id, _ = parsed
    for p in by_id.values():
        for s in p.spells:
            assert s.provenance or s.status == "inferred_from_upgrade"
            for u in s.upgrades:
                assert u.provenance and all(pr.line_no > 0 and pr.raw_text for pr in u.provenance)
        for e in p.equipment:
            assert e.provenance and e.provenance[0].pane == "central"


def test_non_sheet_screenshots_are_excluded(parsed):
    by_id, _ = parsed
    p = by_id["image-2934c401eddc9aa8.png"]          # gameplay screenshot: hotkey pane only
    assert p.parse_status == "excluded" and not p.spells


def test_real_record_combat_heavy(parsed):
    by_id, _ = parsed
    p = by_id["Capture-3a7628f1314cda79.PNG"]
    names = {s.name for s in p.spells}
    assert "Storm Drake" not in names and "Chain Lightning" not in names     # damage-list only
    teleport = next(s for s in p.spells if s.name == "Teleport")
    assert [u.name for u in teleport.upgrades] == ["Quickcast"]
    assert "Adventuring Party" in {t["name"] for t in p.trials}


def test_gold_accuracy(parsed):
    by_id, _ = parsed
    gold = load_gold(GOLD)
    assert len(gold) == 25 and {g.split for g in gold} == {"dev", "heldout"}
    res = evaluate(list(by_id.values()), gold)["by_split"]
    # Floors, not targets: a regression below these fails the build.
    for split in ("dev", "heldout"):
        r = res[split]
        assert r["spells"].precision >= 0.98 and r["spells"].recall >= 0.98
        assert r["equipment"].precision >= 0.98 and r["equipment"].recall >= 0.97
        assert r["spell_upgrade_pairs"].precision >= 0.98 and r["spell_upgrade_pairs"].recall >= 0.97


def test_guide_link_round_trip(parsed, cat):
    by_id, _ = parsed
    consts = read_guide_constants(ROOT / "data" / "cache" / "app_js_live.js")
    p = by_id["image-cddb41a6e8d8c596.png"]
    url, _missing = build_link(p, cat, consts)
    from urllib.parse import parse_qs, urlparse
    g = parse_qs(urlparse(url).query)[consts["GUIDE_PARAM"]][0]
    ver, eq, sp, title = g.split(consts["GUIDE_SEP"], 3)
    assert ver == consts["GUIDE_VER"]
    by_sp = {v: k for k, v in cat.sp_ids.items()}
    decoded = [by_sp[i] for _h, items in decode_track(sp) for it in items for i in it]
    spells_seen = set()
    for key in decoded:                          # the site drops an upgrade before its spell
        if "::" in key:
            assert key.split("::")[0] in spells_seen
        else:
            spells_seen.add(key)
    assert {s.name for s in p.spells} == spells_seen
    by_eq = {v: k for k, v in cat.equipment_ids.items()}
    assert {by_eq[i] for _h, items in decode_track(eq) for it in items for i in it} == \
        {e.name for e in p.equipment if e.kind == "equipment"}


def test_outputs_agree_json_sqlite(parsed):
    """Run `python -m rw3builds run` first; checks the written artifacts agree with each other."""
    if not (OUT / "rw3_builds.sqlite").exists():
        import pytest
        pytest.skip("out/ not generated yet")
    data = json.loads((OUT / "builds.json").read_text(encoding="utf-8"))
    con = sqlite3.connect(OUT / "rw3_builds.sqlite")
    try:
        n_json_pairs = sum(len(s["upgrades"]) for r in data["records"] for s in r["spells"])
        n_db_pairs = con.execute("SELECT COUNT(*) FROM run_spell_upgrade").fetchone()[0]
        assert n_json_pairs == n_db_pairs
        n_json_count = sum(r["is_countable"] for r in data["records"])
        assert n_json_count == con.execute("SELECT COUNT(*) FROM v_countable_runs").fetchone()[0]
        # Every run upgrade points at its parent spell's run_spell row (FK) and catalog parent.
        bad = con.execute("""SELECT COUNT(*) FROM run_spell_upgrade rsu JOIN catalog_upgrade u USING (upgrade_id)
                             WHERE u.spell_id <> rsu.spell_id""").fetchone()[0]
        assert bad == 0
    finally:
        con.close()


def test_determinism(records, cat):
    from rw3builds.pipeline import run
    sample = [records[k] for k in sorted(records)[:60]]
    a, _ = run(sample, cat)
    b, _ = run(sample, cat)
    assert [json.dumps(x.to_dict(), sort_keys=True) for x in a] == [json.dumps(x.to_dict(), sort_keys=True) for x in b]
