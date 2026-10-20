# How the OCR text is structured (measured on all 595 records)

Source: `RW3_wins_data_07.08.26 RAW.txt` from `theverbivore/RW3-WinData.fan` @ `80d5d39a`. EasyOCR
emitted text boxes roughly top-to-bottom, so the multi-column victory screen became a single
interleaved line stream. All counts below come from the measurement scripts used while building
`segment.py`. Re-running the pipeline reproduces the per-record anchors in `builds.json` (`anchors`).

## Screen layout

| Pane | Contents | Used for the build? |
|---|---|---|
| Left | `Spells (S)` spell-casting hotkey list (index / name / charges), `Equipment (E)` icon row | **No** |
| Centre, column 1 | Bare `Spells` header → each spell, its purchased upgrades below it, `N Upgrade(s) Available` notices → `Learn a Spell (S)` button | **Yes** - spells + upgrades |
| Centre, column 2 | Bare `Equipment` header → every held equipment item, companion and school tome → `Craft Equipment (E)` button, then `Components`, `Desired` | **Yes** - up to `Craft Equipment` |
| Right | `Outcome: VICTORY`, `Realm N, Turn M`, `Turns taken:` `N (L)` / `N (G)`, `Spell Casts:` / `Damage to Enemies:` / `Damage to Wizard:` lists, `Status Effects`, `Purchases:` log, trial names | Metadata only (outcome, realm, turns, trials) |

## Anchors

| Anchor (OCR variants handled) | Records containing it |
|---|---:|
| bare `Spells` header | 575 |
| bare `Equipment` header (`Equipnent`, `Equipmnent`) | 575 |
| `Learn a Spell (S)` (`Learn & Spell`, `(8)`, split `Learn` / `Spell (S)`) | 572 |
| `Craft Equipment (E)` (`(K)`, `(D)`, `(F)`, `Equipnent`) | 570 |
| `Outcome:` (`Outcone`, `VICTORI`, `VIGTCRY`) | 559 |
| `Spells (S)` left-pane header | 582 |
| `Purchases:` | 336 |
| `Desired` | 286 |

- **Order:** `Spells` comes before `Learn a Spell` in 571/572 records, and `Equipment` before `Craft Equipment` in 570/570.
- **Which button comes first:** `Craft Equipment` precedes `Learn a Spell` in 384 records, and `Learn a Spell` comes first in 185. Long spell lists run far past the end of the equipment column.
- **No sheet:** the 20 records missing every column anchor are gameplay or combat screenshots ("You cast X", hotkey pane only). They're excluded.

## What lies inside the spell window, between the Spells header and Learn a Spell

| Panel | Inside the window / present |
|---|---:|
| Left hotkey list | 557 / 560 |
| `Spell Casts:` list | 303 / 324 |
| `Components` | 447 / 533 |
| `Damage to Enemies:` | 229 / 266 |
| `Desired` | 134 / 276 |
| `Purchases:` | 107 / 333 |

So the anchors bound the columns, but every line inside them still needs a pane decision.

## Line shapes that separate the panes

- **Hotkey entries** come with numbers. Either an index line and a charges line sit on both sides
  (`1` / `Fireball` / `19`), or the number is glued on (`68 Blink`, `13, Rain of Thunderbolts`,
  `1Multicast`, `1l Lightning Bolt`). A glyph icon (`M Pillar of Fire`, `X! Word of Chaos`) also
  marks a hotkey entry: all 41 glyph-prefixed spell lines in the dataset had a clean duplicate.
- **Central sheet lines** never carry numbers.
- **Combat stats and casts** have a number prefix (`9005 Storm Drake`, `4313 Chain Lightning`) or a
  multiplier (`Fire Wyrm Spirit Armor x81`). Summons share names with spells (Storm Drake), and
  equipment casts spells you don't own (`131 Immolate`).
- **The Purchases log** writes upgrades as `Spell: Upgrade` and wraps them (`Lightning Spire: Resistance` …
  `Penetration`). Counts appear in parentheses (`Darkness (5)`).
- **The Desired list** (craft wishlist) shows each item next to a recipe-icon line (`REET***`, `DEE***`,
  `AAEE#*`). It always comes after `Craft Equipment`.
- **`N Upgrade(s) Available`** is a notice under a spell. The OCR sometimes splits it
  (`2` / `Upgrades Available`).

## Wrapped names

The narrow columns wrap long names onto two lines, and the second line usually lands several lines
later because the rows interleave. Measured distances for `Flagellant's` → `Cup` were 5–27 lines,
and in 31 of 50 records `Cup` is missing entirely. The hotkey pane wraps its own copies of spell
names too (`Twili` / `Gaze`, `Savage` / `Spree`).

## Can upgrades be tied to their spells?

**Mostly, yes, through the catalog rather than through line order.**
- **Catalog:** of 772 upgrade names, 764 belong to exactly one spell, and spell names never coincide
  with upgrade names.
- **Line order:** "nearest preceding owned spell" agrees with the catalog only about 80% of the time
  (see `quality_report.md`). That's too weak to decide anything.
- **The 8 shared names** (Quickcast, Dragon Mage, Blindcasting, Shield Burn, Freezing, Glassify,
  Lifesteal, Dual Wind) resolve only when exactly one candidate parent spell is in the build.
  Otherwise they stay unresolved.
