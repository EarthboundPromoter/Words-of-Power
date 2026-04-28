# Words of Power

**Version 0.3.0**

An accessibility mod for Rift Wizard 2 that provides full speech output through NVDA, JAWS, and other screen readers.

## About Rift Wizard 2

> Rift Wizard 2 is a tough as nails traditional roguelike wizard simulator. You play as an immortal amnesiac wizard who must journey through the cosmos to defeat his nemesis. Each run, you'll build a unique repertoire of spells, passive skills, and magical artifacts.
>
> — [Steam store page](https://store.steampowered.com/app/2058570/Rift_Wizard_2/)

## Requirements

- [Rift Wizard 2](https://store.steampowered.com/app/2058570/Rift_Wizard_2/) (Steam, Windows)
- A screen reader: [NVDA](https://www.nvaccess.org/), [JAWS](https://www.freedomscientific.com/products/software/jaws/), or any screen reader supported by [Tolk](https://github.com/dkager/tolk) (Window-Eyes, SuperNova, System Access, ZoomText, SAPI5)

## Download

**[Download the latest release →](https://github.com/EarthboundPromoter/Words-of-Power/releases/latest)**

Click the link above, then download the `.zip` file listed under Assets.

## Quick Start

1. Your screen reader must be running before you launch the game.
2. Extract the downloaded zip. Copy the `screen_reader` folder into `RiftWizard2/mods/` so the path looks like `RiftWizard2/mods/screen_reader/screen_reader.py`. (Create the `mods` folder if it doesn't exist.)
3. Make sure `Tolk.dll` is in the `screen_reader` folder alongside `screen_reader.py`. If Tolk.dll is not present, the mod falls back to direct NVDA support only.
4. Launch the game normally. You'll hear "Words of Power version 0.3.0" if it's working.
5. Debug log writes to `screen_reader_debug.log` in the mod folder.

## How It Works

The mod hooks into the game's Python source and voices every gameplay-relevant event. All game screens are fully accessible — menus, shops, character sheets, combat, deploy, custom game setup, key rebinding, everything. The goal is for the mod to disappear — you're not using an accessibility tool, you're just playing Rift Wizard 2. Where a sighted player sees a small damage number and infers "resisted," you hear "resisted." The same information, the same challenge, the same game.

Every death should be attributable to your decisions, never to missing information.

### Speech Batching

A busy enemy turn can generate 20+ events. Dumping them sequentially is unusable. The mod organizes speech into three tiers:

**Immediate** — Damage you take, your HP, death. Speaks instantly, even during enemy turns. You never miss being hit.

**Queued** — Your spell results. Damage dealt, kills, buffs applied. Held until end of turn and delivered in order, so your spell's effects aren't interleaved with enemy noise.

**Collapsed** — Everything else. Enemy attacks, summons, world events. Grouped by target unit, sorted nearest first, line-of-sight before out-of-sight. Three enemies hitting your Wolf becomes one block: who hit it, how hard, remaining HP. Twenty events become a structured summary.

Combat has a rhythm: what happened to you, what your spells did, what happened in the world.

Player-initiated speech (scan keys, movement, shops, UI) always speaks immediately and bypasses batching entirely.

### Automatic Feedback

The mod tracks resources so you don't have to count. Spell charges announce at half, low, last, and depleted. HP warnings fire at 20% and 10%. Buffs warn one turn before expiring. Damage against resistant or vulnerable targets is tagged — the speech equivalent of seeing bigger or smaller numbers on screen.

## Keybinds

The game's own controls are unchanged. Press H in-game for its native help screen. Press Shift+/ (?) for the full mod keybind reference. The first section below is the game's native controls; everything after is added by the mod.

> **Note:** On first launch, the mod rebinds tooltip cycling from PgUp/PgDn to **Backslash** (previous) and **Backspace** (next) for screen reader compatibility. PgUp/PgDn are kept as secondary bindings. Fast Forward is unbound to free Backspace. You can change any of these in Options > Key Rebind.

### Game Keybinds

The game's defaults, included here so you don't have to keep two reference docs open. Bindings can be customized in Options > Key Rebind.

**Movement**

| Key | Function |
|-----|----------|
| **Arrow keys** | Cardinal movement (also Numpad 8/2/4/6) |
| **Numpad 7/9/1/3** | Diagonal movement (NW/NE/SW/SE). Without numpad, use the mod's RCtrl+Arrow combos. |
| **Space** or **Numpad 5** | Pass turn / channel current spell |
| **W** | Walk — move continuously toward a target tile |

**Spells & Items**

| Key | Function |
|-----|----------|
| **1–0** | Select Spell 1 through 10 |
| **Shift+1–0** | Spell info (in some screens) |
| **Alt+1–0** | Use item 1 through 10 |
| **Enter** | Confirm / cast / accept (also Numpad Enter) |
| **Escape** | Abort current action / back out of menu |
| **Tab** | Cycle to next valid target while a spell is selected |
| **R** | Reroll rifts (level select screen) |

**Information**

| Key | Function |
|-----|----------|
| **C** or **`** (backtick) | Open Character Sheet |
| **S** | Open Spells screen |
| **K** | Open Skills screen |
| **V** | Look mode (free cursor over the map) |
| **M** | Message log |
| **H** or **/** | Help screen |
| **T** | Show Threat Zone (the mod overrides this with its own threat readout) |
| **L** | Show Line of Sight (the mod overrides this with its own LoS summary) |
| **Backslash** | Previous tooltip (was PgUp; rebound by the mod for screen reader compatibility) |
| **Backspace** | Next tooltip (was PgDn; rebound by the mod) |

**Other**

| Key | Function |
|-----|----------|
| **A** | Auto-pickup nearby items |
| **I** or **.** (period) | Interact with the prop on your tile |

### Scans

| Key | Function |
|-----|----------|
| **E** | Enemy scan — press repeatedly to cycle through all enemies, nearest first. Shift+E reverses. |
| **Y** | Ally scan — press repeatedly to cycle through allied units, nearest first. Shift+Y reverses. |
| **L** | Line of sight — enemy count by type with direction (gestalt overview) |
| **N** | Spawner scan — press repeatedly to cycle through spawner/lair units. Shift+N reverses. |
| **Q** | Landmark scan — press repeatedly to cycle through rifts, shops, shrines, orbs, pickups. Shift+Q reverses. |
| **B** | Spatial raycast — walkable distance in all 8 directions |
| **X** | Hazard scan — clouds, storms, fire, webs |
| **T** | Threat check — adjacent melee danger (safe / pressed / surrounded) |
| **D** | Detail — full info on whatever is under the cursor (units, portals, shops, terrain, props) |

### Unit Marking

| Key | Function |
|-----|----------|
| **Alt+E** | Mark/unmark the last enemy announced by E scan |
| **Alt+Y** | Mark/unmark the last ally announced by Y scan |
| **Alt+N** | Mark/unmark the last spawner announced by N scan |
| **Alt+Q** | Mark/unmark the last landmark announced by Q scan |

Marked targets are tagged in scan output and get a per-turn pathfinding update (see Pathfinding below). One mark at a time — marking a new target replaces the previous mark. Marks auto-clear when the unit dies or the landmark is collected. Pressing the same Alt+key on the current mark unmarks it.

### Pathfinding

| Key | Function |
|-----|----------|
| **P** | Path to look-mode cursor — full compressed path to whatever the cursor is on (unit, prop, floor, wall) |
| **Shift+P** | Refresh path to marked target — re-announce the full compressed path without having to unmark + remark |

When you mark a target, the mod announces the full path immediately (`Marked Wolf. 12 steps. Northeast 4, north 3, east 5, arrive adjacent.`). On each subsequent turn until you arrive, you get a compact next-step line (`Northwest to Wolf, 12 HP.`). Diagonals are used wherever the game's pathfinder uses them — what you hear matches what your wizard would actually walk. Hostile units route to the cheapest walkable adjacent tile (since you can't stand on top of an enemy), and the path tail says `arrive adjacent` instead of `arrive`. Unreachable destinations report `No path.` Adjacent and on-tile cases stay silent so the per-turn line doesn't compete with the melee threat tracker.

Set `pathfind_marked = false` in `settings.ini` to silence the per-turn channel. The on-mark announcement and Shift+P still work — you just won't get a turn-by-turn navigation step.

### Status

| Key | Function |
|-----|----------|
| **F** | Vitals — HP, shields, SP, active effects and durations |
| **Shift+F** | Ally overview — buffered list of all allies with HP |
| **G** | Charges — selected spell's charges, or all spells if none selected |

### Speech Control

| Key | Function |
|-----|----------|
| **Left Ctrl** | Cancel speech |
| **Z** | Repeat last message |
| **[** | Speech history back (200 messages stored) |
| **]** | Speech history forward |

### Movement

| Key | Function |
|-----|----------|
| **RCtrl+Arrow** | Diagonal movement (Up=NW, Right=NE, Down=SE, Left=SW) |

### Deploy Mode

Active only during the starting placement phase before each level.

| Key | Function |
|-----|----------|
| **1** | Quadrant overview — enemies, spawners, loot by area |
| **2** | Cycle Memory Orbs |
| **3** | Cycle Pickups |
| **4** | Cycle Spawners |
| **5** | Cycle Shops / Shrines / Circles |

### Shop

| Key | Function |
|-----|----------|
| **Tab** | Filter guide — active filters and available filter keys |

Tag and attribute filters are voiced when toggled.

## Tips

- **L is your glance. E is your focus.** L tells you what's in sight and where. E cycles through detail on each enemy. Use L for quick awareness, E when you need specifics.
- **N for spawners.** Spawners are threat multipliers. Tracking them separately saves you from scanning past regular enemies to find them.
- **Alt+E to track a target.** Mark a priority target (spawner, dangerous enemy) and get passive direction updates each turn without having to re-scan.
- **B after any displacement.** Tells you room shape and corridor exits. Essential for orientation.
- **[ is your rewind.** Missed something? Step back through the speech buffer.
- **Deploy mode matters.** Press 1 for the overview, 2-5 to scout specifics. Starting position is a real decision.
- **Log file is your replay.** Everything is in `screen_reader_debug.log`, timestamped and labeled.

## Reporting Issues

Include: what you were doing, what you heard (or didn't), and the relevant section of the debug log.

## Privacy

This mod makes no network connections. It does not collect, transmit, or upload any data. Everything stays on your machine.

If you read the source code, you'll see references to a `telemetry` module. This is a dev-only tool the author uses for post-run analysis — it writes structured logs to local disk to help improve speech output. The telemetry module is not included in the release download, so the import silently fails and every telemetry call is a no-op. Even if the module were present, it requires a manually created sentinel file to activate, and contains no network code.

## Known Issues

See [KNOWN_ISSUES.md](KNOWN_ISSUES.md).

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Credits

- Rift Wizard 2 by Dylan White
- [Tolk](https://github.com/dkager/tolk) by Davy Kager
- [NVDA](https://www.nvaccess.org/) by NV Access
