from pathlib import Path

import pytest

from rw3builds.catalog import load_catalog
from rw3builds.normalize import Normalizer
from rw3builds.records import Line, Record, split_records

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache"


def _need_cache():
    if not (CACHE / "raw_ocr.txt").exists() or not (CACHE / "ids_live.json").exists():
        pytest.skip("source cache missing - run `python -m rw3builds run` once to download it")


@pytest.fixture(scope="session")
def cat():
    _need_cache()
    return load_catalog(CACHE)


@pytest.fixture(scope="session")
def norm(cat):
    return Normalizer(cat)


@pytest.fixture(scope="session")
def records():
    _need_cache()
    return {r.record_id: r for r in split_records((CACHE / "raw_ocr.txt").read_text(encoding="utf-8"))}


@pytest.fixture(scope="session")
def parsed(records, cat):
    from rw3builds.pipeline import run
    parses, cal = run(list(records.values()), cat)
    return {p.record_id: p for p in parses}, cal


def make_record(lines: list[str], record_id: str = "test.png") -> Record:
    """A synthetic record from real OCR line excerpts (line numbers are 1-based positions)."""
    return Record(record_id, 0, tuple(Line(i + 1, i, t) for i, t in enumerate(lines)))
