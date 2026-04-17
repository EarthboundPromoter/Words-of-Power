#!/usr/bin/env python3
"""
backfill_old_runs.py — reconstruct telemetry JSONL from archived prose logs.

Walks `mods/screen_reader/logs/screen_reader_debug_*.log` and emits structured
JSONL under `telemetry/historical_<log_timestamp>/` by feeding each prose line
through the same classifier used at runtime.

What's recoverable:
  - select / target_tile / cast / turn_signal / shop / charsheet / tooltip
  - state transitions / threat / enemy/landmark/ally/spawner scans
  - level_enter via [Screen Reader] Level N loaded markers
  - per-line turn + position (from T## @(x,y) prefixes in prose)

What's NOT recoverable (no prose equivalent):
  - hotkey events (mod didn't log keypresses pre-telemetry)
  - turn_end vitals snapshots (only on-demand [Vitals] existed)
  - precise cursor coords on target hovers (prose described the tile, not coords)

Usage:
    python backfill_old_runs.py                # process all logs
    python backfill_old_runs.py --log FILE     # one specific log
    python backfill_old_runs.py --dry-run      # scan only, report what would be written

Output layout mirrors native runs so scan_run.py and scan_all_runs.py work
transparently:
    telemetry/historical_YYYY-MM-DD_HH-MM-SS/
        run.jsonl
        realm_NN.jsonl
"""

import argparse
import datetime
import glob
import json
import os
import re
import sys
import time

MOD_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(MOD_DIR, "logs")
TELEM_DIR = os.path.join(MOD_DIR, "telemetry")

# Import the classifier's prefix map + regexes directly so schema stays in sync.
sys.path.insert(0, MOD_DIR)
import telemetry as _t  # noqa: E402

_LEVEL_RE = re.compile(r"\[Screen Reader\] Level (\d+) loaded")
_TIME_RE = re.compile(r"^\[(\d{2}):(\d{2}):(\d{2})\]")
_LOGNAME_RE = re.compile(r"screen_reader_debug_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.log")


def parse_timestamp(line, date_fallback):
    """Extract seconds-since-epoch from a log line. Falls back to date_fallback."""
    m = _TIME_RE.match(line)
    if not m:
        return None
    h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        dt = date_fallback.replace(hour=h, minute=mi, second=s, microsecond=0)
        return int(dt.timestamp())
    except Exception:
        return None


def classify_line(body):
    """Return (event_type, trimmed_msg) or None for unknown prefixes."""
    for prefix, ev in _t._PREFIX_MAP.items():
        if body.startswith(prefix):
            text = body[len(prefix):].strip()
            text = re.sub(r"^T\d+\s+@\(\d+,\d+\)\s*", "", text)
            return ev, text
    return None


def process_log(log_path, dry_run=False):
    """Walk one prose log, emit JSONL into a historical_<timestamp>/ dir.

    Each log is treated as one historical run. Realm boundaries come from the
    [Screen Reader] Level N loaded markers. Returns (events_written, realms_seen).
    """
    fname = os.path.basename(log_path)
    m = _LOGNAME_RE.match(fname)
    if not m:
        return 0, 0, None
    stamp = m.group(1)
    out_dir = os.path.join(TELEM_DIR, f"historical_{stamp}")
    # Anchor date for per-line timestamp reconstruction
    try:
        anchor = datetime.datetime.strptime(stamp, "%Y-%m-%d_%H-%M-%S")
    except Exception:
        anchor = datetime.datetime.now()

    if not dry_run:
        os.makedirs(out_dir, exist_ok=True)

    # State
    cur_realm = None
    cur_file = None
    cur_path = None
    cur_turn = 0
    cur_pos = None
    events_written = 0
    realms_seen = set()
    started = False

    def open_realm(realm):
        nonlocal cur_file, cur_path
        if cur_file is not None:
            cur_file.close()
        cur_path = os.path.join(out_dir, f"realm_{int(realm):02d}.jsonl")
        if not dry_run:
            cur_file = open(cur_path, "a", encoding="utf-8")
        else:
            cur_file = None

    def write(row):
        nonlocal events_written
        events_written += 1
        if cur_file is not None:
            cur_file.write(json.dumps(row, separators=(",", ":")) + "\n")

    with open(log_path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            raw = raw.rstrip("\n")
            if not raw:
                continue
            ts = parse_timestamp(raw, anchor)
            body = raw.split("] ", 1)[-1] if raw.startswith("[") else raw

            # Update turn/pos tracking (same logic as telemetry.capture)
            mt = _t._TURN_RE.search(body)
            if mt:
                cur_turn = int(mt.group(1))
            mp = _t._POS_RE.search(body)
            if mp:
                cur_pos = [int(mp.group(1)), int(mp.group(2))]

            # Realm transition marker
            ml = _LEVEL_RE.search(body)
            if ml:
                cur_realm = int(ml.group(1))
                realms_seen.add(cur_realm)
                open_realm(cur_realm)
                cur_turn = 0
                cur_pos = None
                row = {"ev": "level_enter", "ts": ts or 0, "t": 0, "r": cur_realm,
                       "source": "backfill"}
                write(row)
                continue

            # Pre-realm startup lines — write run_start once
            if not started and cur_file is None:
                started = True
                if not dry_run:
                    with open(os.path.join(out_dir, "run.jsonl"), "w", encoding="utf-8") as rf:
                        hdr = {"ev": "run_start", "ts": ts or int(time.time()),
                               "run_number": None, "mod_version": "backfill",
                               "saves_dir": None, "source": f"log/{fname}"}
                        rf.write(json.dumps(hdr, separators=(",", ":")) + "\n")

            if cur_file is None and cur_realm is None:
                # Haven't hit a realm marker yet — buffer these into realm_00
                open_realm(0)
                cur_realm = 0

            # Classify and emit
            result = classify_line(body)
            if result is None:
                continue
            ev, msg = result
            row = {"ev": ev, "ts": ts or 0, "t": cur_turn, "msg": msg,
                   "source": "backfill"}
            if cur_pos is not None:
                row["p"] = cur_pos
            if cur_realm is not None:
                row["r"] = cur_realm
            write(row)

    if cur_file is not None:
        cur_file.close()

    return events_written, len(realms_seen), out_dir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", help="Specific log file to process")
    ap.add_argument("--dry-run", action="store_true", help="Scan only")
    args = ap.parse_args()

    if args.log:
        logs = [args.log]
    else:
        logs = sorted(glob.glob(os.path.join(LOGS_DIR, "screen_reader_debug_*.log")))

    if not logs:
        print("No prose logs found.")
        return

    total_events = 0
    total_realms = 0
    for log in logs:
        events, realms, out_dir = process_log(log, dry_run=args.dry_run)
        if out_dir is None:
            continue
        total_events += events
        total_realms += realms
        tag = "[dry]" if args.dry_run else "[wrote]"
        print(f"{tag} {os.path.basename(log)}: {events} events, {realms} realms -> {os.path.basename(out_dir)}")

    print()
    print(f"Total: {total_events} events across {total_realms} realms in {len(logs)} logs")


if __name__ == "__main__":
    main()
