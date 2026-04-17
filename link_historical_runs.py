#!/usr/bin/env python3
"""
link_historical_runs.py — heuristic run_number lookup for historical telemetry.

Backfilled runs don't know their `run_number` (prose logs didn't carry it).
This script matches each `historical_YYYY-MM-DD_HH-MM-SS/` dir to a `saves/N/`
folder by comparing the log's timestamp against the saves folder's newest-file
modification time. Close matches win.

Writes the result back into each historical run's `run.jsonl` as an additional
`session_start` line with run_number populated, and also updates the top-line
run_start in place. Produces `telemetry/run_number_index.json` at the root:
    {
        "historical_2026-04-15_15-31-16": 101,
        ...
    }

Idempotent: running twice yields the same output. Safe to re-run after new
backfills.
"""

import datetime
import glob
import json
import os
import re
import sys

MOD_DIR = os.path.dirname(os.path.abspath(__file__))
GAME_DIR = os.path.abspath(os.path.join(MOD_DIR, "..", ".."))
TELEM_DIR = os.path.join(MOD_DIR, "telemetry")
SAVES_DIR = os.path.join(GAME_DIR, "saves")

_STAMP_RE = re.compile(r"historical_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})")


def saves_folder_latest_mtime(run_num):
    """Return the latest mtime of any file in saves/<run_num>/, or None."""
    path = os.path.join(SAVES_DIR, str(run_num))
    if not os.path.isdir(path):
        return None
    latest = 0.0
    for root, _, files in os.walk(path):
        for fn in files:
            try:
                m = os.path.getmtime(os.path.join(root, fn))
                if m > latest:
                    latest = m
            except OSError:
                continue
    return latest or None


def all_saves_mtimes():
    """Return {run_number: latest_mtime} for every saves/<N>/ folder."""
    if not os.path.isdir(SAVES_DIR):
        return {}
    out = {}
    for d in os.listdir(SAVES_DIR):
        if not d.isdigit():
            continue
        m = saves_folder_latest_mtime(int(d))
        if m:
            out[int(d)] = m
    return out


def match_historical_to_run(hist_dir, saves_mtimes):
    """Find the saves run_number whose latest mtime is closest to this log's
    stamp. Returns (run_number, delta_seconds) or (None, None).

    Picks the save whose mtime is >= the log-start time but within 24h.
    Fallback: whichever save is closest overall.
    """
    m = _STAMP_RE.search(os.path.basename(hist_dir))
    if not m:
        return None, None
    try:
        log_time = datetime.datetime.strptime(m.group(1), "%Y-%m-%d_%H-%M-%S").timestamp()
    except Exception:
        return None, None

    # Prefer save folders touched AFTER the log started (game wrote during play)
    # but still close. 24h window.
    candidates = [
        (rn, mt, mt - log_time)
        for rn, mt in saves_mtimes.items()
        if 0 <= (mt - log_time) <= 24 * 3600
    ]
    if candidates:
        rn, mt, delta = min(candidates, key=lambda x: x[2])
        return rn, int(delta)

    # Fallback: absolute closest
    if saves_mtimes:
        rn, mt = min(saves_mtimes.items(), key=lambda kv: abs(kv[1] - log_time))
        return rn, int(mt - log_time)

    return None, None


def update_run_jsonl(hist_dir, run_number):
    """Rewrite run.jsonl with run_number populated in the run_start line."""
    path = os.path.join(hist_dir, "run.jsonl")
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as f:
        lines = [l for l in f if l.strip()]
    if not lines:
        return False
    try:
        hdr = json.loads(lines[0])
    except Exception:
        return False
    if hdr.get("run_number") == run_number:
        return False  # No change
    hdr["run_number"] = run_number
    hdr["saves_dir"] = f"saves/{run_number}"
    lines[0] = json.dumps(hdr, separators=(",", ":")) + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return True


def main():
    if not os.path.isdir(TELEM_DIR):
        print("No telemetry directory found.", file=sys.stderr)
        sys.exit(1)

    hist_dirs = sorted(glob.glob(os.path.join(TELEM_DIR, "historical_*")))
    if not hist_dirs:
        print("No historical runs found.")
        return

    saves_mtimes = all_saves_mtimes()
    if not saves_mtimes:
        print("No saves/<N>/ folders found.", file=sys.stderr)
        sys.exit(1)

    index = {}
    for hist in hist_dirs:
        rn, delta = match_historical_to_run(hist, saves_mtimes)
        key = os.path.basename(hist)
        if rn is None:
            print(f"  [no match] {key}")
            continue
        index[key] = rn
        changed = update_run_jsonl(hist, rn)
        flag = "updated" if changed else "unchanged"
        dstr = f"+{delta}s" if delta is not None and delta >= 0 else f"{delta}s"
        print(f"  [{flag}] {key} -> saves/{rn} ({dstr})")

    # Write index
    idx_path = os.path.join(TELEM_DIR, "run_number_index.json")
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, sort_keys=True)
    print(f"\nWrote {idx_path} with {len(index)} entries.")


if __name__ == "__main__":
    main()
