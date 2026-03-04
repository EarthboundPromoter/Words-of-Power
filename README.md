# Rift Wizard 2 Screen Reader Mod

## What Is Rift Wizard 2?

Rift Wizard 2 (RW2) is a tactical turn-based grid-based traditional roguelike developed by Dylan White. You play as a nameless amnesiac wizard, fated to descend through portals to seek out and kill the big bad, Mordred. In practice, this means descending through level after procedurally generated level killing hordes of enemies, picking up loot, getting stronger, and inevitably getting yourself killed in embarrassing fashion. The game features hundreds of spells with every spell having at least a couple mutually exclusive upgrades, skills that offer powerful passive effects, items and equipment that synergize with all of the above, and a rogue's gallery of mean and creative enemy types to contend with. Its brilliance lies in its size and flexibility. If you can imagine how two spells will work together, it probably works. The game rewards creative thinking, ingenuity, curiosity, and a willingness to learn as you play. It's brilliant.

## What Is This Mod?

This mod enables text to speech access to RW2 via NVDA's native controller dll. Support for other screen readers is planned, but for now, NVDA is required.

### Design Principles

The goal is not "accessibility mode." The goal is that the mod disappears and you just play the game.

That means no separate accessibility layer sitting on top of the real game. No extended sequences of key presses to get basic information. No modal interfaces you have to enter and exit to find out what's next to you. Every tool the mod provides is a single key press that gives you what you need and gets out of the way, and the automatic voicing — combat events, movement feedback, shop descriptions — follows your intent, not a script. If you're casting a spell, you hear what your spell did. If you're browsing a shop, you hear what you're looking at. If you're just walking, you hear what's underfoot. The mod watches what you're doing and voices accordingly.

The scan keys — enemies, landmarks, hazards, spatial, threat — are composable tools, not a fixed workflow. There's no "right order" to press them in. You use whichever ones you need, whenever you need them, and they each give you one clean piece of the picture. A player three hours in will use them differently than a player thirty hours in, and both are using them correctly. The mod doesn't prescribe how you play. It gives you the pieces and trusts you to assemble them.

The speech itself is designed with the same care. Every phrase is chosen for economy — fewer words that carry more meaning, because at speech speed you don't get to re-read a sentence. Damage types are embedded in spell results, not announced separately. Target groups are ordered by proximity because the nearest threat is the one that matters most. HP is a footer, not a header, because you need to know who got hit before you need to know how much they have left. None of these decisions are arbitrary. Each one is the result of testing, listening, and asking "could I play this game from the speech alone and make good decisions?"

The bar is not "does the mod report the right information." The bar is "does the player have what they need to play at their actual skill level." Equivalent access, not simplified access. The same game, the same decisions, the same depth — delivered through speech instead of a screen.

## How It Works

The mod hooks into RW2's Python source and voices every gameplay-relevant event — combat, navigation, spells, shops, menus, all of it. The challenge is that a tactical roguelike generates a lot of events per turn. A busy enemy phase can produce 20+ individual messages: damage, deaths, spell casts, summons, status effects. Dumping all of that into speech sequentially is a wall of noise. So the mod doesn't do that.

### Speech Batching

Everything you hear is organized into three tiers.

**Immediate** is survival information. Damage you take, your HP, death. These speak the instant they happen, even during the enemy turn. You will never miss being hit.

**Queued** is the result of your own actions. Your spell hits something, kills something, applies a buff. These are held until the end of the turn and delivered in order, so you get a clean readout of what your spell did without enemy actions interleaved in the middle.

**Collapsed** is everything else — enemy attacks, world events, summons. Instead of one message per event, the mod groups them by target. If three enemies hit your Wolf, you hear one block: the Wolf's name, who hit it, how hard, and its remaining HP. Targets are sorted nearest first, line of sight before out of sight. Twenty events become a structured summary you can actually follow.

The result is that combat has a rhythm. You hear what happened to you, then what your spells did, then what happened in the world. Busy turns stay readable. Quiet turns stay brief.

### Spatial Awareness

You can't glance at the screen, so the mod gives you tools to build a mental map on demand.

**E key** is your enemy scan — how many enemies on the level, then the nearest ones with distance, direction, and line of sight status. If an enemy is behind a wall but reachable by walking around, it tells you that too. This is the key you'll hit most.

**Q key** is your landmark scan — rifts, shops, shrines, orbs, pickups. Same format: what's there, how far, which direction.

**B key** is your spatial probe. It fires a raycast in all eight directions and tells you how far you can walk before hitting a wall or edge. This is how you find corridors, gauge room sizes, and plan escape routes.

**X key** is your hazard scan — storm clouds, fire, webs, anything on the ground you'd rather not step in.

Get in the habit of pressing E and Q at the start of every turn, especially after teleporting or entering a new area. They're your eyes. The sooner they become reflexive, the less you'll think about them.

### Deploy Mode

Every level starts with a deploy phase where you choose your starting position before anything can attack you. The mod adds navigation tools so you can make an informed decision instead of guessing:

**Key 1** gives you a quadrant overview — enemy counts, spawners, orbs, and shops broken out by area. **Keys 2-5** cycle through specific categories (orbs, pickups, spawners, shops), jumping your cursor to each one and announcing its direction. Look before you leap.

### Combat Feedback

The mod tracks your resources so you don't have to count in your head. Spell charges announce at half, low, last, and depleted. HP warnings fire at 20% and again at 10%. Buff expirations warn you one turn before they drop. Vulnerability and resistance tags tell you when your damage is being amplified or reduced — the speech equivalent of seeing bigger or smaller numbers on screen.

**F key** gives you a full vitals readout whenever you want it — HP, shields, SP, active effects and their durations.

**T key** tells you your melee threat status. Adjacent enemies are the most dangerous thing in a roguelike, and this key tells you whether you're clear, pressed, or surrounded.

**D key** gives you the full breakdown on whatever you're examining — abilities, passives, resistances, movement. Use it when you encounter something you haven't seen before.

### Speech Control

**Left Ctrl** cancels current speech. **Z** repeats the last thing spoken. **[** and **]** step backward and forward through your speech history — the last 200 messages are stored. You don't have to catch everything on the first pass.

## Roguelike Tips

If you're new to roguelikes, or to games that kill you and mean it, welcome. The learning curve is real but the genre is worth it. Here are some universals.

**You will die, and that's the game working correctly.** Permadeath is what makes your decisions matter. When you can't reload, every choice has weight — whether to use a consumable, whether to fight or run, whether to push one more floor or call it. That weight is the whole point. Lean into it.

**Corridors good, open space bad.** In the open, enemies can come at you from every direction. In a corridor, they queue up single file. When a fight turns ugly, back into a narrow space. When a fight is going fine, know where the nearest narrow space is anyway, just in case.

**Getting surrounded kills you.** This is the most common way to die in the entire genre. One or two adjacent enemies is a fight. Four or five is a death sentence. If you can see it developing, fix it now. Not next turn. Now.

**Save yourself before you need saving.** The time to retreat is when you first think "this might go badly," not three turns later when it already has. A retreat you didn't end up needing cost you nothing. A retreat you needed and didn't take cost you the run.

**Everything is a resource, including your position.** Health, charges, consumables, items, even where you're standing on the map — all of it is finite, all of it is spent by playing, and managing it is the game. Don't hoard everything waiting for a perfect moment that never comes. Don't blow it all on floor 1 either. Finding the middle is a skill, and you build it by getting it wrong a few times.

**Figure out what killed you.** After every death, think back. When did the run actually go wrong? It's almost never the turn you died on — it's usually several turns earlier, when you made the decision that locked you into a losing position. Finding that moment is how you stop making the same mistake twice.

**The first few runs are tuition.** You're going to die early, die often, and die to things you didn't see coming. That's fine. Every death teaches you something — an enemy type, a resource curve, a positioning mistake. Eventually the game clicks and you start seeing the decisions before they punish you. That's when it gets really good.

## Keybinds

### Game Controls

These are the base game's controls. The mod voices their results but doesn't change how they work.

#### Movement

| Key | Function |
|-----|----------|
| **Arrow Keys** | Move in 4 directions |
| **Numpad 1-9** | Move in 8 directions (diagonals included) |
| **Numpad 5** or **Space** | Pass turn |
| **W** | Toggle walk mode (move without attacking) |

#### Spells & Items

| Key | Function |
|-----|----------|
| **1-0** | Select spell (slots 1-10) |
| **Tab** | Cycle targets while casting |
| **Enter** | Confirm cast |
| **Escape** | Cancel spell selection |
| **Alt + 1-0** | Use item (slots 1-10) |

#### Shops & Menus

| Key | Function |
|-----|----------|
| **S** | Open spell shop (when standing on one) |
| **K** | Open upgrades/skills shop |
| **I** or **.** | Interact with tile (enter shops, shrines, etc.) |
| **C** | Character sheet — spells, skills, equipment |
| **V** | Look mode — explore the level with a cursor |
| **M** | Message log |
| **R** | Reroll rifts (one earned per cleared level) |

### Mod Controls

These are added by the mod.

#### Scans

| Key | Function |
|-----|----------|
| **E** | Enemy scan — count, nearest with distance, direction, line of sight |
| **Q** | Landmark scan — rifts, shops, shrines, orbs, pickups, equipment |
| **B** | Spatial raycast — walkable distance in all 8 directions |
| **X** | Hazard scan — clouds, storms, webs |
| **T** | Threat check — melee threat level |
| **D** | Unit detail — full abilities, passives, traits for examined unit |

#### Status

| Key | Function |
|-----|----------|
| **F** | Vitals — HP, shields, SP, status effects |
| **G** | Charges — selected spell, or all spells if none selected |

#### Speech

| Key | Function |
|-----|----------|
| **Left Ctrl** | Cancel speech |
| **Z** | Repeat last |
| **[** | History back |
| **]** | History forward |

#### Deploy Mode

| Key | Function |
|-----|----------|
| **1** | Quadrant overview |
| **2** | Cycle Memory Orbs |
| **3** | Cycle Pickups |
| **4** | Cycle Spawners |
| **5** | Cycle Shops, Shrines, Circles |

#### Shop

| Key | Function |
|-----|----------|
| **Tab** | Filter guide — active filters and available keys |

Filters are voiced when toggled.

## Credits

Rift Wizard 2 is developed by Dylan White. This mod is an independent accessibility project, not affiliated with or endorsed by the game's developer.

NVDA (NonVisual Desktop Access) is a free, open-source screen reader for Windows by NV Access.
