# Known Issues

## Inaccessible Base-Game Features

- **"Never Learned" and "Never Victory" buttons** — These are mouse-only in the base game and have no keyboard equivalent. Not accessible without a mouse.
- **Empty shop** — If a shop has no items remaining, nothing is spoken. You'll hear silence when examining the tile.

## Speech Output

- **High-density turns** — Proc-heavy builds in late game can generate dozens of events per turn. Speech batching handles this well in most cases, but particularly chaotic turns (mass summons chaining into mass kills) may still produce long output. Active development is focused here.
- **Cooldown ready notification** — The mod announces when a spell comes off cooldown, but no playtest has encountered a cooldown spell yet. This feature exists but is unverified.

## Setup Notes

- Your screen reader must be running before you launch the game. If it starts after the game, the mod won't connect.
- Tolk.dll must be in the `mods/screen_reader/` folder alongside `screen_reader.py`. Without it, the mod falls back to direct NVDA support only (no JAWS or other screen readers).
