# Build search: Magic Missile

Frequencies use **unique countable winning builds** as the denominator (an `Outcome: VICTORY` line was read, the character sheet produced spells, duplicate posts removed). Everything below is computed from `out/rw3_builds.sqlite` by `queries/spell_search.sql`.

## 1. Winning builds containing the spell

- Countable winning builds in the dataset: **553**
- Containing Magic Missile: **75** (13.6%)
  - 75 read from the central Spells column

## 2. Upgrades identified for Magic Missile

Share = runs with the upgrade / 75 builds containing Magic Missile. `verified` = the catalog fixes the parent spell (or this is the only candidate parent in the build). `inferred` = attached to a spell whose own line was not read. Positional (`probable`) association is disabled - see the quality report.

| Upgrade | Verified | Inferred | Share (all) |
|---|---:|---:|---:|
| Ricochet | 33 | 0 | 44.0% |
| Shield Burn | 28 | 0 | 37.3% |
| Disruption Bolt | 21 | 0 | 28.0% |
| Arcane Crossfire | 17 | 0 | 22.7% |

**Unresolved (shared upgrade names; parent could not be decided, NOT counted above):**

- `Shield Burn` in 1 build(s) owning Magic Missile, Siphon Shields

## 3. Other spells most common in Magic Missile builds

| Spell | Builds | Share | of which inferred |
|---|---:|---:|---:|
| Blink | 27 | 36.0% | 0 |
| Disperse | 25 | 33.3% | 0 |
| Arcane Warding | 15 | 20.0% | 0 |
| Teleport | 15 | 20.0% | 0 |
| Void Beam | 14 | 18.7% | 0 |
| Dragon Claw | 13 | 17.3% | 0 |
| Void Drake | 13 | 17.3% | 0 |
| Underworld Passage | 12 | 16.0% | 0 |
| Fireball | 11 | 14.7% | 0 |
| Soul Tax | 11 | 14.7% | 1 |
| Petrify | 10 | 13.3% | 0 |
| Purity | 10 | 13.3% | 0 |
| Annihilate | 9 | 12.0% | 0 |
| Cantrip Cascade | 8 | 10.7% | 0 |
| Chain Lightning | 8 | 10.7% | 0 |
| Summon Blade | 8 | 10.7% | 0 |
| Dominate | 7 | 9.3% | 0 |
| Essence Flux | 7 | 9.3% | 0 |
| Lightning Bolt | 7 | 9.3% | 0 |
| Mystic Vision | 7 | 9.3% | 0 |

## 4. Equipment most common in Magic Missile builds

The Equipment column lists everything the character holds (several body armors can appear), not only what is equipped.

| Equipment | Kind | Slot | Builds | Share |
|---|---|---|---:|---:|
| Arcane Staff | equipment | Weapon | 27 | 36.0% |
| Fae Plate | equipment | Body | 26 | 34.7% |
| Sorcery Staff | equipment | Weapon | 25 | 33.3% |
| Sonic Shields | equipment | Trinket | 22 | 29.3% |
| Arcane Tome | tome |  | 17 | 22.7% |
| Battlemage Staff | equipment | Weapon | 16 | 21.3% |
| Robe of Void | equipment | Body | 16 | 21.3% |
| Sorcery Tome | tome |  | 16 | 21.3% |
| Multimancer's Staff | equipment | Weapon | 14 | 18.7% |
| The Bladestaff | equipment | Weapon | 14 | 18.7% |
| Disintegrator | equipment | Trinket | 13 | 17.3% |
| Arcane Frenzy Mask | equipment | Head | 12 | 16.0% |
| Conjuration Staff | equipment | Weapon | 12 | 16.0% |
| Philosopher's Stone | equipment | Trinket | 12 | 16.0% |
| Boreal Armor | equipment | Body | 11 | 14.7% |
| Magic Wand | equipment | Weapon | 11 | 14.7% |
| Fae Thorn Staff | equipment | Weapon | 10 | 13.3% |
| Magic Minion Shield | equipment | Trinket | 10 | 13.3% |
| Shepherd's Staff | equipment | Weapon | 10 | 13.3% |
| Amphisbaena Ring | equipment | Trinket | 9 | 12.0% |

## 5. Individual reconstructed builds (first 5, validated first)

### `image-f713eca8c3b0fee7.png` - realm 21, 237 turns, status `validated`
[View on the RW3 compendium](https://hpp3.github.io/rw3/?g=1_C8b.2r.38.8k.2f.3c.9.8f.6q.5g.3e.4x_Ce1.ak.al.ao.an.am.f0.f1.f4.f2.5.8.f.hi.3w.jg_Win+image-f713eca8c3b0fee7.png)

- **Magic Missile**: -
- **Heaven's Wrath**: Culling, Heaven's Promise, Halt Heretics, Fiery Wrath
- **Multicast**: Echo Mage, Spell Weaving, Multi Mastery
- **Annihilate**: Comprehensive Annihilation
- **Arcane Warding**: -
- **Purity**: -
- **Darkness**: -
- **Seal Fate**: -
- Equipment: Storm Wand, Disintegrator, Paladin, Echo Staff, Holy Tome, The Dynamo, Crisis Charm, Enchantment Staff, Annihilator Staff, Talking Hat, Robe of Agony, Multimancer's Staff, Erebus Lance, Lightning Staff

### `image-13b4d25590d83064.png` - realm 20, 271 turns, status `validated`
[View on the RW3 compendium](https://hpp3.github.io/rw3/?g=1_Cf.1g.6y.8b.7c.73.5g.39.8s.1f.3v.t_Ce1.e3.e2.91.a.e.d.7x.7y.dc.od.oh.d7.da_Win+image-13b4d25590d83064.png)

- **Magic Missile**: Disruption Bolt, Arcane Crossfire
- **Floating Eye**: -
- **Arc Lightning**: Proton Storm, Multi Flash
- **Faehaunt Garden**: Fae Pupils
- **Lightning Form**: -
- **Void Beam**: Void Pulse
- **Lightning Bolt**: Repeater Bolts
- Equipment: Arcane Staff, Brain Hat, Robe of Void, Storm Wand, Shepherd's Staff, Runespeaker's Gorget, Multimancer's Staff, Eldritch Mantle, Timestriders, Boreal Armor, Galvanic Armor, Battlemage Staff

### `image-51e4572130358fca.png` - realm 21, 348 turns, status `validated`
[View on the RW3 compendium](https://hpp3.github.io/rw3/?g=1_C3o.d.2b.9a.7d.50.7s.3n.85.56_Ce1.e4.e2.e5.5a.5d.5e.mu.f.od.og.oh.7x.80.f0.f3.f4.5k.5m.5l_Win+image-51e4572130358fca.png)

- **Magic Missile**: Ricochet, Arcane Crossfire, Shield Burn
- **Disperse**: Violent Warp, Void Sickness
- **Teleport**: -
- **Arcane Warding**: -
- **Void Beam**: Void Curse, Void Pulse
- **Faehaunt Garden**: Glass Garden
- **Multicast**: Preparedness, Spell Weaving
- **Dominate**: Conqueror, Brute Force
- Equipment: Fae Thorn Staff, Translocation Tome, Arcane Frenzy Mask, Cracklevoid, Void Spike Stone, Silken Links, Magic Minion Shield, Sonic Shields, Fae Plate, Stone Mask, Memory Staff

### `image-4f6f60ea2a82edf4.png` - realm 21, 390 turns, status `validated`
[View on the RW3 compendium](https://hpp3.github.io/rw3/?g=1_C3n.7t.5g.99.f.g.4s.v.7r.2r.t.68.1j.9.5i.3t_Ce1.e4.e3.9l.9m.5a.5b.5d.od.og.oh.l1.l2.l5.ny.nz.o0_Win+image-4f6f60ea2a82edf4.png)

- **Magic Missile**: Ricochet, Disruption Bolt
- **Furnace of Sorcery**: Arcane Eyebolts
- **Disperse**: Far Sending, Violent Warp
- **Void Beam**: Void Curse, Void Pulse
- **Soul Tax**: Arcane Taxation, Soul Debt
- **Underworld Passage**: Make Entrance, Quickcast
- Equipment: Fae Plate, Sorcery Staff, Multimancer's Staff, Void Oculus, Arcane Staff, Arch Sorcerer's Staff, Iron Legion's Banner, Fire Tome, Blazeblood Staff, Solid Steel Staff, Disintegrator, Battlemage Staff, Pyrophilia Locket, Cannibal Mask, Annihilator Staff, Holy Tome, Neanderthal's Tooth, Flagellant's Cup

### `Screenshot_24-138896587f6eb497.png` - realm 21, 419 turns, status `validated`
[View on the RW3 compendium](https://hpp3.github.io/rw3/?g=1_Cd.7t.8s.v.51.6a.3n.38.t.6y.29.9c.5w.49_Ce1.e4.e3.5a.5d.14.17.16.az.b2.b0.8h.8l.2x.2z.2y.37.38.3b.u.d7.d9_Win+Screenshot_24-138896587f6eb497.png)

- **Magic Missile**: Ricochet, Disruption Bolt
- **Disperse**: Violent Warp
- **Blink**: Dissolution, Blindcasting
- **Holy Fire**: Holy Smite, Divine Blaze
- **Fireball**: Shaped Blast
- **Cantrip Cascade**: Evocation Amalgamation, Cantrip Burst
- **Chain Lightning**: Chain Fireball, Lightning Shield
- **Blazerip**: -
- **Lightning Bolt**: Energy Bolt
- Equipment: Arcane Frenzy Mask, Sorcery Staff, Timestriders, Blazeblood Staff, Magic Wand, Pyrostatic Oculus, Fae Plate, Echo Staff, Battlemage Staff, Robe of Void, Coruscating Wand, Lightning Tome, Voidflame Lantern, Philosopher's Stone, Haunted Blood Vial

