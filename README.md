# rw3-builds

Turns the OCR dump of community Rift Wizard 3 victory screenshots
([theverbivore/RW3-WinData.fan](https://github.com/theverbivore/RW3-WinData.fan)) into a clean,
searchable database of winning builds. Each spell's purchased upgrades stay attached to it, and every
item records where it came from.

A build is only what's in the **central character sheet**: the Spells column (`Spells` …
`Learn a Spell (S)`) and the Equipment column (`Equipment` … `Craft Equipment (E)`). The left
hotkey pane and the right pane (Purchases log, combat stats) are never used as build evidence; the
right pane supplies only outcome, realm, turn counts and trial names. See
[`docs/ocr-structure.md`](docs/ocr-structure.md) for how that was established from the data.

## Quick start

```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m rw3builds run                     # download (pinned commits) + parse + write out/
.venv/bin/python -m rw3builds run --raw path/to/RAW.txt   # use a local copy of the raw OCR file
.venv/bin/python -m rw3builds run --offline           # reuse data/cache only
.venv/bin/python -m rw3builds query --spell "Magic Missile"   # build-search report (Markdown)
.venv/bin/pytest -q
```

## Outputs (`out/`)

| File | What it is |
|---|---|
| `builds.json` | One record per screenshot. Holds spells with nested `upgrades`, plus equipment, unresolved upgrades, out-of-scope mentions, unknown tokens, flags, trials and meta. Every item carries `provenance` (line number, raw OCR text, matched text, normalization, pane, rule). |
| `rw3_builds.sqlite` | The normalized database (schema below). |
| `csv/*.csv` | Every table and view as CSV. |
| `quality_report.md` / `.html` | Coverage, gold-set precision and recall, positional calibration, flags, unknown tokens and the review queue. |
| `demo_magic_missile.md` | The Magic Missile build search. |
| `source/` | A verbatim copy of the raw file, `records.jsonl` (one raw record per line) and the fetch manifest with sha256 hashes. |

### Status values

| Field | Value | Meaning |
|---|---|---|
| `run.parse_status` | `validated` | No review flags, all upgrades verified |
| | `partial` | Some upgrades unresolved, or a spell only implied by an upgrade |
| | `needs_review` | At least one review flag (listed in the report) |
| | `excluded` | Not a character sheet, or not a victory |
| | `failed` | The parser raised an error |
| `run.is_countable` | `1` | A victory was read, spells were extracted, and it's not a duplicate post. This is the denominator for frequencies. |
| `run_spell.status` | `owned` | The spell's line was read in the central Spells column |
| | `inferred_from_upgrade` | Only one of the spell's upgrades was read |
| `run_spell_upgrade.association` | `verified` | The catalog fixes the parent, or this is the only candidate parent in the build |
| | `inferred` | The parent spell itself was only inferred |
| | `probable` | Positional rule; currently disabled by calibration |

## Google Sheet viewer

[RW3 Builds](https://docs.google.com/spreadsheets/d/1zy1UheY0slhMtVXuQdh5WNN5rVqbx-N-44pJheBYpXM/edit)
imports `out/sheet/*.tsv` from this repo's `main` branch with `IMPORTDATA`, and every count in it is
a formula over the Builds tab.
- **Search:** type or pick any spell or equipment name to see its share of wins, its upgrades
  (verified / inferred / unresolved), the spells and equipment seen with it, and the matching
  builds with compendium links.
- **Spells, Upgrades, Equipment:** pick rates over all countable wins.

To refresh the sheet:

```bash
.venv/bin/python -m rw3builds run && .venv/bin/python -m rw3builds.export_sheet
git add out && git commit -m "Refresh data" && git push
```

GitHub's raw CDN and Sheets both cache, so a push can take a few minutes to show up.

## Schema

```
catalog_spell(spell_id, name, level, tags, sp_id, snapshots)
catalog_upgrade(upgrade_id, spell_id -> catalog_spell, name, sp_id, name_shared_with_other_spells)
    UNIQUE(spell_id, name): Quickcast on Teleport and Quickcast on Freeze are different rows
catalog_equipment(equipment_id, name, kind [equipment|companion|tome], slot, tags, compendium_id, source)
run(run_id, record_id, outcome, victory_confirmed, realm, turns_game, turns_level, hp, hp_max, sp, sh,
    parse_status, is_countable, duplicate_of, flags, trials, compendium_url, raw_text)
run_spell(run_id, spell_id, status)
run_spell_upgrade(run_id, spell_id, upgrade_id, association, method)
    FK (run_id, spell_id) -> run_spell
run_unresolved_upgrade(run_id, upgrade_name, candidate_spells, owned_candidates, reason, raw_text)
run_equipment(run_id, equipment_id)
run_notice(run_id, spell_id, upgrades_available)    -- "N Upgrades Available"; NOT purchases
extraction(...)                                     -- per-item provenance
out_of_scope_mention(...), unknown_token(...), source_file(...)
views: v_countable_runs, v_run_spells_named, v_run_upgrades_named, v_run_equipment_named
```

`queries/spell_search.sql` has the build-search queries (spell → upgrades / co-spells /
co-equipment / builds) and examples ("Magic Missile AND Lightning Bolt", "Magic Missile with
Ricochet", "one full build").

## Each build's compendium link

`run.compendium_url` opens the build as a shareable Guide on
[hpp3.github.io/rw3](https://hpp3.github.io/rw3/) (the `?g=` format from the site's `app.js`):
- **Core section:** verified spells and upgrades.
- **Maybe section:** inferred ones.
- Equipment, using the compendium's stable IDs.

## How it works

1. **`fetch.py`** downloads the inputs, each pinned to an exact commit:
   - the raw OCR file;
   - six hpp3/rw3 compendium `data.json` snapshots covering 06-05..07-20;
   - the live `ids.json` / `app.js`, for links;
   - the localization string table, for trial names.
2. **`records.py`** splits the file on `=== SCREENSHOT: … ===`, verbatim.
3. **`catalog.py`** builds the union of the snapshots: spells, upgrades with every possible parent,
   equipment with slots, companions, school tomes (pattern rule) and trials.
4. **`normalize.py`** matches each line in tiers, strictest first: `exact` → `casefold_nospace` →
   affix strip (kept as pane evidence) → `ocr_confusion` (m/n, l/1/I, 0/o; only when exactly one
   catalog name matches) → `fuzzy` (rapidfuzz ≥ 92 with a margin; flagged). Separately, wrapped
   names are rebuilt: `line_join` (adjacent lines), `wrap_pair_nonadjacent`, and `wrap_fragment`
   (a unique whole-word prefix or suffix).
5. **`segment.py`** sets the column windows from the anchors and gives every line a pane by its shape.
6. **`extract.py`** assembles the build and links each upgrade to its spell:
   `catalog_unique` → `catalog_build_disambiguated` → `implied_parent` → otherwise unresolved.
7. **`pipeline.py`** calibrates the positional rule, assigns statuses and marks duplicates.
8. Exporters, `report.py` and `queries.py` write the outputs.

Read [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) before drawing conclusions from the frequencies.
