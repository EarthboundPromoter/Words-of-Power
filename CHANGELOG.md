# Changelog

All notable changes to Words of Power are documented here.

## [0.3.0] - 2026-04-28

### New Feature: Pathfinding

- **Marked target pathfinding** — Marking a target with Alt+E/N/Q/Y now announces the full compressed path on placement, then the next-step direction with target name and HP each subsequent turn. Diagonals included, matching the game's own pathfinding. Hostile units route to the cheapest walkable adjacent tile (since the target's tile is impassable to the player). Spawners get HP because they have HP. Landmarks omit the HP clause. LoS transitions surface a richer line (`Northwest to Wolf, 12 HP, blocked.`) since you're entering engagement range. Adjacent and on-tile cases stay silent — the melee threat tracker and on-mark announcement already cover those.
- **P, path to look-mode cursor** — In look mode, P announces the full compressed path from your wizard to whatever is under the cursor: unit, prop, floor tile, anything. Walls and chasms report as impassable.
- **Shift+P, refresh path to marked target** — Re-announce the full compressed path to your current mark, without having to unmark and remark. Useful for reorienting during a long approach.
- **Settings: pathfind_marked = true** (default) — Toggle the per-turn navigation channel. The on-mark and Shift+P announcements still work when this is off; only the per-turn prefix is silenced.
- **Settings: show_coordinates default flipped to true** — Players asked for grid coordinates often enough that the default was wrong. Existing installs keep whatever's written in their settings.ini. New installs get coordinates on by default.

### Documentation

- **README** — New "Game Keybinds" section listing the game's own controls alongside the mod's hotkey tables, so the keybind reference is one document instead of two.
- **In-game keybind reference (Shift+/)** — Updated to mention P and Shift+P.

## [0.2.5] - 2026-04-24

### Bug Fixes

- **Tile type under cloud now spoken in Look mode** — Looking at a Storm Cloud (or any cloud) on an empty floor tile now reads "Storm Cloud, 5 turns. Floor" instead of just "Storm Cloud, 5 turns". Cloud-on-wall and cloud-on-chasm already worked; cloud-on-floor was the missing case. Reported by playtester (Boing) on a Storm Troll realm where the cloud overlay made it impossible to tell what terrain was underneath.
- **Spurious "Within AoE" warning on non-AoE spells with stacked radius** — Movement spells like Blink and Teleport pick up a `radius >= 1` stat from global radius modifiers (e.g., Aether Wisp), but the radius is purely cosmetic — no damage or effect propagates. The cursor's AoE warning now checks the spell's *base* radius rather than its modified radius, so single-target/movement spells no longer announce "Within AoE 1 enemy" when the cursor sits on a unit.

## [0.2.4] - 2026-04-22

### New Features

- **Enters line of sight** — Enemies entering your field of view are announced with name and direction ("Wolf appears, 3 east"). When the player moves, a full visibility diff detects all newly visible enemies. When enemies move into view or spawn in sight, they're announced individually. Large groups (above threshold) collapse to a count ("7 enemies enter view"). Dead units are cleaned from tracking automatically.
- **Enemy cast batching** — Non-summon enemy casts (Stone Gaze, Heal Ally, etc.) now route through the collapsed speech tier and group by caster and spell, matching summon cast behavior ("5 Cockatrices cast Stone Gaze"). Previously these were silently dropped during batching.
- **Flush-time dedup** — Three or more consecutive identical speech lines during batch flush are coalesced ("4 times. Wolf appears, 3 east"). Reduces repetition in high-density turns.

### Improvements

- **Same-shape group merging** — Single-event target groups sharing the same event type and payload (e.g., thirteen identical heals) are merged into one collective line ("13 Ghostly Cursed Cats heal 5, east"). Applies to heals, damage, and deaths.
- **Pre-activation batching fix** — Batcher now activates before spell resolution, so events fired during the player's cast are captured by the collapse tier instead of falling through to immediate speech.
- **Known issues updated** — Removed stale entries for screens voiced in 0.2.2 and outdated playtesting coverage claims.

### Post-Release Hotfix

- **Telemetry import crash fix** — Fixed a crash when the dev-only telemetry module is absent. The import fallback had both attempts in a single try/except, so if the package import failed the bare import also raised an unhandled ImportError. Now falls back cleanly to disabled telemetry. Does not affect gameplay.

## [0.2.3] - 2026-04-10

### New Features

- **PgUp/PgDn tooltip cycling** — Spell upgrades, summoned unit stat blocks, and equipment details are now voiced when cycling through extra examine tooltips. Previously this was completely silent, blocking access to pre-purchase evaluation of spell upgrades and summon stats.
- **Screen-reader-friendly keybinds** — Tooltip cycling rebound from PgUp/PgDn (which conflict with NVDA numpad passthrough) to **Backslash** (prev) and **Backspace** (next). PgUp/PgDn kept as secondary bindings. Fast Forward unbound to free Backspace. Migration happens automatically on first load with a one-time announcement; players can rebind in Options at any time.
- **Level-complete stats summary** — Clearing a level now reads the full stats summary (turns, spell casts, damage dealt/taken, items used, purchases) via buffered speech. Use [ ] to navigate sections. Previously only the gameover screen had stats voicing.
- **Spell reorder feedback** — Shift+Up/Down in the character sheet now announces which spell you moved past: "Moved above Fireball" or "Moved below Icicle".

### Bug Fixes

- **Poison blocks potion: now voiced (GH#13)** — Attempting to use a healing potion while poisoned now says "poisoned" instead of the generic "cannot cast".
- **Level-complete turn stomp** — The post-victory turn signal no longer interrupts the level-complete stats readout.

## [0.2.2] - 2026-04-09

### Multi-Screen-Reader Support

- **Tolk integration** — TTS now uses the Tolk abstraction library, which auto-detects the active screen reader. Supports NVDA, JAWS, SAPI5, Window-Eyes, SuperNova, System Access, and ZoomText.
- **NVDA fallback preserved** — If Tolk.dll is not present, falls back to direct NVDA DLL calls (previous behavior).
- **SAPI as last resort** — SAPI is enabled but deprioritized so real screen readers are always preferred.

### All Game Screens Now Voiced

- **Key rebind screen** — Full voicing of the rebind controls menu. Announces function name, slot (primary/secondary), and current key binding on navigation. "Press a key to bind" prompt when entering rebind mode.
- **Custom game setup** — Mutator browser with name and description readout. Announces selected mutators and play button with count.
- **Mutator parameter picker** — Voiced navigation of parameter options for configurable mutators.
- **Mutator value entry** — Speaks each digit as typed, announces backspace. No unvoiced screens remain.

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
- **Purchase confirmation** — Fires on actual purchase, not when confirm dialog opens. Distinguishes "Learned" / "Equipped" / "Purchased". Log now includes SP cost.
- **Deploy overview pickup counts** — Key 1 overview now counts pickups (heals, charges, hearts, scrolls, equipment) per quadrant alongside orbs and shops.
- **Staff/equipment effects** — All code paths now show equipment bonuses: shop, character sheet, D-key, and equip-on-pickup.
- **GH#1, #2, #3, #10, #11, #12 closed.**

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
