"""Download (or reuse cached) source files, pinned to exact commits.

Every input the pipeline reads is listed in ``SOURCES`` with the commit it is pinned to, so a
run is reproducible byte-for-byte. Downloads land in ``data/cache/`` and are recorded in
``manifest.json`` with their sha256. Nothing is ever written to the upstream repositories.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

RAW_REPO = "theverbivore/RW3-WinData.fan"
RAW_COMMIT = "80d5d39acb756fc9ed6ebaf08ff95b082655e066"  # 2026-07-08, the only data upload
RAW_PATH = "RW3_wins_data_07.08.26 RAW.txt"

CATALOG_REPO = "hpp3/rw3"
# data.json snapshots spanning the screenshots' date range (~2026-06-06 .. 07-08). The union is
# the catalog; each name remembers which snapshots it appears in.
CATALOG_SNAPSHOTS = {
    "2026-06-05": "e477605760ae13a18ab89102e1c08e1e514bace2",
    "2026-06-06": "62f8c55b5681f7270ae11f44156e6f5485234f1a",
    "2026-06-11": "7844c816e1b303edb3cc22172658f7831507bcfe",
    "2026-06-24": "06f394815e7a420406924ad229acf79af02846e3",
    "2026-07-01": "3dab8bd7114aae6f4c71065c62d253e3700af863",
    "2026-07-20": "b149eddd296f8886fc9cad1963221fc920cfed83",
}
# The live compendium at pin time: stable ids + guide-link format (ids are append-only, so links
# built from these resolve on the live site).
CATALOG_LIVE_COMMIT = "13051a575a08f170b454c3883fa4e5783b02d296"  # 2026-10-13

# The Chinese-localization mod's English string table (every string literal in the game's .py
# files, with file:line origins). Used ONLY for names the compendium does not carry: the trial
# (run-modifier) list in Mutators.py. Never used for spells/upgrades/equipment.
LOC_REPO = "MengUkal/rift-wizard-3-chinese-localization"
LOC_COMMIT = "8b259d611c406153ed1cafe2f446c099c631c7be"  # 2026-10-16


@dataclass(frozen=True)
class Source:
    key: str
    repo: str
    commit: str
    path: str

    @property
    def url(self) -> str:
        return (
            f"https://raw.githubusercontent.com/{self.repo}/{self.commit}/"
            + urllib.parse.quote(self.path)
        )

    @property
    def cache_name(self) -> str:
        return f"{self.key}{Path(self.path).suffix}"


def sources() -> list[Source]:
    out = [Source("raw_ocr", RAW_REPO, RAW_COMMIT, RAW_PATH)]
    for date, commit in CATALOG_SNAPSHOTS.items():
        out.append(Source(f"catalog_{date}", CATALOG_REPO, commit, "site/data.json"))
    out.append(Source("catalog_live", CATALOG_REPO, CATALOG_LIVE_COMMIT, "site/data.json"))
    out.append(Source("ids_live", CATALOG_REPO, CATALOG_LIVE_COMMIT, "ids.json"))
    out.append(Source("app_js_live", CATALOG_REPO, CATALOG_LIVE_COMMIT, "site/app.js"))
    out.append(Source("loc_keys", LOC_REPO, LOC_COMMIT, "keys.json"))
    return out


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_all(cache_dir: Path, *, raw_override: Path | None = None, offline: bool = False) -> dict:
    """Ensure every source is in ``cache_dir``; return the manifest (key -> metadata)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cache_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    for src in sources():
        dest = cache_dir / src.cache_name
        entry = manifest.get(src.key, {})
        if src.key == "raw_ocr" and raw_override is not None:
            shutil.copyfile(raw_override, dest)
            manifest[src.key] = {"url": str(raw_override.resolve()), "repo": None, "commit": None,
                                 "path": raw_override.name, "sha256": _sha256(dest), "local": True}
            log.info("using local raw file %s", raw_override)
            continue
        if dest.exists() and entry.get("commit") == src.commit and entry.get("sha256") == _sha256(dest):
            log.debug("cached %s", src.key)
            continue
        if offline:
            raise FileNotFoundError(f"{src.key} not cached and --offline was given ({dest})")
        log.info("downloading %s", src.url)
        with urllib.request.urlopen(src.url, timeout=60) as resp:
            dest.write_bytes(resp.read())
        manifest[src.key] = {"url": src.url, "repo": src.repo, "commit": src.commit,
                             "path": src.path, "sha256": _sha256(dest), "local": False}

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest
