# Changelog

All notable changes to Words of Power are documented here.

## [0.2.1] - 2026-03-28

### Character Sheet & Detail Overhaul

- **Character sheet full voicing** — Spells, equipment, upgrades, and skills now read complete data (tags, range, bonuses, full description) instead of first-sentence truncation. Same detail level as the shop.
- **D-key describes everything** — No longer unit-only. Full detail on units (including player), portals, shops/shrines, equipment pickups, spell scrolls, consumables, clouds, and terrain. Works in all modes (normal, targeting, look, deploy).

### New Features

- **Y-key ally scanner** — Cycle through allied units one at a time, nearest first. Shift+Y reverses. Alt+Y marks.
- **Shift+F ally overview** — Buffered list of all allies with HP, nearest first. Each entry is a separate chunk for [ ] review.
- **Deploy overview buffer splitting** — Key 1 overview now splits per-quadrant for [ ] navigation.
- **Coordinate toggle** — `settings.ini` option (`show_coordinates = true`) appends grid coordinates to movement, scans, combat, look mode, targeting, and deploy.

### Bug Fixes

- **Scan reverse cycling** — Shift+E/N/Q/Y was broken (modifier keydown reset the scanner). Fixed across all four scanners.
- **Death attribution** — DOT/buff deaths (poison, etc.) now name the effect instead of "Killed by Wizard".
- **Purchase confirmation** — Fires on actual purchase, not when confirm dialog opens. Distinguishes "Learned" / "Equipped" / "Purchased".
- **GH#12 closed** — Bestiary raw object was already fixed.

## [0.2.0] - 2026-03-06

### Q-Key Landmark Cycling + Scanner Unification

- **Q-key converted to cycling** — Q no longer dumps all landmarks at once. Press Q to cycle through pickups and landmarks one at a time, nearest first. Shift+Q reverses. First press speaks a category-aware count header: "8 items. 3 orbs, 1 shop, 2 shrines, 1 rift, 1 scroll." Subsequent presses cycle through entries with "N of M" position.
- **Locked rifts removed from Q scan** — Locked rifts are not actionable during combat. They no longer appear in the landmark scan. Unlocked rifts still appear.
- **Alt+Q landmark marking** — Cycle to a landmark with Q, then press Alt+Q to mark it. Marked landmarks get a direction update each turn. Auto-clears when the prop disappears (e.g., pickup collected).
- **CycleScanner class** — E, N, and Q scanning now share a unified `CycleScanner` infrastructure. Identical cycling, reverse, count-header, and turn-reset behavior across all three keys. ~150 lines of duplicate state management replaced.
- **Generalized marking** — Mark system now supports both units (via E/N) and landmarks (via Q). One mark at a time. Alt+E, Alt+N, and Alt+Q all toggle the mark on the last scanned target.

### Bug Fixes

- **Deploy spawner numbering** — Same-name spawners on deploy get ordinal suffixes ("Spawner, Fire Imp 1", "Spawner, Fire Imp 2"). Computed at display time, stable across wrap.
- **Deploy spawner re-sort removed** — Wrap no longer re-sorts the cycle list. Stable cycle order.
- **E-key count dedup** — Count header ("21 enemies") only spoken once per turn, not on every cycle reset.
- **N-key count dedup** — Same fix applied to spawner cycling.
- **L-key "here" fix** — Units at the player's position now say ", here" instead of a trailing space.
- **Purchase confirmation ordering** — "Learned [spell]" now speaks before character sheet announcement, not after.
- **Keybind help deferral** — Keybind announcements on state change now speak after all other state-entry speech, not before.
- **Char sheet "False" fix** — Character sheet no longer speaks "False" after purchasing a spell. Game sets examine target to boolean False post-purchase; now caught and silenced.

### Post-Release Hotfix (b9d860e)

- **Mark LoS transitions** — Marked targets now report "blocked" or "in sight" on visibility changes. First update reports current LoS status. Steady-state updates show direction only (no noise). No via hints — just raw LoS state.
- **RCtrl diagonal movement** — Non-numpad players can now move diagonally with RCtrl+arrow. Counterclockwise mapping: RCtrl+Up=NW, RCtrl+Right=NE, RCtrl+Down=SE, RCtrl+Left=SW. Works in movement, spell targeting, and deploy cursor.

### Post-Release Hotfix 2

- **European keyboard diagonal fix** — Diagonal movement now also triggers on LCtrl+Alt+arrow. On Spanish and other European laptop keyboards, AltGr sends a synthetic LCtrl+RAlt combination; RCtrl alone was never fired. Both LCtrl+LAlt and LCtrl+RAlt are now accepted alongside RCtrl.
- **README download link** — Added a prominent Download section with a direct link to the latest release and explicit extraction/install instructions. Addresses install friction reported by multiple testers.

### Post-Release Hotfix 3

- **Coordinate toggle** — New `settings.ini` configuration file with a `show_coordinates` option (default: false). When enabled, absolute grid coordinates are appended to movement, enemy/spawner/landmark scans, combat output (damage dealt, deaths, collapsed tier), look mode, spell targeting, and deploy cursor. The settings file is created automatically on first run and survives mod updates. Requested by community tester.
- **Deploy coordinate display** — Coordinate toggle now also covers deploy mode: tile announcements on cursor movement and cycle-jump announcements (keys 2–5) both include coordinates when enabled.

## [0.1.0] - 2026-03-06

First versioned release. Includes all features developed through 68 sessions, plus the spatial navigation overhaul below.

### Spatial Navigation Overhaul

- **E-key enemy cycling** — E no longer dumps all enemies at once. Press E to hear one enemy at a time, nearest first. Press again for the next. No limit — cycle through every enemy on the level. Shift+E cycles backward. Resets when you take any other action or a new turn begins.
- **L-key line of sight summary** — New key. Press L for an instant gestalt of what's visible: "4 in sight. 2 Goblins south, Fire Imp east, Wolf north." Grouped by type and direction. Quick tactical awareness without cycling through individuals.
- **N-key spawner cycling** — New key. Same cycling pattern as E, but filtered to spawners/lairs only. Shift+N reverses. Spawners are threat multipliers — now they have their own dedicated scan.
- **Unit marking (Alt+E / Alt+N)** — Cycle to a unit with E or N, then press Alt+E or Alt+N to mark it. Marked units are tagged in scan output ("marked") and get a direction update each turn ("Marked: Goblin Lair, 5 south"). Press Alt+E/N again on the same unit to unmark. Auto-clears when the marked unit dies.

### New Features

- **On-death effect announcements** — Units with on-death effects (explodes, splits, etc.) now show this in look mode and unit detail (D key).
- **Centralized state transition voicing** — All 15 game states are now detected and announced. Unvoiced states (key rebinding, custom mutator screens) say "Coming soon" instead of silence.
- **Bestiary voicing** — The bestiary screen now speaks monster descriptions for monsters you've encountered.
- **Shop subtype fixes** — Spell upgrade shops now say "Upgrade [SpellName]" instead of generic headers. Shop names, currency types (SP/HP/Gold), and "Owned" status are correctly voiced.
- **Purchase confirmation** — Hearing "Learned [SpellName]" when you buy a spell.
- **Shift+/ mod keybind reference** — Press Shift+/ (?) during gameplay for a spoken list of all mod keybinds.
- **Auto-announce enemy count on level start** — First turn of each level speaks "N enemies, M spawners" automatically.
- **Keybind announcements on state entry** — Relevant mod keybinds are announced when entering shops, character sheet, and other screens.
- **Version announcement on load** — Mod now speaks its version number on startup.

### Bug Fixes

- **GH#6:** Trinkets/equipment with no description no longer cause silent pickups.
- **GH#7:** Deploy spawner key (4) no longer fires the native spell chooser alongside the mod scan.
- **GH#8:** Boss-spawned units (buff-based summons) now announced.
- **GH#9:** Shop and character sheet exits now announced (superseded by centralized state voicing).
- **GH#11:** Spell purchases now logged and spoken ("Learned [SpellName]").
- **GH#12:** Bestiary no longer reads raw Python object references — monster descriptions are now properly voiced.

### Notes

- All features in this release are implemented but await playtest verification. If you encounter issues, please include the relevant section of your `screen_reader_debug.log` when reporting.
- The mod now announces its version ("Words of Power version 0.1.0") on startup so testers can confirm which build they're running.
