"""Extraction rules on real OCR excerpts (synthetic records assembled from dataset lines)."""
from conftest import make_record

from rw3builds.extract import extract

HEADER = ["HP 360/360", "Realm 20", "SP 28", "Spells", "Equipment", "Outcome: VICTORY", "Realm 20, Turn 1"]
FOOTER = ["Craft Equipment (E)", "Learn a Spell (S)", "Resistances", "Menu (ESCAPE)"]


def _x(lines, cat, norm, allow_positional=False):
    return extract(make_record(HEADER + lines + FOOTER), cat, norm, allow_positional=allow_positional)


def _spells(p):
    return {s.name: [u.name for u in s.upgrades] for s in p.spells}


def test_basic_build_and_meta(cat, norm):
    p = _x(["Fireball", "Blazing Wand", "Turns taken:", "Meteor", "Fae Plate", "Spells (S)",
            "1 Upgrade Available", "1 (L)", "493 (G)"], cat, norm)
    assert (p.outcome, p.realm, p.turns_game, p.turns_level, p.hp_max) == ("VICTORY", 20, 493, 1, 360)
    assert _spells(p) == {"Fireball": ["Meteor"]}
    assert [e.name for e in p.equipment] == ["Blazing Wand", "Fae Plate"]


def test_upgrades_available_is_never_an_upgrade(cat, norm):
    p = _x(["Fireball", "2 Upgrades Available", "Meteor"], cat, norm)
    sp = p.spells[0]
    assert [u.name for u in sp.upgrades] == ["Meteor"]
    assert sp.notices and sp.notices[0]["available"] == 2 and sp.notices[0]["association"] == "positional"


def test_split_notice_count_is_not_a_hotkey_number(cat, norm):
    p = _x(["Wave of Dread", "2", "Upgrades Available"], cat, norm)
    assert p.spells[0].notices[0]["available"] == 2


def test_hotkey_duplicate_does_not_create_a_second_instance(cat, norm):
    # Hotkey entry = index / name / charges. The central copy has no numbers around it.
    p = _x(["Fireball", "Blazing Wand", "1", "Fireball", "19", "Meteor"], cat, norm)
    assert [s.name for s in p.spells] == ["Fireball"]
    assert len(p.spells[0].provenance) == 1 and p.spells[0].provenance[0].pane == "central"


def test_spell_only_in_hotkey_list_is_not_added(cat, norm):
    p = _x(["Fireball", "Meteor", "3", "Flame Burst", "6"], cat, norm)
    assert "Flame Burst" not in _spells(p)
    assert "spell_only_in_hotkey_list:Flame Burst" in p.flags


def test_combat_stats_and_casts_do_not_add_spells(cat, norm):
    # From Capture-3a7628...: damage list "9005 Storm Drake" (a summon), casts "7 Darkness".
    p = _x(["Summon Wizard", "Wizard Gang", "Damage to Enemies:", "9005 Storm Drake", "4313 Chain Lightning",
            "Casts:", "7 Darkness"], cat, norm)
    assert set(_spells(p)) == {"Summon Wizard"}
    assert {m.name for m in p.out_of_scope_mentions} >= {"Storm Drake", "Chain Lightning", "Darkness"}


def test_purchases_log_colon_form_and_wrap_never_add_upgrades(cat, norm):
    # From Screenshot_2026-06-14: "Lightning Spire: Resistance" + "Penetration" is the right pane.
    p = _x(["Lightning Spire", "Purchases:", "Lightning Spire: Resistance", "Lightning Forn", "Penetration"],
           cat, norm)
    assert _spells(p) == {"Lightning Spire": [], "Lightning Form": []}


def test_purchase_only_upgrade_name_is_not_an_upgrade(cat, norm):
    p = _x(["Annihilate", "Purchases:", "Annihilate: Mega Annihilate"], cat, norm)
    assert _spells(p) == {"Annihilate": []}


def test_equipment_after_craft_and_desired_is_excluded(cat, norm):
    lines = HEADER + ["Fireball", "Blazing Wand", "Craft Equipment (E)", "Desired", "Jaculus Idol", "REET***",
                      "Learn a Spell (S)"]
    p = extract(make_record(lines), cat, norm, allow_positional=False)
    assert [e.name for e in p.equipment] == ["Blazing Wand"]


def test_desired_recipe_line_excludes_equipment_even_inside_window(cat, norm):
    p = _x(["Fireball", "Helm of Hexes", "DEE***", "Fae Plate"], cat, norm)
    assert [e.name for e in p.equipment] == ["Fae Plate"]


def test_spells_after_learn_a_spell_are_excluded(cat, norm):
    lines = HEADER + ["Fireball", "Craft Equipment (E)", "Learn a Spell (S)", "Purchases:", "Flame Burst"]
    p = extract(make_record(lines), cat, norm, allow_positional=False)
    assert set(_spells(p)) == {"Fireball"}


def test_missing_end_anchor_falls_back_and_flags(cat, norm):
    lines = HEADER + ["Fireball", "Meteor", "Fae Plate", "Resistances", "Flame Burst"]
    p = extract(make_record(lines), cat, norm, allow_positional=False)
    assert "missing_learn_spell_anchor" in p.flags and "missing_craft_equipment_anchor" in p.flags
    assert set(_spells(p)) == {"Fireball"}          # window ended at Resistances


def test_shared_upgrade_resolves_only_with_one_owned_candidate(cat, norm):
    # Shield Burn is defined by Magic Missile, Siphon Shields and Death Shock.
    one = _x(["Magic Missile", "Shield Burn"], cat, norm)
    assert _spells(one) == {"Magic Missile": ["Shield Burn"]}
    assert one.spells[0].upgrades[0].method == "catalog_build_disambiguated"
    two = _x(["Magic Missile", "Siphon Shields", "Shield Burn"], cat, norm)
    assert _spells(two) == {"Magic Missile": [], "Siphon Shields": []}
    assert two.unresolved_upgrades[0].name == "Shield Burn"
    assert sorted(two.unresolved_upgrades[0].owned_candidates) == ["Magic Missile", "Siphon Shields"]


def test_positional_rule_only_when_enabled(cat, norm):
    lines = ["Magic Missile", "Siphon Shields", "Shield Burn"]
    p = _x(lines, cat, norm, allow_positional=True)
    assert _spells(p)["Siphon Shields"] == ["Shield Burn"]
    assert p.spells[1].upgrades[0].association == "probable"


def test_upgrade_implies_missing_parent_as_inferred(cat, norm):
    p = _x(["Fireball", "Lingering Form"], cat, norm)     # Lightning Form line itself missing
    lf = next(s for s in p.spells if s.name == "Lightning Form")
    assert lf.status == "inferred_from_upgrade" and lf.upgrades[0].association == "inferred"
    assert "spell_inferred_from_upgrade:Lightning Form" in p.flags


def test_wrapped_equipment_halves(cat, norm):
    p = _x(["Fireball", "Flagellant's", "Meteor", "1", "Cup"], cat, norm)
    eq = {e.name: e.provenance[0].normalization for e in p.equipment}
    assert "wrap_pair_nonadjacent" in eq["Flagellant's Cup"]


def test_spell_halves_are_not_paired(cat, norm):
    # The hotkey pane wraps its own copies; a spell must come from a central line.
    p = _x(["Fireball", "Twilight", "3", "Gaze"], cat, norm)
    assert "Twilight Gaze" not in _spells(p)


def test_trials_are_metadata_not_build(cat, norm):
    p = _x(["Adventuring Party", "Fireball"], cat, norm)
    assert [t["name"] for t in p.trials] == ["Adventuring Party"]
    assert set(_spells(p)) == {"Fireball"} and not p.equipment


def test_outcome_ocr_variants():
    from rw3builds.extract import normalize_outcome
    assert normalize_outcome("VICTORY") == normalize_outcome("VICTORI") == normalize_outcome("VIGTCRY") == "VICTORY"
    assert normalize_outcome("DEFEAT") == "DEFEAT"


def test_stat_label_upgrade_names_are_held_back(cat, norm):
    # "Shields" is Void Drake's upgrade AND the tail of a wrapped "Sonic Shields".
    p = _x(["Void Drake", "Shields", "Void Mutations"], cat, norm)
    assert _spells(p) == {"Void Drake": ["Void Mutations"]}
    u = p.unresolved_upgrades[0]
    assert u.name == "Shields" and u.owned_candidates == ["Void Drake"] and "stat" in u.reason


def test_one_word_upgrade_held_back_only_with_competing_half(cat, norm):
    assert _spells(_x(["Fireball", "Meteor"], cat, norm)) == {"Fireball": ["Meteor"]}
    p = _x(["Fireball", "Meteor", "Fae Plate", "Shower"], cat, norm)     # Meteor Shower's other half
    assert _spells(p) == {"Fireball": []} and p.unresolved_upgrades[0].name == "Meteor"


def test_stat_label_is_never_a_fragment_and_weak_upgrade_never_implies_a_spell(cat, norm):
    # "Damage" alone once became "Damage Assimilation" and implied Orb of Assimilation.
    p = _x(["Fireball", "Damage"], cat, norm)
    assert set(_spells(p)) == {"Fireball"}
    p = _x(["Fireball", "Invincible"], cat, norm)     # unique prefix of Invincible Maw (Hungry Maw)
    assert "Hungry Maw" not in _spells(p)
    assert p.unresolved_upgrades[0].name == "Invincible Maw" and "weak" in p.unresolved_upgrades[0].reason
