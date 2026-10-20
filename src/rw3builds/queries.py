"""Run the build-search SQL in ``queries/spell_search.sql`` and render a Markdown report."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

SQL_FILE = Path(__file__).resolve().parents[2] / "queries" / "spell_search.sql"


def load_named_queries(path: Path = SQL_FILE) -> dict[str, str]:
    out: dict[str, str] = {}
    for block in re.split(r"^-- name: ", path.read_text(encoding="utf-8"), flags=re.M)[1:]:
        name, _, body = block.partition("\n")
        out[name.strip()] = body.strip()
    return out


def _rows(con, sql, **params):
    cur = con.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def run_build(con: sqlite3.Connection, run_id: int) -> dict:
    run = _rows(con, "SELECT record_id, outcome, realm, turns_game, parse_status, flags, compendium_url "
                     "FROM run WHERE run_id = :r", r=run_id)[0]
    spells = _rows(con, "SELECT s.name, rs.status FROM run_spell rs JOIN catalog_spell s USING (spell_id) "
                        "WHERE rs.run_id = :r ORDER BY rs.first_line_no", r=run_id)
    ups = _rows(con, "SELECT s.name AS spell, u.name AS upgrade, rsu.association, rsu.method FROM run_spell_upgrade rsu "
                     "JOIN catalog_spell s ON s.spell_id = rsu.spell_id JOIN catalog_upgrade u ON u.upgrade_id = rsu.upgrade_id "
                     "WHERE rsu.run_id = :r ORDER BY rsu.first_line_no", r=run_id)
    unres = _rows(con, "SELECT upgrade_name, owned_candidates FROM run_unresolved_upgrade WHERE run_id = :r", r=run_id)
    eq = _rows(con, "SELECT e.name, e.kind, e.slot FROM run_equipment re JOIN catalog_equipment e USING (equipment_id) "
                    "WHERE re.run_id = :r ORDER BY re.first_line_no", r=run_id)
    for s in spells:
        s["upgrades"] = [u for u in ups if u["spell"] == s["name"]]
    return {**run, "spells": spells, "unresolved": unres, "equipment": eq}


def _pct(n, d):
    return f"{100 * n / d:.1f}%" if d else "n/a"


def spell_report(db: Path, spell: str, n_builds: int = 5) -> str:
    q = load_named_queries()
    con = sqlite3.connect(db)
    try:
        if not con.execute("SELECT 1 FROM catalog_spell WHERE name = ?", (spell,)).fetchone():
            raise SystemExit(f"'{spell}' is not a catalog spell name")
        denom = _rows(con, q["denominator"])[0]["countable_wins"]
        by_status = {r["status"]: r["runs"] for r in _rows(con, q["wins_with_spell"], spell=spell)}
        n = sum(by_status.values())
        lines = [f"# Build search: {spell}", "",
                 "Frequencies use **unique countable winning builds** as the denominator (an `Outcome: VICTORY` "
                 "line was read, the character sheet produced spells, duplicate posts removed). Everything below "
                 "is computed from `out/rw3_builds.sqlite` by `queries/spell_search.sql`.", "",
                 "## 1. Winning builds containing the spell", "",
                 f"- Countable winning builds in the dataset: **{denom}**",
                 f"- Containing {spell}: **{n}** ({_pct(n, denom)})"]
        for st, c in sorted(by_status.items()):
            label = {"owned": "read from the central Spells column", "inferred_from_upgrade":
                     "implied only by one of its upgrades (spell line not read)"}.get(st, st)
            lines.append(f"  - {c} {label}")
        lines += ["", f"## 2. Upgrades identified for {spell}", "",
                  f"Share = runs with the upgrade / {n} builds containing {spell}. `verified` = the catalog fixes the "
                  "parent spell (or this is the only candidate parent in the build). `inferred` = attached to a spell whose "
                  "own line was not read. Positional (`probable`) association is disabled - see the quality report.", "",
                  "| Upgrade | Verified | Inferred | Share (all) |", "|---|---:|---:|---:|"]
        ups: dict[str, dict[str, int]] = {}
        for r in _rows(con, q["upgrade_frequency"], spell=spell):
            ups.setdefault(r["upgrade"], {})[r["association"]] = r["runs"]
        for name, d in sorted(ups.items(), key=lambda kv: -sum(kv[1].values())):
            tot = sum(d.values())
            lines.append(f"| {name} | {d.get('verified', 0)} | {d.get('inferred', 0) + d.get('probable', 0)} | {_pct(tot, n)} |")
        unres = _rows(con, q["unresolved_for_spell"], spell=spell)
        if unres:
            lines += ["", "**Unresolved (shared upgrade names; parent could not be decided, NOT counted above):**", ""]
            for r in unres:
                lines.append(f"- `{r['upgrade_name']}` in {r['runs']} build(s) owning {', '.join(json.loads(r['owned_candidates']))}")
        lines += ["", f"## 3. Other spells most common in {spell} builds", "",
                  "| Spell | Builds | Share | of which inferred |", "|---|---:|---:|---:|"]
        for r in _rows(con, q["co_spells"], spell=spell)[:20]:
            lines.append(f"| {r['spell']} | {r['runs']} | {_pct(r['runs'], n)} | {r['runs_inferred']} |")
        lines += ["", f"## 4. Equipment most common in {spell} builds", "",
                  "The Equipment column lists everything the character holds (several body armors can appear), "
                  "not only what is equipped.", "", "| Equipment | Kind | Slot | Builds | Share |", "|---|---|---|---:|---:|"]
        for r in _rows(con, q["co_equipment"], spell=spell)[:20]:
            lines.append(f"| {r['equipment']} | {r['kind']} | {r['slot'] or ''} | {r['runs']} | {_pct(r['runs'], n)} |")
        lines += ["", f"## 5. Individual reconstructed builds (first {n_builds}, validated first)", ""]
        for r in _rows(con, q["runs_with_spell"], spell=spell)[:n_builds]:
            b = run_build(con, r["run_id"])
            lines.append(f"### `{b['record_id']}` - realm {b['realm']}, {b['turns_game']} turns, status `{b['parse_status']}`")
            if b["compendium_url"]:
                lines.append(f"[View on the RW3 compendium]({b['compendium_url']})")
            lines.append("")
            for s in b["spells"]:
                tag = "" if s["status"] == "owned" else " *(inferred from upgrade)*"
                up = ", ".join(u["upgrade"] + ("" if u["association"] == "verified" else f" ({u['association']})")
                               for u in s["upgrades"]) or "-"
                lines.append(f"- **{s['name']}**{tag}: {up}")
            for u in b["unresolved"]:
                lines.append(f"- *unresolved upgrade* `{u['upgrade_name']}` (could belong to {', '.join(json.loads(u['owned_candidates']))})")
            lines.append(f"- Equipment: {', '.join(e['name'] for e in b['equipment']) or '-'}")
            lines.append("")
        return "\n".join(lines) + "\n"
    finally:
        con.close()
