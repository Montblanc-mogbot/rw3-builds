"""Normalized SQLite database + CSV export.

Upgrades are catalog rows keyed by (spell, upgrade name), so "Quickcast" on Teleport and on
Freeze are different rows and a run's upgrade always points at exactly one parent spell.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .catalog import Catalog
from .models import RecordParse

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE source_file (
    key TEXT PRIMARY KEY, url TEXT, repo TEXT, commit_sha TEXT, path TEXT, sha256 TEXT NOT NULL
);

CREATE TABLE catalog_spell (
    spell_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, level INTEGER, tags TEXT,
    sp_id INTEGER, snapshots TEXT NOT NULL
);
CREATE TABLE catalog_upgrade (
    upgrade_id INTEGER PRIMARY KEY,
    spell_id INTEGER NOT NULL REFERENCES catalog_spell(spell_id),
    name TEXT NOT NULL, sp_id INTEGER,
    name_shared_with_other_spells INTEGER NOT NULL,     -- 1 for Quickcast, Shield Burn, ...
    UNIQUE (spell_id, name)
);
CREATE TABLE catalog_equipment (
    equipment_id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, -- equipment|companion|tome
    slot TEXT, tags TEXT, compendium_id INTEGER, source TEXT NOT NULL, snapshots TEXT NOT NULL,
    UNIQUE (kind, name)
);

CREATE TABLE run (
    run_id INTEGER PRIMARY KEY,
    record_id TEXT NOT NULL UNIQUE,            -- screenshot file name in the raw OCR dump
    header_line_no INTEGER NOT NULL,
    outcome TEXT, outcome_raw TEXT,
    victory_confirmed INTEGER NOT NULL,        -- an Outcome: VICTORY line was read
    realm INTEGER, turns_game INTEGER, turns_level INTEGER,
    hp INTEGER, hp_max INTEGER, sp INTEGER, sh INTEGER,
    parse_status TEXT NOT NULL,                -- validated|partial|needs_review|excluded|failed
    is_countable INTEGER NOT NULL,             -- victory, has spells, not a duplicate
    duplicate_of TEXT,
    flags TEXT NOT NULL,                       -- JSON list
    trials TEXT NOT NULL,                      -- JSON list of run-modifier names (metadata)
    compendium_url TEXT,
    error TEXT,
    raw_text TEXT NOT NULL
);

CREATE TABLE run_spell (
    run_id INTEGER NOT NULL REFERENCES run(run_id),
    spell_id INTEGER NOT NULL REFERENCES catalog_spell(spell_id),
    status TEXT NOT NULL,                      -- owned | inferred_from_upgrade
    first_line_no INTEGER,
    PRIMARY KEY (run_id, spell_id)
);
CREATE TABLE run_spell_upgrade (
    run_id INTEGER NOT NULL,
    spell_id INTEGER NOT NULL,
    upgrade_id INTEGER NOT NULL REFERENCES catalog_upgrade(upgrade_id),
    association TEXT NOT NULL,                 -- verified | probable | inferred
    method TEXT NOT NULL,                      -- catalog_unique | catalog_build_disambiguated | positional | implied_parent
    first_line_no INTEGER,
    PRIMARY KEY (run_id, upgrade_id),
    FOREIGN KEY (run_id, spell_id) REFERENCES run_spell(run_id, spell_id)
);
CREATE TABLE run_unresolved_upgrade (
    run_id INTEGER NOT NULL REFERENCES run(run_id),
    upgrade_name TEXT NOT NULL,
    candidate_spells TEXT NOT NULL,            -- JSON: every spell defining this upgrade name
    owned_candidates TEXT NOT NULL,            -- JSON: those present in this build
    reason TEXT NOT NULL,
    raw_text TEXT NOT NULL, line_no INTEGER
);
CREATE TABLE run_equipment (
    run_id INTEGER NOT NULL REFERENCES run(run_id),
    equipment_id INTEGER NOT NULL REFERENCES catalog_equipment(equipment_id),
    first_line_no INTEGER,
    PRIMARY KEY (run_id, equipment_id)
);
CREATE TABLE run_notice (
    run_id INTEGER NOT NULL REFERENCES run(run_id),
    spell_id INTEGER NOT NULL REFERENCES catalog_spell(spell_id),
    upgrades_available INTEGER,                -- "N Upgrades Available" - NOT purchased upgrades
    association TEXT NOT NULL                  -- always 'positional'
);
CREATE TABLE run_component (
    run_id INTEGER NOT NULL REFERENCES run(run_id), name TEXT NOT NULL
);

-- Provenance for every build item: which line, what OCR text, what normalization, which rule.
CREATE TABLE extraction (
    extraction_id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES run(run_id),
    item_kind TEXT NOT NULL,                   -- spell | upgrade | equipment | unresolved_upgrade
    item_name TEXT NOT NULL, parent_spell TEXT,
    line_no INTEGER NOT NULL, raw_text TEXT NOT NULL, matched_text TEXT NOT NULL,
    normalization TEXT NOT NULL, pane TEXT NOT NULL, rule TEXT NOT NULL, fuzzy_score REAL,
    status TEXT NOT NULL
);
CREATE TABLE out_of_scope_mention (
    run_id INTEGER NOT NULL REFERENCES run(run_id), name TEXT NOT NULL, kind TEXT NOT NULL,
    line_no INTEGER NOT NULL, raw_text TEXT NOT NULL, pane TEXT NOT NULL, rule TEXT NOT NULL
);
CREATE TABLE unknown_token (
    run_id INTEGER NOT NULL REFERENCES run(run_id), line_no INTEGER NOT NULL, raw_text TEXT NOT NULL,
    zone TEXT NOT NULL, name_like INTEGER NOT NULL
);

CREATE INDEX ix_run_spell_spell ON run_spell(spell_id);
CREATE INDEX ix_rsu_spell ON run_spell_upgrade(spell_id);
CREATE INDEX ix_run_equipment_eq ON run_equipment(equipment_id);
CREATE INDEX ix_extraction_run ON extraction(run_id);

CREATE VIEW v_countable_runs AS SELECT * FROM run WHERE is_countable = 1;

CREATE VIEW v_run_spells_named AS
SELECT r.run_id, r.record_id, s.name AS spell, rs.status
FROM run_spell rs JOIN run r USING (run_id) JOIN catalog_spell s USING (spell_id);

CREATE VIEW v_run_upgrades_named AS
SELECT r.run_id, r.record_id, s.name AS spell, u.name AS upgrade, rsu.association, rsu.method
FROM run_spell_upgrade rsu JOIN run r USING (run_id)
JOIN catalog_spell s ON s.spell_id = rsu.spell_id
JOIN catalog_upgrade u ON u.upgrade_id = rsu.upgrade_id;

CREATE VIEW v_run_equipment_named AS
SELECT r.run_id, r.record_id, e.name AS equipment, e.kind, e.slot
FROM run_equipment re JOIN run r USING (run_id) JOIN catalog_equipment e USING (equipment_id);
"""

TABLES = ["source_file", "catalog_spell", "catalog_upgrade", "catalog_equipment", "run", "run_spell",
          "run_spell_upgrade", "run_unresolved_upgrade", "run_equipment", "run_notice", "run_component",
          "extraction", "out_of_scope_mention", "unknown_token"]


def write_sqlite(path: Path, parses: list[RecordParse], cat: Catalog, manifest: dict,
                 raw_text_by_id: dict[str, str]) -> None:
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    cur = con.cursor()
    for key, m in sorted(manifest.items()):
        cur.execute("INSERT INTO source_file VALUES (?,?,?,?,?,?)",
                    (key, m.get("url"), m.get("repo"), m.get("commit"), m.get("path"), m["sha256"]))

    spell_id: dict[str, int] = {}
    for i, e in enumerate(cat.spells(), start=1):
        spell_id[e.name] = i
        cur.execute("INSERT INTO catalog_spell VALUES (?,?,?,?,?,?)",
                    (i, e.name, _int(e.level), json.dumps(list(e.tags)), cat.sp_ids.get(e.name),
                     json.dumps(sorted(e.snapshots))))
    upgrade_id: dict[tuple[str, str], int] = {}
    uid = 0
    for e in sorted((e for e in cat.entries.values() if e.kind == "upgrade"), key=lambda e: e.name):
        for parent in sorted(e.parents):
            uid += 1
            upgrade_id[(parent, e.name)] = uid
            cur.execute("INSERT INTO catalog_upgrade VALUES (?,?,?,?,?)",
                        (uid, spell_id[parent], e.name, cat.sp_ids.get(f"{parent}::{e.name}"),
                         int(len(e.parents) > 1)))
    equip_id: dict[str, int] = {}
    eid = 0
    for e in sorted((e for e in cat.entries.values() if e.kind in ("equipment", "companion", "tome")),
                    key=lambda e: (e.kind, e.name)):
        eid += 1
        equip_id[e.name] = eid
        cur.execute("INSERT INTO catalog_equipment VALUES (?,?,?,?,?,?,?,?)",
                    (eid, e.name, e.kind, e.slot, json.dumps(list(e.tags)),
                     cat.equipment_ids.get(e.name) if e.kind == "equipment" else None, e.source,
                     json.dumps(sorted(e.snapshots))))

    for run_id, p in enumerate(parses, start=1):
        cur.execute("INSERT INTO run VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            run_id, p.record_id, p.header_line_no, p.outcome, p.outcome_raw, int(p.outcome == "VICTORY"),
            p.realm, p.turns_game, p.turns_level, p.hp, p.hp_max, p.sp, p.sh, p.parse_status,
            int(p.is_countable), p.duplicate_of, json.dumps(p.flags),
            json.dumps(sorted({t["name"] for t in p.trials})), p.compendium_url, p.error,
            raw_text_by_id[p.record_id]))
        for s in p.spells:
            sid = spell_id[s.name]
            cur.execute("INSERT INTO run_spell VALUES (?,?,?,?)",
                        (run_id, sid, s.status, s.provenance[0].line_no if s.provenance else
                         (s.upgrades[0].provenance[0].line_no if s.upgrades else None)))
            for pr in s.provenance:
                _extraction(cur, run_id, "spell", s.name, None, pr, s.status)
            for u in s.upgrades:
                cur.execute("INSERT INTO run_spell_upgrade VALUES (?,?,?,?,?,?)",
                            (run_id, sid, upgrade_id[(s.name, u.name)], u.association, u.method,
                             u.provenance[0].line_no))
                for pr in u.provenance:
                    _extraction(cur, run_id, "upgrade", u.name, s.name, pr, u.association)
            for n in s.notices:
                cur.execute("INSERT INTO run_notice VALUES (?,?,?,?)", (run_id, sid, n["available"], n["association"]))
        for u in p.unresolved_upgrades:
            pr = u.provenance[0]
            cur.execute("INSERT INTO run_unresolved_upgrade VALUES (?,?,?,?,?,?,?)",
                        (run_id, u.name, json.dumps(u.candidates), json.dumps(u.owned_candidates), u.reason,
                         pr.raw_text, pr.line_no))
            for pr in u.provenance:
                _extraction(cur, run_id, "unresolved_upgrade", u.name, None, pr, "unresolved")
        for e in p.equipment:
            cur.execute("INSERT INTO run_equipment VALUES (?,?,?)", (run_id, equip_id[e.name], e.provenance[0].line_no))
            for pr in e.provenance:
                _extraction(cur, run_id, "equipment", e.name, None, pr, "owned")
        for c in sorted(set(p.components)):
            cur.execute("INSERT INTO run_component VALUES (?,?)", (run_id, c))
        for m in p.out_of_scope_mentions:
            pr = m.provenance
            cur.execute("INSERT INTO out_of_scope_mention VALUES (?,?,?,?,?,?,?)",
                        (run_id, m.name, m.kind, pr.line_no, pr.raw_text, pr.pane, pr.rule))
        for t in p.unknown_tokens:
            cur.execute("INSERT INTO unknown_token VALUES (?,?,?,?,?)", (run_id, t.line_no, t.raw_text, t.zone, int(t.name_like)))
    con.commit()
    con.close()


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _extraction(cur, run_id, kind, name, parent, pr, status):
    cur.execute("INSERT INTO extraction (run_id,item_kind,item_name,parent_spell,line_no,raw_text,matched_text,"
                "normalization,pane,rule,fuzzy_score,status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, kind, name, parent, pr.line_no, pr.raw_text, pr.matched_text, pr.normalization,
                 pr.pane, pr.rule, pr.fuzzy_score, status))


def export_csv(db: Path, out_dir: Path) -> list[Path]:
    import pandas as pd
    out_dir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    paths = []
    try:
        for t in TABLES + ["v_run_spells_named", "v_run_upgrades_named", "v_run_equipment_named"]:
            df = pd.read_sql_query(f"SELECT * FROM {t}", con)
            if t == "run":
                df = df.drop(columns=["raw_text"])          # raw text lives in source/records.jsonl
            p = out_dir / f"{t}.csv"
            df.to_csv(p, index=False)
            paths.append(p)
    finally:
        con.close()
    return paths
