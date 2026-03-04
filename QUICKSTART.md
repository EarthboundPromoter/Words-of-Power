# Rift Wizard 2 Screen Reader Mod

## Setup

1. NVDA must be running before you launch the game.
2. The mod folder goes in `RiftWizard2/mods/screen_reader/`. It should contain `screen_reader.py` and `nvdaControllerClient64.dll`.
3. Launch the game normally. You'll hear "Screen reader mod loaded" if it's working.
4. Debug log writes to `screen_reader_debug.log` in the mod folder.

## Design

The mod hooks into the game's Python source and voices every gameplay-relevant event. The goal is equivalent access — the same information a sighted player gets, delivered through speech. Not simplified, not computed for you. If a sighted player sees a small damage number and infers "resisted," you hear "resisted." If a sighted player has to learn which spells counter which enemies, so do you. The mod provides perception, not analysis.

The success criterion: every death should be attributable to your decisions, never to missing information.

### Speech Batching

A busy enemy turn can generate 20+ events. Dumping them sequentially is unusable. The mod organizes speech into three tiers:

**Immediate** — Damage you take, your HP, death. Speaks instantly, even during enemy turns. You never miss being hit.

**Queued** — Your spell results. Damage dealt, kills, buffs applied. Held until end of turn and delivered in order, so your spell's effects aren't interleaved with enemy noise.

**Collapsed** — Everything else. Enemy attacks, summons, world events. Grouped by target unit, sorted nearest first, line-of-sight before out-of-sight. Three enemies hitting your Wolf becomes one block: who hit it, how hard, remaining HP. Twenty events become a structured summary.

Combat has a rhythm: what happened to you, what your spells did, what happened in the world.

Player-initiated speech (scan keys, movement, shops, UI) always speaks immediately and bypasses batching entirely.

### Automatic Feedback

The mod tracks resources so you don't have to count. Spell charges announce at half, low, last, and depleted. HP warnings fire at 20% and 10%. Buffs warn one turn before expiring. Damage against resistant or vulnerable targets is tagged — the speech equivalent of seeing bigger or smaller numbers on screen.

## Keybinds — Mod

The game's own controls are unchanged. Press H in-game for its native help screen. Everything below is added by the mod.

### Scans

| Key | Function |
|-----|----------|
| **E** | Enemy scan — count, nearest with distance, direction, LoS status |
| **Q** | Landmark scan — rifts, shops, shrines, orbs, pickups, equipment |
| **B** | Spatial raycast — walkable distance in all 8 directions |
| **X** | Hazard scan — clouds, storms, fire, webs |
| **T** | Threat check — adjacent melee danger (safe / pressed / surrounded) |
| **D** | Unit detail — full abilities, passives, resistances, movement |

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

- **E and Q are your eyes.** Press them constantly — start of turn, after teleporting, after anything changes. Make it reflexive.
- **B after any displacement.** Tells you room shape and corridor exits. Essential for orientation.
- **[ is your rewind.** Missed something? Step back through the speech buffer.
- **Deploy mode matters.** Press 1 for the overview, 2-5 to scout specifics. Starting position is a real decision.
- **Log file is your replay.** Everything is in `screen_reader_debug.log`, timestamped and labeled.

## Reporting Issues

Include: what you were doing, what you heard (or didn't), and the relevant section of the debug log.
