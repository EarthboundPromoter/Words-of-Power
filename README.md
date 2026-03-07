# Words of Power

**Version 0.2.0**

An accessibility mod for Rift Wizard 2 that provides full speech output through NVDA.

## About Rift Wizard 2

> Rift Wizard 2 is a tough as nails traditional roguelike wizard simulator. You play as an immortal amnesiac wizard who must journey through the cosmos to defeat his nemesis. Each run, you'll build a unique repertoire of spells, passive skills, and magical artifacts.
>
> — [Steam store page](https://store.steampowered.com/app/2058570/Rift_Wizard_2/)

## Requirements

- [Rift Wizard 2](https://store.steampowered.com/app/2058570/Rift_Wizard_2/) (Steam, Windows)
- [NVDA](https://www.nvaccess.org/) screen reader

## Quick Start

1. NVDA must be running before you launch the game.
2. The mod folder goes in `RiftWizard2/mods/screen_reader/`. It should contain `screen_reader.py` and `nvdaControllerClient64.dll`.
3. Launch the game normally. You'll hear "Words of Power version 0.2.0" if it's working.
4. Debug log writes to `screen_reader_debug.log` in the mod folder.

## How It Works

The mod hooks into the game's Python source and voices every gameplay-relevant event. The goal is for the mod to disappear — you're not using an accessibility tool, you're just playing Rift Wizard 2. Where a sighted player sees a small damage number and infers "resisted," you hear "resisted." The same information, the same challenge, the same game.

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

The game's own controls are unchanged. Press H in-game for its native help screen. Press Shift+/ (?) for the full mod keybind reference. Everything below is added by the mod.

### Scans

| Key | Function |
|-----|----------|
| **E** | Enemy scan — press repeatedly to cycle through all enemies, nearest first. Shift+E reverses. |
| **L** | Line of sight — enemy count by type with direction (gestalt overview) |
| **N** | Spawner scan — press repeatedly to cycle through spawner/lair units. Shift+N reverses. |
| **Q** | Landmark scan — press repeatedly to cycle through rifts, shops, shrines, orbs, pickups. Shift+Q reverses. |
| **B** | Spatial raycast — walkable distance in all 8 directions |
| **X** | Hazard scan — clouds, storms, fire, webs |
| **T** | Threat check — adjacent melee danger (safe / pressed / surrounded) |
| **D** | Unit detail — full abilities, passives, resistances, movement |

### Unit Marking

| Key | Function |
|-----|----------|
| **Alt+E** | Mark/unmark the last enemy announced by E scan |
| **Alt+N** | Mark/unmark the last spawner announced by N scan |
| **Alt+Q** | Mark/unmark the last landmark announced by Q scan |

Marked targets are tagged in scan output and get a direction update each turn. One mark at a time — marking a new target replaces the previous mark. Marks auto-clear when the unit dies or the landmark is collected.

### Status

| Key | Function |
|-----|----------|
| **F** | Vitals — HP, shields, SP, active effects and durations |
| **G** | Charges — selected spell's charges, or all spells if none selected |

### Speech Control

| Key | Function |
|-----|----------|
| **Left Ctrl** | Cancel speech |
| **Z** | Repeat last message |
| **[** | Speech history back (200 messages stored) |
| **]** | Speech history forward |

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

## Known Issues

See [KNOWN_ISSUES.md](KNOWN_ISSUES.md).

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Credits

- Rift Wizard 2 by Dylan White
- [NVDA](https://www.nvaccess.org/) by NV Access
