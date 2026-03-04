# Known Issues

## Unvoiced Screens

The following screens do not have speech output yet:

- **Custom game mutator screens** — The three screens for configuring custom game mutators (setup, parameter selection, value entry) are silent. Standard game modes work fine.
- **Key rebind screen** — The in-game key rebinding interface has no speech output.
- **"Never Learned" and "Never Victory" buttons** — These are mouse-only in the base game and have no keyboard equivalent. Not accessible without a mouse.
- **Empty shop** — If a shop has no items remaining, nothing is spoken. You'll just hear silence when examining the tile.

## Untested Features

- **Cooldown ready notification** — The mod announces when a spell comes off cooldown, but no playtest has encountered a cooldown spell yet. This feature exists but is unverified.

## Setup Notes

- NVDA must be running before you launch the game. If NVDA starts after the game, the mod won't connect.
- The mod requires `nvdaControllerClient64.dll` in the `mods/screen_reader/` folder. This file ships with NVDA — see QUICKSTART.md for where to find it.
