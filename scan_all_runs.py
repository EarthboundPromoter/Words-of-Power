#!/usr/bin/env python3
"""
scan_all_runs.py — cross-run aggregation for framework validation.

Walks every run in mods/screen_reader/telemetry/ (both native `run_*` dirs
and backfilled `historical_*` dirs), extracts per-run summary rows, and
computes aggregate statistics.

Use cases:
  - "What's my median F-usage across all runs?"
  - "Do runs with higher cancel rates reach deeper realms?"
  - "Which hotkeys are never pressed?" (evidence for feature pruning)
  - "Do win runs differ from death runs in information-query patterns?"

Output modes:
  --table         (default) compact per-run table + aggregate stats
  --csv           CSV of per-run rows (pipe to a spreadsheet or duckdb)
  --hotkey-usage  distribution of hotkey usage across runs (unused ones surface)
  --outcomes      wins vs deaths: aggregate comparison
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

MOD_DIR = os.path.dirname(os.path.abspath(__file__))
TELEM_DIR = os.path.join(MOD_DIR, "telemetry")


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
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


def list_runs():
    if not os.path.isdir(TELEM_DIR):
        return []
    return sorted(
        os.path.join(TELEM_DIR, d)
        for d in os.listdir(TELEM_DIR)
        if (d.startswith("run_") or d.startswith("historical_"))
        and os.path.isdir(os.path.join(TELEM_DIR, d))
    )


def summarize_run(run_dir):
    """Extract one summary row for a single run."""
    hdr = read_jsonl(os.path.join(run_dir, "run.jsonl"))
    run_number = hdr[0].get("run_number") if hdr else None
    mod_ver = hdr[0].get("mod_version") if hdr else "?"
    kind = "native" if os.path.basename(run_dir).startswith("run_") else "historical"

    realms = sorted(
        int(f[6:8])
        for f in os.listdir(run_dir)
        if f.startswith("realm_") and f.endswith(".jsonl")
    )

    hotkeys = Counter()
    total_events = 0
    total_selects = 0
    total_cancels = 0
    total_hovers = 0
    total_charsheet = 0
    total_tooltip = 0
    total_shop_opens = 0
    total_buys = 0
    turns_total = 0
    max_realm_reached = realms[-1] if realms else 0
    outcome = None   # "victory" / "defeat" / None (in progress)
    final_realm = None
    final_turns = None

    for r in realms:
        events = read_jsonl(os.path.join(run_dir, f"realm_{r:02d}.jsonl"))
        total_events += len(events)
        turn_max = 0
        for e in events:
            ev = e.get("ev")
            t = e.get("t", 0)
            if t > turn_max:
                turn_max = t
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
                    total_cancels += 1
                else:
                    total_selects += 1
            elif ev == "target_tile":
                total_hovers += 1
            elif ev == "charsheet":
                total_charsheet += 1
            elif ev == "tooltip":
                total_tooltip += 1
            elif ev in ("shop", "shop_open"):
                total_shop_opens += 1
            elif ev == "shop_buy":
                total_buys += 1
            elif ev == "gameover":
                outcome = e.get("outcome")
                final_realm = e.get("realm")
                final_turns = e.get("total_turns")
            elif ev == "gameover_prose":
                # Backfill path — parse from prose msg like
                #   "Victory: Realm 1, 76 turns (5 chunks)"
                #   "Defeat: Realm 12, 443 turns (7 chunks)"
                msg = e.get("msg", "")
                if msg.lower().startswith("victory"):
                    outcome = "victory"
                elif msg.lower().startswith("defeat"):
                    outcome = "defeat"
                import re as _re_go
                m = _re_go.search(r"Realm\s+(\d+),\s+(\d+)\s+turns", msg)
                if m:
                    final_realm = int(m.group(1))
                    final_turns = int(m.group(2))
        turns_total += turn_max

    cancel_rate = (total_cancels / (total_selects + total_cancels)
                   if (total_selects + total_cancels) > 0 else 0.0)

    return {
        "run_dir": os.path.basename(run_dir),
        "kind": kind,
        "run_number": run_number,
        "mod_ver": mod_ver,
        "realms": len(realms),
        "max_realm": max_realm_reached,
        "turns_total": turns_total,
        "outcome": outcome,
        "final_realm": final_realm,
        "final_turns": final_turns,
        "events": total_events,
        "selects": total_selects,
        "cancels": total_cancels,
        "cancel_rate": round(cancel_rate, 2),
        "hovers": total_hovers,
        "charsheet": total_charsheet,
        "tooltip": total_tooltip,
        "shop_opens": total_shop_opens,
        "buys": total_buys,
        "hotkeys": hotkeys,
    }


def print_table(rows):
    if not rows:
        print("No runs found.")
        return
    cols = ["run_dir", "kind", "max_realm", "outcome", "turns_total",
            "selects", "cancels", "cancel_rate", "hovers", "buys", "events"]
    header = " | ".join(f"{c:>12}" for c in cols)
    print(header)
    print("-" * len(header))
    for r in rows:
        print(" | ".join(f"{str(r.get(c, ''))[:12]:>12}" for c in cols))

    # Aggregates
    print()
    print("=== AGGREGATE ===")
    outcomes = Counter(r["outcome"] or "in_progress" for r in rows)
    print(f"outcomes: {dict(outcomes)}")

    total_hotkeys = Counter()
    for r in rows:
        total_hotkeys.update(r["hotkeys"])
    print(f"\ntop hotkeys across all runs: "
          f"{', '.join(f'{k} x{v}' for k, v in total_hotkeys.most_common(15))}")

    if rows:
        def med(xs):
            xs = sorted(xs)
            return xs[len(xs) // 2] if xs else 0
        print(f"\nmedian per run:")
        print(f"  max_realm: {med([r['max_realm'] for r in rows])}")
        print(f"  turns_total: {med([r['turns_total'] for r in rows])}")
        print(f"  cancel_rate: {med([r['cancel_rate'] for r in rows])}")
        print(f"  selects: {med([r['selects'] for r in rows])}")
        print(f"  hovers: {med([r['hovers'] for r in rows])}")


def print_hotkey_usage(rows):
    """Per-run hotkey matrix. Unused keys surface as columns of zeros."""
    known_keys = ["f", "S+f", "e", "S+e", "A+e", "n", "S+n", "A+n",
                  "q", "S+q", "A+q", "y", "S+y", "A+y",
                  "g", "d", "t", "b", "x", "l", "z", "c",
                  "left ctrl", "[", "]", "tab", "return", "escape",
                  "\\", "backspace", "S+/"]
    print(f"{'run':<24} " + " ".join(f"{k:<6}" for k in known_keys))
    totals = Counter()
    for r in rows:
        row = f"{r['run_dir'][:24]:<24} "
        for k in known_keys:
            v = r["hotkeys"].get(k, 0)
            totals[k] += v
            row += f"{v:<6} "
        print(row)
    print()
    print("totals: " + " ".join(f"{k}={totals[k]}" for k in known_keys))
    unused = [k for k in known_keys if totals[k] == 0]
    if unused:
        print(f"\nNEVER PRESSED across all runs: {unused}")


def print_outcomes(rows):
    """Compare wins vs deaths aggregate."""
    wins = [r for r in rows if r["outcome"] == "victory"]
    deaths = [r for r in rows if r["outcome"] == "defeat"]
    in_prog = [r for r in rows if not r["outcome"]]

    def agg(group, label):
        if not group:
            print(f"{label}: no runs")
            return
        n = len(group)
        avg = lambda key: sum(r[key] for r in group) / n
        print(f"{label} (n={n}):")
        print(f"  avg max_realm: {avg('max_realm'):.1f}")
        print(f"  avg turns_total: {avg('turns_total'):.1f}")
        print(f"  avg cancel_rate: {avg('cancel_rate'):.2f}")
        print(f"  avg selects: {avg('selects'):.1f}")
        print(f"  avg hovers: {avg('hovers'):.1f}")
        print(f"  avg shop_opens: {avg('shop_opens'):.1f}")
        print(f"  avg buys: {avg('buys'):.1f}")

    agg(wins, "WINS")
    print()
    agg(deaths, "DEATHS")
    print()
    agg(in_prog, "IN-PROGRESS")


def print_csv(rows):
    import csv
    w = csv.writer(sys.stdout)
    if not rows:
        return
    cols = [c for c in rows[0].keys() if c != "hotkeys"]
    w.writerow(cols)
    for r in rows:
        w.writerow([r.get(c, "") for c in cols])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", action="store_true", help="Per-run table + aggregates (default)")
    ap.add_argument("--csv", action="store_true", help="CSV of per-run rows")
    ap.add_argument("--hotkey-usage", action="store_true", help="Hotkey matrix; surfaces unused keys")
    ap.add_argument("--outcomes", action="store_true", help="Wins vs deaths aggregate")
    ap.add_argument("--kind", choices=["native", "historical", "all"], default="all",
                    help="Filter cohort: native (telemetry-era), historical (backfilled), or all (default)")
    args = ap.parse_args()

    runs = list_runs()
    rows = [summarize_run(d) for d in runs]
    if args.kind != "all":
        rows = [r for r in rows if r["kind"] == args.kind]
        if not rows:
            print(f"No runs of kind={args.kind}.", file=sys.stderr)
            sys.exit(1)
        print(f"# Filtered to kind={args.kind} ({len(rows)} runs)\n")

    if args.csv:
        print_csv(rows)
    elif args.hotkey_usage:
        print_hotkey_usage(rows)
    elif args.outcomes:
        print_outcomes(rows)
    else:
        print_table(rows)


if __name__ == "__main__":
    main()
