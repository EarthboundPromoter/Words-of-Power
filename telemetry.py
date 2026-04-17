"""
Telemetry: compact JSONL capture of the player-subjective layer.

Gated by a sentinel file `telemetry_enabled` in the mod dir. If absent,
all public calls are fast no-ops and no files are created. Not shipped
to players — used only for post-run analysis by the mod author + Claude.

Data layout (under mod_dir/telemetry/):
    current.txt                       — absolute path to active run dir
    run_YYYYMMDD_HHMMSS/
        run.jsonl                     — header events (mod ver, run_number, start)
        realm_NN.jsonl                — one file per realm; rotates on level_enter

Events are JSONL, one per line. Compact keys:
    ev   event type     ts  epoch seconds (int)
    t    turn number    p   [x, y] player pos (when known)
    r    realm/level_num (redundant with file, kept for grep)

The `capture(prose)` classifier inspects messages already produced by the
existing log() function and emits structured twins for known tagged events
(Select/Target Tile/Cancel/Cast/Hotkey/CharSheet/Tooltip/Shop/etc). This
avoids touching dozens of call sites — the prose log is the source of truth,
telemetry is a parallel structured view of the same stream.

Explicit emit() calls fill gaps the prose log doesn't cover: hotkey press
events, turn-end vitals snapshots, and level-enter headers with run_number
cross-reference to the game's own saves/<run>/ artifacts.
"""

import datetime
import json
import os
import re
import time

_mod_dir = os.path.dirname(os.path.abspath(__file__))
_sentinel_path = os.path.join(_mod_dir, "telemetry_enabled")
ENABLED = os.path.exists(_sentinel_path)

_state = {
    "run_dir": None,
    "realm_file": None,       # open file handle for current realm jsonl (subjective layer)
    "combat_file": None,      # open file handle for current realm combat jsonl (heavy)
    "realm_num": None,
    "run_number": None,
    "turn": 0,
    "player_pos": None,       # (x, y) or None
}

# Events routed to the combat file — heavy data not needed for default analysis.
# scan_run reads the subjective file by default; combat file is opt-in via --combat.
_COMBAT_EVENTS = {
    "damage_out", "damage_in", "combat", "combat_minion", "combat_world",
    "damage_out_detail", "damage_in_detail",
    "kill", "enemy_cast", "enemy_heal", "summon_cast", "spawn", "shield",
    "hp",
}


def _write(event: dict) -> None:
    """Append one JSON line to the active realm file.

    Combat-family events (damage, kills, enemy casts, spawns, etc.) are routed
    to the parallel combat file so the subjective-layer file stays compact.
    """
    ev = event.get("ev", "")
    f = _state["combat_file"] if ev in _COMBAT_EVENTS else _state["realm_file"]
    if f is None:
        return
    try:
        f.write(json.dumps(event, separators=(",", ":")) + "\n")
        f.flush()
    except Exception:
        pass


def init_run(run_number, mod_version: str) -> None:
    """Open a run directory. Idempotent by run_number — resuming a saved run
    re-uses the existing dir so one game run maps to one telemetry dir across
    however many play sessions it spans.

    Appends a `session_start` event each time this is called, so resumed
    sessions are visible as separate events inside the run.jsonl.
    """
    if not ENABLED:
        return
    try:
        telem_root = os.path.join(_mod_dir, "telemetry")
        os.makedirs(telem_root, exist_ok=True)

        # Try to find an existing run dir for this run_number (resume case).
        existing = None
        if run_number is not None:
            for d in os.listdir(telem_root):
                if not d.startswith("run_"):
                    continue
                run_path = os.path.join(telem_root, d, "run.jsonl")
                if not os.path.exists(run_path):
                    continue
                try:
                    with open(run_path, encoding="utf-8") as f:
                        first = f.readline().strip()
                    if first and json.loads(first).get("run_number") == run_number:
                        existing = os.path.join(telem_root, d)
                        break
                except Exception:
                    continue

        if existing:
            run_dir = existing
            is_resume = True
        else:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            run_dir = os.path.join(telem_root, f"run_{ts}")
            os.makedirs(run_dir, exist_ok=True)
            is_resume = False

        _state["run_dir"] = run_dir
        _state["run_number"] = run_number

        run_jsonl = os.path.join(run_dir, "run.jsonl")
        mode = "a" if is_resume else "w"
        with open(run_jsonl, mode, encoding="utf-8") as f:
            if not is_resume:
                header = {
                    "ev": "run_start",
                    "ts": round(time.time(), 3),
                    "run_number": run_number,
                    "mod_version": mod_version,
                    "saves_dir": os.path.join("saves", str(run_number)) if run_number is not None else None,
                }
                f.write(json.dumps(header, separators=(",", ":")) + "\n")
            session_ev = {
                "ev": "session_resume" if is_resume else "session_start",
                "ts": round(time.time(), 3),
                "run_number": run_number,
                "mod_version": mod_version,
            }
            f.write(json.dumps(session_ev, separators=(",", ":")) + "\n")

        with open(os.path.join(telem_root, "current.txt"), "w", encoding="utf-8") as f:
            f.write(run_dir)
    except Exception:
        pass


def set_realm(realm_num) -> None:
    """Rotate to a new realm pair (subjective + combat). Called on level_enter."""
    if not ENABLED or _state["run_dir"] is None:
        return
    try:
        for key in ("realm_file", "combat_file"):
            if _state[key] is not None:
                try:
                    _state[key].close()
                except Exception:
                    pass
        subj_path = os.path.join(_state["run_dir"], f"realm_{int(realm_num):02d}.jsonl")
        combat_path = os.path.join(_state["run_dir"], f"realm_{int(realm_num):02d}_combat.jsonl")
        _state["realm_file"] = open(subj_path, "a", encoding="utf-8")
        _state["combat_file"] = open(combat_path, "a", encoding="utf-8")
        _state["realm_num"] = realm_num
        _state["turn"] = 0
        _state["player_pos"] = None
    except Exception:
        pass


def set_turn(turn_num) -> None:
    _state["turn"] = int(turn_num) if turn_num is not None else _state["turn"]


def set_pos(x, y) -> None:
    _state["player_pos"] = (int(x), int(y))


def emit(ev: str, **fields) -> None:
    """Emit a structured event. Fast no-op if telemetry disabled.

    Uses fractional-second timestamps (ts is a float) so sub-second
    deliberation timing is preserved. Precision is wall-clock; don't rely
    on it for anything tighter than ~50ms.
    """
    if not ENABLED:
        return
    if _state["realm_file"] is None and _state["combat_file"] is None:
        return
    row = {"ev": ev, "ts": round(time.time(), 3), "t": _state["turn"]}
    if _state["player_pos"] is not None:
        row["p"] = list(_state["player_pos"])
    if _state["realm_num"] is not None:
        row["r"] = _state["realm_num"]
    row.update(fields)
    _write(row)


# ---------------------------------------------------------------------------
# Prose classifier — parses already-tagged log messages into structured events
# ---------------------------------------------------------------------------

_POS_RE = re.compile(r"@\((\d+),(\d+)\)")
_TURN_RE = re.compile(r"\bT(\d+)\b")

# Prefix → event type. Subset focused on player-subjective layer + context.
# Combat damage/kill detail is NOT mirrored here — the game's combat_log.txt
# already has canonical form. We capture the deliberation and mindset layer.
_PREFIX_MAP = {
    "[Select]":            "select",
    "[Target Tile]":       "target_tile",
    "[Target]":            "target_cycle",
    "[Threat]":            "threat_query",
    "[Enemies]":           "enemy_scan",
    "[Landmarks]":         "landmark_scan",
    "[Allies]":            "ally_scan",
    "[Spawners]":          "spawner_scan",
    "[Space]":             "space_query",
    "[Hazards]":           "hazard_query",
    "[LoS]":               "los_query",
    "[Vitals]":            "vitals_query",
    "[Charges]":           "charges_query",
    "[Detail]":            "detail_query",
    "[Mark]":              "mark",
    "[CharSheet]":         "charsheet",
    "[Tooltip]":           "tooltip",
    "[Shop]":              "shop",
    "[Cast]":              "cast",
    "[Cast Fail]":         "cast_fail",
    "[Turn]":              "turn_signal",
    "[Level Start]":       "level_start_prose",
    "[State]":             "state",
    "[Deploy]":            "deploy",
    # Combat / damage family — mirrored so attritional analysis is possible
    # without falling back to the game's combat_log.txt for every query.
    "[Damage OUT]":        "damage_out",
    "[Damage IN]":         "damage_in",
    "[Combat]":            "combat",
    "[Collapsed minion]":  "combat_minion",
    "[Collapsed world]":   "combat_world",
    "[Death]":             "kill",
    "[Enemy Cast]":        "enemy_cast",
    "[Enemy Heal]":        "enemy_heal",
    "[Summon Cast]":       "summon_cast",
    "[Spawn]":             "spawn",
    "[Shield]":            "shield",
    "[HP]":                "hp",
    "[Item]":              "item_pickup",
    "[Reroll]":            "reroll",
    "[Look]":              "look",
    # Uses `gameover_prose` (not `gameover`) so this doesn't collide with the
    # explicit gameover emit at runtime. Backfill relies on this.
    "[Gameover]":          "gameover_prose",
}


def capture(full_message: str) -> None:
    """Classify a prose log line and emit a structured twin if recognized.

    Called from the mod's log() function. Intentionally forgiving — unknown
    prefixes are silently skipped so telemetry stays focused on known events.
    """
    if not ENABLED or _state["realm_file"] is None:
        return
    try:
        # Strip timestamp prefix "[HH:MM:SS] "
        body = full_message.split("] ", 1)[-1] if full_message.startswith("[") else full_message

        # Update turn/pos from the message itself when present — keeps state
        # fresh even if the explicit hooks missed an update.
        m = _TURN_RE.search(body)
        if m:
            _state["turn"] = int(m.group(1))
        m = _POS_RE.search(body)
        if m:
            _state["player_pos"] = (int(m.group(1)), int(m.group(2)))

        # Match tag prefix
        for prefix, ev in _PREFIX_MAP.items():
            if body.startswith(prefix):
                text = body[len(prefix):].strip()
                # Trim T## @(x,y) leader if present — redundant with t/p fields
                text = re.sub(r"^T\d+\s+@\(\d+,\d+\)\s*", "", text)
                emit(ev, msg=text)
                return
    except Exception:
        pass
