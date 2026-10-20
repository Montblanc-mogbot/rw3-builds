"""Normalization tiers on OCR errors taken verbatim from the dataset."""
import pytest


@pytest.mark.parametrize("raw, name, method", [
    ("Pillar ofFire", "Pillar of Fire", "casefold_nospace"),
    ("Storn Drake", "Storm Drake", "ocr_confusion"),
    ("Slime Forn", "Slime Form", "ocr_confusion"),
    ("Conprehensive Annihilation", "Comprehensive Annihilation", "ocr_confusion"),
    ("Enchantnent Staff", "Enchantment Staff", "ocr_confusion"),
    ("Sline Tome", "Slime Tome", "ocr_confusion"),
    ("Fireball", "Fireball", "exact"),
    ("Cleric", "Cleric", "exact"),
])
def test_tiers(norm, raw, name, method):
    m = norm.match(raw)
    assert m is not None and m.name == name and m.method == method


@pytest.mark.parametrize("raw, name, prefix", [
    ("68 Blink", "Blink", "68"),                              # hotkey charges
    ("13, Rain of Thunderbolts", "Rain of Thunderbolts", "13,"),
    ('"0 Flame Burst', "Flame Burst", '"0'),
    ("1Multicast", "Multicast", "1"),                          # glued digit
    ("1l Lightning Bolt", "Lightning Bolt", "1l"),
    ("4313 Chain Lightning", "Chain Lightning", "4313"),       # combat stats
])
def test_number_prefix_is_kept_as_pane_evidence(norm, raw, name, prefix):
    m = norm.match(raw)
    assert m.name == name and m.prefix == prefix and m.has_number_affix
    assert not m.method.startswith("fuzzy"), "a number prefix must never be absorbed by fuzzy matching"


def test_glyph_prefix_has_no_number(norm):
    m = norm.match("M Pillar of Fire")
    assert m.name == "Pillar of Fire" and m.prefix == "M" and not m.has_number_affix


def test_count_suffix(norm):
    m = norm.match("Darkness (5)")
    assert m.name == "Darkness" and m.suffix == "(5)"


def test_upgrade_notice_is_not_a_name(norm):
    assert norm.match("1 Upgrade Available") is None
    assert norm.match("2 Upgrades Available") is None


def test_fuzzy_needs_clear_margin(norm):
    m = norm.match("Arcane Marding")
    assert m.name == "Arcane Warding" and m.method == "fuzzy" and m.score >= 92
    assert norm.match("Tord Tome") is None            # Word Tome? too far - stays unknown


def test_colliding_confusion_keys_never_autocorrect(norm):
    # "Plague Bringer" (upgrade) and "Plaguebringer" (equipment) share a key; only exact works.
    assert "plaguebrlnger" in norm.collisions()
    assert norm.match("Plague Bringer").name == "Plague Bringer"
    assert norm.match("Plaguebringer").name == "Plaguebringer"


def test_line_join_and_fragments(norm):
    assert norm.match_join(["Flagellant's", "Cup"]).name == "Flagellant's Cup"
    m, complement = norm.match_fragment("Marksman")
    assert m.name == "Marksman Cap" and complement == "Cap"
    assert norm.match_fragment("Staff") is None          # too short / many completions
    assert norm.match_fragment("Rift") is None
