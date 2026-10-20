# Known limitations

These are known, measured gaps. Where the parser can't decide, it records the candidate text and
says why instead of guessing.

## The data itself
- **OCR text only, no screenshots.** Anything EasyOCR dropped or merged can't be recovered. Pixel
  positions weren't kept, so column membership has to be inferred from line shape.
- **Victory isn't always provable.** 20 character sheets have no `Outcome:` line (most are
  combat-summary layouts). They're kept, with `victory_confirmed = 0`, but they're left out of
  every frequency count.
- **The Equipment column is the inventory, not the loadout.** It lists everything the wizard holds,
  so several body armors in one build is normal. The data can't tell which items were equipped.

## Spell → upgrade links
- **Shared upgrade names** (Quickcast ×5 spells, Dragon Mage ×6, Blindcasting ×4, Shield Burn ×3,
  Freezing, Glassify, Lifesteal, Dual Wind) are linked only when exactly one candidate parent spell
  is in the build. Otherwise they go to `run_unresolved_upgrade`, and the Magic Missile demo lists
  them separately.
- **Position isn't used.** The positional rule (nearest preceding spell) was calibrated against the
  catalog at about 80% accuracy, below the 95% bar, so it's disabled and nothing is labelled `probable`.
- **Generic one-word upgrade names** are held back as unresolved: the stat labels `Shields`,
  `Radius` and `Bonus`, and words that are half of a longer name when the other half is present
  (`Meteor` / `Meteor Shower`).
- **Inferred spells.** An upgrade read in the central column implies its parent spell. If the
  parent's own line wasn't read, the spell is stored as `inferred_from_upgrade` and the record is
  flagged. Upgrades with a weak identity (fuzzy match, or a fragment whose other half is missing)
  never imply a spell.

## Column and pane decisions
- **Hotkey-only spells aren't added.** A spell seen only in the left hotkey list (122 cases) is
  excluded and flagged. Sometimes it's really owned and the OCR lost the central line. Sometimes the
  "hotkey signature" was really numbers from a neighbouring panel. The text can't tell these apart.
- **Purchases-log spells look like central lines.** A bare `Fireball` in the Purchases log can't be
  distinguished from a central line. Bought spells are owned, so ownership is still right, but the
  evidence pane is uncertain.
- **Wrapped names:**
  - Upgrades and equipment are completed from a unique fragment (`Flagellant's` → Flagellant's Cup).
    When the other half isn't in the record, the item is kept but flagged `wrap_fragment_unconfirmed`.
  - Spells are never assembled from fragments or separated halves, because the hotkey pane wraps
    spell names too. A spell joined from two *adjacent* lines with no corroborating upgrade is
    flagged `spell_only_from_wrapped_lines`.
  - Halves shared by several names (`Staff`, `Rift`, `Claw Staff`) stay in `unknown_token`.
- **`Necromancer`** is both a trial name and a companion. Inside the Equipment column it's flagged
  ambiguous and left out.
- **Known misses.** The dev gold set has one: `Harlord Heln` → Warlord Helm, an H/W confusion plus
  m→n. Fixing it would need looser matching rules than were justified.

## Catalog and versions
- **Version mismatch.** Names come from the hpp3/rw3 compendium snapshots of 2026-06-05..07-20, which
  match the screenshots' period (build 23995367). The compendium may itself differ slightly from a
  given player's patch.
- **Supplementary sources.**
  - School tomes (`<School> Tome`) and Tavern companions are generated in-game, so the compendium
    doesn't list them. They come from a pattern rule over spell tags and from companion units.
  - Trial names come from the localization mod's string table (`Mutators.py`).
- **Compendium links don't fully resolve.** Links target the *live* site. Items removed in the
  2026-09-01 patch (`Banner of the Horde`; upgrades such as `Mystic Vision::Bonus`) are dropped by
  the site when the link opens. The database itself keeps them.

## How accuracy was measured
- **The gold set is a human reading of the same OCR text.** It has 25 records: 10 dev and 15
  held-out. It measures how well the parser reads the OCR, not whether the OCR matches the screenshot.
- **The gold set shares the parser's catalog.** It was annotated with the same catalog, and for most
  upgrades the catalog alone fixes the parent. So agreement on spell→upgrade pairs mostly confirms
  the column and pane decisions. It doesn't test the catalog.
- **Baseline before tuning.** `docs/gold-baseline-before-tuning.md` records the held-out score from
  the first run, before any gold-informed tuning. Later fixes were driven by dev disagreements and by
  full-dataset audits (fuzzy matches, fragment completions, inferred spells), not by the held-out records.
- **Coverage is not accuracy.** For example, "96% of records have spells" says nothing about whether
  those spells are right.
