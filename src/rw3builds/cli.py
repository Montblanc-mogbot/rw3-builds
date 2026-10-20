"""Command-line entry point: ``python -m rw3builds <command>``."""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .catalog import load_catalog
from .evaluate import evaluate, load_gold
from .export_sqlite import export_csv, write_sqlite
from .fetch import fetch_all
from .guide_link import build_link, read_guide_constants
from .pipeline import run as run_pipeline
from .queries import spell_report
from .records import split_records
from .report import build_report, markdown_to_html

ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger("rw3builds")


def _build_record_json(p) -> dict:
    """The public JSON shape: spells with nested upgrades, equipment, and full provenance."""
    d = asdict(p)
    d.pop("positional_checks", None)
    d["trials"] = sorted({t["name"] for t in p.trials})
    d["trial_mentions"] = [t for t in asdict(p)["trials"]]
    return d


def cmd_run(args) -> int:
    cache, out = Path(args.cache_dir), Path(args.out_dir)
    manifest = fetch_all(cache, raw_override=Path(args.raw) if args.raw else None, offline=args.offline)
    raw_path = cache / "raw_ocr.txt"
    raw = raw_path.read_text(encoding="utf-8")
    records = split_records(raw)
    log.info("%d screenshot records", len(records))
    cat = load_catalog(cache)
    parses, cal = run_pipeline(records, cat)

    consts = read_guide_constants(cache / "app_js_live.js")
    missing_ids = set()
    for p in parses:
        if p.is_countable or p.parse_status in ("validated", "partial", "needs_review"):
            p.compendium_url, miss = build_link(p, cat, consts)
            missing_ids.update(miss)
    if missing_ids:
        log.info("%d names have no stable compendium id (left out of links): %s", len(missing_ids),
                 ", ".join(sorted(missing_ids)[:20]))

    out.mkdir(parents=True, exist_ok=True)
    src_dir = out / "source"
    src_dir.mkdir(exist_ok=True)
    # E. Unmodified source: verbatim copy + one JSON line per record + the fetch manifest.
    shutil.copyfile(raw_path, src_dir / raw_path.name)
    with open(src_dir / "records.jsonl", "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps({"record_id": r.record_id, "header_line_no": r.header_line_no,
                                "first_line_no": r.lines[0].no if r.lines else None,
                                "raw_text": r.raw_text}, ensure_ascii=False) + "\n")
    shutil.copyfile(cache / "manifest.json", src_dir / "manifest.json")

    # A. JSON
    payload = {
        "generator": f"rw3builds {__version__}",
        "sources": manifest,
        "positional_calibration": {"checks": cal.checks, "correct": cal.correct,
                                   "accuracy": cal.accuracy, "enabled": cal.positional_enabled},
        "records": [_build_record_json(p) for p in parses],
    }
    (out / "builds.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=False) + "\n",
                                     encoding="utf-8")
    # B. SQLite + C. CSV
    db = out / "rw3_builds.sqlite"
    write_sqlite(db, parses, cat, manifest, {r.record_id: r.raw_text for r in records})
    export_csv(db, out / "csv")
    # D. Quality report
    gold = load_gold(ROOT / "tests" / "gold")
    evaluation = evaluate(parses, gold) if gold else None
    md = build_report(parses, cal, cat, manifest, evaluation)
    (out / "quality_report.md").write_text(md, encoding="utf-8")
    (out / "quality_report.html").write_text(markdown_to_html(md, "RW3 build data quality"), encoding="utf-8")
    # Demo search
    (out / "demo_magic_missile.md").write_text(spell_report(db, "Magic Missile"), encoding="utf-8")
    log.info("wrote %s", ", ".join(str(p.relative_to(out)) for p in sorted(out.iterdir())))
    return 0


def cmd_query(args) -> int:
    md = spell_report(Path(args.db), args.spell, n_builds=args.builds)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
    else:
        sys.stdout.write(md)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rw3builds", description="Rift Wizard 3 winning-build extraction pipeline")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="fetch (or reuse cache), parse every record, write out/")
    r.add_argument("--raw", help="use this local copy of the raw OCR text instead of downloading it")
    r.add_argument("--offline", action="store_true", help="never download; fail if a source is not cached")
    r.add_argument("--cache-dir", default=str(ROOT / "data" / "cache"))
    r.add_argument("--out-dir", default=str(ROOT / "out"))
    r.set_defaults(fn=cmd_run)
    q = sub.add_parser("query", help="build-search report for one spell")
    q.add_argument("--spell", required=True)
    q.add_argument("--db", default=str(ROOT / "out" / "rw3_builds.sqlite"))
    q.add_argument("--builds", type=int, default=5, help="individual builds to show")
    q.add_argument("--out", help="write Markdown here instead of stdout")
    q.set_defaults(fn=cmd_query)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    return args.fn(args)
