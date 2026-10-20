-- Build-search queries. Parameter :spell is a canonical spell name, e.g. 'Magic Missile'.
-- Denominator everywhere = unique countable winning builds (run.is_countable = 1: an
-- "Outcome: VICTORY" line was read, spells were extracted, and the run is not a duplicate post).

-- name: wins_with_spell
-- Countable wins containing the spell, split by how the spell itself was established.
SELECT rs.status, COUNT(*) AS runs
FROM run_spell rs
JOIN run r USING (run_id)
JOIN catalog_spell s USING (spell_id)
WHERE r.is_countable = 1 AND s.name = :spell
GROUP BY rs.status;

-- name: denominator
SELECT COUNT(*) AS countable_wins FROM run WHERE is_countable = 1;

-- name: upgrade_frequency
-- Upgrades attached to the spell, by association strength. 'verified' = the catalog fixes the
-- parent (or only one candidate parent is in the build); 'inferred' = the parent spell itself was
-- only implied by the upgrade. Unresolved shared-name upgrades are reported separately below.
SELECT u.name AS upgrade, rsu.association, COUNT(*) AS runs
FROM run_spell_upgrade rsu
JOIN run r USING (run_id)
JOIN catalog_spell s ON s.spell_id = rsu.spell_id
JOIN catalog_upgrade u ON u.upgrade_id = rsu.upgrade_id
WHERE r.is_countable = 1 AND s.name = :spell
GROUP BY u.name, rsu.association
ORDER BY runs DESC, u.name;

-- name: unresolved_for_spell
-- Upgrades whose name this spell shares with other spells, seen in builds that own the spell
-- AND another candidate parent, so the parent could not be decided.
SELECT uu.upgrade_name, uu.owned_candidates, COUNT(*) AS runs
FROM run_unresolved_upgrade uu
JOIN run r USING (run_id)
WHERE r.is_countable = 1 AND EXISTS (SELECT 1 FROM json_each(uu.owned_candidates) j WHERE j.value = :spell)
GROUP BY uu.upgrade_name, uu.owned_candidates
ORDER BY runs DESC;

-- name: co_spells
-- Other spells in builds containing the spell (owned on both sides, unless noted).
SELECT s2.name AS spell, COUNT(*) AS runs,
       SUM(rs2.status = 'owned') AS runs_owned, SUM(rs2.status <> 'owned') AS runs_inferred
FROM run_spell rs1
JOIN catalog_spell s1 ON s1.spell_id = rs1.spell_id
JOIN run r ON r.run_id = rs1.run_id
JOIN run_spell rs2 ON rs2.run_id = rs1.run_id AND rs2.spell_id <> rs1.spell_id
JOIN catalog_spell s2 ON s2.spell_id = rs2.spell_id
WHERE r.is_countable = 1 AND s1.name = :spell
GROUP BY s2.name
ORDER BY runs DESC, s2.name;

-- name: co_equipment
SELECT e.name AS equipment, e.kind, e.slot, COUNT(*) AS runs
FROM run_spell rs
JOIN catalog_spell s USING (spell_id)
JOIN run r ON r.run_id = rs.run_id
JOIN run_equipment re ON re.run_id = rs.run_id
JOIN catalog_equipment e ON e.equipment_id = re.equipment_id
WHERE r.is_countable = 1 AND s.name = :spell
GROUP BY e.name, e.kind, e.slot
ORDER BY runs DESC, e.name;

-- name: runs_with_spell
SELECT r.run_id, r.record_id, r.realm, r.turns_game, r.parse_status, r.compendium_url
FROM run r
JOIN run_spell rs USING (run_id)
JOIN catalog_spell s USING (spell_id)
WHERE r.is_countable = 1 AND s.name = :spell
ORDER BY (r.parse_status = 'validated') DESC, r.turns_game, r.record_id;

-- ---------------------------------------------------------------------------------------------
-- Ad-hoc examples (not used by the report). Run with:  sqlite3 out/rw3_builds.sqlite < file
-- ---------------------------------------------------------------------------------------------

-- name: example_two_spells
-- Countable wins containing BOTH Magic Missile and Lightning Bolt.
SELECT r.record_id, r.turns_game, r.parse_status
FROM v_countable_runs r
WHERE EXISTS (SELECT 1 FROM v_run_spells_named v WHERE v.run_id = r.run_id AND v.spell = 'Magic Missile')
  AND EXISTS (SELECT 1 FROM v_run_spells_named v WHERE v.run_id = r.run_id AND v.spell = 'Lightning Bolt')
ORDER BY r.turns_game;

-- name: example_spell_upgrade_combo
-- Countable wins whose Magic Missile has the Ricochet upgrade (verified link only).
SELECT r.record_id, r.turns_game
FROM v_run_upgrades_named v JOIN v_countable_runs r USING (run_id)
WHERE v.spell = 'Magic Missile' AND v.upgrade = 'Ricochet' AND v.association = 'verified'
ORDER BY r.turns_game;

-- name: example_full_build
-- One complete build: spells with their upgrades, then equipment.
SELECT 'spell' AS kind, s.spell AS name, group_concat(u.upgrade, ', ') AS detail
FROM v_run_spells_named s
LEFT JOIN v_run_upgrades_named u ON u.run_id = s.run_id AND u.spell = s.spell
WHERE s.record_id = 'image-cddb41a6e8d8c596.png'
GROUP BY s.spell
UNION ALL
SELECT 'equipment', equipment, kind FROM v_run_equipment_named WHERE record_id = 'image-cddb41a6e8d8c596.png';
