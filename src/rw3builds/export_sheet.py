"""Tab-separated data blocks for the Google Sheet viewer.

The sheet holds data only in the Builds tab plus three item lists; every count and share in the
sheet is a formula over Builds. List columns are "|"-delimited ("|Fireball|Flame Burst|") so a
formula can test membership with COUNTIF(range, "*|" & name & "|*"). No catalog name contains
| : * ? ~ or a double quote (checked by `check_names`), so those patterns are unambiguous.

Usage:  python -m rw3builds.export_sheet [out/rw3_builds.sqlite] [out/sheet]
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path


def _pipe(items) -> str:
    items = [i for i in items if i]
    return "|" + "|".join(items) + "|" if items else ""


def guide_code(url: str | None) -> str:
    """The VER_equipment_sp part of a compendium ?g= link (the title is dropped; the sheet
    rebuilds the link as  https://hpp3.github.io/rw3/?g=<code>_Build+<n>)."""
    if not url:
        return ""
    from urllib.parse import parse_qs, urlparse
    g = parse_qs(urlparse(url).query)["g"][0]
    return "_".join(g.split("_", 3)[:3])


def check_names(con) -> None:
    bad = [n for (n,) in con.execute("SELECT name FROM catalog_spell UNION SELECT name FROM catalog_upgrade "
                                     "UNION SELECT name FROM catalog_equipment") if re.search(r'[|:*?~"]', n)]
    if bad:
        raise SystemExit(f"names would break the sheet's COUNTIF patterns: {bad}")


def builds_rows(con) -> list[list]:
    rows = []
    runs = con.execute("SELECT run_id, record_id, realm, turns_game, parse_status, trials, compendium_url "
                       "FROM v_countable_runs ORDER BY run_id").fetchall()
    for n, (run_id, rec, realm, turns, status, trials, url) in enumerate(runs, start=1):
        spells = con.execute("SELECT s.name, rs.status FROM run_spell rs JOIN catalog_spell s USING (spell_id) "
                             "WHERE rs.run_id = ? ORDER BY rs.first_line_no", (run_id,)).fetchall()
        ups = con.execute("SELECT s.name, u.name, rsu.association FROM run_spell_upgrade rsu "
                          "JOIN catalog_spell s ON s.spell_id = rsu.spell_id "
                          "JOIN catalog_upgrade u ON u.upgrade_id = rsu.upgrade_id "
                          "WHERE rsu.run_id = ? ORDER BY rsu.first_line_no", (run_id,)).fetchall()
        unres = con.execute("SELECT upgrade_name, owned_candidates, candidate_spells FROM run_unresolved_upgrade "
                            "WHERE run_id = ?", (run_id,)).fetchall()
        eq = con.execute("SELECT e.name FROM run_equipment re JOIN catalog_equipment e USING (equipment_id) "
                         "WHERE re.run_id = ? ORDER BY re.first_line_no", (run_id,)).fetchall()
        import json
        unres_txt = []
        for name, owned, cands in unres:
            who = json.loads(owned) or json.loads(cands)
            unres_txt.append(f"{name} ({' or '.join(who)})")
        trials_txt = ", ".join(json.loads(trials)) if trials else ""
        rows.append([
            n, rec, realm if realm is not None else "", turns if turns is not None else "", status,
            _pipe(s for s, _ in spells),
            _pipe(s for s, st in spells if st != "owned"),
            _pipe(f"{s}: {u}" for s, u, a in ups if a == "verified"),
            _pipe(f"{s}: {u}" for s, u, a in ups if a != "verified"),
            _pipe(unres_txt),
            _pipe(e for (e,) in eq),
            trials_txt,
            guide_code(url),
        ])
    return rows


def spell_list(con) -> list[list]:
    """All catalog spells, most-picked first (order only; counts in the sheet are formulas)."""
    return [[n] for (n,) in con.execute(
        "SELECT s.name FROM catalog_spell s LEFT JOIN run_spell rs ON rs.spell_id = s.spell_id "
        "AND rs.run_id IN (SELECT run_id FROM v_countable_runs) GROUP BY s.spell_id "
        "ORDER BY COUNT(rs.run_id) DESC, s.name")]


def upgrade_list(con) -> list[list]:
    return [[s, u] for s, u in con.execute(
        "SELECT s.name, u.name FROM catalog_upgrade u JOIN catalog_spell s USING (spell_id) "
        "LEFT JOIN run_spell_upgrade r ON r.upgrade_id = u.upgrade_id "
        "AND r.run_id IN (SELECT run_id FROM v_countable_runs) GROUP BY u.upgrade_id "
        "ORDER BY COUNT(r.run_id) DESC, s.name, u.name")]


def equipment_list(con) -> list[list]:
    return [[n, k, slot or ""] for n, k, slot in con.execute(
        "SELECT e.name, e.kind, e.slot FROM catalog_equipment e LEFT JOIN run_equipment r "
        "ON r.equipment_id = e.equipment_id AND r.run_id IN (SELECT run_id FROM v_countable_runs) "
        "GROUP BY e.equipment_id ORDER BY COUNT(r.run_id) DESC, e.name")]


def write_tsv(path: Path, rows: list[list]) -> None:
    path.write_text("\n".join("\t".join(str(c) for c in r) for r in rows) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    root = Path(__file__).resolve().parents[2]
    db = Path(argv[0]) if argv else root / "out" / "rw3_builds.sqlite"
    out = Path(argv[1]) if len(argv) > 1 else root / "out" / "sheet"
    out.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    try:
        check_names(con)
        write_tsv(out / "builds.tsv", builds_rows(con))
        write_tsv(out / "spells.tsv", spell_list(con))
        write_tsv(out / "upgrades.tsv", upgrade_list(con))
        write_tsv(out / "equipment.tsv", equipment_list(con))
    finally:
        con.close()
    for p in sorted(out.iterdir()):
        print(p.name, sum(1 for _ in p.open(encoding="utf-8")), "rows", p.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
