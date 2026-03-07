# Words of Power v0.2.0

First off — thank you to matrheine and rashad for playtesting. Your feedback shaped the biggest changes in this build. The spatial memory load problem you both surfaced from different angles drove the entire navigation redesign. Every log you sent, every observation you shared, directly made the mod better. That's not a platitude — you can see your fingerprints on the specific features below.

## What's New in a Nutshell

The scanning system has been completely rebuilt. Instead of dumping all enemies or landmarks in a single burst of speech, everything now cycles one at a time. Two new scan keys (L for line of sight overview, N for spawners) give you faster tactical awareness. You can mark any target — enemy, spawner, or landmark — and get passive direction updates every turn. Twelve bug fixes, six new features, and a unified scanner architecture under the hood.

## Keybind Changes You Need to Know

These are gameplay-affecting. If you've been playing the previous build, your muscle memory will need to adjust.

### E key works differently now

**Before:** Press E, hear all enemies dumped at once.
**Now:** Press E, hear one enemy. Press E again for the next. Cycles through every enemy on the level, nearest first. **Shift+E** cycles backward.

This is the direct response to the spatial memory load feedback. Instead of trying to hold five enemies in your head from one burst of speech, you hear them one at a time and can stop when you have what you need.

### Two new scan keys: L and N

**L — Line of sight summary.** A quick tactical glance: "4 in sight. 2 Goblins south, Fire Imp east, Wolf north." What you're facing and where, one sentence. Use this instead of E when you just want the overview.

**N — Spawner scan.** Same cycling as E, but only spawners and lairs. Shift+N reverses. Spawners are threat multipliers — this was a direct feature request. No more scanning past regular enemies to find them.

**The loop: L for "what's here?", E for "tell me about each one", N for "where are the spawners?"**

### Q key works differently now

**Before:** Press Q, hear all landmarks dumped at once.
**Now:** Press Q, hear one landmark. Press Q again for the next. Nearest first. **Shift+Q** reverses. First press gives a category count: "5 items. 2 orbs, 1 shop, 2 rifts."

### Marking: Alt+E, Alt+N, Alt+Q

Cycle to any target with E, N, or Q, then press Alt+that key to mark it. Marked targets get a direction update every turn: "Marked: Spawner, Bat, 8 east 5 north." Auto-clears when the unit dies or the landmark is collected. One mark at a time.

### Shift+/ (question mark) — Keybind reference

Press Shift+/ during gameplay for a spoken list of all mod keybinds. If you forget what a key does, this is your reference.

## Other New Features

- **On-death effects** — Units that explode, split, or trigger effects on death now show this in look mode and D-key detail.
- **All game screens detected** — Every screen transition is now announced. Screens that don't have speech yet say "Coming soon" instead of silence.
- **Bestiary voiced** — Monster descriptions are now spoken when browsing the bestiary.
- **Shop headers fixed** — Spell upgrade shops say "Upgrade [SpellName]" instead of generic headers. Currency types (SP/HP/Gold) and "Owned" status are correct.
- **Purchase confirmation** — You hear "Learned [SpellName]" when you buy a spell.
- **Level start count** — First turn of each level automatically speaks "N enemies, M spawners."

## Bug Fixes

- Trinkets/equipment with no description no longer cause silent pickups
- Deploy spawner key (4) no longer fires the native spell chooser alongside the mod scan
- Boss-spawned units now announced
- Shop and character sheet exits now announced
- Bestiary no longer reads raw Python object references
- Deploy spawners with the same name now get numbered suffixes ("Spawner, Fire Imp 1", "Spawner, Fire Imp 2")
- Deploy cycling no longer re-sorts on wrap
- E and N count headers only speak once per turn instead of on every cycle reset
- L-key units at the player's position now say "here" instead of showing a blank direction
- "Learned [spell]" now speaks before the character sheet announcement, not after
- Keybind help on screen transitions now speaks after other announcements, not before
- Character sheet no longer speaks "False" after purchasing a spell

## How to Update

Replace the `screen_reader.py` file in your `mods/screen_reader/` folder with the new one from the repo. The DLL hasn't changed. You'll hear "Words of Power version 0.2.0" on startup to confirm you're on the new build.

Keep sending logs and feedback. Every report makes the mod better.
