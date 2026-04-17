#!/usr/bin/env python3
"""
scan_run.py — compact summary of the active (or specified) telemetry run.

Usage:
    python scan_run.py                 # active run, latest realm
    python scan_run.py --realm 7       # active run, specific realm
    python scan_run.py --run <path>    # explicit run dir
    python scan_run.py --tail 50       # last N events instead of summary
    python scan_run.py --list          # list all runs

Designed to be read by Claude. Output is terse, stable tokens, fits easily
in a single tool-result context window. Combines:
  - telemetry JSONL (subjective: hotkeys, targeting, shop browse, dwell)
  - saves/<run>/stats.level_N.txt (objective per-realm summary)
  - cross-reference paths to screenshots + combat_log
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

MOD_DIR = os.path.dirname(os.path.abspath(__file__))
GAME_DIR = os.path.abspath(os.path.join(MOD_DIR, "..", ".."))
TELEM_DIR = os.path.join(MOD_DIR, "telemetry")


def read_current_run():
    p = os.path.join(TELEM_DIR, "current.txt")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return f.read().strip() or None


def list_runs():
    if not os.path.isdir(TELEM_DIR):
        return []
    return sorted(
        os.path.join(TELEM_DIR, d)
        for d in os.listdir(TELEM_DIR)
        if d.startswith("run_") and os.path.isdir(os.path.join(TELEM_DIR, d))
    )


def read_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def summarize_realm(run_dir, realm_num, run_number, include_combat=False):
    rf = os.path.join(run_dir, f"realm_{int(realm_num):02d}.jsonl")
    events = read_jsonl(rf)
    if include_combat:
        cf = os.path.join(run_dir, f"realm_{int(realm_num):02d}_combat.jsonl")
        combat_events = read_jsonl(cf)
        # Merge by timestamp so analysis sees a unified event stream
        events = sorted(events + combat_events, key=lambda e: e.get("ts", 0))
    if not events:
        return f"realm {realm_num}: no telemetry data\n"

    turns = max((e.get("t", 0) for e in events), default=0)
    hotkeys = Counter()
    selects = []
    cancels = 0
    commits = 0
    target_hovers = 0
    shop_events = 0
    shop_purchases = []
    charsheet_nav = 0
    tooltip_cycles = 0
    last_vitals = None
    dwell_times = []
    dwell_by_turn = {}           # turn -> seconds spent deliberating
    events_per_turn = Counter()  # turn -> event count (density proxy)
    prev_turn_ts = None
    prev_turn_num = None
    # New fields for items 1/2/3/4/10
    rerolls = 0
    cast_fails = 0
    damage_in_by_source = Counter()   # source_name -> total dmg taken
    damage_in_events = 0
    kills = 0
    look_tiles = set()                # (cx, cy) unique tiles examined in Look mode
    roster = None                     # populated from level_enter if present
    hp_low_watermark = None           # lowest HP seen across turn_ends

    for e in events:
        ev = e.get("ev")
        t = e.get("t")
        if t is not None:
            events_per_turn[t] += 1
        if ev == "hotkey":
            k = e.get("key", "?")
            mods = []
            if e.get("shift"): mods.append("S")
            if e.get("alt"): mods.append("A")
            if e.get("ctrl"): mods.append("C")
            tag = ("+".join(mods) + "+" if mods else "") + k
            hotkeys[tag] += 1
        elif ev == "select":
            msg = e.get("msg", "")
            if msg.lower().startswith("cancelled"):
                cancels += 1
            else:
                selects.append(msg)
                if not msg.lower().startswith("cancelled"):
                    commits += 1
        elif ev == "target_tile":
            target_hovers += 1
        elif ev == "cast":
            commits += 1
        elif ev == "shop" or ev == "shop_open":
            shop_events += 1
        elif ev == "shop_buy":
            shop_purchases.append((e.get("item"), e.get("cost"), e.get("sp_after")))
        elif ev == "charsheet":
            charsheet_nav += 1
        elif ev == "tooltip":
            tooltip_cycles += 1
        elif ev == "turn_end":
            last_vitals = e
            cur_ts = e.get("ts")
            cur_t = e.get("t")
            if prev_turn_ts is not None and cur_ts is not None:
                dwell = cur_ts - prev_turn_ts
                dwell_times.append(round(dwell, 1))
                if prev_turn_num is not None:
                    dwell_by_turn[prev_turn_num] = round(dwell, 1)
            prev_turn_ts = cur_ts
            prev_turn_num = cur_t
            hp = e.get("hp")
            if hp is not None:
                if hp_low_watermark is None or hp < hp_low_watermark:
                    hp_low_watermark = hp
        elif ev == "level_enter":
            roster = e.get("roster") or roster
        elif ev == "reroll":
            rerolls += 1
        elif ev == "cast_fail":
            cast_fails += 1
        elif ev == "damage_in":
            damage_in_events += 1
            # Prose format example: "Prince of Ruin, 13 Lightning" or
            # "Fire Drake hits Wizard, 10 Fire"
            msg = e.get("msg", "")
            import re as _re_dmg
            m = _re_dmg.search(r"([A-Za-z ][A-Za-z ]+?),?\s+(\d+)\s+\w+$", msg)
            if m:
                damage_in_by_source[m.group(1).strip()] += int(m.group(2))
        elif ev == "kill":
            kills += 1
        elif ev == "look":
            cx = e.get("cx")
            cy = e.get("cy")
            if cx is not None and cy is not None:
                look_tiles.add((cx, cy))

    dwell_median = sorted(dwell_times)[len(dwell_times) // 2] if dwell_times else None
    dwell_max = max(dwell_times) if dwell_times else None

    lines = [f"=== realm {realm_num} (turns: {turns}, events: {len(events)}) ==="]
    if last_vitals:
        lines.append(
            f"last vitals: HP {last_vitals.get('hp')}/{last_vitals.get('hp_max')} "
            f"SP {last_vitals.get('sp')} shields {last_vitals.get('shields')} "
            f"status {last_vitals.get('status') or []}"
        )
    dwell_s = (f"median {dwell_median}s max {dwell_max}s"
               if dwell_median is not None else "n/a")
    lines.append(
        f"deliberation: {len(selects)} selects, {cancels} cancels, "
        f"{target_hovers} target hovers, dwell {dwell_s}"
    )
    lines.append(
        f"browsing: {charsheet_nav} charsheet nav, {tooltip_cycles} tooltip cycles, "
        f"{shop_events} shop events"
    )
    if shop_purchases:
        buys = ", ".join(
            f"{it} ({c} SP -> {sp} left)" if c is not None else f"{it}"
            for (it, c, sp) in shop_purchases
        )
        lines.append(f"purchases: {buys}")
    if rerolls or cast_fails:
        bits = []
        if rerolls:
            bits.append(f"{rerolls} reroll{'s' if rerolls != 1 else ''}")
        if cast_fails:
            bits.append(f"{cast_fails} cast-fail{'s' if cast_fails != 1 else ''}")
        lines.append("friction: " + ", ".join(bits))
    if damage_in_events and damage_in_by_source:
        top_dmg = ", ".join(f"{src} {dmg}" for src, dmg in
                            damage_in_by_source.most_common(5))
        lines.append(f"damage taken ({damage_in_events} hits"
                     + (f", HP low {hp_low_watermark}" if hp_low_watermark is not None else "")
                     + f"): {top_dmg}")
    if kills:
        lines.append(f"kills: {kills}")
    if look_tiles:
        lines.append(f"look-mode coverage: {len(look_tiles)} unique tiles examined")
    if roster:
        top_enemies = sorted(roster.items(), key=lambda kv: -kv[1])[:8]
        lines.append("enemy roster: " +
                     ", ".join(f"{n}x{c}" for n, c in top_enemies))
    if hotkeys:
        top = ", ".join(f"{k} x{v}" for k, v in hotkeys.most_common(10))
        lines.append(f"hotkeys: {top}")

    # Decision density: turns ranked by dwell (time spent deliberating) and
    # by event count. Surfaces the moments of heaviest thinking.
    if dwell_by_turn:
        top_dwell = sorted(dwell_by_turn.items(), key=lambda kv: -kv[1])[:5]
        top_dwell = [(t, d) for (t, d) in top_dwell if d >= 3]  # skip trivial
        if top_dwell:
            lines.append("heaviest dwell: " +
                         ", ".join(f"T{t} ({d}s)" for t, d in top_dwell))
    if events_per_turn:
        top_density = sorted(events_per_turn.items(), key=lambda kv: -kv[1])[:5]
        lines.append("heaviest event-density turns: " +
                     ", ".join(f"T{t} ({n})" for t, n in top_density))

    # Game's own stats file
    if run_number is not None:
        stats_path = os.path.join(GAME_DIR, "saves", str(run_number),
                                  f"stats.level_{realm_num}.txt")
        if os.path.exists(stats_path):
            lines.append("--- game stats ---")
            with open(stats_path, encoding="utf-8") as f:
                lines.append(f.read().strip())

        shot = os.path.join(GAME_DIR, "saves", str(run_number),
                            f"level_{realm_num}_begin.png")
        if os.path.exists(shot):
            lines.append(f"screenshot: {shot}")

    return "\n".join(lines) + "\n"


def summarize_run(run_dir, include_combat=False):
    run_hdr = read_jsonl(os.path.join(run_dir, "run.jsonl"))
    run_number = run_hdr[0].get("run_number") if run_hdr else None
    mod_ver = run_hdr[0].get("mod_version") if run_hdr else "?"

    realms = sorted(set(
        int(f[6:8])
        for f in os.listdir(run_dir)
        if f.startswith("realm_") and f.endswith(".jsonl")
        and not f.endswith("_combat.jsonl")
    ))
    out = [f"RUN {os.path.basename(run_dir)} | run_number={run_number} | mod v{mod_ver}",
           f"realms: {realms}"]
    for r in realms:
        out.append(summarize_realm(run_dir, r, run_number, include_combat=include_combat))
    return "\n".join(out)


def tail_events(run_dir, n, include_combat=False):
    realms = sorted(
        f for f in os.listdir(run_dir)
        if f.startswith("realm_") and f.endswith(".jsonl")
        and not f.endswith("_combat.jsonl")
    )
    if not realms:
        return "no realm files"
    latest = os.path.join(run_dir, realms[-1])
    events = read_jsonl(latest)
    if include_combat:
        combat_path = latest.replace(".jsonl", "_combat.jsonl")
        events = sorted(events + read_jsonl(combat_path),
                        key=lambda e: e.get("ts", 0))
    return "\n".join(json.dumps(e, separators=(",", ":")) for e in events[-n:])


def combat_slice(run_dir, realm_num, turn_start=None, turn_end=None):
    """Return combat events for a realm, optionally filtered by turn range."""
    cf = os.path.join(run_dir, f"realm_{int(realm_num):02d}_combat.jsonl")
    events = read_jsonl(cf)
    if turn_start is not None:
        events = [e for e in events if e.get("t", 0) >= turn_start]
    if turn_end is not None:
        events = [e for e in events if e.get("t", 0) <= turn_end]
    return events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", help="Path to run dir (defaults to current)")
    ap.add_argument("--realm", type=int, help="Specific realm only")
    ap.add_argument("--tail", type=int, help="Tail last N events (latest realm)")
    ap.add_argument("--list", action="store_true", help="List all runs")
    ap.add_argument("--combat", action="store_true",
                    help="Include combat events (damage/kills/etc). Heavy on large realms.")
    ap.add_argument("--combat-slice", nargs=3, metavar=("REALM", "TSTART", "TEND"),
                    help="Return raw combat events for REALM between TSTART and TEND")
    args = ap.parse_args()

    if args.list:
        for r in list_runs():
            print(r)
        return

    run_dir = args.run or read_current_run()
    if not run_dir or not os.path.isdir(run_dir):
        print("No active run. Telemetry may be disabled (missing sentinel "
              "`telemetry_enabled` in mod dir) or no run has started yet.",
              file=sys.stderr)
        sys.exit(1)

    if args.combat_slice:
        realm, ts, te = int(args.combat_slice[0]), int(args.combat_slice[1]), int(args.combat_slice[2])
        for e in combat_slice(run_dir, realm, ts, te):
            print(json.dumps(e, separators=(",", ":")))
        return

    if args.tail:
        print(tail_events(run_dir, args.tail, include_combat=args.combat))
        return

    if args.realm is not None:
        run_hdr = read_jsonl(os.path.join(run_dir, "run.jsonl"))
        rn = run_hdr[0].get("run_number") if run_hdr else None
        print(summarize_realm(run_dir, args.realm, rn, include_combat=args.combat))
        return

    print(summarize_run(run_dir, include_combat=args.combat))


if __name__ == "__main__":
    main()
