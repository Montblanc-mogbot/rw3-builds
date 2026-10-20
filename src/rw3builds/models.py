"""Plain data types for one parsed record. Everything carries its provenance."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Provenance:
    line_no: int                 # line in the raw file
    raw_text: str                # exact OCR line(s)
    matched_text: str            # text after affix stripping / joining
    normalization: str           # exact | casefold_nospace | ocr_confusion | fuzzy (+ modifiers)
    pane: str                    # central | left | right | other
    rule: str                    # why the pane/scope decision was made
    fuzzy_score: float | None = None


@dataclass
class UpgradeOut:
    name: str
    association: str             # verified | probable | inferred
    method: str                  # catalog_unique | catalog_build_disambiguated | positional | implied_parent
    provenance: list[Provenance] = field(default_factory=list)


@dataclass
class SpellOut:
    name: str
    status: str                  # owned | inferred_from_upgrade
    upgrades: list[UpgradeOut] = field(default_factory=list)
    notices: list[dict] = field(default_factory=list)   # "N Upgrades Available", positional only
    provenance: list[Provenance] = field(default_factory=list)


@dataclass
class EquipmentOut:
    name: str
    kind: str                    # equipment | companion | tome
    slot: str | None
    provenance: list[Provenance] = field(default_factory=list)


@dataclass
class UnresolvedUpgrade:
    name: str
    candidates: list[str]
    owned_candidates: list[str]
    reason: str
    provenance: list[Provenance] = field(default_factory=list)


@dataclass
class Mention:
    """A catalog name seen outside the build columns (never build content)."""
    name: str
    kind: str
    provenance: Provenance


@dataclass
class UnknownToken:
    line_no: int
    raw_text: str
    zone: str                    # spell_window | equipment_window | both | outside
    name_like: bool


@dataclass
class RecordParse:
    record_id: str
    header_line_no: int
    outcome: str | None
    outcome_raw: str | None
    realm: int | None
    turns_game: int | None
    turns_level: int | None
    hp: int | None
    hp_max: int | None
    sp: int | None
    sh: int | None
    spells: list[SpellOut] = field(default_factory=list)
    equipment: list[EquipmentOut] = field(default_factory=list)
    unresolved_upgrades: list[UnresolvedUpgrade] = field(default_factory=list)
    out_of_scope_mentions: list[Mention] = field(default_factory=list)
    unknown_tokens: list[UnknownToken] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    trials: list[dict] = field(default_factory=list)     # run modifiers seen anywhere (metadata)
    anchors: dict = field(default_factory=dict)
    # Calibration data for the positional rule: for upgrades whose parent the catalog fixes,
    # what "nearest preceding owned spell" would have said. Never used to assign anything.
    positional_checks: list[dict] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    parse_status: str = "unparsed"
    duplicate_of: str | None = None
    is_countable: bool = False
    compendium_url: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)
