# Rift Wizard 2 Screen Reader Mod — Words of Power
MOD_VERSION = "0.2.0"

import sys
import os

import datetime
import ctypes

# Get the directory where this mod file is located
mod_dir = os.path.dirname(os.path.abspath(__file__))

# Add base game directory to path (for Level, Spells, etc.)
game_dir = os.path.abspath(os.path.join(mod_dir, '../..'))
if game_dir not in sys.path:
    sys.path.append(game_dir)

# Set up logging to file — archive previous log before overwriting
log_file_path = os.path.join(mod_dir, "screen_reader_debug.log")
log_archive_dir = os.path.join(mod_dir, "logs")
os.makedirs(log_archive_dir, exist_ok=True)
if os.path.exists(log_file_path) and os.path.getsize(log_file_path) > 0:
    mtime = os.path.getmtime(log_file_path)
    stamp = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d_%H-%M-%S")
    archive_name = f"screen_reader_debug_{stamp}.log"
    try:
        os.rename(log_file_path, os.path.join(log_archive_dir, archive_name))
    except OSError:
        pass  # If rename fails (e.g. duplicate), just overwrite
log_file = open(log_file_path, 'w', encoding='utf-8')

def log(message):
    """Write to both console and log file."""
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    full_message = f"[{timestamp}] {message}"
    print(full_message)
    log_file.write(full_message + "\n")
    log_file.flush()

log("=" * 60)
log(f"Words of Power v{MOD_VERSION}")
log(f"Mod directory: {mod_dir}")
log(f"Game directory: {game_dir}")
log(f"Log file: {log_file_path}")
log("=" * 60)

# ============================================================================
# SETTINGS
# ============================================================================
import configparser as _configparser

_settings_path = os.path.join(mod_dir, "settings.ini")
_settings = _configparser.ConfigParser()

if not os.path.exists(_settings_path):
    with open(_settings_path, 'w', encoding='utf-8') as _f:
        _f.write(
            "# Words of Power settings\n"
            "# Edit this file to customize mod behavior. Restart the game after changes.\n"
            "\n"
            "[words_of_power]\n"
            "\n"
            "# Show absolute grid coordinates in scan output and movement announcements.\n"
            "# Coordinates appear after direction info: \"Wolf, 3 east (12,8)\"\n"
            "# Default: false\n"
            "show_coordinates = false\n"
        )
    log("[Settings] Created default settings.ini")
else:
    _settings.read(_settings_path, encoding='utf-8')
    log("[Settings] Loaded settings.ini")

class _Cfg:
    show_coordinates = _settings.getboolean('words_of_power', 'show_coordinates', fallback=False)

cfg = _Cfg()
log(f"[Settings] show_coordinates = {cfg.show_coordinates}")

# ============================================================================
# NVDA INTEGRATION
# ============================================================================
# DLL exports (verified via PE export table inspection):
#   nvdaController_testIfRunning  -> returns 0 if NVDA is running
#   nvdaController_speakText      -> speaks text via NVDA
#   nvdaController_cancelSpeech   -> cancels current speech
#   nvdaController_brailleMessage -> sends braille output
# ============================================================================

class NVDATTS:
    """Direct NVDA integration using ctypes."""

    def __init__(self):
        self.nvda = None
        self.enabled = False

        dll_path = os.path.join(mod_dir, "nvdaControllerClient64.dll")

        if not os.path.exists(dll_path):
            log("[NVDA] ERROR: DLL not found at: " + dll_path)
            return

        log(f"[NVDA] Found DLL: {dll_path}")

        try:
            # Initialize COM on main thread before any DLL calls
            try:
                ctypes.windll.ole32.CoInitializeEx(None, 0x2)
                log("[NVDA] COM initialized on main thread (STA)")
            except Exception as e:
                log(f"[NVDA] COM init warning: {e}")

            self.nvda = ctypes.CDLL(dll_path)
            log("[NVDA] DLL loaded successfully")

            # Configure testIfRunning function
            self.nvda.nvdaController_testIfRunning.restype = ctypes.c_long

            # Test if NVDA is running
            result = self.nvda.nvdaController_testIfRunning()
            log(f"[NVDA] testIfRunning returned: {result}")

            if result == 0:
                log("[NVDA] NVDA is running!")

                # Configure speakText function
                self.nvda.nvdaController_speakText.argtypes = [ctypes.c_wchar_p]
                self.nvda.nvdaController_speakText.restype = ctypes.c_long

                # Configure cancelSpeech function
                self.nvda.nvdaController_cancelSpeech.restype = ctypes.c_long

                self.enabled = True
                log("[NVDA] TTS engine initialized successfully!")
            else:
                log(f"[NVDA] NVDA is not running (code {result})")
                log("[NVDA] Make sure NVDA is running before starting the game")

        except Exception as e:
            log(f"[NVDA] ERROR during initialization: {e}")
            import traceback
            log(traceback.format_exc())

    def speak(self, text):
        """Speak text via NVDA."""
        if self.enabled:
            try:
                result = self.nvda.nvdaController_speakText(text)
                if result != 0:
                    log(f"[NVDA] speakText returned error: {result}")
            except Exception as e:
                log(f"[NVDA] Error speaking: {e}")
                log(f"[Fallback] {text}")
        else:
            log(f"[TTS] {text}")

    def cancel(self):
        """Cancel current NVDA speech."""
        if self.enabled:
            try:
                self.nvda.nvdaController_cancelSpeech()
            except Exception as e:
                log(f"[NVDA] Error canceling speech: {e}")

# Initialize NVDA TTS
tts = NVDATTS()
# All DLL calls go through async_tts (SyncTTS wrapper) for consistent history tracking.
log(f"Words of Power v{MOD_VERSION} initialization complete")

# ============================================================================
# PHASE 0.5: Level Lifecycle Hook
# ============================================================================

log("[Init] Level lifecycle hook...")

import Level

_original_setup_logging = Level.Level.setup_logging
log("Level lifecycle hook base captured")

# ============================================================================
# PHASE 1-2: Event Hooks - All Combat & Game Events
# ============================================================================

log("[Init] Event triggers...")

import threading
import math
import time
from collections import deque

class SyncTTS:
    """Thin TTS wrapper — all DLL calls happen directly on the calling thread.
    nvdaController_speakText is non-blocking IPC (<1ms), safe to call from
    the main thread at 30 FPS. No worker threads, no COM apartment issues.

    Rolling history buffer: last 200 speech events stored in a deque.
    [ key = step back, ] key = step forward, Z = repeat at cursor."""
    def __init__(self, base_tts):
        self.base_tts = base_tts
        self._history = deque(maxlen=200)
        self._cursor = -1  # -1 = live (latest entry)

    @property
    def _last_spoken(self):
        """Backward compat for any code reading _last_spoken."""
        return self._history[-1] if self._history else ""

    def speak(self, text):
        self._history.append(text)
        self._cursor = -1  # reset to live on new speech
        self.base_tts.speak(text)

    def cancel(self):
        self.base_tts.cancel()

    def history_back(self):
        """Step one entry older. Cancel current speech, speak that entry."""
        if not self._history:
            return
        if self._cursor == -1:
            self._cursor = len(self._history) - 2  # skip the very latest (just heard)
        else:
            self._cursor -= 1
        if self._cursor < 0:
            self._cursor = 0
            self.base_tts.cancel()
            self.base_tts.speak("Start of history")
            return
        self.base_tts.cancel()
        self.base_tts.speak(self._history[self._cursor])

    def history_forward(self):
        """Step one entry newer. Cancel current speech, speak that entry."""
        if self._cursor == -1:
            self.base_tts.cancel()
            self.base_tts.speak("End of history")
            return
        self._cursor += 1
        if self._cursor >= len(self._history):
            self._cursor = -1
            self.base_tts.cancel()
            self.base_tts.speak("End of history")
            return
        self.base_tts.cancel()
        self.base_tts.speak(self._history[self._cursor])

    def speak_batched(self, chunks):
        """Speak full text as one utterance, but add each chunk to history
        individually for [/] navigation of large text blocks."""
        for chunk in chunks:
            self._history.append(chunk)
        self._cursor = -1
        self.base_tts.speak(' '.join(chunks))

async_tts = SyncTTS(tts)
async_tts.speak(f"Words of Power version {MOD_VERSION}")
log(f"[Init] Spoke version: {MOD_VERSION}")

# ============================================================================
# SPEECH BATCHING — Priority Queue + Flush System
# ============================================================================
# During enemy turns, non-critical speech is held in a queue and delivered
# at the turn boundary (is_awaiting_input transition). Critical speech
# (player damage, death, HP) bypasses the queue and speaks immediately.
#
# Lifecycle per turn:
#   1. is_awaiting_input → True:  flush() delivers queue, then turn signal
#   2. Player acts:               start_batching() activates queue
#   3. Events fire:               speak_queued() holds, speak_immediate() bypasses
#   4. is_awaiting_input → True:  back to step 1
# ============================================================================

class SpeechBatcher:
    """Queues speech during enemy turns, flushes at turn boundary.

    Two queues:
    - _queue: QUEUED tier — (seq, text) tuples, delivered flat in order
    - _collapsed: COLLAPSED tier — event dicts with metadata, grouped by
      target unit at flush time (Phase B target-first grouping)

    Thread-safe: the charge timer (threading.Timer) calls speak_queued from
    a background thread. The lock protects all mutable state.
    All actual NVDA DLL calls happen through async_tts.speak() which is
    synchronous and non-blocking (<1ms IPC)."""

    def __init__(self, tts_backend):
        self._tts = tts_backend
        self._queue = []       # list of (seq, text) tuples — QUEUED tier
        self._collapsed = []   # list of event dicts — COLLAPSED tier
        self._seq = 0          # monotonic sequence counter
        self._lock = threading.Lock()
        self._active = False   # True when batching (enemy turn in progress)

    @property
    def is_active(self):
        """Check if batching is currently active (enemy turn in progress)."""
        return self._active

    def start_batching(self):
        """Begin batching: queued messages will be held until flush().
        Called when is_awaiting_input transitions False (player acted)."""
        with self._lock:
            self._active = True

    def speak_immediate(self, text):
        """Speak immediately, bypassing the queue. For IMMEDIATE tier."""
        self._tts.speak(text)

    def speak_queued(self, text):
        """Queue a message if batching is active, otherwise speak immediately.
        Handles events during the player's own turn (first turn, etc.) by
        falling through to immediate speech when _active is False."""
        with self._lock:
            if self._active:
                self._seq += 1
                self._queue.append((self._seq, text))
                return
        self._tts.speak(text)

    def speak_collapsed(self, event_dict):
        """Queue a structured event for collapsed-tier target grouping at flush.
        Falls through to immediate flat speech when not batching (first turn)."""
        with self._lock:
            if self._active:
                self._seq += 1
                event_dict['seq'] = self._seq
                self._collapsed.append(event_dict)
                return
        # Not batching — speak flat text immediately
        text = event_dict.get('text', '')
        if text:
            self._tts.speak(text)

    def flush(self):
        """Deliver queued + collapsed messages in priority order, then clear.
        Called at is_awaiting_input True transition, BEFORE the turn signal.

        Flush order:
        1. QUEUED messages (flat, chronological) — player spell results, kills
        2. COLLAPSED minion target groups (T2) — nearest in-LoS first
        3. COLLAPSED world target groups (T3) — nearest in-LoS first
        4. COLLAPSED summon casts — grouped by caster×spell"""
        with self._lock:
            if not self._queue and not self._collapsed:
                self._active = False
                return
            queued = sorted(self._queue, key=lambda x: x[0])
            collapsed = list(self._collapsed)
            self._queue.clear()
            self._collapsed.clear()
            self._active = False

        # Phase 1: QUEUED messages (flat, chronological)
        for seq, text in queued:
            self._tts.speak(text)

        # Phase 2: COLLAPSED events (target-grouped)
        if collapsed:
            _flush_collapsed_events(collapsed, self._tts)

        q_count = len(queued)
        c_count = len(collapsed)
        # Only log dense turns (collapsed content = multi-actor combat)
        if c_count > 0 or q_count > 3:
            log(f"[Batch] {_log_ctx()} Flushed {q_count}q + {c_count}c")

    def clear(self):
        """Discard all queued messages without speaking.
        Called on LCtrl cancel and level transitions."""
        with self._lock:
            dropped_q = len(self._queue)
            dropped_c = len(self._collapsed)
            self._queue.clear()
            self._collapsed.clear()
            self._active = False
        total = dropped_q + dropped_c
        if total:
            log(f"[Batch] Cleared {dropped_q} queued + {dropped_c} collapsed")

# ============================================================================
# COLLAPSED TIER: Target-First Grouping (Phase B)
# ============================================================================
# At flush time, collapsed events are grouped by target unit. Within each
# target group, damage entries are collapsed by (source_name, spell, dtype).
# Groups ordered by LoS (in-sight first), then proximity (nearest first).
# ============================================================================

def _flush_collapsed_events(events, tts):
    """Group and deliver collapsed-tier events at turn boundary.

    Ordering:
    1. Minion target groups (T2): in-LoS nearest first, then out-of-LoS
    2. World target groups (T3): in-LoS nearest first, then out-of-LoS
    3. Summon casts: grouped by (caster_type, spell)
    """
    try:
        # Separate by tier
        minion_events = []
        world_events = []
        summon_casts = []

        for evt in events:
            tier = evt.get('tier', TIER_WORLD)
            if tier == TIER_SUMMON:
                summon_casts.append(evt)
            elif tier == TIER_MINION:
                minion_events.append(evt)
            else:
                world_events.append(evt)

        # T2: Minion target groups
        if minion_events:
            groups = _build_target_groups(minion_events)
            _deliver_target_groups(groups, tts, "minion")

        # T3: World target groups
        if world_events:
            groups = _build_target_groups(world_events)
            _deliver_target_groups(groups, tts, "world")

        # Summon casts (no target — grouped by caster×spell)
        if summon_casts:
            _deliver_summon_casts(summon_casts, tts)
    except Exception as e:
        log(f"[Collapsed] Error in flush: {e}")
        # Fallback: deliver as flat text
        for evt in events:
            text = evt.get('text', '')
            if text:
                tts.speak(text)

def _build_target_groups(events):
    """Group events by target unit into target groups.
    Returns list of group dicts sorted by LoS (in-sight first) then distance."""
    groups = {}  # id(target_unit) -> group dict

    for evt in events:
        target = evt.get('target_unit')
        if target is None:
            continue  # Skip events with no target (shouldn't happen here)
        target_id = id(target)

        if target_id not in groups:
            groups[target_id] = {
                'target_name': evt.get('target_name', 'unknown'),
                'target_unit': target,
                'direction': evt.get('direction', ''),
                'cardinal': evt.get('cardinal', ''),
                'distance': evt.get('distance', 0),
                'los': evt.get('los', True),
                'events': [],
            }
        groups[target_id]['events'].append(evt)

    # Sort: in-LoS first (False < True, so not-los=True sorts after),
    # then by distance ascending (nearest first)
    return sorted(groups.values(), key=lambda g: (not g['los'], g['distance']))

def _deliver_target_groups(groups, tts, tier_label):
    """Format and deliver target groups with LoS split."""
    for group in groups:
        text = _format_target_group(group)
        if not group['los']:
            cardinal = group.get('cardinal', '')
            prefix = f"Out of sight, {cardinal}" if cardinal else "Out of sight"
            text = f"{prefix}. {text}"
        log(f"[Collapsed {tier_label}] {_log_ctx()} {text}")
        tts.speak(text)

def _format_target_group(group):
    """Format a single target group into spoken text.

    Format: '[Target], [direction]. [source entries]. [Target HP/killed].'
    Out-of-LoS targets skip direction (it's in the 'Out of sight' prefix).
    """
    target_name = group['target_name']
    direction = group['direction']
    events = sorted(group['events'], key=lambda e: e.get('seq', 0))
    target_unit = group['target_unit']

    # Analyze events: group damage by (source, spell, dtype), track heals/death
    damage_groups = {}  # (source_name, spell_name, damage_type) -> {count, total}
    seen_damage_keys = []  # preserve chronological first-appearance order
    heal_total = 0
    is_dead = False
    is_expired = False

    for evt in events:
        etype = evt.get('event_type', '')
        if etype == 'damage':
            key = (evt.get('source_name', ''),
                   evt.get('spell_name', ''),
                   evt.get('damage_type', ''))
            if key not in damage_groups:
                damage_groups[key] = {'count': 0, 'total': 0}
                seen_damage_keys.append(key)
            damage_groups[key]['count'] += 1
            damage_groups[key]['total'] += evt.get('damage', 0)
        elif etype == 'heal':
            heal_total += evt.get('heal_amount', 0)
        elif etype == 'death':
            is_dead = True
            is_expired = evt.get('is_expired', False)

    # Build parts: header, source entries, footer
    parts = []

    # Header: target name + direction (in-LoS only; out-of-LoS skips direction)
    coord_tag = ""
    if cfg.show_coordinates and target_unit is not None:
        tx = getattr(target_unit, 'x', None)
        ty = getattr(target_unit, 'y', None)
        if tx is not None and ty is not None:
            coord_tag = f" ({tx},{ty})"
    if group['los'] and direction:
        parts.append(f"{target_name}, {direction}{coord_tag}")
    else:
        parts.append(f"{target_name}{coord_tag}")

    # Source entries (damage collapsed by source×spell×dtype)
    source_entries = []
    for key in seen_damage_keys:
        source, spell, dtype = key
        info = damage_groups[key]
        entry_parts = []
        # Count + source name (pluralized if >1)
        if info['count'] > 1:
            entry_parts.append(f"{info['count']} {_pluralize(source)}")
        else:
            entry_parts.append(source)
        # Spell name: skip if same as source, or generic melee (no tactical info)
        show_spell = spell and spell != source and spell != "Melee Attack"
        if show_spell:
            entry_parts.append(spell)
        # Damage total + type (drop dtype when spell name already contains it)
        if show_spell and dtype and dtype.lower() in spell.lower():
            entry_parts.append(str(info['total']))
        else:
            entry_parts.append(f"{info['total']} {dtype}")
        source_entries.append(" ".join(entry_parts))

    if heal_total > 0:
        source_entries.append(f"healed {heal_total}")

    if source_entries:
        parts.append(", ".join(source_entries))

    # Footer: HP snapshot or killed/expired (target name already in header)
    if is_dead:
        parts.append("expired" if is_expired else "killed")
    elif target_unit is not None:
        hp = getattr(target_unit, 'cur_hp', '?')
        max_hp = getattr(target_unit, 'max_hp', '?')
        if isinstance(hp, int) and hp <= 0:
            # Target was killed (death event routed elsewhere, e.g. player kill → QUEUED)
            parts.append("killed")
        else:
            parts.append(f"{hp} of {max_hp}")

    return ". ".join(parts)

def _deliver_summon_casts(casts, tts):
    """Group and deliver summon casts by (caster_name, spell_name)."""
    groups = {}  # (caster_name, spell_name) -> count
    order = []   # preserve first-appearance order
    for evt in casts:
        key = (evt.get('source_name', ''), evt.get('spell_name', ''))
        if key not in groups:
            groups[key] = 0
            order.append(key)
        groups[key] += 1

    for key in order:
        caster, spell = key
        count = groups[key]
        if count > 1:
            text = f"{count} {_pluralize(caster)} cast {spell}"
        else:
            text = f"{caster} casts {spell}"
        log(f"[Collapsed summon] {_log_ctx()} {text}")
        tts.speak(text)

batcher = SpeechBatcher(async_tts)
async_tts.speak("Screen reader mod loaded")

# Helper: get a safe name from any object
def _name(obj, fallback="something"):
    if obj is None:
        return fallback
    name = getattr(obj, 'name', fallback) or fallback
    # Invert "X Spawner" → "Spawner, X" so the priority word leads in audio
    if isinstance(name, str) and name.endswith(' Spawner'):
        name = f"Spawner, {name[:-len(' Spawner')]}"
    return name

# Helper: identify if a unit is the player
def _is_player(unit):
    return getattr(unit, 'is_player_controlled', False)

# Helper: detect Soulbound buff on a unit (lich soul jar mechanic)
def _has_soulbound(unit):
    for b in getattr(unit, 'buffs', []):
        if type(b).__name__ == 'Soulbound':
            return b
    return None

# Helper: get source name (source can be Spell or Buff, both have .name and .owner)
def _source_name(source):
    if source is None:
        return "unknown"
    owner = getattr(source, 'owner', None)
    if owner is not None:
        return _name(owner)
    return _name(source)

def are_adjacent(a, b):
    """Chebyshev adjacency check (distance <= 1). Accounts for unit.radius (large units)."""
    r = getattr(a, 'radius', 0) + getattr(b, 'radius', 0)
    return Level.distance(Level.Point(a.x, a.y), Level.Point(b.x, b.y), diag=True) <= 1 + r

def _cardinal_direction(dx, dy):
    """Convert dx, dy offset to cardinal direction string. Screen coords: y+ = south."""
    if dx == 0 and dy == 0:
        return ""
    angle = math.atan2(-dy, dx)
    degrees = math.degrees(angle) % 360
    directions = ["east", "northeast", "north", "northwest", "west", "southwest", "south", "southeast"]
    index = round(degrees / 45) % 8
    return directions[index]

# ---- Pathfinding Via Hints ----
# Maps atan2-based index (E=0,NE=1,N=2,...) to clockwise-from-north (N=0,NE=1,E=2,...)
_ATAN_TO_CW = [2, 1, 0, 7, 6, 5, 4, 3]

def _bearing_index(dx, dy):
    """Convert (dx, dy) to 8-way compass index (0=N, 1=NE, 2=E, ... 7=NW).
    Returns None if dx == dy == 0."""
    if dx == 0 and dy == 0:
        return None
    angle = math.atan2(-dy, dx)
    degrees = math.degrees(angle) % 360
    return _ATAN_TO_CW[round(degrees / 45) % 8]

_VIA_HINT_CAP = 3  # Max blocked entries per scan that get pathfinding computation

# ---- Level-Load Coverage Audit ----
# Scans every tile on level load, logs objects the mod doesn't currently handle.
# Zero speech output — log-only diagnostic for between-session review.
_KNOWN_PROP_TYPES = {
    'Portal', 'HealDot', 'ManaDot', 'ChargeDot', 'SpellScroll', 'HeartDot',
    'GoldDot', 'PlaceOfPower', 'NPC', 'Shop', 'EquipPickup', 'ItemPickup',
    'ShrineShop', 'ShiftingShop', 'MiniShop', 'DuplicatorShop', 'AmnesiaShop',
}

def _audit_level(level, level_num):
    """Iterate all tiles, log unhandled objects. Called once per level load."""
    try:
        clouds = []
        unknown_props = []
        water_tiles = 0
        unusual_buffs = []

        for tile in level.iter_tiles():
            # Clouds — zero current coverage
            if tile.cloud is not None:
                c = tile.cloud
                ctype = type(c).__name__
                cname = getattr(c, 'name', ctype)
                clouds.append(f"{cname}({ctype}) @({tile.x},{tile.y})")

            # Props — check against known whitelist
            if tile.prop is not None:
                ptype = type(tile.prop).__name__
                if ptype not in _KNOWN_PROP_TYPES:
                    pname = getattr(tile.prop, 'name', ptype)
                    unknown_props.append(f"{pname}({ptype}) @({tile.x},{tile.y})")

            # Water tiles — undiscussed tile state
            if getattr(tile, 'water', None) is not None:
                water_tiles += 1

        # Unit audit — check for unusual buffs/attributes on all units
        for unit in level.units:
            uname = getattr(unit, 'name', '?')
            # Soul jar mechanic
            if getattr(unit, 'soul_jar', None) is not None:
                unusual_buffs.append(f"SOUL_JAR: {uname} @({unit.x},{unit.y}) jar={unit.soul_jar}")
            # Check for buffs that might matter
            for buff in getattr(unit, 'buffs', []):
                bname = getattr(buff, 'name', type(buff).__name__)
                btype = type(buff).__name__
                # Flag buffs that create secondary objects or have unusual mechanics
                if hasattr(buff, 'spawner') or 'jar' in btype.lower() or 'jar' in bname.lower():
                    unusual_buffs.append(f"BUFF: {uname} has {bname}({btype}) @({unit.x},{unit.y})")

        # Log results
        if clouds:
            log(f"[AUDIT L{level_num}] CLOUDS ({len(clouds)}): {'; '.join(clouds)}")
        if unknown_props:
            log(f"[AUDIT L{level_num}] UNKNOWN PROPS ({len(unknown_props)}): {'; '.join(unknown_props)}")
        if water_tiles:
            log(f"[AUDIT L{level_num}] WATER TILES: {water_tiles}")
        if unusual_buffs:
            log(f"[AUDIT L{level_num}] UNUSUAL UNITS: {'; '.join(unusual_buffs)}")
        if not clouds and not unknown_props and not water_tiles and not unusual_buffs:
            log(f"[AUDIT L{level_num}] Clean — no unhandled objects")
    except Exception as e:
        log(f"[AUDIT L{level_num}] Error: {e}")

def _via_hint(level, ref_point, target_point, player):
    """Compute ', via south' style routing hint for a blocked target.
    Returns '' if path aligns with bearing, is unavailable, or any error."""
    try:
        path = level.find_path(ref_point, target_point, player, pythonize=True)
        if not path:
            return ""
        step = path[0]
        step_dx = step.x - ref_point.x
        step_dy = step.y - ref_point.y
        target_dx = target_point.x - ref_point.x
        target_dy = target_point.y - ref_point.y
        step_idx = _bearing_index(step_dx, step_dy)
        target_idx = _bearing_index(target_dx, target_dy)
        if step_idx is None or target_idx is None:
            return ""
        diff = abs(step_idx - target_idx)
        if diff > 4:
            diff = 8 - diff
        if diff <= 1:
            return ""
        via_dir = _cardinal_direction(step_dx, step_dy)
        return f", via {via_dir}" if via_dir else ""
    except Exception:
        return ""

def _direction_offset(dx, dy):
    """Exact directional offset for wayfinding. Screen coords: x+ = east, y+ = south.
    Examples: '5 south', '3 southeast', '5 south 3 east', 'here'."""
    if dx == 0 and dy == 0:
        return "here"
    adx, ady = abs(dx), abs(dy)
    ew = "east" if dx > 0 else "west" if dx < 0 else ""
    ns = "south" if dy > 0 else "north" if dy < 0 else ""
    if dx == 0:
        return f"{ady} {ns}"
    if dy == 0:
        return f"{adx} {ew}"
    if adx == ady:
        return f"{adx} {ns}{ew}"
    # Off-axis: larger component first
    if ady >= adx:
        return f"{ady} {ns} {adx} {ew}"
    return f"{adx} {ew} {ady} {ns}"

# ---- Spatial Raycast Helper ----

def _ray_length(level, x, y, dx, dy):
    """Count walkable tiles from (x,y) stepping by (dx,dy), not counting start tile."""
    length = 0
    cx, cy = x + dx, y + dy
    while 0 <= cx < level.width and 0 <= cy < level.height:
        if not level.tiles[cx][cy].can_walk:
            break
        length += 1
        cx += dx
        cy += dy
    return length

# 8 directions clockwise: label, dx, dy
_RAYCAST_DIRS = [
    ("north", 0, -1),
    ("northeast", 1, -1),
    ("east", 1, 0),
    ("southeast", 1, 1),
    ("south", 0, 1),
    ("southwest", -1, 1),
    ("west", -1, 0),
    ("northwest", -1, -1),
]

# ---- Terrain Classification ----
# Passive corridor/junction/dead-end detection from raycast data (Session 53).
# Only cardinal axes used — corridors in RW2 are overwhelmingly cardinal-aligned.

def _count_exits(level, x, y):
    """Count cardinal directions with at least 1 walkable neighbor from (x,y)."""
    count = 0
    for dx, dy in [(0, -1), (0, 1), (1, 0), (-1, 0)]:
        nx, ny = x + dx, y + dy
        if 0 <= nx < level.width and 0 <= ny < level.height and level.tiles[nx][ny].can_walk:
            count += 1
    return count

def _check_corridor_end(level, tx, ty, corridor_dx, corridor_dy):
    """Check if corridor terminal tile is a dead end, following through one bend.
    corridor_dx/dy: unit step direction from player toward this terminal tile.
    Returns True if the corridor effectively dead-ends (including via a single bend)."""
    exits = _count_exits(level, tx, ty)
    if exits == 1:
        return True  # Simple dead end
    if exits != 2:
        return False  # 3+ exits = junction, not a dead end
    # Exactly 2 exits: one back toward player, one perpendicular (a bend).
    # Follow the perpendicular direction and check if it dead-ends.
    back_dx, back_dy = -corridor_dx, -corridor_dy
    for dx, dy in [(0, -1), (0, 1), (1, 0), (-1, 0)]:
        if dx == back_dx and dy == back_dy:
            continue
        nx, ny = tx + dx, ty + dy
        if 0 <= nx < level.width and 0 <= ny < level.height and level.tiles[nx][ny].can_walk:
            ray = _ray_length(level, tx, ty, dx, dy)
            if ray < 1:
                continue
            end_x, end_y = tx + dx * ray, ty + dy * ray
            return _count_exits(level, end_x, end_y) == 1
    return False

def _classify_terrain(level, x, y):
    """Classify tile geometry from cardinal raycasts.
    Returns (class_name, axis_label) or (class_name, None).
    class_name: 'corridor', 'junction', 'dead_end', 'bend', 'open'.
    axis_label: corridor axis + dead end terminus info, None otherwise.
    Corridor dead end detection: checks terminal tiles so player knows
    before committing whether a corridor leads nowhere."""
    n = _ray_length(level, x, y, 0, -1)
    s = _ray_length(level, x, y, 0, 1)
    e = _ray_length(level, x, y, 1, 0)
    w = _ray_length(level, x, y, -1, 0)

    # Count open cardinal directions (distance >= 1)
    exits = sum(1 for d in (n, s, e, w) if d >= 1)

    # Corridor: one axis open (combined >= 2), perpendicular both blocked
    # Check terminus tiles for dead ends so player knows before entering
    if n + s >= 2 and e == 0 and w == 0:
        dead_ends = []
        if n >= 1 and _check_corridor_end(level, x, y - n, 0, -1):
            dead_ends.append('north')
        if s >= 1 and _check_corridor_end(level, x, y + s, 0, 1):
            dead_ends.append('south')
        axis = 'north-south'
        if dead_ends:
            axis += ', dead end ' + ' and '.join(dead_ends)
        return ('corridor', axis)
    if e + w >= 2 and n == 0 and s == 0:
        dead_ends = []
        if e >= 1 and _check_corridor_end(level, x + e, y, 1, 0):
            dead_ends.append('east')
        if w >= 1 and _check_corridor_end(level, x - w, y, -1, 0):
            dead_ends.append('west')
        axis = 'east-west'
        if dead_ends:
            axis += ', dead end ' + ' and '.join(dead_ends)
        return ('corridor', axis)

    # Dead end: exactly one cardinal exit
    if exits == 1:
        return ('dead_end', None)

    # Junction: 3+ cardinal exits AND at least one axis is corridor-like
    if exits >= 3:
        has_narrow_axis = (e == 0 or w == 0 or n == 0 or s == 0)
        if has_narrow_axis:
            return ('junction', None)

    # For bend vs junction vs open, count diagonal exits too.
    # Diagonal paths are real movement options the player can take.
    # Cardinal-only exits miss cases like (2,18) where N + E + NE = 3 real paths.
    diag_exits = 0
    for _, dx, dy in _RAYCAST_DIRS:
        if abs(dx) == 1 and abs(dy) == 1:  # diagonal direction
            if _ray_length(level, x, y, dx, dy) >= 1:
                diag_exits += 1
    total_exits = exits + diag_exits

    # Junction: 3+ total movement options in constrained space
    if total_exits >= 3:
        has_narrow_axis = (e == 0 or w == 0 or n == 0 or s == 0)
        if has_narrow_axis:
            return ('junction', None)

    # Bend/turn: exactly 2 total exits (L-shaped corridor turn)
    if total_exits == 2:
        return ('bend', None)

    # Open: room or unconstrained space — the default, silent
    return ('open', None)

_TERRAIN_LABELS = {
    'corridor': lambda axis: f"corridor {axis}",
    'junction': lambda axis: "junction",
    'dead_end': lambda axis: "dead end",
    'bend': lambda axis: "turn",
}

def _scan_corridor_branches(level, px, py, axis):
    """Walk a corridor axis and find perpendicular openings.
    Distinguishes alcoves (1-tile pocket, single exit back to corridor) from
    branches (corridor continues or connects to other terrain).
    Returns list of "[alcove|branch] [perp_dir] [dist] [axis_dir]" strings.
    Ordered: axis-positive direction first (north/east), nearest to furthest,
    then axis-negative (south/west), nearest to furthest."""
    results = []

    def _classify_opening(cx, cy, dx, dy, dist, axis_dir_name):
        """Classify a perpendicular opening as alcove or branch.
        cx, cy: corridor tile position. dx, dy: perpendicular step."""
        perp_name = {(1, 0): 'east', (-1, 0): 'west',
                     (0, -1): 'north', (0, 1): 'south'}[(dx, dy)]
        ray = _ray_length(level, cx, cy, dx, dy)
        if ray == 1 and _count_exits(level, cx + dx, cy + dy) == 1:
            results.append(f"alcove {perp_name} {dist} {axis_dir_name}")
        else:
            results.append(f"branch {perp_name} {dist} {axis_dir_name}")

    if axis.startswith('north-south'):
        for i in range(1, _ray_length(level, px, py, 0, -1) + 1):
            ty = py - i
            if px + 1 < level.width and level.tiles[px + 1][ty].can_walk:
                _classify_opening(px, ty, 1, 0, i, 'north')
            if px - 1 >= 0 and level.tiles[px - 1][ty].can_walk:
                _classify_opening(px, ty, -1, 0, i, 'north')
        for i in range(1, _ray_length(level, px, py, 0, 1) + 1):
            ty = py + i
            if px + 1 < level.width and level.tiles[px + 1][ty].can_walk:
                _classify_opening(px, ty, 1, 0, i, 'south')
            if px - 1 >= 0 and level.tiles[px - 1][ty].can_walk:
                _classify_opening(px, ty, -1, 0, i, 'south')
    elif axis.startswith('east-west'):
        for i in range(1, _ray_length(level, px, py, 1, 0) + 1):
            tx = px + i
            if py - 1 >= 0 and level.tiles[tx][py - 1].can_walk:
                _classify_opening(tx, py, 0, -1, i, 'east')
            if py + 1 < level.height and level.tiles[tx][py + 1].can_walk:
                _classify_opening(tx, py, 0, 1, i, 'east')
        for i in range(1, _ray_length(level, px, py, -1, 0) + 1):
            tx = px - i
            if py - 1 >= 0 and level.tiles[tx][py - 1].can_walk:
                _classify_opening(tx, py, 0, -1, i, 'west')
            if py + 1 < level.height and level.tiles[tx][py + 1].can_walk:
                _classify_opening(tx, py, 0, 1, i, 'west')
    return results

# ---- Deploy Navigation Helpers ----
# Quadrant overview + category cycling for deploy phase (Session 49, Bug #38).

_DEPLOY_CENTER = 16  # Map center for quadrant labels (33x33 grid, 0-indexed)

def _quadrant_label(x, y):
    """Fixed quadrant relative to map center. NE/SE/SW/NW."""
    c = _DEPLOY_CENTER
    if x >= c:
        return "northeast" if y < c else "southeast"
    else:
        return "northwest" if y < c else "southwest"

def _deploy_get_orbs(level):
    """Memory Orbs on level. Returns [(prop, x, y), ...]."""
    results = []
    for tile in level.iter_tiles():
        if tile.prop and type(tile.prop).__name__ == 'ManaDot':
            results.append((tile.prop, tile.x, tile.y))
    return results

def _deploy_get_pickups(level):
    """Item pickups on level (heals, charges, hearts, gold, scrolls, equipment, items).
    Excludes Memory Orbs (separate category). Returns [(prop, x, y, name), ...]."""
    results = []
    for tile in level.iter_tiles():
        prop = tile.prop
        if prop is None:
            continue
        cls = type(prop).__name__
        # Naming mirrors _classify_prop (which is scoped inside UI hooks block)
        if cls == 'SpellScroll':
            spell = getattr(prop, 'spell', None)
            name = f"Scroll: {_name(spell, 'unknown')}" if spell else "Scroll"
        elif cls == 'EquipPickup':
            item = getattr(prop, 'item', None)
            name = f"Equipment: {_name(item)}" if item else "Equipment"
        elif cls == 'ItemPickup':
            item = getattr(prop, 'item', None)
            name = f"Item: {_name(item)}" if item else "Item"
        elif cls == 'HeartDot':
            bonus = getattr(prop, 'bonus', 10)
            name = f"Ruby Heart, plus {bonus} max HP"
        elif cls == 'HealDot':
            name = "Full Heal"
        elif cls == 'ChargeDot':
            name = "Spell Recharge"
        elif cls == 'GoldDot':
            gold = getattr(prop, 'gold', 1)
            name = f"Gold, {gold}"
        else:
            continue  # Not a pickup type
        results.append((prop, tile.x, tile.y, name))
    return results

def _deploy_get_spawners(level):
    """Spawner units on level. Returns [(unit, x, y), ...]."""
    return [(u, u.x, u.y) for u in level.units
            if getattr(u, 'is_lair', False)]

def _number_deploy_dupes(items):
    """Add ordinal suffix to duplicate names in a deploy cycling list.
    Items are (entity, x, y, name) tuples. Returns new list with
    ' 1', ' 2' etc. appended to names that appear more than once."""
    from collections import Counter
    base_names = [n for _, _, _, n in items]
    counts = Counter(base_names)
    if not any(c > 1 for c in counts.values()):
        return items
    seen = {}
    result = []
    for entity, x, y, n in items:
        if counts[n] > 1:
            seen[n] = seen.get(n, 0) + 1
            result.append((entity, x, y, f"{n} {seen[n]}"))
        else:
            result.append((entity, x, y, n))
    return result

def _deploy_get_interactions(level):
    """Shops, shrines, circles, NPCs on level. Returns [(prop, x, y, name), ...]."""
    results = []
    seen_positions = set()
    for tile in level.iter_tiles():
        prop = tile.prop
        if prop is None:
            continue
        cls = type(prop).__name__
        # Naming mirrors _classify_prop (which is scoped inside UI hooks block)
        if cls == 'PlaceOfPower':
            tag = getattr(prop, 'tag', None)
            tag_name = getattr(tag, 'name', '') if tag else ''
            name = f"{tag_name} Circle" if tag_name else "Circle"
        elif cls == 'MiniShop':
            name = "Miniaturization Shrine"
        elif cls == 'DuplicatorShop':
            name = "Duplication Shrine"
        elif cls == 'AmnesiaShop':
            name = "Amnesia Shrine"
        elif cls in ('Shop', 'ShrineShop', 'ShiftingShop'):
            name = _name(prop, "Shop")
        elif cls == 'NPC':
            name = _name(prop)
        elif hasattr(prop, 'shop_type') or hasattr(prop, 'items'):
            name = _name(prop, "Shop")
        else:
            continue
        seen_positions.add((tile.x, tile.y))
        results.append((prop, tile.x, tile.y, name))
    return results

# ---- Collapsed Tier Constants & Helpers ----
# Phase B speech batching: events grouped by target unit at flush time.
TIER_MINION = 2   # Player-team minion events (damage, heals, deaths)
TIER_WORLD = 3    # Enemy/world events (damage, heals, deaths)
TIER_SUMMON = 4   # Summon casts (no target, grouped by caster×spell)

def _pluralize(name):
    """Simple English pluralization for unit names at speech speed."""
    if not name:
        return name
    if name.endswith(('s', 'x', 'z')):
        return name + 'es'
    if name.endswith('ch') or name.endswith('sh'):
        return name + 'es'
    if name.endswith('f'):
        return name[:-1] + 'ves'
    if name.endswith('fe'):
        return name[:-2] + 'ves'
    if name.endswith('y') and len(name) > 1 and name[-2] not in 'aeiouAEIOU':
        return name[:-1] + 'ies'
    return name + 's'

def _compute_event_metadata(unit):
    """Compute LoS, direction, distance from player to target unit.
    Called at event time — stores position snapshot for flush-time grouping."""
    try:
        level = unit.level
        player = level.player_unit
        if not player:
            return {'los': True, 'direction': 'nearby', 'cardinal': '',
                    'distance': 0, 'target_x': getattr(unit, 'x', 0),
                    'target_y': getattr(unit, 'y', 0)}
        tx, ty = unit.x, unit.y
        px, py = player.x, player.y
        los = level.can_see(px, py, tx, ty)
        dx, dy = tx - px, ty - py
        direction = _direction_offset(dx, dy)
        cardinal = _cardinal_direction(dx, dy)
        distance = max(abs(dx), abs(dy))
        return {'los': los, 'direction': direction, 'cardinal': cardinal,
                'distance': distance, 'target_x': tx, 'target_y': ty}
    except:
        return {'los': True, 'direction': 'nearby', 'cardinal': '',
                'distance': 0, 'target_x': 0, 'target_y': 0}

# ---- Batched HP Announcement ----
# When player takes multiple hits in one turn, only announce HP once at the end.
# Each damage event resets a short timer; HP is spoken when the timer fires.

_pending_hp_unit = None

# ---- Turn Signal ----
# Track is_awaiting_input transitions to announce turn boundaries.
# _turn_count: incremented each time is_awaiting_input goes False→True.
# _turn_announced: prevents re-firing on subsequent frames of the same turn.
# Both reset on level transition in patched_setup_logging_v2.
_turn_count = [0]
_turn_announced = [False]
_last_turn_time = [0]  # time.time() of last spoken turn announcement (debounce)
_level_complete = [False]  # Suppress post-level noise (minion heals, etc.) (#46)
_game_ref = [None]  # Stored reference to Game instance (set in process_level_input)

def _log_ctx():
    """Return compact 'T{turn} @(x,y)' context for log lines. Falls back gracefully."""
    try:
        t = _turn_count[0]
        game = _game_ref[0]
        if game and game.p1:
            return f"T{t} @({game.p1.x},{game.p1.y})"
        return f"T{t}"
    except:
        return ""

# ---- Charge Warning System ----
# Tracks which threshold breakpoints have been announced per spell this level.
# Keys: spell name (str). Values: set of threshold names already announced.
# Reset on every level transition in patched_setup_logging_v2.
_charge_announced = {}

def _get_charge_info(spell):
    """Read current and max charges from a spell. Returns (cur, max) or (None, None)."""
    max_charges = getattr(spell, 'max_charges', 0)
    if not max_charges:
        return None, None
    cur = getattr(spell, 'cur_charges', max_charges)
    try:
        stat_max = spell.get_stat('max_charges') if hasattr(spell, 'get_stat') else max_charges
    except:
        stat_max = max_charges
    return cur, stat_max

def _check_charge_threshold(spell):
    """Check if a charge threshold was just crossed after a cast.
    Returns announcement text or empty string. Fires once per threshold per spell per level."""
    try:
        cur, stat_max = _get_charge_info(spell)
        if cur is None:
            return ""
        sname = _name(spell, "")
        if not sname:
            return ""

        # Initialize tracking for this spell if needed
        if sname not in _charge_announced:
            _charge_announced[sname] = set()
        announced = _charge_announced[sname]

        # Compute thresholds
        half = stat_max // 2
        low = max(int(stat_max * 0.25), 2)

        # First cast always fires to establish the budget for this floor.
        # Pre-mark any thresholds already crossed so they don't re-fire.
        if 'first' not in announced:
            announced.add('first')
            if stat_max >= 4 and cur <= half:
                announced.add('half')
            if cur <= low:
                announced.add('low')
            if cur <= 1:
                announced.add('last')
            if cur == 0:
                announced.add('depleted')
            return f"{sname}: {cur} of {stat_max} charges"

        # Subsequent casts: check thresholds from most severe to least
        if cur == 0 and 'depleted' not in announced:
            announced.add('depleted')
            return f"{sname}: depleted"
        if cur == 1 and 'last' not in announced:
            announced.add('last')
            return f"{sname}: last charge"
        if cur <= low and cur > 0 and 'low' not in announced:
            announced.add('low')
            return f"{sname}: charges low"
        if stat_max >= 4 and cur <= half and 'half' not in announced:
            announced.add('half')
            return f"{sname}: half charges"
        return ""
    except Exception as e:
        log(f"[Charges] Error in threshold check: {e}")
        return ""

def _schedule_hp_announcement(unit):
    """Mark that HP should be announced at the next turn boundary flush.
    Multiple hits per turn just overwrite the reference — only the final
    HP value is spoken, after all enemies have acted. (#39)"""
    global _pending_hp_unit
    _pending_hp_unit = unit

def _flush_hp():
    """Compute and speak HP if a damage event flagged it. Called at turn
    boundary AFTER batcher.flush() so HP is the last thing before turn signal."""
    global _pending_hp_unit
    unit = _pending_hp_unit
    if unit is None:
        return
    _pending_hp_unit = None
    hp = getattr(unit, 'cur_hp', '?')
    max_hp = getattr(unit, 'max_hp', '?')
    prefix = ""
    if isinstance(hp, int) and isinstance(max_hp, int) and max_hp > 0:
        pct = hp / max_hp
        if pct <= 0.15:
            prefix = "Critical. "
        elif pct <= 0.30:
            prefix = "Low. "
    text = f"{prefix}HP {hp} of {max_hp}"
    log(f"[HP] {_log_ctx()} {text}")
    async_tts.speak(text)

def _cancel_hp_announcement():
    """Cancel pending HP announcement (e.g., on player death or speech cancel)."""
    global _pending_hp_unit
    _pending_hp_unit = None

def _flush_cloud_arrivals():
    """Deliver batched cloud arrival announcements at turn boundary.
    Groups by (owner, cloud_type), computes general direction from player.
    Called after batcher.flush() + _flush_hp() + adjacency heartbeat."""
    global _cloud_arrivals
    if not _cloud_arrivals:
        return
    arrivals = list(_cloud_arrivals)
    _cloud_arrivals.clear()

    # Get player position for direction
    game = _game_ref[0] if _game_ref[0] else None
    if game is None or game.p1 is None:
        return
    px, py = game.p1.x, game.p1.y

    # Group by (owner_name, cloud_type)
    groups = {}  # (owner_name, cloud_name) → [(x, y), ...]
    for cname, owner, x, y in arrivals:
        owner_name = _name(owner, "") if owner else ""
        key = (owner_name, cname)
        if key not in groups:
            groups[key] = []
        groups[key].append((x, y))

    for (owner_name, cname), positions in groups.items():
        count = len(positions)
        # General direction: average position relative to player (rounded for clean speech)
        avg_x = sum(p[0] for p in positions) / count
        avg_y = sum(p[1] for p in positions) / count
        dx = round(avg_x - px)
        dy = round(avg_y - py)
        direction = _direction_offset(dx, dy)

        cloud_label = f"{count} {cname}{'s' if count != 1 else ''}"
        if owner_name:
            text = f"{owner_name} spawns {cloud_label}, {direction}"
        else:
            text = f"{cloud_label}, {direction}"
        log(f"[Clouds] {_log_ctx()} {text}")
        async_tts.speak(text)

# ---- Event Handlers ----

_charge_announce_timer = None

def on_spell_cast(event):
    """Announce spell casts — player casts with charge tracking, enemy ability usage."""
    global _charge_announce_timer
    try:
        if not _is_player(event.caster):
            # Enemy/non-player ability usage — skip melee (covered by damage events)
            if getattr(event.spell, 'melee', False):
                return
            spell_name = _name(event.spell, "")
            caster_name = _name(event.caster, "")
            if not spell_name or not caster_name:
                return
            text = f"{caster_name} casts {spell_name}"
            # Summon casts → collapsed (grouped by caster×spell at flush)
            is_summon = spell_name.lower().startswith('summon')
            if is_summon:
                log(f"[Summon Cast] {_log_ctx()} {text}")
                batcher.speak_collapsed({
                    'tier': TIER_SUMMON,
                    'event_type': 'cast',
                    'source_name': caster_name,
                    'spell_name': spell_name,
                    'text': text,
                })
            else:
                # Non-summon enemy casts: during batching, damage events carry
                # source attribution in collapsed groups so cast is redundant.
                # When not batching (first turn), speak for awareness.
                log(f"[Enemy Cast] {_log_ctx()} {text}")
                if not batcher.is_active:
                    async_tts.speak(text)
            return
        text = f"Cast {_name(event.spell)}"
        log(f"[Cast] {_log_ctx()} {text}")
        batcher.speak_immediate(text)

        # Check charge thresholds after cast — delayed so it queues after
        # damage/death/heal events from this cast resolve first
        spell = event.spell
        charge_text = _check_charge_threshold(spell)
        if charge_text:
            if _charge_announce_timer is not None:
                _charge_announce_timer.cancel()
            def _announce_charges(ct=charge_text):
                log(f"[Charges] {_log_ctx()} {ct}")
                batcher.speak_queued(ct)
            _charge_announce_timer = threading.Timer(0.25, _announce_charges)
            _charge_announce_timer.daemon = True
            _charge_announce_timer.start()
    except Exception as e:
        log(f"[Cast] Error: {e}")

def on_damaged(event):
    """Announce all combat damage: player in/out, ally damage, and enemy-on-enemy."""
    try:
        unit = event.unit
        dmg = event.damage
        if dmg <= 0:
            return
        dtype = _name(event.damage_type, "")
        spell_name = _name(event.source, "")
        caster = _name(getattr(event.source, 'owner', None), "")

        if _is_player(unit):
            # Player takes damage — distinguish self-hit from enemy attack
            # HP announced separately after batch resolves
            source_owner = getattr(event.source, 'owner', None)
            if isinstance(event.source, Level.Buff):
                # Status effect tick (Poison, burning, etc.) — not a player action
                label = spell_name or "status effect"
            elif _is_player(source_owner):
                # Genuinely self-inflicted damage (own AoE, HP cost, etc.)
                label = f"Self-hit, {spell_name}" if spell_name else "Self-hit"
            elif caster and spell_name and caster != spell_name:
                label = f"{caster}, {spell_name}"
            else:
                label = caster or spell_name or "unknown"
            text = f"{label}: {dmg} {dtype} damage"
            log(f"[Damage IN] {_log_ctx()} {text}")
            batcher.speak_immediate(text)
            _schedule_hp_announcement(unit)
        elif _is_player(getattr(event.source, 'owner', None)):
            # Player/ally deals damage: "Icicle: Goblin, 6 Physical"
            resist_tag = ""
            resist_val = unit.resists.get(event.damage_type, 0) if hasattr(unit, 'resists') else 0
            if resist_val >= 50:
                resist_tag = " resisted"
            elif resist_val < 0:
                resist_tag = " vulnerable"
            # Soulbound hint: when hitting a lich at minimal HP that won't die
            soul_tag = ""
            if _has_soulbound(unit) and getattr(unit, 'cur_hp', 99) <= 1:
                soul_tag = ", soulbound"
            coord_tag = f" ({unit.x},{unit.y})" if cfg.show_coordinates else ""
            text = f"{spell_name}: {_name(unit)}{coord_tag}, {dmg} {dtype}{resist_tag}{soul_tag}"
            log(f"[Damage OUT] {_log_ctx()} {text}")
            batcher.speak_queued(text)
        else:
            # Non-player damage: enemy hits ally, enemy hits enemy, etc.
            # Skip buff/status ticks on non-player units (predictable, noisy)
            if isinstance(event.source, Level.Buff):
                return
            target_name = _name(unit)
            source_name = caster or spell_name or "unknown"
            if caster:
                fallback = f"{caster} hits {target_name}, {dmg} {dtype}"
            else:
                fallback = f"{target_name} hit, {dmg} {dtype}"
            log(f"[Combat] {_log_ctx()} {fallback}")
            # Route to collapsed tier for target-first grouping (Phase B)
            is_minion = getattr(unit, 'team', None) == Level.TEAM_PLAYER
            tier = TIER_MINION if is_minion else TIER_WORLD
            meta = _compute_event_metadata(unit)
            batcher.speak_collapsed({
                'tier': tier,
                'event_type': 'damage',
                'target_unit': unit,
                'target_name': target_name,
                'source_name': source_name,
                'spell_name': spell_name,
                'damage': dmg,
                'damage_type': dtype,
                'text': fallback,
                **meta,
            })
    except Exception as e:
        log(f"[Damage] Error: {e}")

def on_death(event):
    """Announce deaths."""
    try:
        unit = event.unit
        if _is_player(unit):
            _cancel_hp_announcement()
            batcher.clear()  # Don't flush stale events after death
            text = "You died"
            if event.damage_event and event.damage_event.source:
                text = f"Killed by {_source_name(event.damage_event.source)}"
            log(f"[Death] {_log_ctx()} {text}")
            batcher.speak_immediate(text)
        else:
            name = _name(unit)
            coord_tag = f" ({unit.x},{unit.y})" if cfg.show_coordinates else ""
            if event.damage_event is None:
                # No damage caused this death — duration expired (turns_to_death)
                is_expired = True
                fallback = f"{name}{coord_tag} expired"
            else:
                is_expired = False
                fallback = f"{name}{coord_tag} killed"
            log(f"[Death] {_log_ctx()} {fallback}")
            # Player-caused kills → QUEUED for salience (adjacent to damage output)
            killed_by_player = False
            if event.damage_event is not None:
                source_owner = getattr(event.damage_event.source, 'owner', None)
                if _is_player(source_owner):
                    killed_by_player = True
            if killed_by_player:
                batcher.speak_queued(fallback)
            else:
                # Route to collapsed tier — death terminates target group (Phase B)
                is_minion = getattr(unit, 'team', None) == Level.TEAM_PLAYER
                tier = TIER_MINION if is_minion else TIER_WORLD
                meta = _compute_event_metadata(unit)
                batcher.speak_collapsed({
                    'tier': tier,
                    'event_type': 'death',
                    'target_unit': unit,
                    'target_name': name,
                    'is_expired': is_expired,
                    'text': fallback,
                    **meta,
                })
    except Exception as e:
        log(f"[Death] Error: {e}")

def on_healed(event):
    """Announce healing — player and non-player units."""
    try:
        amount = -event.heal  # Healing is stored as negative
        if amount <= 0:
            return
        if _is_player(event.unit):
            source = _name(event.source, "")
            text = f"Healed {amount}"
            if source:
                text = f"Healed {amount} by {source}"
            log(f"[Heal] {_log_ctx()} {text}")
            batcher.speak_queued(text)
        else:
            # Non-player healed (enemy Satyr healing allies, etc.)
            is_minion = getattr(event.unit, 'team', None) == Level.TEAM_PLAYER
            # Suppress minion heals after level complete — zero tactical value (#46)
            if _level_complete[0] and is_minion:
                return
            healed_name = _name(event.unit)
            fallback = f"{healed_name} heals {amount}"
            log(f"[Enemy Heal] {_log_ctx()} {fallback}")
            # Route to collapsed tier for target-first grouping (Phase B)
            tier = TIER_MINION if is_minion else TIER_WORLD
            meta = _compute_event_metadata(event.unit)
            batcher.speak_collapsed({
                'tier': tier,
                'event_type': 'heal',
                'target_unit': event.unit,
                'target_name': healed_name,
                'heal_amount': amount,
                'text': fallback,
                **meta,
            })
    except Exception as e:
        log(f"[Heal] Error: {e}")

def on_buff_apply(event):
    """Announce buffs and debuffs applied to the player."""
    try:
        if not _is_player(event.unit):
            return
        buff = event.buff
        bname = _name(buff, "")
        if not bname:
            return
        # buff_type: 1=bless, 2=curse, 0=passive, 3=item
        btype = getattr(buff, 'buff_type', 0)
        turns = getattr(buff, 'turns_left', 0)

        if btype == 2:
            prefix = "Cursed"
        elif btype == 1:
            prefix = "Blessed"
        else:
            prefix = "Buff"

        text = f"{prefix}: {bname}"
        if turns and turns > 0:
            text += f", {turns} turns"
        log(f"[Buff+] {_log_ctx()} {text}")
        batcher.speak_queued(text)
    except Exception as e:
        log(f"[Buff+] Error: {e}")

def on_buff_remove(event):
    """Announce significant buff/debuff removal from the player."""
    try:
        if not _is_player(event.unit):
            return
        buff = event.buff
        bname = _name(buff, "")
        if not bname:
            return

        # Channel buff special handling (#37, #40)
        if isinstance(buff, Level.ChannelBuff):
            # buff.spell is the spell's cast method (bound method), not the spell object
            spell_method = getattr(buff, 'spell', None)
            spell_obj = getattr(spell_method, '__self__', spell_method)
            spell_name = _name(spell_obj, "spell")
            if getattr(buff, 'turns_left', 0) > 0:
                # Removed before duration expired — player broke the channel
                text = f"Channel broken: {spell_name}"
            else:
                # Duration ran out naturally
                text = f"Channel complete: {spell_name}"
            log(f"[Buff-] {_log_ctx()} {text}")
            batcher.speak_queued(text)
            return

        btype = getattr(buff, 'buff_type', 0)
        # Only announce curse removals and bless expirations
        if btype == 2:
            text = f"Curse ended: {bname}"
        elif btype == 1:
            text = f"Expired: {bname}"
        else:
            return
        log(f"[Buff-] {_log_ctx()} {text}")
        batcher.speak_queued(text)
    except Exception as e:
        log(f"[Buff-] Error: {e}")

def on_item_pickup(event):
    """Announce item pickups. For Memory Orbs, also announce new SP total."""
    try:
        item_name = _name(event.item)
        desc = (event.item.get_description() or '') if hasattr(event.item, 'get_description') else getattr(event.item, 'description', '')
        text = f"Picked up {item_name}"
        if desc and desc != "Undescribed Item":
            text += f". {desc}"
        # If it's a Memory Orb, append new SP total
        if item_name == "Memory Orb":
            player = getattr(getattr(event.item, 'level', None), 'player_unit', None)
            if player:
                text += f", {player.xp} SP"
        log(f"[Item] {_log_ctx()} {text}")
        batcher.speak_queued(text)
    except Exception as e:
        log(f"[Item] Error: {e}")

def on_level_complete(event):
    """Announce level completion and reroll grant."""
    try:
        _level_complete[0] = True
        game = _game_ref[0]
        rerolls = getattr(game, 'rift_rerolls', 0) if game else 0
        text = f"Level complete. {rerolls} reroll" if rerolls else "Level complete"
        log(f"[Level] {_log_ctx()} {text}")
        batcher.speak_immediate(text)
    except Exception as e:
        log(f"[Level] Error: {e}")

def on_shield_removed(event):
    """Announce when a unit's shield absorbs a hit (#44)."""
    try:
        unit = event.unit
        name = _name(unit)
        remaining = getattr(unit, 'shields', 0)
        if _is_player(unit):
            if remaining > 0:
                text = f"Shield lost, {remaining} remaining"
            else:
                text = "Last shield lost"
            log(f"[Shield] {_log_ctx()} {text}")
            batcher.speak_immediate(text)
        else:
            if remaining > 0:
                text = f"{name} shield broken, {remaining} remaining"
            else:
                text = f"{name} shield broken"
            log(f"[Shield] {_log_ctx()} {text}")
            batcher.speak_queued(text)
    except Exception as e:
        log(f"[Shield] Error: {e}")

# ---- Adjacency Threat Tracking (S58) ----
# Passive melee threat awareness: announces when hostile units enter/leave adjacency.
# Two layers: per-unit announcements (IMMEDIATE, causal) + turn-end heartbeat.
# Vocabulary: "contact" for entry, "leaves" for exit. "melee" avoided (game term collision).
# Config gates speech only; state tracking is unconditional.

class AdjacencyTracker:
    """Tracks hostile units adjacent to the player. Announces entries, exits, heartbeat."""
    DESCRIPTORS = [(8, "Surrounded"), (6, "Swamped"), (3, "Pressed")]

    def __init__(self, tts):
        self._tts = tts
        self._adjacent = set()  # unit references currently adjacent to player
        self.config = {
            'entries': True,      # per-unit contact announcements
            'exits': True,        # per-unit leaves announcements
            'heartbeat': True,    # turn-end count
            'descriptors': True,  # pressed/swamped/surrounded labels
        }

    def reset(self):
        """Clear state for level transition."""
        self._adjacent.clear()

    def _descriptor(self, count):
        if not self.config['descriptors']:
            return ""
        for threshold, label in self.DESCRIPTORS:
            if count >= threshold:
                return label
        return ""

    def _format_count(self, count):
        """Format count with optional descriptor. Returns 'Clear.' at 0."""
        if count == 0:
            return "Clear."
        desc = self._descriptor(count)
        if desc:
            return f"{desc}, {count} adjacent."
        return f"{count} adjacent."

    def _announce_entry(self, unit_name, count, player_initiated):
        if not self.config['entries']:
            return
        count_text = self._format_count(count)
        if player_initiated:
            text = f"You contact {unit_name}. {count_text}"
        else:
            text = f"{unit_name}, contact. {count_text}"
        log(f"[Contact] {_log_ctx()} {text}")
        self._tts.speak(text)

    def _announce_exit(self, unit_name, count, player_initiated):
        if not self.config['exits']:
            return
        count_text = self._format_count(count)
        if player_initiated:
            text = f"You leave {unit_name}. {count_text}"
        else:
            text = f"{unit_name} leaves. {count_text}"
        log(f"[Contact] {_log_ctx()} {text}")
        self._tts.speak(text)

    def on_unit_moved(self, evt):
        """EventOnMoved handler. Detects entry/exit for any unit (player or enemy)."""
        try:
            if _level_complete[0]:
                return
            game = _game_ref[0]
            if not game or not game.p1:
                return
            unit = evt.unit
            player = game.p1

            if _is_player(unit):
                self._on_player_moved(game.cur_level, player)
                return

            if not unit.is_alive():
                return
            if not Level.are_hostile(unit, player):
                return

            was_adj = unit in self._adjacent
            now_adj = are_adjacent(unit, player)

            if now_adj and not was_adj:
                self._adjacent.add(unit)
                self._announce_entry(_name(unit), len(self._adjacent), False)
            elif was_adj and not now_adj:
                self._adjacent.discard(unit)
                self._announce_exit(_name(unit), len(self._adjacent), False)
        except Exception as e:
            log(f"[Contact] on_moved error: {e}")

    def on_unit_added(self, evt):
        """EventOnUnitAdded handler. Catches summons/spawns into adjacency."""
        try:
            if _level_complete[0]:
                return
            game = _game_ref[0]
            if not game or not game.p1:
                return
            unit = evt.unit
            player = game.p1
            if not unit.is_alive() or not Level.are_hostile(unit, player):
                return
            if are_adjacent(unit, player):
                self._adjacent.add(unit)
                self._announce_entry(_name(unit), len(self._adjacent), False)
        except Exception as e:
            log(f"[Contact] on_unit_added error: {e}")

    def on_unit_death(self, evt):
        """EventOnDeath handler. Removes dead unit from adjacency set."""
        try:
            if _level_complete[0]:
                return
            unit = evt.unit
            if unit in self._adjacent:
                self._adjacent.discard(unit)
                self._announce_exit(_name(unit), len(self._adjacent), False)
        except Exception as e:
            log(f"[Contact] on_death error: {e}")

    def _on_player_moved(self, level, player):
        """Full recompute when the player moves. Announces all changes."""
        new_adj = set()
        for unit in level.units:
            if unit == player or not unit.is_alive():
                continue
            if Level.are_hostile(unit, player) and are_adjacent(unit, player):
                new_adj.add(unit)

        exits = self._adjacent - new_adj
        entries = new_adj - self._adjacent

        # Exits first (ring loosening), then entries (ring tightening)
        for unit in exits:
            self._adjacent.discard(unit)
            self._announce_exit(_name(unit), len(self._adjacent), True)

        for unit in entries:
            self._adjacent.add(unit)
            self._announce_entry(_name(unit), len(self._adjacent), True)

    def heartbeat(self):
        """Turn-end heartbeat. Recomputes adjacency set and speaks count if > 0."""
        try:
            game = _game_ref[0]
            if not game or not game.p1:
                return
            if _level_complete[0]:
                return
            level = game.cur_level
            player = game.p1

            # Recompute from scratch — catches any missed events
            current = set()
            for unit in level.units:
                if unit == player or not unit.is_alive():
                    continue
                if Level.are_hostile(unit, player) and are_adjacent(unit, player):
                    current.add(unit)
            self._adjacent = current

            count = len(self._adjacent)
            if count == 0 or not self.config['heartbeat']:
                return
            text = self._format_count(count)
            log(f"[Contact heartbeat] {_log_ctx()} {text}")
            self._tts.speak(text)
        except Exception as e:
            log(f"[Contact] heartbeat error: {e}")

adjacency_tracker = AdjacencyTracker(async_tts)

# Pickle-safe wrappers: the game pickles Game→Level→event_manager→_handlers during save.
# Module-level functions serialize by name reference. Bound methods would serialize the
# instance (AdjacencyTracker→SyncTTS→ctypes.CDLL → PicklingError). These wrappers avoid that.
def _on_moved_adjacency(evt):
    adjacency_tracker.on_unit_moved(evt)

def _on_unit_added_adjacency(evt):
    adjacency_tracker.on_unit_added(evt)

def _on_death_adjacency(evt):
    adjacency_tracker.on_unit_death(evt)

# Pickle-safe wrapper: Buff-based spawn announcement (boss minions, etc.)
def _on_unit_added_spawn(evt):
    """Announce non-spell spawns (buff-based summons like boss minion generation).
    Spell-based summons are already announced via on_spell_cast; skip those."""
    try:
        unit = evt.unit
        if _level_complete[0]:
            return
        game = _game_ref[0]
        if game is None or game.p1 is None:
            return
        # Skip player
        if unit is game.p1:
            return
        # Skip spell-based summons (already announced via on_spell_cast)
        source = getattr(unit, 'source', None)
        if source is not None and isinstance(source, Level.Spell):
            return
        # Skip Soul Jars (handled by dedicated handler)
        uname = getattr(unit, 'name', '')
        if 'Soul Jar' in uname:
            return
        # Skip allied summons (player minions) — already covered by spell cast
        if not Level.are_hostile(unit, game.p1):
            return
        # Announce hostile buff-based spawn
        dx = unit.x - game.p1.x
        dy = unit.y - game.p1.y
        offset = _direction_offset(dx, dy)
        text = f"{uname} spawned, {offset}"
        log(f"[Spawn] {_log_ctx()} {text} @({unit.x},{unit.y})")
        batcher.speak_collapsed({
            'tier': TIER_WORLD,
            'event_type': 'spawn',
            'source_name': uname,
            'spell_name': '',
            'text': text,
        })
    except Exception as e:
        log(f"[Spawn] Error: {e}")

# Pickle-safe wrapper: Soul Jar creation detection
def _on_unit_added_souljar(evt):
    """Announce when a Soul Jar unit is summoned (lich mechanic).
    IMMEDIATE tier — mission-critical new information."""
    try:
        unit = evt.unit
        uname = getattr(unit, 'name', '')
        if 'Soul Jar' not in uname:
            return
        game = _game_ref[0] if _game_ref[0] else None
        if game is None or game.p1 is None:
            return
        dx = unit.x - game.p1.x
        dy = unit.y - game.p1.y
        offset = _direction_offset(dx, dy)
        text = f"Soul Jar created, {offset}"
        log(f"[Soul Jar] {_log_ctx()} {text} @({unit.x},{unit.y})")
        batcher.speak_immediate(text)
    except Exception as e:
        log(f"[Soul Jar] Error: {e}")

# ---- Trigger Registration ----

def register_triggers(event_manager):
    """Register all event triggers on the given event manager (once only).
    Uses direct handler-in-list check to prevent duplicates.
    NOTE: EventHandler stores handlers in _handlers (defaultdict), NOT global_triggers (that's Buff)."""
    # Guard: EventHandler may not have _handlers during save-load (on_loaded path)
    if not hasattr(event_manager, '_handlers'):
        log(f"[Screen Reader] EventManager {id(event_manager)} has no _handlers yet, deferring trigger registration")
        return
    # Check the correct attribute: EventHandler._handlers[event_type][None] for global triggers
    existing = list(event_manager._handlers[Level.EventOnSpellCast][None])
    if on_spell_cast in existing:
        log(f"[Screen Reader] Triggers already present on EventManager {id(event_manager)}, skipping (had {len(existing)} SpellCast triggers)")
        return
    log(f"[Screen Reader] Registering triggers on EventManager {id(event_manager)} (had {len(existing)} SpellCast triggers)")
    event_manager.register_global_trigger(Level.EventOnSpellCast, on_spell_cast)
    event_manager.register_global_trigger(Level.EventOnDamaged, on_damaged)
    event_manager.register_global_trigger(Level.EventOnDeath, on_death)
    event_manager.register_global_trigger(Level.EventOnHealed, on_healed)
    event_manager.register_global_trigger(Level.EventOnBuffApply, on_buff_apply)
    event_manager.register_global_trigger(Level.EventOnBuffRemove, on_buff_remove)
    event_manager.register_global_trigger(Level.EventOnItemPickup, on_item_pickup)
    event_manager.register_global_trigger(Level.EventOnLevelComplete, on_level_complete)
    event_manager.register_global_trigger(Level.EventOnShieldRemoved, on_shield_removed)
    # Adjacency threat tracking (S58) — use pickle-safe wrappers, not bound methods
    event_manager.register_global_trigger(Level.EventOnMoved, _on_moved_adjacency)
    event_manager.register_global_trigger(Level.EventOnUnitAdded, _on_unit_added_adjacency)
    event_manager.register_global_trigger(Level.EventOnDeath, _on_death_adjacency)
    # Soul Jar creation detection (S59 — Bug #47)
    event_manager.register_global_trigger(Level.EventOnUnitAdded, _on_unit_added_souljar)
    # Buff-based spawn announcement (S65 — boss minions, etc.)
    event_manager.register_global_trigger(Level.EventOnUnitAdded, _on_unit_added_spawn)
    log("[Screen Reader] Triggers registered: SpellCast, Damaged, Death, Healed, BuffApply, BuffRemove, ItemPickup, LevelComplete, ShieldRemoved, Moved, UnitAdded (adjacency+souljar+spawn)")

# Update lifecycle hook to register triggers on every level transition
def patched_setup_logging_v2(self, logdir, level_num):
    """Level lifecycle hook: re-registers all triggers on each new level."""
    _original_setup_logging(self, logdir, level_num)
    player = getattr(self, 'player_unit', None)
    pos = f" @({player.x},{player.y})" if player else ""
    log(f"[Screen Reader] Level {level_num} loaded{pos} - EventManager {id(self.event_manager)}")
    register_triggers(self.event_manager)
    # Reset per-level state for new floor
    _charge_announced.clear()
    _cancel_hp_announcement()
    batcher.clear()
    _turn_count[0] = 0
    _turn_announced[0] = False
    _level_complete[0] = False
    adjacency_tracker.reset()
    _cloud_arrivals.clear()
    # Movement direction state reset (defined later, but these are module-level mutable lists)
    try:
        _last_move_dir[0] = None
        _last_blocked_dir[0] = None
        _last_terrain_class[0] = None
    except NameError:
        pass  # First load — movement hook not installed yet
    async_tts.speak(f"Level {level_num}")
    _audit_level(self, level_num)

Level.Level.setup_logging = patched_setup_logging_v2

log("Event triggers configured")

# ============================================================================
# CLOUD ARRIVAL TRACKING — Patch add_obj to intercept cloud placement
# ============================================================================
# Accumulates cloud additions during a turn. Flushed at turn boundary by
# _flush_cloud_arrivals() alongside batcher.flush(). Grouped by owner+type.
# ============================================================================

_cloud_arrivals = []

_original_add_obj = Level.Level.add_obj

def patched_add_obj(self, obj, x, y):
    _original_add_obj(self, obj, x, y)
    try:
        if isinstance(obj, Level.Cloud):
            owner = getattr(obj, 'owner', None)
            cname = getattr(obj, 'name', type(obj).__name__)
            _cloud_arrivals.append((cname, owner, x, y))
    except Exception:
        pass  # Never break game's add_obj

Level.Level.add_obj = patched_add_obj

log("Cloud arrival tracking installed")

# ============================================================================
# BUFF EXPIRATION WARNING + COOLDOWN READY NOTIFICATION
# ============================================================================
# Buff expiry: after advance_buffs(), warn on player buffs with 1 turn left.
# Cooldown ready: before pre_advance() drops cooldowns at 1, announce them.
# Both patch Level.Unit methods — filter to wizard only (not summoned allies).
# ============================================================================

_original_advance_buffs = Level.Unit.advance_buffs

def patched_advance_buffs(self):
    _original_advance_buffs(self)
    try:
        if getattr(getattr(self, 'level', None), 'player_unit', None) is not self:
            return
        seen = set()
        for buff in self.buffs:
            if getattr(buff, 'turns_left', 0) != 1:
                continue
            btype = getattr(buff, 'buff_type', 0)
            if btype not in (1, 2):
                continue
            bname = _name(buff, "")
            if not bname or bname in seen:
                continue
            seen.add(bname)
            text = f"{bname} fading" if btype == 1 else f"{bname} ending"
            log(f"[Buff Expiry] {_log_ctx()} {text}")
            batcher.speak_queued(text)
    except Exception as e:
        log(f"[Buff Expiry] Error: {e}")

Level.Unit.advance_buffs = patched_advance_buffs

_original_pre_advance = Level.Unit.pre_advance

def patched_pre_advance(self):
    ready_spells = []
    if getattr(getattr(self, 'level', None), 'player_unit', None) is self:
        ready_spells = [spell for spell, cd in self.cool_downs.items() if cd == 1]
    _original_pre_advance(self)
    try:
        for spell in ready_spells:
            text = f"{_name(spell)} ready"
            log(f"[Cooldown] {_log_ctx()} {text}")
            batcher.speak_queued(text)
    except Exception as e:
        log(f"[Cooldown] Error: {e}")

Level.Unit.pre_advance = patched_pre_advance

log("Buff expiration + cooldown ready hooks installed")

# ============================================================================
# CAST FAILURE HELPERS
# ============================================================================

def _get_cost_failure_reason(spell):
    """Determine specific reason why can_pay_costs() failed."""
    caster = getattr(spell, 'caster', None)
    if caster is None:
        return "cannot cast"
    if caster.is_stunned():
        return "stunned"
    if caster.is_silenced() and not getattr(spell, 'melee', False):
        return "silenced"
    cd = caster.cool_downs.get(spell, 0)
    if cd > 0:
        return f"on cooldown, {cd} turns"
    if getattr(spell, 'max_charges', 0) and getattr(spell, 'cur_charges', 0) <= 0:
        return "no charges"
    try:
        hp_cost = spell.get_stat('hp_cost') if hasattr(spell, 'get_stat') else 0
        if hp_cost and hp_cost >= caster.cur_hp:
            return "not enough HP"
    except:
        pass
    return "cannot cast"

def _get_cast_failure_reason(spell, x, y):
    """Determine specific reason why can_cast() failed at target (x, y)."""
    caster = getattr(spell, 'caster', None)
    if caster is None:
        return "cannot cast"
    level = caster.level
    dx = abs(caster.x - x)
    dy = abs(caster.y - y)
    if not getattr(spell, 'can_target_self', True) and dx == 0 and dy == 0:
        return "can't target self"
    if getattr(spell, 'must_target_walkable', False) and not level.can_walk(x, y):
        return "not walkable"
    if caster.is_blind() and max(dx, dy) > 1 + getattr(caster, 'radius', 0):
        return "blinded"
    melee = getattr(spell, 'melee', False)
    try:
        r = spell.get_stat('range') + (getattr(caster, 'radius', 0) if melee else 0)
    except:
        r = getattr(spell, 'range', 0)
    if melee:
        if max(dx, dy) > (1 + getattr(caster, 'radius', 0)):
            return "out of range"
    else:
        if dx * dx + dy * dy > r * r:
            return "out of range"
    u = level.get_unit_at(x, y)
    if not getattr(spell, 'can_target_empty', True) and not u:
        return "no target"
    if getattr(spell, 'must_target_empty', False) and u:
        return "tile occupied"
    try:
        if spell.get_stat('requires_los'):
            if not level.can_see(caster.x, caster.y, x, y, light_walls=getattr(spell, 'cast_on_walls', False)):
                return "no line of sight"
    except:
        pass
    return "cannot cast"

# ============================================================================
# UI HOOKS: Spell Selection Announcements
# ============================================================================
# PyGameView.choose_spell() is called by both numrow keys and spell list.
# PyGameView.abort_cur_spell() is called when deselecting (Escape/right-click).
# ============================================================================

log("[Init] UI hooks...")

# The game runs as __main__, so "import RiftWizard2" would trigger a second
# full module load. Instead, get the actual running module from sys.modules.
_main = sys.modules.get('__main__')
_PyGameView = getattr(_main, 'PyGameView', None)

if _PyGameView is None:
    # Fallback: search all loaded modules for PyGameView
    for _mod in sys.modules.values():
        _PyGameView = getattr(_mod, 'PyGameView', None)
        if _PyGameView is not None:
            break

if _PyGameView is not None:
    # Startup guard: verify all methods we patch still exist
    _expected_methods = [
        'choose_spell', 'abort_cur_spell', 'cast_cur_spell',
        'cycle_tab_targets', 'try_examine_tile',
        'shop_selection_adjust', 'shop_page_adjust',
        'open_shop', 'toggle_shop_filter', 'process_shop_input',
        'open_char_sheet', 'adjust_char_sheet_selection',
        'toggle_char_sheet_selection_type',
        'process_level_input', 'try_move', 'deploy',
    ]
    for _method_name in _expected_methods:
        if not hasattr(_PyGameView, _method_name):
            log(f"[WARNING] PyGameView.{_method_name} not found — game may have updated. Patch will be skipped.")

    _original_choose_spell = _PyGameView.choose_spell
    _original_abort_spell = _PyGameView.abort_cur_spell
    _original_cast_cur_spell = _PyGameView.cast_cur_spell

    def patched_choose_spell(self, spell):
        """Announce spell selection with range and specific failure reason."""
        # During deploy, number keys are hijacked for category cycling — suppress native spell select
        if getattr(self.game, 'deploying', False):
            return
        # LookSpell (V key) — not a real spell selection, skip combat announcement
        if type(spell).__name__ == 'LookSpell':
            _original_choose_spell(self, spell)
            async_tts.speak("Look mode")
            log("[Select] Look mode")
            return
        # Walk spell — movement/rift selection, not a combat spell (#29)
        if _name(spell).lower() == 'walk':
            _original_choose_spell(self, spell)
            async_tts.speak("Walk mode")
            log("[Select] Walk mode")
            return
        # Item spell (ALT+number) — announce as item with description
        item_obj = getattr(spell, 'item', None)
        if item_obj:
            _original_choose_spell(self, spell)
            try:
                name = _name(spell)
                qty = getattr(item_obj, 'quantity', 1)
                desc = getattr(item_obj, 'description', '')
                parts = [f"Item: {name}"]
                if qty > 1:
                    parts.append(f"{qty} remaining")
                if desc and desc != "Undescribed Item":
                    parts.append(desc)
                text = ". ".join(parts)
                async_tts.speak(text)
                log(f"[Select Item] {text}")
            except Exception as e:
                log(f"[Select Item] Error: {e}")
            return
        cost_ok = spell.can_pay_costs()
        reason = "" if cost_ok else _get_cost_failure_reason(spell)
        _original_choose_spell(self, spell)
        try:
            name = _name(spell)
            # Build range suffix
            range_text = ""
            melee = getattr(spell, 'melee', False)
            if melee:
                range_text = "Melee"
            else:
                try:
                    rng = spell.get_stat('range') if hasattr(spell, 'get_stat') else getattr(spell, 'range', 0)
                except:
                    rng = getattr(spell, 'range', 0)
                if rng:
                    range_text = f"Range {rng}"
            # AoE profile: radius + shape keyword
            aoe_text = ""
            try:
                radius = spell.get_stat('radius') if hasattr(spell, 'get_stat') else getattr(spell, 'radius', 0)
            except:
                radius = getattr(spell, 'radius', 0)
            if radius and radius > 0:
                aoe_text = f"{radius} radius"
            else:
                # Check description for beam/cone
                raw_desc = ""
                if hasattr(spell, 'get_description'):
                    try:
                        raw_desc = (spell.get_description() or "").lower()
                    except:
                        pass
                if 'beam' in raw_desc or 'line' in raw_desc:
                    aoe_text = "beam"
                elif 'cone' in raw_desc:
                    aoe_text = "cone"
            if not cost_ok:
                parts = [name]
                if range_text:
                    parts.append(range_text)
                if aoe_text:
                    parts.append(aoe_text)
                text = f"{', '.join(parts)}: {reason}"
                async_tts.speak(text)
                log(f"[Select] {text}")
            else:
                parts = [name]
                if range_text:
                    parts.append(range_text)
                if aoe_text:
                    parts.append(aoe_text)
                text = ". ".join(parts) if len(parts) > 1 else name
                async_tts.speak(text)
                log(f"[Select] {text}")
        except Exception as e:
            log(f"[Select] Error: {e}")

    def patched_abort_spell(self):
        """Announce spell deselection."""
        _original_abort_spell(self)
        # Reset AoE tracking and dedup state on spell cancel
        _aoe_announced_state[0] = False
        _last_examine_xy[0] = None
        try:
            async_tts.speak("Cancelled")
            log("[Select] Cancelled")
        except Exception as e:
            log(f"[Select] Error: {e}")

    _PyGameView.choose_spell = patched_choose_spell
    _PyGameView.abort_cur_spell = patched_abort_spell
    log("  Spell select/cancel hooks installed")

    # ---- Cast Failure Feedback ----

    def patched_cast_cur_spell(self):
        """Announce specific reason when a spell cast fails at confirmation."""
        spell = self.cur_spell
        target = self.cur_spell_target
        will_fail = False
        reason = ""
        if spell and target:
            try:
                if not spell.can_cast(target.x, target.y):
                    will_fail = True
                    reason = _get_cast_failure_reason(spell, target.x, target.y)
            except:
                pass
        _original_cast_cur_spell(self)
        if will_fail and reason:
            text = f"{_name(spell)}: {reason}"
            log(f"[Cast Fail] {_log_ctx()} {text}")
            async_tts.speak(text)

    _PyGameView.cast_cur_spell = patched_cast_cur_spell
    log("  Cast failure feedback hook installed")

    # ---- Shop Navigation Hooks ----

    # Attribute names used in spell tooltips (from RiftWizard2.py tt_attrs)
    _tt_attrs = [
        'damage', 'minion_health', 'minion_damage', 'minion_duration',
        'minion_range', 'duration', 'radius', 'num_summons', 'num_targets',
        'shields', 'shot_cooldown', 'strikechance', 'cooldown',
        'cascade_range', 'max_channel',
    ]

    def _describe_spell(spell):
        """Build a full spoken description of a spell, matching the examine panel."""
        parts = []

        # Name
        parts.append(_name(spell))

        # Tags
        tags = getattr(spell, 'tags', [])
        if tags:
            tag_names = [_name(t) for t in tags]
            parts.append(", ".join(tag_names))

        # Level
        level = getattr(spell, 'level', 0)
        if level:
            parts.append(f"Level {level}")

        # Range and AoE shape
        melee = getattr(spell, 'melee', False)
        radius = 0
        if hasattr(spell, 'get_stat'):
            try:
                radius = spell.get_stat('radius')
            except:
                radius = getattr(spell, 'radius', 0)
        else:
            radius = getattr(spell, 'radius', 0)

        # Detect AoE shape from description keywords
        raw_desc = ""
        if hasattr(spell, 'get_description'):
            raw_desc = (spell.get_description() or "").lower()
        elif hasattr(spell, 'description'):
            raw_desc = (spell.description or "").lower()

        if 'beam' in raw_desc or 'line' in raw_desc:
            shape = "beam"
        elif 'cone' in raw_desc:
            shape = "cone"
        elif 'burst' in raw_desc or (radius and radius > 0):
            shape = "burst"
        elif getattr(spell, 'range', 0) == 0:
            shape = "self"
        else:
            shape = "single target"

        if melee:
            r_text = "Melee"
        else:
            if hasattr(spell, 'get_stat'):
                try:
                    rng = spell.get_stat('range')
                except:
                    rng = getattr(spell, 'range', 0)
            else:
                rng = getattr(spell, 'range', 0)
            los = getattr(spell, 'requires_los', True)
            r_text = f"Range {rng}" if rng else ""
            if rng and not los:
                r_text += ", ignores line of sight"

        # Combine range + shape + radius into one clear line
        shape_parts = []
        if r_text:
            shape_parts.append(r_text)
        if shape == "beam":
            shape_parts.append("beam")
        elif shape == "cone":
            if radius:
                shape_parts.append(f"{radius} tile cone")
            else:
                shape_parts.append("cone")
        elif shape == "burst":
            shape_parts.append(f"{radius} tile burst" if radius else "burst")
        elif shape == "self":
            shape_parts.append("self target")
        else:
            shape_parts.append("single target")

        if shape_parts:
            parts.append(", ".join(shape_parts))

        # Quick cast
        try:
            if hasattr(spell, 'get_stat') and spell.get_stat('quick_cast'):
                parts.append("Quick cast")
        except:
            pass

        # Charges
        max_charges = getattr(spell, 'max_charges', 0)
        if max_charges:
            cur = getattr(spell, 'cur_charges', max_charges)
            try:
                stat_max = spell.get_stat('max_charges') if hasattr(spell, 'get_stat') else max_charges
            except:
                stat_max = max_charges
            parts.append(f"Charges {cur} of {stat_max}")

        # HP cost
        if hasattr(spell, 'get_stat'):
            try:
                hp_cost = spell.get_stat('hp_cost')
                if hp_cost:
                    parts.append(f"HP cost {hp_cost}")
            except:
                pass

        # Equipment/buff bonus dictionaries (tag_bonuses, global_bonuses, resists, etc.)
        # These store effects that the game renders visually but have no description string.
        def _fmt_attr(a):
            return ' '.join(w.capitalize() for w in a.replace('_', ' ').split())

        bonus_lines = []

        # Tag bonuses (percentage)
        for tag, bonuses in getattr(spell, 'tag_bonuses_pct', {}).items():
            tag_n = _name(tag)
            for attr, val in bonuses.items():
                if val:
                    bonus_lines.append(f"{tag_n} spells gain {int(val)}% {_fmt_attr(attr)}")

        # Tag bonuses (flat)
        for tag, bonuses in getattr(spell, 'tag_bonuses', {}).items():
            tag_n = _name(tag)
            for attr, val in bonuses.items():
                if val:
                    bonus_lines.append(f"{tag_n} spells gain {val} {_fmt_attr(attr)}")

        # Spell-specific bonuses (percentage)
        for spell_class, bonuses in getattr(spell, 'spell_bonuses_pct', {}).items():
            try:
                spell_n = spell_class().name
            except:
                spell_n = str(spell_class)
            for attr, val in bonuses.items():
                if val:
                    bonus_lines.append(f"{spell_n} gains {int(val)}% {_fmt_attr(attr)}")

        # Spell-specific bonuses (flat)
        for spell_class, bonuses in getattr(spell, 'spell_bonuses', {}).items():
            try:
                spell_n = spell_class().name
            except:
                spell_n = str(spell_class)
            for attr, val in bonuses.items():
                if val:
                    bonus_lines.append(f"{spell_n} gains {val} {_fmt_attr(attr)}")

        # Global bonuses (percentage)
        for attr, val in getattr(spell, 'global_bonuses_pct', {}).items():
            if val:
                if val >= 0:
                    bonus_lines.append(f"All spells gain {int(val)}% {_fmt_attr(attr)}")
                else:
                    bonus_lines.append(f"All spells lose {int(val)}% {_fmt_attr(attr)}")

        # Global bonuses (flat)
        for attr, val in getattr(spell, 'global_bonuses', {}).items():
            if val:
                if val >= 0:
                    bonus_lines.append(f"All spells gain {val} {_fmt_attr(attr)}")
                else:
                    bonus_lines.append(f"All spells lose {val} {_fmt_attr(attr)}")

        # Resists
        for tag, val in getattr(spell, 'resists', {}).items():
            if val:
                bonus_lines.append(f"{val}% {_name(tag)} resist")

        if bonus_lines:
            parts.append(". ".join(bonus_lines))

        # Description text (strip game markup like [9_dark:dark] -> "9 dark")
        import re
        desc = ""
        if hasattr(spell, 'get_description'):
            desc = spell.get_description() or ''
        elif hasattr(spell, 'description'):
            desc = spell.description or ''
        if desc:
            def _clean_tag(m):
                content = m.group(1)
                if ':' in content:
                    content = content.split(':')[0]
                return content.replace('_', ' ')
            desc = re.sub(r'\[([^\]]*)\]', _clean_tag, desc)
            parts.append(desc)

        # Attributes (damage, radius, duration, etc.)
        attrs = []
        for attr in _tt_attrs:
            val = getattr(spell, attr, None) if not hasattr(spell, 'get_stat') else None
            if hasattr(spell, 'get_stat'):
                try:
                    val = spell.get_stat(attr)
                except:
                    val = getattr(spell, attr, None)
            if val:
                attr_label = ' '.join(w.capitalize() for w in attr.replace('_', ' ').split())
                attrs.append(f"{val} {attr_label}")
        if attrs:
            parts.append("Attributes: " + ", ".join(attrs))

        # Upgrades
        upgrades = getattr(spell, 'spell_upgrades', [])
        if upgrades:
            upg_names = [f"{getattr(u, 'level', '?')}: {_name(u)}" for u in upgrades]
            parts.append("Upgrades: " + ", ".join(upg_names))

        return ". ".join(parts)

    _original_shop_sel_adjust = _PyGameView.shop_selection_adjust
    _original_shop_page_adjust = _PyGameView.shop_page_adjust
    _original_open_shop = _PyGameView.open_shop

    def _shop_item_cost(view, target):
        """Get cost info for a shop item, handling different currency types."""
        game = getattr(view, 'game', None)
        if game is None:
            return ""
        try:
            # Level shops (SHOP_TYPE_SHOP) use shop-specific currencies
            if getattr(view, 'shop_type', -1) == getattr(_main, 'SHOP_TYPE_SHOP', 3):
                shop = getattr(game.cur_level, 'cur_shop', None) if game.cur_level else None
                if shop:
                    currency = getattr(shop, 'currency', 0)
                    if currency == Level.CURRENCY_PICK:
                        return ""  # Free pick-one shops — no cost to announce
                    elif currency == Level.CURRENCY_MAX_HP:
                        item_cost = getattr(target, 'cost', 0)
                        affordable = shop.can_shop(game.p1, target)
                        suffix = "" if affordable else ", cannot afford"
                        return f"Cost {item_cost} max HP{suffix}"
                    else:
                        # CURRENCY_GOLD or unknown
                        item_cost = getattr(target, 'cost', 0)
                        affordable = shop.can_shop(game.p1, target)
                        suffix = "" if affordable else ", cannot afford"
                        return f"Cost {item_cost} gold{suffix}"
            # SP-based shops (SPELLS, UPGRADES, SPELL_UPGRADES)
            cost = game.get_upgrade_cost(target)
            affordable = game.can_buy_upgrade(target)
            owned = game.has_upgrade(target)
            if owned:
                # In Learn Spell shop, owned spells open upgrades on confirm
                if getattr(view, 'shop_type', -1) == _SHOP_TYPE_SPELLS:
                    return "Owned, enter to view upgrades"
                return "Owned"
            if not affordable and isinstance(target, Level.Upgrade) and getattr(target, 'prereq', None):
                if game.spell_is_upgraded(target.prereq):
                    return "Locked, 1 upgrade per spell"
            suffix = "" if affordable else ", cannot afford"
            return f"Cost {cost} SP{suffix}"
        except:
            return ""

    _last_shop_target = [None]

    def _describe_bestiary_entry(target):
        """Describe a bestiary monster entry, respecting slain/unslain visibility.
        Unslain monsters are hidden by the game — we match that behavior."""
        name = _name(target)
        if _SteamAdapter and not _SteamAdapter.has_slain(name):
            return "Unknown monster"
        # Slain — full Tier 2 unit description (same as D-key detail)
        return _describe_unit(target)

    def patched_shop_selection_adjust(self, inc):
        """Announce shop/bestiary item when navigating."""
        _original_shop_sel_adjust(self, inc)
        try:
            target = self._examine_target
            if target is not None and target is not _last_shop_target[0]:
                _last_shop_target[0] = target
                if getattr(self, 'shop_type', -1) == _SHOP_TYPE_BESTIARY:
                    # Bestiary: unit description, no cost
                    text = _describe_bestiary_entry(target)
                else:
                    cost = _shop_item_cost(self, target)
                    desc = _describe_spell(target)
                    text = f"{cost}. {desc}" if cost else desc
                async_tts.speak(text)
                log(f"[Shop] {text}")
        except Exception as e:
            log(f"[Shop] Error: {e}")

    def patched_shop_page_adjust(self, inc):
        """Announce page change with first item description."""
        _last_shop_target[0] = None
        _original_shop_page_adjust(self, inc)
        try:
            target = self._examine_target
            page = getattr(self, 'shop_page', 0) + 1
            if target is not None:
                if getattr(self, 'shop_type', -1) == _SHOP_TYPE_BESTIARY:
                    desc = _describe_bestiary_entry(target)
                    text = f"Page {page}. {desc}"
                else:
                    cost = _shop_item_cost(self, target)
                    desc = _describe_spell(target)
                    text = f"Page {page}. {cost}. {desc}" if cost else f"Page {page}. {desc}"
            else:
                text = f"Page {page}, empty"
            async_tts.speak(text)
            log(f"[Shop] {text}")
        except Exception as e:
            log(f"[Shop] Error: {e}")

    def patched_open_shop(self, shop_type, spell=None):
        """Announce entering shop/bestiary/upgrade screen with appropriate header."""
        _last_shop_target[0] = None
        _original_open_shop(self, shop_type, spell=spell)
        try:
            target = self._examine_target
            game = getattr(self, 'game', None)

            if shop_type == _SHOP_TYPE_BESTIARY:
                # Bestiary: slain count header + first entry
                num_slain = _SteamAdapter.get_num_slain() if _SteamAdapter else 0
                total = len(self.get_shop_options())
                header = f"Bestiary, {num_slain} of {total} slain"
                desc = _describe_bestiary_entry(target) if target else None
                text = f"{header}. {desc}" if desc else header

            elif shop_type == _SHOP_TYPE_SPELL_UPGRADES:
                # Spell upgrade picker: "Upgrade [SpellName], N SP available"
                spell_name = _name(getattr(self, 'shop_upgrade_spell', None)) if hasattr(self, 'shop_upgrade_spell') else "Spell"
                sp_total = getattr(game.p1, 'xp', 0) if game and game.p1 else 0
                header = f"Upgrade {spell_name}, {sp_total} SP available"
                if target is not None:
                    cost = _shop_item_cost(self, target)
                    desc = _describe_spell(target)
                    text = f"{header}. {cost}. {desc}" if cost else f"{header}. {desc}"
                else:
                    text = header

            elif shop_type == _SHOP_TYPE_SHOP:
                # Level shop: use the shop prop's name (Amnesia Shrine, Shoe Box, etc.)
                shop_prop = getattr(game.cur_level, 'cur_shop', None) if game and game.cur_level else None
                shop_name = getattr(shop_prop, 'name', 'Shop') if shop_prop else 'Shop'
                shop_desc = getattr(shop_prop, 'description', '') if shop_prop else ''
                header = shop_name
                if shop_desc and shop_desc.strip():
                    header += f". {shop_desc.strip()}"
                if target is not None:
                    cost = _shop_item_cost(self, target)
                    desc = _describe_spell(target)
                    text = f"{header}. {cost}. {desc}" if cost else f"{header}. {desc}"
                else:
                    text = header

            else:
                # SPELLS or UPGRADES: "Learn Spell/Skill, N SP available"
                sp_total = getattr(game.p1, 'xp', 0) if game and game.p1 else 0
                if shop_type == _SHOP_TYPE_UPGRADES:
                    label = "Learn Skill"
                else:
                    label = "Learn Spell"
                header = f"{label}, {sp_total} SP available"
                if target is not None:
                    cost = _shop_item_cost(self, target)
                    desc = _describe_spell(target)
                    text = f"{header}. {cost}. {desc}" if cost else f"{header}. {desc}"
                else:
                    text = f"{header}, empty"

            async_tts.speak(text)
            log(f"[Shop] Opened: {text}")
        except Exception as e:
            log(f"[Shop] Error: {e}")

    _original_try_buy = _PyGameView.try_buy_shop_selection
    _suppress_char_sheet_for_purchase = [False]

    def patched_try_buy_shop_selection(self, prompt=True):
        """Announce purchase result after buy attempt."""
        target = self._examine_target
        target_name = _name(target) if target else None

        # Check if this is an owned spell (will open upgrades, not buy)
        game = getattr(self, 'game', None)
        is_owned_spell = (game and target in getattr(game.p1, 'spells', []))

        if not is_owned_spell and target_name:
            _suppress_char_sheet_for_purchase[0] = True

        _original_try_buy(self, prompt)

        try:
            _suppress_char_sheet_for_purchase[0] = False
            if is_owned_spell:
                # Opened upgrades view — patched_open_shop handles announcement
                return

            # Check if purchase happened: shop type/state changed or target removed
            if target_name and self.state != getattr(_main, 'STATE_SHOP', 2):
                # Shop closed after purchase — speak purchase, then char sheet
                async_tts.speak(f"Learned {target_name}")
                log(f"[Shop] Purchased: {target_name}")
                # Speak char sheet overview after purchase (was suppressed)
                try:
                    _speak_char_sheet_overview(self)
                except Exception:
                    pass
        except Exception as e:
            _suppress_char_sheet_for_purchase[0] = False
            log(f"[Shop] Buy announce error: {e}")

    _PyGameView.shop_selection_adjust = patched_shop_selection_adjust
    _PyGameView.shop_page_adjust = patched_shop_page_adjust
    _PyGameView.open_shop = patched_open_shop
    _PyGameView.try_buy_shop_selection = patched_try_buy_shop_selection
    log("  Shop navigation hooks installed")

    # ---- Shop Filter Hooks ----

    _original_toggle_shop_filter = _PyGameView.toggle_shop_filter
    _original_process_shop_input = _PyGameView.process_shop_input

    # Grab game-side references for filter data
    _tag_keys = getattr(_main, 'tag_keys', {})
    _attr_keys = getattr(_main, 'attr_keys', {})
    _filter_attrs = getattr(_main, 'filter_attrs', [])
    _SHOP_TYPE_SPELLS = getattr(_main, 'SHOP_TYPE_SPELLS', 0)
    _SHOP_TYPE_UPGRADES = getattr(_main, 'SHOP_TYPE_UPGRADES', 1)
    _SHOP_TYPE_SPELL_UPGRADES = getattr(_main, 'SHOP_TYPE_SPELL_UPGRADES', 2)
    _SHOP_TYPE_SHOP = getattr(_main, 'SHOP_TYPE_SHOP', 3)
    _SHOP_TYPE_BESTIARY = getattr(_main, 'SHOP_TYPE_BESTIARY', 4)
    _SteamAdapter = getattr(_main, 'SteamAdapter', None)
    if _SteamAdapter is None:
        try:
            import SteamAdapter as _SteamAdapter
        except ImportError:
            _SteamAdapter = None
    # Reverse lookups: Tag -> key letter, attr string -> key letter
    _reverse_tag_keys = {v: k for k, v in _tag_keys.items()}
    _reverse_attr_keys = {v: k for k, v in _attr_keys.items()}

    def patched_toggle_shop_filter(self, tag=None, attr=None):
        """Announce filter toggle with name, on/off state, and result count."""
        _original_toggle_shop_filter(self, tag=tag, attr=attr)
        try:
            if tag:
                state = "on" if tag in self.tag_filter else "off"
                name = tag.name
            elif attr:
                state = "on" if attr in self.attr_filter else "off"
                name = Level.format_attr(attr)
            else:
                return
            count = len(self.get_shop_options())
            if count == 0:
                text = f"{name} {state}. No results."
            else:
                text = f"{name} {state}. {count} results."
            async_tts.speak(text)
            log(f"[Shop Filter] {text}")
        except Exception as e:
            log(f"[Shop Filter] Error: {e}")

    def _speak_shop_filter_guide(view):
        """Read out the full filter guide: active filters, then all keybinds."""
        try:
            parts = []
            # Active filters summary
            active_tags = list(view.tag_filter) if hasattr(view, 'tag_filter') else []
            active_attrs = list(view.attr_filter) if hasattr(view, 'attr_filter') else []
            if active_tags or active_attrs:
                active_names = [t.name for t in active_tags] + [Level.format_attr(a) for a in active_attrs]
                parts.append("Active: " + ", ".join(active_names))
            else:
                parts.append("No active filters")

            # Tag keybinds — use game's spell_tags order (only tags present in spell pool)
            game = getattr(view, 'game', None)
            spell_tags = getattr(game, 'spell_tags', []) if game else []
            tag_entries = []
            for tag in spell_tags:
                if tag == Level.Tags.Consumable:
                    continue
                key = _reverse_tag_keys.get(tag)
                if key:
                    tag_entries.append(f"{key.upper()} {tag.name}")
            if tag_entries:
                parts.append("Tags: " + ", ".join(tag_entries))

            # Attribute keybinds
            attr_entries = []
            for attr in _filter_attrs:
                key = _reverse_attr_keys.get(attr)
                if key:
                    attr_entries.append(f"Shift {key.upper()} {Level.format_attr(attr)}")
            if attr_entries:
                parts.append("Attributes: " + ", ".join(attr_entries))

            text = ". ".join(parts)
            async_tts.speak(text)
            log(f"[Shop Guide] {text}")
        except Exception as e:
            log(f"[Shop Guide] Error: {e}")

    def patched_process_shop_input(self):
        """Intercept Tab key for filter guide readout before normal shop input.
        Also detect shop exit (state change back to level)."""
        if self.shop_type in (_SHOP_TYPE_SPELLS, _SHOP_TYPE_UPGRADES):
            import pygame
            for evt in self.events:
                if evt.type == pygame.KEYDOWN and evt.key == pygame.K_TAB:
                    _speak_shop_filter_guide(self)
                    break
        _original_process_shop_input(self)

    _PyGameView.toggle_shop_filter = patched_toggle_shop_filter
    _PyGameView.process_shop_input = patched_process_shop_input
    log("  Shop filter hooks installed (toggle announcements + Tab guide)")

    # ---- Character Sheet Hooks ----

    _SLOT_NAMES = {0: "Staff", 1: "Robe", 2: "Helmet", 3: "Gloves", 4: "Boots", 5: "Trinket"}
    _LEARN_SPELL = getattr(_main, 'LEARN_SPELL_TARGET', None)
    _LEARN_SKILL = getattr(_main, 'LEARN_SKILL_TARGET', None)

    def _describe_examine_target(view):
        """Return speech text for the current examine_target in the character sheet."""
        target = view.examine_target
        if target is None or target is False:
            return "Nothing selected"

        # "Learn new spell" / "Learn new skill" placeholder items
        if target is _LEARN_SPELL:
            return "Learn New Spell. Press Enter to open spell shop"
        if target is _LEARN_SKILL:
            return "Learn New Skill. Press Enter to open skill shop"

        # Player spell
        if isinstance(target, Level.Spell) and target in view.game.p1.spells:
            name = _name(target)
            charges = getattr(target, 'cur_charges', 0)
            max_ch = 0
            try:
                max_ch = target.get_stat('max_charges')
            except:
                max_ch = getattr(target, 'max_charges', 0)
            rng = 0
            try:
                rng = target.get_stat('range')
            except:
                rng = getattr(target, 'range', 0)
            parts = [name]
            if max_ch:
                parts.append(f"{charges} of {max_ch} charges")
            if getattr(target, 'melee', False):
                parts.append("Melee")
            elif rng:
                parts.append(f"Range {rng}")
            desc = getattr(target, 'description', '')
            if desc:
                # First sentence only for brevity
                first = desc.split('\n')[0].split('.')[0]
                if first:
                    parts.append(first)
            return ". ".join(parts)

        # Equipment
        if isinstance(target, Level.Equipment):
            name = _name(target)
            slot = _SLOT_NAMES.get(getattr(target, 'slot', -1), "Equipment")
            desc = ''
            try:
                desc = target.get_description() or ''
            except:
                desc = getattr(target, 'description', '')
            parts = [f"{slot}: {name}"]
            if desc:
                first = desc.split('\n')[0].split('.')[0]
                if first:
                    parts.append(first)
            return ". ".join(parts)

        # Skill (passive buff without prereq) or spell upgrade (has prereq)
        if isinstance(target, Level.Upgrade):
            name = _name(target)
            prereq = getattr(target, 'prereq', None)
            if prereq:
                # Spell upgrade
                return f"Upgrade: {name} for {_name(prereq)}"
            else:
                # Skill
                desc = ''
                try:
                    desc = target.get_description() or ''
                except:
                    desc = getattr(target, 'description', '')
                parts = [f"Skill: {name}"]
                if desc:
                    first = desc.split('\n')[0].split('.')[0]
                    if first:
                        parts.append(first)
                return ". ".join(parts)

        # Buff (generic — shouldn't normally appear but handle gracefully)
        if isinstance(target, Level.Buff):
            name = _name(target)
            return f"Buff: {name}"

        # Fallback for any TooltipExamineTarget or unknown
        desc = getattr(target, 'description', '')
        if desc:
            return desc
        return str(target)

    def _char_sheet_section_name(view):
        """Return which section the current examine_target belongs to."""
        target = view.examine_target
        if target is _LEARN_SPELL:
            return "Spells"
        if target is _LEARN_SKILL:
            return "Skills"
        if isinstance(target, Level.Spell) and target in view.game.p1.spells:
            return "Spells"
        if isinstance(target, Level.Upgrade) and getattr(target, 'prereq', None) in view.game.p1.spells:
            return "Spells"
        if isinstance(target, Level.Equipment):
            return "Equipment"
        skills = view.game.p1.get_skills()
        if target in skills:
            return "Skills"
        return "Spells"

    _original_open_char_sheet = _PyGameView.open_char_sheet

    def _speak_char_sheet_overview(view):
        """Build and speak the character sheet overview text."""
        parts = ["Character sheet"]
        items = view.game.p1.items
        if items:
            item_strs = []
            for it in items:
                qty = getattr(it, 'quantity', 1)
                n = _name(it)
                item_strs.append(f"{qty} {n}" if qty > 1 else n)
            parts.append(f"Items: {', '.join(item_strs)}. Use with Alt plus number key")
        section = _char_sheet_section_name(view)
        desc = _describe_examine_target(view)
        parts.append(f"{section}. {desc}")
        text = ". ".join(parts[:2]) + ". " + parts[2] if len(parts) > 2 else ". ".join(parts)
        async_tts.speak(text)
        log(f"[CharSheet] Open: {text}")

    def patched_open_char_sheet(self):
        """Announce character sheet opening with overview."""
        _original_open_char_sheet(self)
        if _suppress_char_sheet_for_purchase[0]:
            # Purchase hook will speak in the right order
            return
        try:
            _speak_char_sheet_overview(self)
        except Exception as e:
            log(f"[CharSheet] Open error: {e}")

    _original_adjust_char_sheet = _PyGameView.adjust_char_sheet_selection

    def patched_adjust_char_sheet_selection(self, diff):
        """Voice navigation within character sheet section (UP/DOWN)."""
        _original_adjust_char_sheet(self, diff)
        try:
            text = _describe_examine_target(self)
            async_tts.speak(text)
            log(f"[CharSheet] Nav: {text}")
        except Exception as e:
            log(f"[CharSheet] Nav error: {e}")

    _original_toggle_char_sheet = _PyGameView.toggle_char_sheet_selection_type

    def patched_toggle_char_sheet_selection_type(self, diff):
        """Voice section switch in character sheet (LEFT/RIGHT)."""
        _original_toggle_char_sheet(self, diff)
        try:
            section = _char_sheet_section_name(self)
            desc = _describe_examine_target(self)
            text = f"{section}. {desc}"
            async_tts.speak(text)
            log(f"[CharSheet] Section: {text}")
        except Exception as e:
            log(f"[CharSheet] Section error: {e}")

    _original_process_char_sheet_input = _PyGameView.process_char_sheet_input

    def patched_process_char_sheet_input(self):
        """Wrapped for state transition detection (centralized hook handles announcement)."""
        _original_process_char_sheet_input(self)

    _PyGameView.open_char_sheet = patched_open_char_sheet
    _PyGameView.adjust_char_sheet_selection = patched_adjust_char_sheet_selection
    _PyGameView.toggle_char_sheet_selection_type = patched_toggle_char_sheet_selection_type
    _PyGameView.process_char_sheet_input = patched_process_char_sheet_input
    log("  Character sheet hooks installed")

    # ---- Target Selection Hooks ----

    _original_cycle_tab = _PyGameView.cycle_tab_targets

    def _describe_tile(view, point):
        """Describe the contents of a tile for Look mode cursor announcements.
        Returns a string like 'Fire Imp. HP 12 of 12. ...' or 'Wall' or 'Floor'."""
        try:
            level = view.game.cur_level
            if level is None:
                return "Unknown"
            x, y = point.x, point.y
            if not level.is_point_in_bounds(Level.Point(x, y)):
                return "Out of bounds"

            tile = level.tiles[x][y]
            parts = []

            # Unit on tile
            unit = tile.unit
            if unit:
                if _is_player(unit):
                    # Brief self-description — full details via F key
                    hp = getattr(unit, 'cur_hp', 0)
                    max_hp = getattr(unit, 'max_hp', 0)
                    parts.append(f"Wizard. {hp} of {max_hp} HP")
                else:
                    parts.append(_describe_unit_tier1(unit))

            # Prop on tile (portal, shrine, item on floor)
            if tile.prop:
                if hasattr(tile.prop, 'level_gen_params'):
                    parts.append(_describe_portal(tile.prop, view))
                else:
                    parts.append(_name(tile.prop))

            # Cloud on tile (fire cloud, poison cloud, etc.)
            if tile.cloud:
                cloud_name = _name(tile.cloud, "Cloud")
                dur = getattr(tile.cloud, 'duration', 0)
                if dur and dur > 0:
                    parts.append(f"{cloud_name}, {dur} turns")
                else:
                    parts.append(cloud_name)

            # Terrain type (only if nothing else to say, or always for wall/chasm)
            if tile.is_wall():
                parts.append("Wall")
            elif tile.is_chasm:
                parts.append("Chasm")
            elif not parts:
                # Empty floor — just say "Floor"
                parts.append("Floor")

            return ". ".join(parts)
        except Exception as e:
            log(f"[Look] Tile describe error: {e}")
            return "Unknown"

    def _describe_tile_brief(view, point):
        """Brief tile description for spell targeting cursor: unit name, or terrain type.
        Lighter than _describe_tile (Look mode) for rapid scanning during targeting."""
        try:
            level = view.game.cur_level
            if level is None:
                return "Unknown"
            x, y = point.x, point.y
            if not level.is_point_in_bounds(Level.Point(x, y)):
                return "Out of bounds"
            tile = level.tiles[x][y]
            # Unit: just name + HP
            unit = tile.unit
            if unit:
                hp = getattr(unit, 'cur_hp', None)
                max_hp = getattr(unit, 'max_hp', None)
                parts = [_name(unit)]
                if hp is not None and max_hp is not None:
                    parts.append(f"{hp} of {max_hp} HP")
                on_death = _get_on_death_text(unit)
                if on_death:
                    parts.append(on_death)
                return ". ".join(parts)
            # Prop
            if tile.prop:
                return _name(tile.prop)
            # Cloud
            if tile.cloud:
                return _name(tile.cloud, "Cloud")
            # Terrain
            if tile.is_wall():
                return "Wall"
            if tile.is_chasm:
                return "Chasm"
            return "Floor"
        except Exception as e:
            log(f"[Target Tile] Describe error: {e}")
            return "Unknown"

    def _describe_portal(portal, view):
        """Build a spoken description of a rift portal's contents."""
        parts = ["Rift"]
        gen_params = getattr(portal, 'level_gen_params', None)
        if gen_params is None:
            return "Rift"

        # Check if contents are hidden (level not cleared yet)
        game = getattr(view, 'game', None)
        if game and (game.next_level or not getattr(game, 'has_granted_xp', True)):
            parts.append("Contents unknown")
            return ". ".join(parts)

        if getattr(portal, 'locked', False):
            parts.append("Locked")

        # Enemies
        enemies = []
        if getattr(gen_params, 'primary_spawn', None):
            try:
                unit = gen_params.primary_spawn()
                enemies.append(unit.name)
            except:
                pass
        if getattr(gen_params, 'secondary_spawn', None) and gen_params.secondary_spawn != gen_params.primary_spawn:
            try:
                unit = gen_params.secondary_spawn()
                enemies.append(unit.name)
            except:
                pass

        drawn_bosses = set()
        for b in getattr(gen_params, 'bosses', []):
            if b.name not in drawn_bosses:
                drawn_bosses.add(b.name)
                if getattr(b, 'is_boss', False):
                    enemies.append(f"Boss: {b.name}")
                else:
                    enemies.append(b.name)

        if enemies:
            parts.append("Contents: " + ", ".join(enemies))

        # Items and Memory Orbs
        item_names = [_name(item) for item in getattr(gen_params, 'items', [])]
        num_xp = getattr(gen_params, 'num_xp', 0)
        if num_xp:
            item_names.append(f"{num_xp} Memory Orb{'s' if num_xp > 1 else ''}")
        if item_names:
            parts.append("Items: " + ", ".join(item_names))

        # Shrine
        shrine = getattr(gen_params, 'shrine', None)
        if shrine:
            shrine_text = _name(shrine)
            if hasattr(shrine, 'items') and shrine.items:
                shrine_items = [_name(item) for item in shrine.items]
                shrine_text += ": " + ", ".join(shrine_items)
            parts.append(shrine_text)

        return ". ".join(parts)

    def _describe_unit(unit):
        """Build a comprehensive spoken description of a unit, matching the visual examine panel."""
        import re
        parts = []

        # Name + Friendly status
        name = _name(unit)
        if getattr(unit, 'team', None) == Level.TEAM_PLAYER and not _is_player(unit):
            parts.append(f"{name}, Friendly")
        else:
            parts.append(name)

        # Turns to death (summoned creatures)
        ttd = getattr(unit, 'turns_to_death', None)
        if ttd:
            parts.append(f"{ttd} turns left")

        # Soulbound (lich soul jar mechanic — cannot die while jar exists)
        if _has_soulbound(unit):
            parts.append("Soulbound")

        # HP
        hp = getattr(unit, 'cur_hp', None)
        max_hp = getattr(unit, 'max_hp', None)
        if hp is not None and max_hp is not None:
            parts.append(f"{hp} of {max_hp} HP")

        # Shields
        shields = getattr(unit, 'shields', 0)
        if shields:
            parts.append(f"{shields} shield{'s' if shields != 1 else ''}")

        # Clarity (debuff immunity)
        clarity = getattr(unit, 'clarity', 0)
        if clarity:
            parts.append(f"{clarity} clarity")

        # Tags (Fire, Ice, Undead, Demon, etc.)
        tags = getattr(unit, 'tags', [])
        if tags:
            tag_names = [getattr(t, 'name', str(t)) for t in tags]
            parts.append(", ".join(tag_names))

        # Spells/Abilities
        spells = getattr(unit, 'spells', [])
        if spells:
            spell_descs = []
            for spell in spells:
                s_parts = [_name(spell)]

                # Damage amount and type
                if hasattr(spell, 'damage'):
                    dmg = spell.get_stat('damage') if hasattr(spell, 'get_stat') else getattr(spell, 'damage', 0)
                    dtype = getattr(spell, 'damage_type', None)
                    if isinstance(dtype, Level.Tag):
                        s_parts.append(f"{dmg} {dtype.name} damage")
                    elif isinstance(dtype, list):
                        random = getattr(spell, 'damage_type_random', False)
                        connector = ' or ' if random else ' and '
                        type_str = connector.join([t.name for t in dtype])
                        s_parts.append(f"{dmg} {type_str} damage")
                    else:
                        s_parts.append(f"{dmg} damage")

                # Range (only if > 1.5, matching game display)
                rng = spell.get_stat('range') if hasattr(spell, 'get_stat') else getattr(spell, 'range', 0)
                if rng > 1.5:
                    s_parts.append(f"range {rng}")

                # Radius
                if hasattr(spell, 'radius'):
                    rad = spell.get_stat('radius') if hasattr(spell, 'get_stat') else getattr(spell, 'radius', 0)
                    if rad > 0:
                        s_parts.append(f"{rad} radius")

                # HP cost
                if hasattr(spell, 'hp_cost'):
                    hp_cost = spell.get_stat('hp_cost') if hasattr(spell, 'get_stat') else getattr(spell, 'hp_cost', 0)
                    if hp_cost > 0:
                        s_parts.append(f"{hp_cost} HP cost")

                # Cooldown with remaining turns
                cd = 0
                try:
                    if hasattr(spell, 'get_stat'):
                        statholder = getattr(spell, 'statholder', None)
                        if statholder and statholder != getattr(spell, 'owner', None):
                            cd = getattr(spell, 'cool_down', 0)
                        else:
                            cd = spell.get_stat('cool_down')
                    else:
                        cd = getattr(spell, 'cool_down', 0)
                except:
                    cd = getattr(spell, 'cool_down', 0)

                if cd > 0:
                    rem_cd = 0
                    caster = getattr(spell, 'caster', None)
                    if caster:
                        rem_cd = caster.cool_downs.get(spell, 0)
                    if rem_cd:
                        s_parts.append(f"{cd} turn cooldown, {rem_cd} remaining")
                    else:
                        s_parts.append(f"{cd} turn cooldown")

                # Description (strip markup tags)
                desc = getattr(spell, 'description', None) or ""
                if not desc and hasattr(spell, 'get_description'):
                    desc = spell.get_description()
                if desc:
                    def _clean_tag(m):
                        content = m.group(1)
                        if ':' in content:
                            content = content.split(':')[0]
                        return content.replace('_', ' ')
                    desc = re.sub(r'\[([^\]]*)\]', _clean_tag, desc)
                    s_parts.append(desc)

                spell_descs.append(", ".join(s_parts))

            parts.append("Abilities: " + "; ".join(spell_descs))

        # Movement traits
        traits = []
        if getattr(unit, 'flying', False):
            traits.append("Flying")
        if getattr(unit, 'stationary', False):
            traits.append("Immobile")
        if getattr(unit, 'burrowing', False):
            traits.append("Burrowing")
        if traits:
            parts.append(", ".join(traits))

        # Damage resistances (sorted high to low, matching game display)
        resists = getattr(unit, 'resists', {})
        if resists:
            resist_entries = [(t, resists[t]) for t in resists if resists[t] != 0]
            resist_entries.sort(key=lambda x: -x[1])
            if resist_entries:
                resist_strs = [f"{val}% {getattr(t, 'name', str(t))}" for t, val in resist_entries]
                parts.append("Resists: " + ", ".join(resist_strs))

        # Passive buffs (permanent abilities with tooltips)
        # Include BUFF_TYPE_PASSIVE (0) and permanent BLESS buffs (type 1, turns_left 0)
        # — permanent BLESS includes on-death effects like DeathExplosion
        buffs = getattr(unit, 'buffs', [])
        if hasattr(unit, 'level'):
            passives = [b for b in buffs
                        if getattr(b, 'buff_type', -1) == 0
                        or (getattr(b, 'buff_type', -1) == 1 and getattr(b, 'turns_left', -1) == 0)]
        else:
            passives = list(buffs)

        passive_descs = []
        for buff in passives:
            tooltip = buff.get_tooltip() if hasattr(buff, 'get_tooltip') else None
            if tooltip:
                passive_descs.append(tooltip)
        if passive_descs:
            parts.append("Passives: " + "; ".join(passive_descs))

        # Status effects (temporary bless/curse with stacks and duration)
        # Exclude permanent BLESS buffs (type 1, turns_left 0) — those are in passives above
        if hasattr(unit, 'level'):
            status_effects = [b for b in buffs
                              if (getattr(b, 'buff_type', -1) == 2)
                              or (getattr(b, 'buff_type', -1) == 1 and getattr(b, 'turns_left', -1) != 0)]
        else:
            status_effects = []

        if status_effects:
            counts = {}
            for effect in status_effects:
                ename = _name(effect, "")
                if not ename:
                    continue
                if ename not in counts:
                    counts[ename] = [0, 0]
                counts[ename][0] += 1
                counts[ename][1] = max(counts[ename][1], getattr(effect, 'turns_left', 0))

            status_strs = []
            for bname, (stacks, duration) in counts.items():
                s = bname
                if stacks > 1:
                    s += f" x{stacks}"
                if duration:
                    s += f" ({duration} turns)"
                status_strs.append(s)

            if status_strs:
                parts.append("Status: " + ", ".join(status_strs))

        return ". ".join(parts)

    def _get_on_death_text(unit):
        """Extract on-death effect descriptions from a unit's buffs.
        Returns a short string like 'On death: 9 Fire damage to adjacent' or '' if none."""
        descs = []
        for buff in getattr(unit, 'buffs', []):
            triggers = getattr(buff, 'owner_triggers', {})
            if Level.EventOnDeath not in triggers:
                continue
            tooltip = buff.get_tooltip() if hasattr(buff, 'get_tooltip') else None
            if not tooltip:
                tooltip = getattr(buff, 'description', None)
            if not tooltip:
                continue
            # Strip leading "On death, " if present — we add our own prefix
            stripped = tooltip
            if stripped.lower().startswith("on death, "):
                stripped = stripped[len("on death, "):]
            elif stripped.lower().startswith("on reaching 0 hp, "):
                stripped = stripped[len("on reaching 0 hp, "):]
            descs.append(stripped)
        if not descs:
            return ""
        return "On death: " + "; ".join(descs)

    def _describe_unit_tier1(unit):
        """Streamlined unit description for Look mode and spell targeting (Tier 1).
        Format: Name → HP → SH → non-zero resists → status effects → ability names → on-death.
        Press D for full detail (Tier 2)."""
        parts = []

        # Name + Friendly status
        name = _name(unit)
        if getattr(unit, 'team', None) == Level.TEAM_PLAYER and not _is_player(unit):
            parts.append(f"{name}, Friendly")
        else:
            parts.append(name)

        # Turns to death (summoned creatures)
        ttd = getattr(unit, 'turns_to_death', None)
        if ttd:
            parts.append(f"{ttd} turns left")

        # Soulbound (lich soul jar mechanic)
        if _has_soulbound(unit):
            parts.append("Soulbound")

        # HP
        hp = getattr(unit, 'cur_hp', None)
        max_hp = getattr(unit, 'max_hp', None)
        if hp is not None and max_hp is not None:
            parts.append(f"{hp} of {max_hp} HP")

        # Shields
        shields = getattr(unit, 'shields', 0)
        if shields:
            parts.append(f"{shields} SH")

        # Non-zero resistances (compact, no "Resists:" prefix)
        resists = getattr(unit, 'resists', {})
        if resists:
            resist_entries = [(t, resists[t]) for t in resists if resists[t] != 0]
            resist_entries.sort(key=lambda x: -x[1])
            if resist_entries:
                resist_strs = [f"{val}% {getattr(t, 'name', str(t))}" for t, val in resist_entries]
                parts.append(", ".join(resist_strs))

        # Status effects (active bless/curse — compact with stacks and abbreviated duration)
        buffs = getattr(unit, 'buffs', [])
        if hasattr(unit, 'level'):
            status_effects = [b for b in buffs if getattr(b, 'buff_type', -1) in [1, 2]]
        else:
            status_effects = []
        if status_effects:
            counts = {}
            for effect in status_effects:
                ename = _name(effect, "")
                if not ename:
                    continue
                if ename not in counts:
                    counts[ename] = [0, 0]
                counts[ename][0] += 1
                counts[ename][1] = max(counts[ename][1], getattr(effect, 'turns_left', 0))
            status_strs = []
            for bname, (stacks, duration) in counts.items():
                s = bname
                if stacks > 1:
                    s += f" x{stacks}"
                if duration:
                    s += f" ({duration}t)"
                status_strs.append(s)
            if status_strs:
                parts.append(", ".join(status_strs))

        # Ability names only (no descriptions, damage, range, etc.)
        spells = getattr(unit, 'spells', [])
        if spells:
            spell_names = [_name(s) for s in spells]
            parts.append(", ".join(spell_names))

        # On-death effects (critical tactical info)
        on_death = _get_on_death_text(unit)
        if on_death:
            parts.append(on_death)

        return ". ".join(parts)

    def _check_aoe_warning(view):
        """Check what units are in the current spell's AoE.
        Returns (range_warning, aoe_info) tuple — both may be empty strings.
        range_warning ("Out of range. ") goes first.
        aoe_info ("Within AoE. You, 3 enemies.") goes before tile/target details.
        Reports enemies, allies, and player in blast zone (#17).
        Only warns for true AoE spells (radius > 0, beams, cones) — not single-target spells."""
        try:
            spell = getattr(view, 'cur_spell', None)
            target = getattr(view, 'cur_spell_target', None)
            if spell is None or target is None:
                return ("", "")
            # Skip walk/movement spells
            if _name(spell).lower() == 'walk':
                return ("", "")
            # Determine if this spell is truly AoE
            try:
                radius = spell.get_stat('radius') if hasattr(spell, 'get_stat') else getattr(spell, 'radius', 0)
            except:
                radius = getattr(spell, 'radius', 0)
            is_aoe = radius and radius > 0
            if not is_aoe:
                # Check for beam/cone/burst in description
                desc = ""
                if hasattr(spell, 'get_description'):
                    try:
                        desc = spell.get_description().lower()
                    except:
                        pass
                elif hasattr(spell, 'description'):
                    desc = (spell.description or "").lower()
                if any(kw in desc for kw in ('beam', 'line', 'cone', 'burst', 'all enemies', 'all units')):
                    is_aoe = True
            if not is_aoe:
                return ("", "")
            player = getattr(getattr(view, 'game', None), 'p1', None)
            if player is None:
                return ("", "")
            if not hasattr(spell, 'get_impacted_tiles'):
                return ("", "")
            impacted = spell.get_impacted_tiles(target.x, target.y)
            level = view.game.cur_level
            player_hit = False
            enemies = 0
            allies = 0
            for p in impacted:
                if not level.is_point_in_bounds(Level.Point(p.x, p.y)):
                    continue
                if p.x == player.x and p.y == player.y:
                    player_hit = True
                    continue
                unit = level.tiles[p.x][p.y].unit
                if unit and getattr(unit, 'cur_hp', 0) > 0:
                    if _is_player(unit):
                        player_hit = True
                    elif getattr(unit, 'team', None) == Level.TEAM_PLAYER:
                        allies += 1
                    else:
                        enemies += 1
            if not player_hit and enemies == 0 and allies == 0:
                return ("", "")
            details = []
            if player_hit:
                details.append("You")
            if enemies > 0:
                details.append(f"{enemies} {'enemy' if enemies == 1 else 'enemies'}")
            if allies > 0:
                details.append(f"{allies} {'ally' if allies == 1 else 'allies'}")
            # Range gate: check if target tile is within casting range
            range_warning = ""
            caster = getattr(spell, 'caster', None)
            if caster is not None:
                dx = abs(caster.x - target.x)
                dy = abs(caster.y - target.y)
                melee = getattr(spell, 'melee', False)
                try:
                    r = spell.get_stat('range') + (getattr(caster, 'radius', 0) if melee else 0)
                except:
                    r = getattr(spell, 'range', 0)
                if melee:
                    if max(dx, dy) > (1 + getattr(caster, 'radius', 0)):
                        range_warning = "Out of range. "
                else:
                    if dx * dx + dy * dy > r * r:
                        range_warning = "Out of range. "
            aoe_info = f"Within AoE {', '.join(details)}."
            return (range_warning, aoe_info)
        except Exception as e:
            log(f"[AoE Check] Error: {e}")
            return ("", "")

    def _describe_target(view):
        """Get a spoken description of the current target."""
        target = view._examine_target
        if target is None:
            return "No target"
        # If it's a unit (has HP), give full examine panel description
        hp = getattr(target, 'cur_hp', None)
        max_hp = getattr(target, 'max_hp', None)
        if hp is not None and max_hp is not None:
            return _describe_unit_tier1(target)
        # If it's a portal/rift, describe its contents
        if hasattr(target, 'level_gen_params'):
            return _describe_portal(target, view)
        # If examine_target is a spell (no HP), there's no unit under cursor
        if hasattr(target, 'cur_charges') or hasattr(target, 'max_charges'):
            return "No target"
        return _name(target)

    def patched_cycle_tab(self):
        """Announce target when TAB cycling, with position counter and AoE warning."""
        _original_cycle_tab(self)
        # Reset AoE and dedup state so subsequent cursor movement can re-trigger
        _aoe_announced_state[0] = False
        _last_examine_xy[0] = None
        try:
            text = _describe_target(self)
            # Add position counter: "2 of 5"
            tab_targets = getattr(self, 'tab_targets', [])
            if tab_targets:
                current = self.deploy_target or self.cur_spell_target
                if current in tab_targets:
                    idx = tab_targets.index(current) + 1
                    text = f"{idx} of {len(tab_targets)}. {text}"
            # AoE: range warning first, then AoE details, then target
            range_warn, aoe_info = _check_aoe_warning(self)
            text = f"{range_warn}{aoe_info} {text}".strip() if (range_warn or aoe_info) else text
            async_tts.speak(text)
            log(f"[Target] {text}")
        except Exception as e:
            log(f"[Target] Error: {e}")

    _PyGameView.cycle_tab_targets = patched_cycle_tab
    log("  Target cycling hook installed")

    # ---- Manual Cursor Movement: AoE Self-Hit Warning + Look Mode ----
    # Arrow keys / mouse move the reticle via try_examine_tile.
    # We hook it to warn when the player enters their own spell's AoE,
    # and to announce tile contents when in Look mode (V key).
    # DEDUP: The game calls try_examine_tile twice per frame (once for
    # keyboard, once for mouse at lines 2451 and 2471 of RiftWizard2.py).
    # We skip duplicate calls to the same point to avoid double-speech.
    # All announcements happen synchronously on the main thread — no timer
    # threads reading game state, which caused hard crashes.

    _original_try_examine_tile = _PyGameView.try_examine_tile
    _aoe_announced_state = [False]  # what we last told the user about AoE
    _last_examine_xy = [None]  # (x, y) of last announced tile — for dedup

    def _announce_look_tile(view, point):
        """Announce full tile contents in Look mode (V key). Main thread only."""
        try:
            text = _describe_tile(view, point)
            if cfg.show_coordinates:
                text = f"{text} ({point.x},{point.y})"
            log(f"[Look] ({point.x},{point.y}) {text}")
            async_tts.speak(text)
        except Exception as e:
            log(f"[Look] Error: {e}")

    def _announce_target_tile(view, point):
        """Announce brief tile + AoE warning during spell targeting. Main thread only."""
        try:
            spell = getattr(view, 'cur_spell', None)
            if spell is None:
                return
            if _name(spell).lower() == 'walk':
                return
            tile_text = _describe_tile_brief(view, point)
            if cfg.show_coordinates:
                tile_text = f"{tile_text} ({point.x},{point.y})"
            range_warn, aoe_info = _check_aoe_warning(view)
            text = f"{range_warn}{aoe_info} {tile_text}".strip() if (range_warn or aoe_info) else tile_text
            log(f"[Target Tile] {text}")
            async_tts.speak(text)
        except Exception as e:
            log(f"[Target Tile] Error: {e}")

    _deploy_tile_suppress = [False]  # Suppress tile announce during cycle jump

    def _announce_deploy_tile(view, point):
        """Announce tile contents at deploy cursor position. Main thread only."""
        if _deploy_tile_suppress[0]:
            _deploy_tile_suppress[0] = False
            return
        try:
            level = view.game.next_level
            if level is None:
                return
            x, y = point.x, point.y
            if not level.is_point_in_bounds(Level.Point(x, y)):
                return

            tile = level.tiles[x][y]
            parts = []

            unit = level.get_unit_at(x, y)
            if unit:
                parts.append(_describe_unit_tier1(unit))

            if tile.prop:
                parts.append(_name(tile.prop))

            if tile.is_wall():
                parts.append("wall")
            elif tile.is_chasm:
                parts.append("chasm")

            if parts:
                text = ", ".join(parts)
            else:
                valid = level.can_stand(x, y, view.game.p1)
                text = "clear" if valid else "blocked"

            log(f"[Deploy] {text}")
            async_tts.speak(text)
        except Exception as e:
            log(f"[Deploy] Tile error: {e}")

    def patched_try_examine_tile(self, point):
        """Hook cursor movement for Look mode, spell targeting, deploy tile feedback.
        Uses point deduplication instead of timer threads — the game calls this
        twice per frame with the same point (keyboard + mouse). We skip the duplicate."""
        _original_try_examine_tile(self, point)
        try:
            xy = (point.x, point.y)
            if xy == _last_examine_xy[0]:
                return  # Same tile as last call — skip duplicate
            _last_examine_xy[0] = xy

            if getattr(self.game, 'deploying', False):
                _announce_deploy_tile(self, point)
            else:
                spell = getattr(self, 'cur_spell', None)
                if spell is not None and type(spell).__name__ == 'LookSpell':
                    _announce_look_tile(self, point)
                elif spell is not None:
                    _announce_target_tile(self, point)
        except Exception as e:
            log(f"[Cursor] Error: {e}")

    _PyGameView.try_examine_tile = patched_try_examine_tile
    log("  Cursor AoE warning + Look mode + spell targeting tile hook installed")

    # ---- Custom Hotkeys: Vitals (F), Enemy Scan (E), Charges (Q) ----
    # These hook process_level_input to intercept KEYDOWN events for our keys.
    # Our keys (E, F, Q) have no handler in normal (non-cheat) gameplay, so passing
    # them through to the original method is safe — they'll be ignored.

    import pygame
    import math

    _original_process_level_input = _PyGameView.process_level_input

    def _query_vitals(view):
        """Speak player vitals: HP, shields, SP, active buffs/debuffs."""
        try:
            game = getattr(view, 'game', None)
            if game is None:
                return
            player = game.p1
            if player is None:
                return

            parts = []

            # HP
            hp = getattr(player, 'cur_hp', 0)
            max_hp = getattr(player, 'max_hp', 0)
            parts.append(f"HP {hp} of {max_hp}")

            # Shields
            shields = getattr(player, 'shields', 0)
            if shields:
                parts.append(f"{shields} shield{'s' if shields != 1 else ''}")

            # SP
            sp = getattr(player, 'xp', 0)
            parts.append(f"{sp} SP")

            # Active buffs and debuffs (skip passive buff_type=0)
            buffs = getattr(player, 'buffs', [])
            status_parts = []
            for buff in buffs:
                btype = getattr(buff, 'buff_type', 0)
                if btype not in (1, 2):
                    continue
                bname = _name(buff, "")
                if not bname:
                    continue
                turns = getattr(buff, 'turns_left', 0)
                prefix = "Cursed" if btype == 2 else ""
                entry = f"{prefix} {bname}".strip() if prefix else bname
                if turns and turns > 0:
                    entry += f" {turns} turns"
                status_parts.append(entry)
            if status_parts:
                parts.append("Status: " + ", ".join(status_parts))

            text = ". ".join(parts)
            log(f"[Vitals] {text}")
            async_tts.speak(text)
        except Exception as e:
            log(f"[Vitals] Error: {e}")

    def _get_scan_reference(view):
        """Return (ref_point, scan_level, qualifier) for the current game state.
        qualifier is None (normal/deploy), "destination" (teleport),
        "target" (non-teleport spell), or "cursor" (look mode).
        """
        game = view.game
        # Deploy: cursor-relative on next level, no qualifier (context is obvious)
        if getattr(game, 'deploying', False) and game.next_level and getattr(view, 'deploy_target', None):
            return (view.deploy_target, game.next_level, None)
        spell = getattr(view, 'cur_spell', None)
        target = getattr(view, 'cur_spell_target', None)
        if spell and target:
            # Look mode — LookSpell pseudo-spell
            if type(spell).__name__ == 'LookSpell':
                return (target, game.cur_level, "cursor")
            # Translocation spell — arriving at target
            if Level.Tags.Translocation in getattr(spell, 'tags', []):
                return (target, game.cur_level, "destination")
            # Other spell targeting
            return (target, game.cur_level, "target")
        # Normal play
        player = game.p1
        return (Level.Point(player.x, player.y), game.cur_level, None)

    def _query_enemies(view, scan_level=None, ref_point=None, qualifier=None, reverse=False):
        """Cycle through enemies one per keypress, nearest-first."""
        try:
            game = getattr(view, 'game', None)
            if game is None:
                return
            player = game.p1
            if player is None:
                return
            level = scan_level or game.cur_level
            if level is None:
                return
            if ref_point is None:
                ref_point = Level.Point(player.x, player.y)
            _qp = f"From {qualifier}. " if qualifier else ""

            rebuilt = _enemy_scanner.needs_rebuild(ref_point)
            if rebuilt:
                enemies = []
                for unit in level.units:
                    if Level.are_hostile(player, unit):
                        dist = Level.distance(ref_point, Level.Point(unit.x, unit.y), diag=True)
                        enemies.append((unit, dist))
                enemies.sort(key=lambda x: x[1])
                _enemy_scanner.set_list(enemies, ref_point)

            if not _enemy_scanner.items:
                text = f"{_qp}No enemies"
                log(f"[Enemies] {_log_ctx()} {_qp}No enemies")
                async_tts.speak(text)
                return

            result = _enemy_scanner.advance(reverse, rebuilt)
            if result is None:
                return
            idx, total, show_count = result
            count_str = f"{total} enem{'y' if total == 1 else 'ies'}"

            unit, dist = _enemy_scanner.items[idx]
            _last_scanned_target[0] = unit
            try:
                visible = level.can_see(ref_point.x, ref_point.y, unit.x, unit.y)
            except:
                visible = True
            los_tag = "" if visible else ", blocked"
            dx = unit.x - ref_point.x
            dy = unit.y - ref_point.y
            offset = _direction_offset(dx, dy)
            via_tag = ""
            if los_tag:
                via_tag = _via_hint(level, ref_point,
                                    Level.Point(unit.x, unit.y), player)
            soul_tag = ", soulbound" if _has_soulbound(unit) else ""
            mark_tag = ", marked" if _is_marked(unit) else ""
            coord_tag = f" ({unit.x},{unit.y})" if cfg.show_coordinates else ""
            entry = f"{_name(unit)}, {offset}{los_tag}{via_tag}{soul_tag}{mark_tag}{coord_tag}"
            position = f"{idx + 1} of {total}"
            log_entry = f"{_name(unit)} @({unit.x},{unit.y}), {offset}{los_tag}{via_tag}{soul_tag}{mark_tag}"

            if show_count:
                text = f"{_qp}{count_str}. {entry}. {position}"
                log(f"[Enemies] {_log_ctx()} {_qp}{count_str}. {log_entry}. {position}")
            else:
                text = f"{_qp}{entry}. {position}"
                log(f"[Enemies] {_log_ctx()} {_qp}{log_entry}. {position}")

            async_tts.speak(text)
        except Exception as e:
            log(f"[Enemies] Error: {e}")

    def _query_spawners(view, scan_level=None, ref_point=None, qualifier=None, reverse=False):
        """Cycle through spawners one per keypress, nearest-first."""
        try:
            game = getattr(view, 'game', None)
            if game is None:
                return
            player = game.p1
            if player is None:
                return
            level = scan_level or game.cur_level
            if level is None:
                return
            if ref_point is None:
                ref_point = Level.Point(player.x, player.y)
            _qp = f"From {qualifier}. " if qualifier else ""

            rebuilt = _spawner_scanner.needs_rebuild(ref_point)
            if rebuilt:
                spawners = []
                for unit in level.units:
                    if Level.are_hostile(player, unit) and getattr(unit, 'is_lair', False):
                        dist = Level.distance(ref_point, Level.Point(unit.x, unit.y), diag=True)
                        spawners.append((unit, dist))
                spawners.sort(key=lambda x: x[1])
                _spawner_scanner.set_list(spawners, ref_point)

            if not _spawner_scanner.items:
                text = f"{_qp}No spawners"
                log(f"[Spawners] {_log_ctx()} {_qp}No spawners")
                async_tts.speak(text)
                return

            result = _spawner_scanner.advance(reverse, rebuilt)
            if result is None:
                return
            idx, total, show_count = result
            count_str = f"{total} spawner{'s' if total != 1 else ''}"

            unit, dist = _spawner_scanner.items[idx]
            _last_scanned_target[0] = unit
            try:
                visible = level.can_see(ref_point.x, ref_point.y, unit.x, unit.y)
            except:
                visible = True
            los_tag = "" if visible else ", blocked"
            dx = unit.x - ref_point.x
            dy = unit.y - ref_point.y
            offset = _direction_offset(dx, dy)
            via_tag = ""
            if los_tag:
                via_tag = _via_hint(level, ref_point,
                                    Level.Point(unit.x, unit.y), player)
            mark_tag = ", marked" if _is_marked(unit) else ""
            coord_tag = f" ({unit.x},{unit.y})" if cfg.show_coordinates else ""
            entry = f"{_name(unit)}, {offset}{los_tag}{via_tag}{mark_tag}{coord_tag}"
            position = f"{idx + 1} of {total}"
            log_entry = f"{_name(unit)} @({unit.x},{unit.y}), {offset}{los_tag}{via_tag}{mark_tag}"

            if show_count:
                text = f"{_qp}{count_str}. {entry}. {position}"
                log(f"[Spawners] {_log_ctx()} {_qp}{count_str}. {log_entry}. {position}")
            else:
                text = f"{_qp}{entry}. {position}"
                log(f"[Spawners] {_log_ctx()} {_qp}{log_entry}. {position}")

            async_tts.speak(text)
        except Exception as e:
            log(f"[Spawners] Error: {e}")

    # Pickup priority tiers (lower = announced first):
    #   0 = Unique finds: equipment, scrolls, items — rare, build-defining
    #   1 = Resources: Memory Orbs (SP), Gold, Spell Recharge — economy/sustain
    #   2 = Stat boosts: Ruby Hearts (permanent HP), Heal Dots — nice but less urgent
    _PICKUP_UNIQUE = 0
    _PICKUP_RESOURCE = 1
    _PICKUP_STAT = 2

    def _classify_prop(prop):
        """Classify a tile prop into a category and readable name.
        Returns (category, priority, name) where category is 'landmark' or 'pickup', or None to skip.
        Priority only matters for pickups (lower = announced first)."""
        cls = type(prop).__name__
        # Landmarks: strategic navigation points
        if hasattr(prop, 'level_gen_params'):
            if getattr(prop, 'locked', False):
                return None
            return ('landmark', 0, "Rift")
        if cls == 'PlaceOfPower':
            tag = getattr(prop, 'tag', None)
            tag_name = getattr(tag, 'name', '') if tag else ''
            return ('landmark', 0, f"{tag_name} Circle" if tag_name else _name(prop))
        # Shops/Shrines (check specific subclasses via class name — avoids import issues)
        if cls in ('ShrineShop', 'ShiftingShop'):
            return ('landmark', 0, _name(prop))
        if cls == 'MiniShop':
            return ('landmark', 0, "Miniaturization Shrine")
        if cls == 'DuplicatorShop':
            return ('landmark', 0, "Duplication Shrine")
        if cls == 'AmnesiaShop':
            return ('landmark', 0, "Amnesia Shrine")
        if cls == 'Shop' or (hasattr(prop, 'shop_type') or hasattr(prop, 'items')):
            # Generic shop fallback
            pname = _name(prop, "")
            if pname and 'shop' in pname.lower() or 'shrine' in pname.lower():
                return ('landmark', 0, pname)
        # Pickups — Tier 0: unique finds (build-defining, don't miss these)
        if cls == 'SpellScroll':
            spell = getattr(prop, 'spell', None)
            sname = _name(spell, "unknown") if spell else "unknown"
            return ('pickup', _PICKUP_UNIQUE, f"Scroll: {sname}")
        if cls == 'EquipPickup':
            item = getattr(prop, 'item', None)
            return ('pickup', _PICKUP_UNIQUE, f"Equipment: {_name(item)}" if item else "Equipment")
        if cls == 'ItemPickup':
            item = getattr(prop, 'item', None)
            return ('pickup', _PICKUP_UNIQUE, f"Item: {_name(item)}" if item else "Item")
        # Pickups — Tier 1: resources (economy, sustain, recharges)
        if cls == 'ManaDot':
            return ('pickup', _PICKUP_RESOURCE, "Memory Orb")
        if cls == 'GoldDot':
            gold = getattr(prop, 'gold', 1)
            return ('pickup', _PICKUP_RESOURCE, f"Gold, {gold}")
        if cls == 'ChargeDot':
            return ('pickup', _PICKUP_RESOURCE, "Spell Recharge")
        # Pickups — Tier 2: stat boosts and heals
        if cls == 'HeartDot':
            bonus = getattr(prop, 'bonus', 10)
            return ('pickup', _PICKUP_STAT, f"Ruby Heart, plus {bonus} max HP")
        if cls == 'HealDot':
            return ('pickup', _PICKUP_STAT, "Heal")
        return None

    def _landmark_cat_label(name):
        """Short category label for count header breakdown."""
        if name.startswith("Scroll:"): return "scroll"
        if name.startswith("Equipment:"): return "equipment"
        if name.startswith("Item:"): return "item"
        if name == "Memory Orb": return "orb"
        if name.startswith("Gold"): return "gold"
        if name == "Spell Recharge": return "recharge"
        if name.startswith("Ruby Heart"): return "heart"
        if name == "Heal": return "heal"
        if name == "Rift": return "rift"
        if "Circle" in name: return "circle"
        if "Shrine" in name: return "shrine"
        return "shop"

    def _query_landmarks(view, scan_level=None, ref_point=None, qualifier=None, reverse=False):
        """Cycle through landmarks/pickups one per keypress, nearest-first."""
        try:
            game = getattr(view, 'game', None)
            if game is None:
                return
            player = game.p1
            if player is None:
                return
            level = scan_level or game.cur_level
            if level is None:
                return
            if ref_point is None:
                ref_point = Level.Point(player.x, player.y)
            _qp = f"From {qualifier}. " if qualifier else ""

            rebuilt = _landmark_scanner.needs_rebuild(ref_point)
            if rebuilt:
                items = []  # (name, dist, offset, tx, ty)
                for tile in level.iter_tiles():
                    prop = tile.prop
                    if prop is None:
                        continue
                    result = _classify_prop(prop)
                    if result is None:
                        continue
                    category, priority, name = result
                    dx = tile.x - ref_point.x
                    dy = tile.y - ref_point.y
                    dist = max(abs(dx), abs(dy))  # Chebyshev
                    offset = _direction_offset(dx, dy)
                    items.append((name, dist, offset, tile.x, tile.y))
                items.sort(key=lambda x: x[1])
                _landmark_scanner.set_list(items, ref_point)

            if not _landmark_scanner.items:
                text = f"{_qp}Nothing found"
                log(f"[Landmarks] {_log_ctx()} {_qp}Nothing found")
                async_tts.speak(text)
                return

            # Category-aware count header
            from collections import Counter
            cat_counts = Counter(_landmark_cat_label(n) for n, *_ in _landmark_scanner.items)
            cat_parts = [f"{c} {lab}{'s' if c > 1 else ''}" for lab, c in cat_counts.items()]
            total = len(_landmark_scanner.items)
            count_str = f"{total} item{'s' if total != 1 else ''}. {', '.join(cat_parts)}"

            result = _landmark_scanner.advance(reverse, rebuilt)
            if result is None:
                return
            idx, total, show_count = result

            name, dist, offset, tx, ty = _landmark_scanner.items[idx]
            _last_scanned_target[0] = (name, tx, ty)
            # Build entry description
            try:
                visible = level.can_see(ref_point.x, ref_point.y, tx, ty)
            except:
                visible = True
            los_tag = "" if visible else ", blocked"
            via_tag = ""
            if los_tag:
                via_tag = _via_hint(level, ref_point,
                                    Level.Point(tx, ty), player)
            mark_tag = ", marked" if _is_marked((name, tx, ty)) else ""
            coord_tag = f" ({tx},{ty})" if cfg.show_coordinates else ""
            entry = f"{name}, {offset}{los_tag}{via_tag}{mark_tag}{coord_tag}"
            position = f"{idx + 1} of {total}"
            log_entry = f"{name} @({tx},{ty}), {offset}{los_tag}{via_tag}{mark_tag}"

            if show_count:
                text = f"{_qp}{count_str}. {entry}. {position}"
                log(f"[Landmarks] {_log_ctx()} {_qp}{count_str}. {log_entry}. {position}")
            else:
                text = f"{_qp}{entry}. {position}"
                log(f"[Landmarks] {_log_ctx()} {_qp}{log_entry}. {position}")

            async_tts.speak(text)
        except Exception as e:
            log(f"[Landmarks] Error: {e}")

    def _query_hazards(view, scan_level=None, ref_point=None, qualifier=None):
        """Speak environmental hazards: spider webs (individual) + cloud counts (aggregate).
        Bound to X key. Separate from Q-key landmarks to avoid overloading that scan."""
        try:
            game = getattr(view, 'game', None)
            if game is None:
                return
            player = game.p1
            level = scan_level or game.cur_level
            if level is None:
                return
            if ref_point is None:
                if player is None:
                    return
                ref_point = Level.Point(player.x, player.y)
            _qp = f"From {qualifier}. " if qualifier else ""

            webs = []       # (dist, offset, x, y) — individual entries
            cloud_counts = {}  # cloud_name → count — aggregate

            for cloud in getattr(level, 'clouds', []):
                ctype = type(cloud).__name__
                if ctype == 'SpiderWeb':
                    dx = cloud.x - ref_point.x
                    dy = cloud.y - ref_point.y
                    dist = max(abs(dx), abs(dy))
                    offset = _direction_offset(dx, dy)
                    webs.append((dist, offset, cloud.x, cloud.y))
                else:
                    cname = getattr(cloud, 'name', ctype)
                    cloud_counts[cname] = cloud_counts.get(cname, 0) + 1

            if not webs and not cloud_counts:
                text = f"{_qp}No hazards"
                log(f"[Hazards] {_log_ctx()} {_qp}No hazards")
                async_tts.speak(text)
                return

            parts = []
            log_parts = []

            # Summary counts
            counts = []
            if webs:
                counts.append(f"{len(webs)} Spider Web{'s' if len(webs) != 1 else ''}")
            total_clouds = sum(cloud_counts.values())
            if total_clouds:
                counts.append(f"{total_clouds} cloud{'s' if total_clouds != 1 else ''}")
            parts.append(", ".join(counts))
            log_parts.append(", ".join(counts))

            # Spider webs — individual with distance/direction (nearest first)
            webs.sort(key=lambda x: x[0])
            for dist, offset, wx, wy in webs:
                parts.append(f"Spider Web, {offset}")
                log_parts.append(f"Spider Web @({wx},{wy}), {offset}")

            # Dynamic clouds — aggregate counts by type
            for cname, count in sorted(cloud_counts.items()):
                parts.append(f"{count} {cname}{'s' if count != 1 else ''}")
                log_parts.append(f"{count} {cname}")

            text = f"{_qp}{'. '.join(parts)}"
            log(f"[Hazards] {_log_ctx()} {_qp}{'. '.join(log_parts)}")
            async_tts.speak(text)
        except Exception as e:
            log(f"[Hazards] Error: {e}")

    def _query_charges(view):
        """Speak current charges of the selected spell (on-demand)."""
        try:
            spell = getattr(view, 'cur_spell', None)
            if spell is None:
                # No spell selected — check all player spells for a quick summary
                game = getattr(view, 'game', None)
                if game is None or game.p1 is None:
                    return
                spells = getattr(game.p1, 'spells', [])
                if not spells:
                    async_tts.speak("No spells")
                    log(f"[Charges] {_log_ctx()} No spells")
                    return
                parts = []
                for s in spells:
                    cur, stat_max = _get_charge_info(s)
                    if cur is not None:
                        parts.append(f"{_name(s)}: {cur} of {stat_max}")
                if parts:
                    text = ". ".join(parts)
                else:
                    text = "No charge spells"
                log(f"[Charges] {_log_ctx()} {text}")
                async_tts.speak(text)
                return

            cur, stat_max = _get_charge_info(spell)
            if cur is None:
                text = f"{_name(spell)}: no charges"
                log(f"[Charges] {_log_ctx()} {text}")
                async_tts.speak(text)
                return

            text = f"{_name(spell)}: {cur} of {stat_max} charges"
            log(f"[Charges] {_log_ctx()} {text}")
            async_tts.speak(text)
        except Exception as e:
            log(f"[Charges] Error: {e}")

    def _query_unit_detail(view):
        """D key: Speak full Tier 2 detail of the unit at cursor position.
        Includes all abilities with damage/range/descriptions, passives, movement traits, etc."""
        try:
            unit = None
            game = view.game
            if game is None:
                return

            # Check examine_target first (set by Tab cycling and cursor movement)
            examine = getattr(view, 'examine_target', None)
            if examine is None:
                examine = getattr(view, '_examine_target', None)
            if examine and hasattr(examine, 'cur_hp') and not _is_player(examine):
                unit = examine

            # Fallback: check tile at cursor position
            if unit is None:
                point = getattr(view, 'cur_spell_target', None)
                if point is None:
                    point = getattr(view, 'deploy_target', None)
                if point is not None:
                    level = view.game.next_level if getattr(game, 'deploying', False) else game.cur_level
                    if level:
                        tile_unit = level.get_unit_at(point.x, point.y)
                        if tile_unit and not _is_player(tile_unit):
                            unit = tile_unit

            if unit is None:
                async_tts.speak("No unit to examine")
                log("[Detail] No unit at cursor")
                return

            text = _describe_unit(unit)
            log(f"[Detail] {text}")
            async_tts.speak(text)
        except Exception as e:
            log(f"[Detail] Error: {e}")

    def _unit_threatens_point(unit, x, y):
        """Check if a unit can threaten a given point via any spell or custom-threatening buff."""
        for spell in getattr(unit, 'spells', []):
            try:
                if spell.can_threaten(x, y):
                    return True
            except:
                pass
        for buff in getattr(unit, 'buffs', []):
            try:
                if buff.can_threaten.__func__ != Level.Buff.can_threaten:
                    if buff.can_threaten(x, y):
                        return True
            except:
                pass
        return False

    def _query_los_summary(view, scan_level=None, ref_point=None, qualifier=None):
        """L key: LoS composition gestalt — count by type with directional clustering."""
        try:
            game = getattr(view, 'game', None)
            if game is None:
                return
            player = game.p1
            if player is None:
                return
            level = scan_level or game.cur_level
            if level is None:
                return
            if ref_point is None:
                ref_point = Level.Point(player.x, player.y)

            _qp = f"From {qualifier}. " if qualifier else ""

            # Gather visible hostile units grouped by (name, direction)
            from collections import Counter
            visible = []
            for unit in level.units:
                if not Level.are_hostile(player, unit):
                    continue
                try:
                    can_see = level.can_see(ref_point.x, ref_point.y, unit.x, unit.y)
                except:
                    can_see = False
                if can_see:
                    dx = unit.x - ref_point.x
                    dy = unit.y - ref_point.y
                    direction = _cardinal_direction(dx, dy)
                    visible.append((_name(unit), direction, unit))

            if not visible:
                text = f"{_qp}Nothing in sight"
                log(f"[LoS] {_log_ctx()} {text}")
                async_tts.speak(text)
                return

            total = len(visible)
            has_marked_visible = any(_is_marked(u) for _, _, u in visible)
            # Group by (name, direction), preserving order of first appearance
            groups = {}
            group_order = []
            for name, direction, _u in visible:
                key = (name, direction)
                if key not in groups:
                    groups[key] = 0
                    group_order.append(key)
                groups[key] += 1

            # Format: "2 Goblins south, Fire Imp east"
            parts = []
            for name, direction in group_order:
                count = groups[(name, direction)]
                dir_suffix = f" {direction}" if direction else ", here"
                if count > 1:
                    parts.append(f"{count} {name}s{dir_suffix}")
                else:
                    parts.append(f"{name}{dir_suffix}")

            count_str = f"{total} in sight"
            mark_note = ". Marked target visible" if has_marked_visible else ""
            text = f"{_qp}{count_str}. {', '.join(parts)}{mark_note}"
            log(f"[LoS] {_log_ctx()} {text}")
            async_tts.speak(text)
        except Exception as e:
            log(f"[LoS] Error: {e}")

    def _query_threat(view, scan_level=None, ref_point=None, qualifier=None):
        """T key: Threat vocalization.
        No unit highlighted: 'Safe' or 'Threatened, N. Enemy, direction.'
        Enemy unit highlighted: 'Threatens you' or 'Can't reach you.'"""
        try:
            game = view.game
            if game is None:
                return
            player = game.p1
            if player is None:
                return
            level = scan_level or game.cur_level
            if level is None:
                return
            if ref_point is not None:
                ref_x, ref_y = ref_point.x, ref_point.y
            else:
                ref_x, ref_y = player.x, player.y
            _qp = f"From {qualifier}. " if qualifier else ""

            # Per-unit threat check: if examining a hostile unit
            examine = getattr(view, 'examine_target', None)
            if examine is None:
                examine = getattr(view, '_examine_target', None)
            if (examine and hasattr(examine, 'cur_hp')
                    and not _is_player(examine)
                    and Level.are_hostile(player, examine)):
                if _unit_threatens_point(examine, ref_x, ref_y):
                    text = f"{_qp}Threatens you"
                else:
                    text = f"{_qp}Can't reach you"
                log(f"[Threat] {_name(examine)}: {text}")
                async_tts.speak(text)
                return

            # Global threat summary
            threatening = []
            for unit in level.units:
                if not Level.are_hostile(player, unit):
                    continue
                if _unit_threatens_point(unit, ref_x, ref_y):
                    dist = max(abs(unit.x - ref_x), abs(unit.y - ref_y))
                    threatening.append((unit, dist))

            if not threatening:
                text = f"{_qp}Safe"
                log(f"[Threat] {_qp}Safe")
                async_tts.speak(text)
                return

            threatening.sort(key=lambda x: x[1])
            parts = [f"Threatened, {len(threatening)}"]
            for unit, dist in threatening[:8]:
                dx = unit.x - ref_x
                dy = unit.y - ref_y
                offset = _direction_offset(dx, dy)
                parts.append(f"{_name(unit)}, {offset}")
            if len(threatening) > 8:
                parts.append(f"and {len(threatening) - 8} more")

            text = f"{_qp}{'. '.join(parts)}"
            log(f"[Threat] {_qp}{'. '.join(parts)}")
            async_tts.speak(text)
        except Exception as e:
            log(f"[Threat] Error: {e}")

    def _query_space(view, scan_level=None, ref_point=None, qualifier=None):
        """B key: Spatial raycast query.
        Prepends terrain classification, then walkable distances in 8 directions.
        Only reports directions with distance >= 1 (skips blocked).
        Clockwise order: N, NE, E, SE, S, SW, W, NW."""
        try:
            game = view.game
            if game is None:
                return
            level = scan_level or game.cur_level
            if level is None:
                return
            if ref_point is not None:
                px, py = ref_point.x, ref_point.y
            else:
                px, py = game.p1.x, game.p1.y
            _qp = f"From {qualifier}. " if qualifier else ""

            # Terrain classification prefix (S53)
            tc, axis = _classify_terrain(level, px, py)
            prefix = _TERRAIN_LABELS[tc](axis) if tc in _TERRAIN_LABELS else "open"

            # Corridor branch scan — report perpendicular openings along the axis
            branch_text = ""
            if tc == 'corridor' and axis:
                branches = _scan_corridor_branches(level, px, py, axis)
                if branches:
                    branch_text = ". ".join(branches)

            parts = []
            for name, dx, dy in _RAYCAST_DIRS:
                dist = _ray_length(level, px, py, dx, dy)
                if dist >= 1:
                    parts.append(f"{name} {dist}")

            rays = ", ".join(parts) if parts else "enclosed"
            if branch_text:
                text = f"{_qp}{prefix}. {branch_text}. {rays}"
            else:
                text = f"{_qp}{prefix}. {rays}"
            log(f"[Space] ({px},{py}) {text}")
            async_tts.speak(text)
        except Exception as e:
            log(f"[Space] Error: {e}")

    # ---- Deploy Phase: State Tracking, Overview & Category Cycling ----
    # Session 49 — Bug #38 deploy spatial navigation.
    # Key 1: quadrant overview. Keys 2-5: cycle orbs, pickups, spawners, shops.

    _was_deploying = [False]

    # ---- CycleScanner: unified one-per-press cycling infrastructure ----

    class CycleScanner:
        """State machine for one-per-press nearest-first cycling scans."""
        def __init__(self, name):
            self.name = name
            self._list = []
            self._idx = 0
            self._ref = None
            self._count_spoken = False

        def reset(self):
            self._list = []
            self._idx = 0
            self._ref = None

        def turn_reset(self):
            self.reset()
            self._count_spoken = False

        def needs_rebuild(self, ref_point):
            return (not self._list
                    or self._ref is None
                    or self._ref.x != ref_point.x
                    or self._ref.y != ref_point.y)

        def set_list(self, items, ref_point):
            self._list = items
            self._idx = 0
            self._ref = ref_point

        def advance(self, reverse=False, rebuilt=False):
            """Advance cycle index. Returns (idx, total, show_count) or None if empty."""
            total = len(self._list)
            if total == 0:
                return None
            if reverse and not rebuilt:
                self._idx = (self._idx - 2) % total
            idx = self._idx % total
            show_count = (idx == 0 and rebuilt and not self._count_spoken)
            if show_count:
                self._count_spoken = True
            self._idx = idx + 1
            return idx, total, show_count

        @property
        def items(self):
            return self._list

    _enemy_scanner = CycleScanner("enemies")
    _spawner_scanner = CycleScanner("spawners")
    _landmark_scanner = CycleScanner("landmarks")

    # ---- Mark/tracking system (Alt+scan key to mark, passive updates) ----
    # Supports both units and landmarks. One mark at a time.
    # Unit mark: stores unit object directly.
    # Landmark mark: stores (name, x, y) tuple.

    _last_scanned_target = [None]   # Most recently announced target (unit or (name, x, y))
    _marked_target = [None]         # Player-marked target for persistent tracking
    _mark_last_visible = [None]     # LoS state: True/False/None (unset). Only speak "blocked" on transition.
    _mark_tier_immediate = [True]   # Config: True = immediate tier, False = turn-end

    def _mark_target_name(target):
        """Get display name for a mark target (unit or landmark tuple)."""
        if isinstance(target, tuple):
            return target[0]
        return _name(target)

    def _mark_scanned_target():
        """Mark the last scanned target. Toggle off if already marked."""
        target = _last_scanned_target[0]
        if target is None:
            async_tts.speak("Nothing to mark")
            log("[Mark] Nothing to mark")
            return
        current = _marked_target[0]
        # Toggle off: same unit (identity) or same landmark (position)
        if current is not None and _same_mark(current, target):
            _marked_target[0] = None
            _mark_last_visible[0] = None
            async_tts.speak(f"Unmarked {_mark_target_name(target)}")
            log(f"[Mark] Unmarked {_mark_target_name(target)}")
        else:
            _marked_target[0] = target
            _mark_last_visible[0] = None  # Force first update to report LoS status
            async_tts.speak(f"Marked {_mark_target_name(target)}")
            log(f"[Mark] Marked {_mark_target_name(target)}")

    def _same_mark(a, b):
        """Check if two mark targets refer to the same thing."""
        a_is_landmark = isinstance(a, tuple)
        b_is_landmark = isinstance(b, tuple)
        if a_is_landmark != b_is_landmark:
            return False
        if a_is_landmark:
            return a[1] == b[1] and a[2] == b[2]  # same position
        return a is b  # unit identity

    def _is_marked(target):
        """Check if a target (unit or landmark tuple) is the current mark."""
        current = _marked_target[0]
        if current is None:
            return False
        return _same_mark(current, target)

    def _get_mark_update(level, ref_point):
        """Get status string for the marked target, or None if no mark/gone.
        Reports 'blocked' only on first update or when LoS status changes."""
        target = _marked_target[0]
        if target is None:
            return None
        if isinstance(target, tuple):
            # Landmark mark — check if prop still exists at position
            name, tx, ty = target
            try:
                tile = level.tiles[tx][ty]
            except (IndexError, TypeError):
                tile = None
            if tile is None or tile.prop is None:
                _marked_target[0] = None
                _mark_last_visible[0] = None
                return f"Marked landmark gone: {name}"
            dx = tx - ref_point.x
            dy = ty - ref_point.y
            direction = _direction_offset(dx, dy)
            # LoS check for landmarks
            try:
                visible = level.can_see(ref_point.x, ref_point.y, tx, ty)
            except Exception:
                visible = True
            los_tag = _mark_los_tag(visible)
            return f"Marked: {name}, {direction}{los_tag}"
        else:
            # Unit mark
            if target not in level.units:
                _marked_target[0] = None
                _mark_last_visible[0] = None
                return "Marked unit dead"
            dx = target.x - ref_point.x
            dy = target.y - ref_point.y
            direction = _direction_offset(dx, dy)
            # LoS check for units
            try:
                visible = level.can_see(ref_point.x, ref_point.y, target.x, target.y)
            except Exception:
                visible = True
            los_tag = _mark_los_tag(visible)
            return f"Marked: {_name(target)}, {direction}{los_tag}"

    def _mark_los_tag(visible):
        """Return LoS tag for mark update. Only speaks on first check or transition."""
        prev = _mark_last_visible[0]
        _mark_last_visible[0] = visible
        if prev is None:
            # First update after marking — always report
            return "" if visible else ", blocked"
        if visible != prev:
            # Transition — report the change
            return ", in sight" if visible else ", blocked"
        # No change — stay quiet
        return ""

    # Cycling state for deploy category navigation (keys 2-5)
    _deploy_cycle_cat = [None]     # Current category (2-5) or None
    _deploy_cycle_items = [[]]     # Sorted entity list for current category
    _deploy_cycle_idx = [0]        # Current index in cycle

    _DEPLOY_CAT_NAMES = {2: "memory orbs", 3: "pickups", 4: "spawners", 5: "shops"}

    def _deploy_reset_cycle():
        """Clear cycling state. Called on deploy entry/exit and arrow movement."""
        _deploy_cycle_cat[0] = None
        _deploy_cycle_items[0] = []
        _deploy_cycle_idx[0] = 0

    def _announce_deploy_overview(view):
        """Quadrant overview: enemy counts + notable entities per quadrant.
        Auto-fires on deploy entry, re-voiced via key 1."""
        try:
            level = view.game.next_level
            if level is None:
                return
            # level_num increments after try_deploy, so during deploy it's still
            # the current level. Add 1 to show the level being deployed to.
            level_num = getattr(view.game, 'level_num', 0) + 1

            # Build per-quadrant aggregates
            quads = {}  # quadrant_name -> {enemies, spawners, props: [str]}
            for q in ("northeast", "southeast", "southwest", "northwest"):
                quads[q] = {"enemies": 0, "spawners": 0, "props": []}

            # Count enemies and spawners by quadrant
            player = view.game.p1
            for unit in level.units:
                if not Level.are_hostile(player, unit):
                    continue
                q = _quadrant_label(unit.x, unit.y)
                if getattr(unit, 'is_lair', False):
                    quads[q]["spawners"] += 1
                else:
                    quads[q]["enemies"] += 1

            # Count notable props by quadrant
            orb_counts = {}   # quadrant -> count
            for tile in level.iter_tiles():
                prop = tile.prop
                if prop is None:
                    continue
                cls = type(prop).__name__
                q = _quadrant_label(tile.x, tile.y)
                if cls == 'ManaDot':
                    orb_counts[q] = orb_counts.get(q, 0) + 1
                elif cls == 'PlaceOfPower':
                    tag = getattr(prop, 'tag', None)
                    tag_name = getattr(tag, 'name', '') if tag else ''
                    quads[q]["props"].append(f"{tag_name} Circle" if tag_name else "Circle")
                elif cls in ('Shop', 'ShrineShop', 'ShiftingShop', 'MiniShop',
                             'DuplicatorShop', 'AmnesiaShop') or hasattr(prop, 'shop_type'):
                    quads[q]["props"].append("shop")
                elif cls == 'NPC':
                    quads[q]["props"].append(_name(prop))

            # Add orb counts to props
            for q, count in orb_counts.items():
                quads[q]["props"].append(f"{count} orb{'s' if count > 1 else ''}")

            # Build speech string: "Deploy, level N. Quadrant: details. ..."
            parts = [f"Deploy, level {level_num}"]
            for q in ("northeast", "southeast", "southwest", "northwest"):
                data = quads[q]
                if data["enemies"] == 0 and data["spawners"] == 0 and not data["props"]:
                    continue  # Skip empty quadrants
                q_parts = []
                if data["enemies"]:
                    q_parts.append(f"{data['enemies']} enem{'y' if data['enemies'] == 1 else 'ies'}")
                if data["spawners"]:
                    q_parts.append(f"{data['spawners']} spawner{'s' if data['spawners'] > 1 else ''}")
                q_parts.extend(data["props"])
                parts.append(f"{q.capitalize()}: {', '.join(q_parts)}")

            text = ". ".join(parts)
            log(f"[Deploy] Overview: {text}")
            async_tts.speak(text)
        except Exception as e:
            log(f"[Deploy] Overview error: {e}")

    def _deploy_cycle(view, category):
        """Cycle through deploy category entities. Jumps cursor to each entity.
        category: 2=orbs, 3=pickups, 4=spawners, 5=shops."""
        try:
            level = view.game.next_level
            if level is None:
                return
            ref = view.deploy_target
            if ref is None:
                return

            # Rebuild list if switching categories
            if _deploy_cycle_cat[0] != category:
                _deploy_cycle_cat[0] = category
                _deploy_cycle_idx[0] = 0

                if category == 2:
                    raw = _deploy_get_orbs(level)
                    items = [(p, x, y, "Memory Orb") for p, x, y in raw]
                elif category == 3:
                    items = _deploy_get_pickups(level)  # Already (prop, x, y, name)
                elif category == 4:
                    raw = _deploy_get_spawners(level)
                    items = [(u, x, y, _name(u)) for u, x, y in raw]
                elif category == 5:
                    items = _deploy_get_interactions(level)  # Already (prop, x, y, name)
                else:
                    return

                # Sort by Chebyshev distance from current cursor
                items.sort(key=lambda e: max(abs(e[1] - ref.x), abs(e[2] - ref.y)))
                _deploy_cycle_items[0] = items

            items = _deploy_cycle_items[0]
            if not items:
                cat_name = _DEPLOY_CAT_NAMES.get(category, "items")
                text = f"No {cat_name}"
                log(f"[Deploy] Cycle: {text}")
                async_tts.speak(text)
                return

            # Get current item
            idx = _deploy_cycle_idx[0] % len(items)
            _entity, x, y, ename = items[idx]

            # For spawners, number duplicates based on current sort order
            if category == 4:
                display_names = _number_deploy_dupes(items)
                ename = display_names[idx][3]

            # Jump cursor (suppress tile announce — we speak our own format)
            view.deploy_target = Level.Point(x, y)
            _last_examine_xy[0] = None  # Reset dedup
            _deploy_tile_suppress[0] = True
            view.try_examine_tile(view.deploy_target)

            # Announce: "Name, quadrant"
            quadrant = _quadrant_label(x, y)
            text = f"{ename}, {quadrant}"
            log(f"[Deploy] Cycle {_DEPLOY_CAT_NAMES.get(category, '?')} [{idx+1}/{len(items)}]: {text}")
            async_tts.speak(text)

            # Advance index (wraps via modulo on next read)
            _deploy_cycle_idx[0] = idx + 1

        except Exception as e:
            log(f"[Deploy] Cycle error: {e}")

    # ---- Gameover / Victory voicing ----
    _gameover_spoken = [False]

    def _announce_gameover(view):
        """Speak game outcome with speak_batched for [/] navigation.
        Victory: narrative sentences as individual chunks.
        Defeat: stats file split by section (turns, spell casts, damage, etc.)."""
        import re as _re_go
        game = view.game
        if not game:
            return
        is_victory = game.victory
        label = "Victory" if is_victory else "Defeat"
        chunks = []

        if is_victory:
            chunks.append("Victory! The Dark Wizard is slain.")
            chunks.append("His beasts have been broken and made tame.")
            chunks.append("The beauty of Avalon will be built again.")
            chunks.append("Your soul is permitted to sleep and dream once more.")
            chunks.append(f"{game.total_turns} total turns.")
        else:
            chunks.append(f"Defeat. Realm {game.level_num}.")

            # Read stats file, split by section for buffer navigation
            try:
                stats_path = os.path.join('saves', str(game.run_number),
                                          'stats.level_%d.txt' % game.level_num)
                if os.path.exists(stats_path):
                    with open(stats_path, 'r') as f:
                        content = f.read().strip()
                    if content:
                        sections = _re_go.split(r'\n\s*\n', content)
                        # Skip first section (Realm/Outcome — already announced)
                        for section in sections[1:]:
                            collapsed = ' '.join(l.strip() for l in section.split('\n') if l.strip())
                            if collapsed:
                                chunks.append(collapsed)
            except Exception:
                chunks.append(f"{game.total_turns} total turns.")

        chunks.append("Press any key to continue.")
        async_tts.speak_batched(chunks)
        log(f"[Gameover] {label}: Realm {game.level_num}, {game.total_turns} turns ({len(chunks)} chunks)")

    def _speak_mod_keybinds():
        """Speak all mod keybind reference. Triggered by Shift+/ (?) in level state."""
        lines = [
            "Mod keybind reference.",
            "F, vitals. HP, shields, status effects.",
            "E, enemy scan. Press repeatedly to cycle, nearest first. Shift reverses.",
            "L, line of sight. Enemy count by type and direction.",
            "N, spawner scan. Press repeatedly to cycle nests. Shift reverses.",
            "Alt plus E, N, or Q, mark or unmark the last scanned target.",
            "Q, landmark scan. Cycle nearest first. Shift Q reverses.",
            "G, charges. Selected spell or all spells.",
            "T, threat. Adjacent enemy count and positions.",
            "D, unit detail. Full stats for unit under cursor.",
            "B, spatial scan. Walkable distances in 8 directions.",
            "X, hazard scan. Clouds and webs.",
            "V, look mode. Cursor to examine tiles.",
            "C, character sheet.",
            "Left control, cancel speech.",
            "Z, repeat last speech.",
            "Left bracket, speech history back. Right bracket, forward.",
            "Slash, game help. Shift slash, this reference.",
            "In deploy: 1 overview, 2 orbs, 3 pickups, 4 spawners, 5 shops.",
            "In shop: Tab for filter guide.",
        ]
        text = " ".join(lines)
        async_tts.speak(text)
        log(f"[Help] Mod keybind reference spoken")

    def patched_process_level_input(self):
        """Intercept mod hotkeys before normal input processing.
        Also detects deploy phase start/abort transitions, turn boundaries,
        gameover/victory voicing, and drives the speech batching flush cycle."""
        deploying = getattr(self.game, 'deploying', False)
        _game_ref[0] = self.game

        # Gameover/victory detection — speak outcome once, then pass through
        # for the "any key → reminisce" transition in the original handler.
        if self.gameover_frames == 0:
            _gameover_spoken[0] = False
        elif not _gameover_spoken[0]:
            _gameover_spoken[0] = True
            batcher.flush()
            _flush_hp()
            _announce_gameover(self)
        if self.gameover_frames > 0:
            _original_process_level_input(self)
            return

        # Turn signal: detect is_awaiting_input False→True transition
        # Suppress during autowalk (#24) and debounce rapid enemy-pass sequences (#32)
        if not deploying:
            awaiting = getattr(self.game.cur_level, 'is_awaiting_input', False)
            if awaiting and not _turn_announced[0]:
                _turn_announced[0] = True
                _turn_count[0] += 1
                now = time.time()
                # Flush queued speech before turn signal, then HP (#39)
                batcher.flush()
                _flush_hp()
                adjacency_tracker.heartbeat()
                _flush_cloud_arrivals()
                _enemy_scanner.turn_reset()
                _spawner_scanner.turn_reset()
                _landmark_scanner.turn_reset()

                # Marked target update — immediate tier: before turn signal
                if _mark_tier_immediate[0] and _marked_target[0] is not None and _turn_count[0] > 1:
                    try:
                        level = self.game.cur_level
                        player = self.game.p1
                        ref = Level.Point(player.x, player.y)
                        update = _get_mark_update(level, ref)
                        if update:
                            async_tts.speak(update)
                            log(f"[Mark] Turn update: {update}")
                    except Exception:
                        pass

                if _turn_count[0] == 1:
                    # Auto-announce enemy/spawner count on level start
                    try:
                        level = self.game.cur_level
                        player = self.game.p1
                        enemies = [u for u in level.units if Level.are_hostile(player, u)]
                        spawners = [u for u in enemies if getattr(u, 'is_lair', False)]
                        parts = [f"{len(enemies)} enem{'y' if len(enemies) == 1 else 'ies'}"]
                        if spawners:
                            parts.append(f"{len(spawners)} spawner{'s' if len(spawners) != 1 else ''}")
                        text = ", ".join(parts)
                        log(f"[Level Start] {text}")
                        async_tts.speak(text)
                    except Exception:
                        pass
                elif (_turn_count[0] > 1
                        and not getattr(self, 'path', None)
                        and now - _last_turn_time[0] > 0.5):
                    _last_turn_time[0] = now
                    text = f"Turn {_turn_count[0]}"
                    log(f"[Turn] {text}")
                    async_tts.speak(text)

                # Marked target update — turn-end tier: after turn signal
                if not _mark_tier_immediate[0] and _marked_target[0] is not None and _turn_count[0] > 1:
                    try:
                        level = self.game.cur_level
                        player = self.game.p1
                        ref = Level.Point(player.x, player.y)
                        update = _get_mark_update(level, ref)
                        if update:
                            async_tts.speak(update)
                            log(f"[Mark] Turn update: {update}")
                    except Exception:
                        pass

        # Deploy start detection
        if deploying and not _was_deploying[0]:
            _was_deploying[0] = True
            _deploy_reset_cycle()
            _announce_deploy_overview(self)

        try:
            for evt in self.events:
                if evt.type != pygame.KEYDOWN:
                    continue
                # Reset scan cycling on keys that aren't the respective scan key
                if evt.key != pygame.K_e:
                    _enemy_scanner.reset()
                if evt.key != pygame.K_n:
                    _spawner_scanner.reset()
                if evt.key != pygame.K_q:
                    _landmark_scanner.reset()
                # Deploy-only number keys: overview (1) and category cycling (2-5)
                if deploying and evt.key == pygame.K_1:
                    _announce_deploy_overview(self)
                elif deploying and evt.key == pygame.K_2:
                    _deploy_cycle(self, 2)
                elif deploying and evt.key == pygame.K_3:
                    _deploy_cycle(self, 3)
                elif deploying and evt.key == pygame.K_4:
                    _deploy_cycle(self, 4)
                elif deploying and evt.key == pygame.K_5:
                    _deploy_cycle(self, 5)
                elif evt.key == pygame.K_f:
                    _query_vitals(self)
                elif evt.key == pygame.K_e:
                    mods = pygame.key.get_mods()
                    if mods & pygame.KMOD_ALT:
                        _mark_scanned_target()
                    else:
                        ref, lvl, qual = _get_scan_reference(self)
                        rev = bool(mods & pygame.KMOD_SHIFT)
                        _query_enemies(self, scan_level=lvl, ref_point=ref, qualifier=qual, reverse=rev)
                elif evt.key == pygame.K_n:
                    mods = pygame.key.get_mods()
                    if mods & pygame.KMOD_ALT:
                        _mark_scanned_target()
                    else:
                        ref, lvl, qual = _get_scan_reference(self)
                        rev = bool(mods & pygame.KMOD_SHIFT)
                        _query_spawners(self, scan_level=lvl, ref_point=ref, qualifier=qual, reverse=rev)
                elif evt.key == pygame.K_g:
                    _query_charges(self)
                elif evt.key == pygame.K_q:
                    mods = pygame.key.get_mods()
                    if mods & pygame.KMOD_ALT:
                        _mark_scanned_target()
                    else:
                        ref, lvl, qual = _get_scan_reference(self)
                        rev = bool(mods & pygame.KMOD_SHIFT)
                        _query_landmarks(self, scan_level=lvl, ref_point=ref, qualifier=qual, reverse=rev)
                elif evt.key == pygame.K_x:
                    ref, lvl, qual = _get_scan_reference(self)
                    _query_hazards(self, scan_level=lvl, ref_point=ref, qualifier=qual)
                elif evt.key == pygame.K_l:
                    ref, lvl, qual = _get_scan_reference(self)
                    _query_los_summary(self, scan_level=lvl, ref_point=ref, qualifier=qual)
                elif evt.key == pygame.K_LCTRL:
                    async_tts.cancel()
                    _cancel_hp_announcement()
                    batcher.clear()
                    log("[Speech] Cancelled")
                elif evt.key == pygame.K_z:
                    # Repeat at current cursor position (don't add to history)
                    idx = async_tts._cursor
                    hist = async_tts._history
                    if hist:
                        entry = hist[idx] if idx >= 0 else hist[-1]
                        async_tts.base_tts.cancel()
                        async_tts.base_tts.speak(entry)
                        log(f"[Repeat] {entry}")
                elif evt.key == pygame.K_LEFTBRACKET:
                    async_tts.history_back()
                    idx = async_tts._cursor
                    if idx >= 0:
                        log(f"[History] Back ({idx+1}/{len(async_tts._history)})")
                elif evt.key == pygame.K_RIGHTBRACKET:
                    async_tts.history_forward()
                    idx = async_tts._cursor
                    pos = idx + 1 if idx >= 0 else len(async_tts._history)
                    log(f"[History] Forward ({pos}/{len(async_tts._history)})")
                elif evt.key == pygame.K_d:
                    _query_unit_detail(self)
                elif evt.key == pygame.K_t:
                    ref, lvl, qual = _get_scan_reference(self)
                    _query_threat(self, scan_level=lvl, ref_point=ref, qualifier=qual)
                elif evt.key == pygame.K_b:
                    ref, lvl, qual = _get_scan_reference(self)
                    _query_space(self, scan_level=lvl, ref_point=ref, qualifier=qual)
                elif evt.key == pygame.K_SLASH and (pygame.key.get_mods() & pygame.KMOD_SHIFT):
                    _speak_mod_keybinds()
                    # Consume event so game doesn't also open Help screen
                    self.events = [e for e in self.events if not (e.type == pygame.KEYDOWN and e.key == pygame.K_SLASH)]
        except Exception as e:
            log(f"[Hotkey] Error: {e}")

        # ---- RCtrl+Arrow diagonal movement ----
        # Intercept arrow keys when Right Ctrl is held, convert to diagonal movement.
        # Must happen before the game sees the arrow event.
        # Counterclockwise mapping: RCtrl+Up=NW, RCtrl+Right=NE, RCtrl+Down=SE, RCtrl+Left=SW
        _RCTRL_DIAG_MAP = {
            pygame.K_UP: Level.Point(-1, -1),     # NW
            pygame.K_RIGHT: Level.Point(1, -1),   # NE
            pygame.K_DOWN: Level.Point(1, 1),      # SE
            pygame.K_LEFT: Level.Point(-1, 1),     # SW
        }
        _diag_consumed = []
        if self.can_execute_inputs():
            keys = pygame.key.get_pressed()
            # Also accept LCtrl+Alt (AltGr on European/Spanish keyboards sends LCtrl+RAlt)
            _diag_trigger = keys[pygame.K_RCTRL] or (
                keys[pygame.K_LCTRL] and (keys[pygame.K_LALT] or keys[pygame.K_RALT]))
            if _diag_trigger:
                for evt in self.events:
                    if evt.type == pygame.KEYDOWN and evt.key in _RCTRL_DIAG_MAP:
                        movedir = _RCTRL_DIAG_MAP[evt.key]
                        if self.cur_spell:
                            new_target = Level.Point(
                                self.cur_spell_target.x + movedir.x,
                                self.cur_spell_target.y + movedir.y)
                            if self.game.cur_level.is_point_in_bounds(new_target):
                                self.cur_spell_target = new_target
                                self.try_examine_tile(new_target)
                        elif deploying and self.deploy_target:
                            new_point = Level.Point(
                                self.deploy_target.x + movedir.x,
                                self.deploy_target.y + movedir.y)
                            if self.game.next_level.is_point_in_bounds(new_point):
                                self.deploy_target = new_point
                                self.try_examine_tile(new_point)
                        else:
                            self.try_move(movedir)
                            self.cur_spell_target = None
                        _diag_consumed.append(evt)
                if _diag_consumed:
                    self.events = [e for e in self.events if e not in _diag_consumed]

        # Capture cursor AFTER our hotkeys, BEFORE game's native input (arrows/mouse)
        _pre_native_pos = None
        if deploying and self.deploy_target:
            _pre_native_pos = (self.deploy_target.x, self.deploy_target.y)

        _original_process_level_input(self)

        # Guard: enter_reminisce() sets self.game = None during gameover transition.
        # All post-processing below requires a valid game reference.
        if self.game is None:
            return

        # Deploy: reset cycle if cursor moved via arrows/mouse (detected by
        # position change during _original_process_level_input, not our cycle jump)
        if deploying and _pre_native_pos and self.deploy_target:
            new_pos = (self.deploy_target.x, self.deploy_target.y)
            if new_pos != _pre_native_pos:
                _deploy_reset_cycle()

        # Turn signal: reset when player acts (is_awaiting_input goes False)
        # Start batching when player acts — events during enemy turn get queued
        if not getattr(self.game.cur_level, 'is_awaiting_input', True):
            if _turn_announced[0]:
                batcher.start_batching()
            _turn_announced[0] = False

        # Post-processing: deploy abort detection
        # (Confirm is handled by patched_deploy, which sets _was_deploying = False first)
        if not getattr(self.game, 'deploying', False) and _was_deploying[0]:
            _was_deploying[0] = False
            _deploy_reset_cycle()
            async_tts.speak("Deploy aborted")
            log("[Deploy] Aborted")

    _PyGameView.process_level_input = patched_process_level_input
    log("  Custom hotkeys installed (F=Vitals, E=Enemies, Q=Landmarks, G=Charges, D=Detail, T=Threat, B=Space, LCtrl=Cancel, Z=Repeat, [/]=History, Deploy:1-5)")

    # ---- Deploy Confirm Hook ----

    _original_deploy = _PyGameView.deploy

    def patched_deploy(self, p):
        """Announce successful deployment."""
        level_before = getattr(self.game, 'level_num', 0)
        _original_deploy(self, p)
        try:
            level_after = getattr(self.game, 'level_num', 0)
            if level_after > level_before:
                _was_deploying[0] = False
                _deploy_reset_cycle()
                async_tts.speak(f"Deployed. Level {level_after}")
                log(f"[Deploy] Confirmed - Level {level_after}")
        except Exception as e:
            log(f"[Deploy] Confirm error: {e}")

    _PyGameView.deploy = patched_deploy
    log("  Deploy confirm hook installed")

    # ---- Rift Reroll Feedback Hook ----
    import Game as _Game_module

    _original_try_reroll = _Game_module.Game.try_reroll_rifts

    def patched_try_reroll_rifts(self):
        """Announce rift reroll success or failure."""
        _game_ref[0] = self
        if self.rift_rerolls:
            _original_try_reroll(self)
            remaining = self.rift_rerolls
            text = f"Rifts rerolled, {remaining} remaining" if remaining else "Rifts rerolled, none remaining"
            async_tts.speak(text)
            log(f"[Reroll] {text}")
        else:
            async_tts.speak("No rerolls")
            log("[Reroll] No rerolls available")

    _Game_module.Game.try_reroll_rifts = patched_try_reroll_rifts
    log("  Rift reroll feedback hook installed")

    # ---- Movement Feedback: Direction + Wall Bumps ----
    # Hook try_move to announce cardinal direction on first step in a new direction,
    # and "Blocked" on wall bumps (once per blocked direction to prevent spam).
    # Melee attacks (walking into enemies) are excluded — on_spell_cast handles those.

    _original_try_move = _PyGameView.try_move
    _last_move_dir = [None]     # (dx, dy) of last successful move direction
    _last_blocked_dir = [None]  # (dx, dy) of last blocked direction (prevents spam)
    _last_terrain_class = [None]  # Terrain classification for transition detection (S53)

    def patched_try_move(self, movedir):
        """Announce movement direction on direction changes, 'Blocked' on wall bumps.
        Auto-walk (self.path non-empty) suppresses all speech to avoid rapid-fire spam."""
        # Auto-walk in progress — execute silently
        if getattr(self, 'path', None):
            return _original_try_move(self, movedir)

        # Pre-check: is there a hostile at the destination? (melee attack, not movement)
        is_melee = False
        try:
            new_x = self.game.p1.x + movedir.x
            new_y = self.game.p1.y + movedir.y
            blocker = self.game.cur_level.get_unit_at(new_x, new_y)
            if blocker and Level.are_hostile(self.game.p1, blocker):
                is_melee = True
        except:
            pass

        result = _original_try_move(self, movedir)
        try:
            if result and not is_melee:
                # Actual movement — announce direction on change.
                # With coords enabled: speak every step (coord is new info each step).
                # Repeated direction + coords: speak coord only (no direction repeat).
                _last_blocked_dir[0] = None
                dir_tuple = (movedir.x, movedir.y)
                direction_changed = dir_tuple != _last_move_dir[0]
                if direction_changed:
                    _last_move_dir[0] = dir_tuple
                dir_name = _cardinal_direction(movedir.x, movedir.y)
                if dir_name and (direction_changed or cfg.show_coordinates):
                    # p1.x/y is not updated synchronously — compute destination from movedir
                    px, py = self.game.p1.x + movedir.x, self.game.p1.y + movedir.y
                    if cfg.show_coordinates:
                        text = f"{dir_name} ({px},{py})" if direction_changed else f"({px},{py})"
                    else:
                        text = dir_name
                    async_tts.speak(text)
                    log(f"[Move] ({px},{py}) {dir_name}")
                # Passive terrain classification — announce on transition only (S53)
                try:
                    tc, axis = _classify_terrain(self.game.cur_level,
                                                 self.game.p1.x, self.game.p1.y)
                    if tc != _last_terrain_class[0]:
                        _last_terrain_class[0] = tc
                        if tc in _TERRAIN_LABELS:
                            terrain_text = _TERRAIN_LABELS[tc](axis)
                            async_tts.speak(terrain_text)
                            log(f"[Terrain] ({self.game.p1.x},{self.game.p1.y}) {terrain_text}")
                except Exception as e:
                    log(f"[Terrain] Error: {e}")
            elif result and is_melee:
                # Melee attack — reset direction tracking, let on_spell_cast handle speech
                _last_move_dir[0] = None
            elif not result:
                # Failed move — announce obstacle type once per direction (#28)
                # If deploy screen just activated, suppress — overview will speak
                if getattr(self.game, 'deploying', False):
                    _last_move_dir[0] = None
                    _last_blocked_dir[0] = None
                else:
                    dir_tuple = (movedir.x, movedir.y)
                    if dir_tuple != _last_blocked_dir[0]:
                        _last_blocked_dir[0] = dir_tuple
                        _last_move_dir[0] = None
                        obstacle = "Blocked"
                        try:
                            bx = self.game.p1.x + movedir.x
                            by = self.game.p1.y + movedir.y
                            dest_tile = self.game.cur_level.tiles[bx][by]
                            if dest_tile.is_chasm:
                                obstacle = "Impossible, chasm"
                            elif dest_tile.is_wall():
                                obstacle = "Impossible, wall"
                            else:
                                blocker = self.game.cur_level.get_unit_at(bx, by)
                                if blocker:
                                    obstacle = f"Blocked by {_name(blocker)}"
                        except (IndexError, KeyError):
                            obstacle = "Impossible, edge"
                        except Exception:
                            pass
                        async_tts.speak(obstacle)
                        log(f"[Move] ({self.game.p1.x},{self.game.p1.y}) {obstacle}")
        except Exception as e:
            log(f"[Move] Error: {e}")
        return result

    _PyGameView.try_move = patched_try_move
    log("  Movement feedback hook installed")

    # ========================================================================
    # CENTRALIZED STATE TRANSITION DETECTION
    # ========================================================================
    # Tracks self.state every frame via draw_screen hook. On any state change,
    # announces the new state. Per-state input processor patches (below) handle
    # richer content voicing; this guarantees no transition is ever silent.
    # ========================================================================

    # All state constants
    _STATE_LEVEL = getattr(_main, 'STATE_LEVEL', 0)
    _STATE_CHAR_SHEET = getattr(_main, 'STATE_CHAR_SHEET', 1)
    _STATE_SHOP = getattr(_main, 'STATE_SHOP', 2)
    _STATE_TITLE = getattr(_main, 'STATE_TITLE', 3)
    _STATE_OPTIONS = getattr(_main, 'STATE_OPTIONS', 4)
    _STATE_MESSAGE = getattr(_main, 'STATE_MESSAGE', 5)
    _STATE_CONFIRM = getattr(_main, 'STATE_CONFIRM', 6)
    _STATE_REMINISCE = getattr(_main, 'STATE_REMINISCE', 7)
    _STATE_REBIND = getattr(_main, 'STATE_REBIND', 8)
    _STATE_COMBAT_LOG = getattr(_main, 'STATE_COMBAT_LOG', 9)
    _STATE_PICK_MODE = getattr(_main, 'STATE_PICK_MODE', 10)
    _STATE_PICK_TRIAL = getattr(_main, 'STATE_PICK_TRIAL', 11)
    _STATE_SETUP_CUSTOM = getattr(_main, 'STATE_SETUP_CUSTOM', 12)
    _STATE_PICK_MUTATOR_PARAMS = getattr(_main, 'STATE_PICK_MUTATOR_PARAMS', 13)
    _STATE_ENTER_MUTATOR_VALUE = getattr(_main, 'STATE_ENTER_MUTATOR_VALUE', 14)

    # Human-readable state names for announcement
    _STATE_NAMES = {
        _STATE_LEVEL: "Level",
        _STATE_CHAR_SHEET: "Character Sheet",
        _STATE_SHOP: "Shop",
        _STATE_TITLE: "Rift Wizard 2",
        _STATE_OPTIONS: "Options",
        _STATE_MESSAGE: "Message",
        _STATE_CONFIRM: "Confirm",
        _STATE_REMINISCE: "Run Complete",
        _STATE_REBIND: "Key Rebind",
        _STATE_COMBAT_LOG: "Combat Log",
        _STATE_PICK_MODE: "Select Game Mode",
        _STATE_PICK_TRIAL: "Select Trial",
        _STATE_SETUP_CUSTOM: "Custom Mutator Setup",
        _STATE_PICK_MUTATOR_PARAMS: "Mutator Parameters",
        _STATE_ENTER_MUTATOR_VALUE: "Enter Mutator Value",
    }

    # States that are NOT YET VOICED — announce "coming soon" on entry
    # These have no input processor patch, so this is the only speech they get.
    _UNVOICED_STATES = {
        _STATE_REBIND,
        _STATE_SETUP_CUSTOM,
        _STATE_PICK_MUTATOR_PARAMS,
        _STATE_ENTER_MUTATOR_VALUE,
    }

    # States where the per-state input patch already handles a richer entry
    # announcement. The centralized hook skips these to avoid double-speaking.
    _SELF_ANNOUNCING_STATES = {
        _STATE_CONFIRM,
        _STATE_TITLE,
        _STATE_PICK_MODE,
        _STATE_PICK_TRIAL,
        _STATE_MESSAGE,
        _STATE_OPTIONS,
        _STATE_REMINISCE,
        _STATE_COMBAT_LOG,
        _STATE_CHAR_SHEET,  # open_char_sheet hook announces
        _STATE_SHOP,        # open_shop hook announces
    }

    # KEY_BIND constants for keybind resolution
    _KB_UP = getattr(_main, 'KEY_BIND_UP', 0)
    _KB_DOWN = getattr(_main, 'KEY_BIND_DOWN', 1)
    _KB_LEFT = getattr(_main, 'KEY_BIND_LEFT', 2)
    _KB_RIGHT = getattr(_main, 'KEY_BIND_RIGHT', 3)
    _KB_CONFIRM = getattr(_main, 'KEY_BIND_CONFIRM', 9)
    _KB_ABORT = getattr(_main, 'KEY_BIND_ABORT', 10)

    def _key_name(view, bind_id):
        """Resolve a KEY_BIND_* to a human-readable key name from current bindings."""
        import pygame
        try:
            keys = view.key_binds.get(bind_id, [])
            for k in keys:
                if k is not None:
                    return pygame.key.name(k)
        except:
            pass
        return "?"

    # Suppression flag — set False to silence keybind announcements once players
    # are comfortable. Can be wired to a config toggle later.
    _ANNOUNCE_KEYBINDS = True

    def _get_state_keybinds(view, state):
        """Return keybind help string for a state, or '' if none/suppressed."""
        if not _ANNOUNCE_KEYBINDS:
            return ""

        up = _key_name(view, _KB_UP)
        down = _key_name(view, _KB_DOWN)
        left = _key_name(view, _KB_LEFT)
        right = _key_name(view, _KB_RIGHT)
        confirm = _key_name(view, _KB_CONFIRM)
        abort = _key_name(view, _KB_ABORT)
        nav_ud = f"{up} and {down} to navigate"
        nav_lr = f"{left} and {right}"

        if state == _STATE_TITLE:
            return f"{nav_ud}. {confirm} to select"

        if state in (_STATE_PICK_MODE, _STATE_PICK_TRIAL):
            return f"{nav_ud}. {confirm} to select. {abort} to go back"

        if state == _STATE_OPTIONS:
            return f"{nav_ud}. {nav_lr} to adjust. {abort} to close"

        if state == _STATE_MESSAGE:
            # Mod adds [ ] for chunk navigation on batched messages
            return f"{confirm} to advance. left bracket for previous. {abort} to close"

        if state == _STATE_CONFIRM:
            return f"{nav_lr} to toggle. {confirm} to accept"

        if state == _STATE_REMINISCE:
            return f"{nav_lr} to browse slides. {abort} to exit"

        if state == _STATE_COMBAT_LOG:
            return f"{nav_ud} to scroll. {nav_lr} to change turn. {abort} to close"

        if state == _STATE_CHAR_SHEET:
            return f"{nav_ud}. {nav_lr} to switch sections. {confirm} to select. {abort} to close"

        if state == _STATE_SHOP:
            shop_type = getattr(view, 'shop_type', -1)
            if shop_type == _SHOP_TYPE_BESTIARY:
                return f"{nav_ud}. {nav_lr} for pages. {abort} to close"
            elif shop_type == _SHOP_TYPE_SPELLS:
                # Learn Spell: explain owned-spell upgrade flow
                return (f"{nav_ud}. {nav_lr} for pages. {confirm} to buy. "
                        f"{confirm} on owned spell to view upgrades. "
                        f"{abort} to close. Letter keys to filter. Tab for filter guide")
            elif shop_type == _SHOP_TYPE_UPGRADES:
                # Learn Skill
                return (f"{nav_ud}. {nav_lr} for pages. {confirm} to buy. "
                        f"{abort} to close. Letter keys to filter. Tab for filter guide")
            elif shop_type == _SHOP_TYPE_SPELL_UPGRADES:
                # Spell upgrade picker
                return f"{nav_ud}. {confirm} to buy upgrade. {abort} to go back"
            else:
                # SHOP_TYPE_SHOP (level shops)
                return f"{nav_ud}. {confirm} to select. {abort} to close"

        # STATE_LEVEL and unvoiced states — no keybinds announced
        return ""

    _prev_state = [None]
    _original_draw_screen = _PyGameView.draw_screen

    _pending_keybinds = [None]  # Deferred keybind speech — spoken on next frame

    def _patched_draw_screen(self, color=None):
        """Centralized state transition detector. Runs every frame.
        Announces state name for non-self-announcing states, and defers
        keybind help to next frame so it speaks after all state-entry content."""
        cur = self.state

        # Speak deferred keybinds from previous frame's transition
        if _pending_keybinds[0] is not None:
            kb = _pending_keybinds[0]
            _pending_keybinds[0] = None
            async_tts.speak(kb)
            log(f"[State] Keybinds: {kb}")

        if cur != _prev_state[0]:
            old_name = _STATE_NAMES.get(_prev_state[0], str(_prev_state[0]))
            new_name = _STATE_NAMES.get(cur, f"Unknown State {cur}")
            log(f"[State] Transition: {old_name} → {new_name}")

            keybinds = _get_state_keybinds(self, cur)

            if cur in _UNVOICED_STATES:
                # NOT YET VOICED — tell the player clearly, no keybinds
                async_tts.speak(f"{new_name}. Coming soon, not currently accessible")
                log(f"[State] {new_name}: unvoiced state, announced coming soon")
            elif cur not in _SELF_ANNOUNCING_STATES:
                # State has no per-state patch AND is not unvoiced — announce name
                # Currently this covers STATE_LEVEL only (no keybinds for Level)
                async_tts.speak(new_name)
                log(f"[State] Announced: {new_name}")
            # else: self-announcing states handle their own entry speech

            # Defer keybind help to next frame — after all state-entry hooks finish
            if keybinds and cur not in _UNVOICED_STATES:
                _pending_keybinds[0] = keybinds

            _prev_state[0] = cur

        _original_draw_screen(self, color)

    _PyGameView.draw_screen = _patched_draw_screen
    log("  Centralized state transition detector installed")

    # ========================================================================
    # STATE SCREEN VOICING
    # ========================================================================
    # Voice navigation for non-gameplay state screens: title, options, confirm,
    # pick mode, pick trial, message, reminisce, combat log.
    # Pattern: wrap process_*_input; detect entry (first call) and selection
    # changes (compare before/after original call).
    # ========================================================================

    # ---- STATE_CONFIRM (Yes/No confirmation dialogs) ----
    _orig_process_confirm = _PyGameView.process_confirm_input
    _sr_confirm_entered = [False]

    def _patched_process_confirm(self):
        if not _sr_confirm_entered[0]:
            _sr_confirm_entered[0] = True
            prompt = getattr(self, 'confirm_text', '') or "Confirm?"
            sel = "Yes" if self.examine_target else "No"
            async_tts.speak(f"{prompt} {sel}")
            log(f"[State] CONFIRM entered: {prompt} → {sel}")

        prev_sel = self.examine_target
        _orig_process_confirm(self)

        if self.state != _STATE_CONFIRM:
            _sr_confirm_entered[0] = False
        elif self.examine_target != prev_sel:
            sel = "Yes" if self.examine_target else "No"
            async_tts.speak(sel)
            log(f"[State] CONFIRM: {sel}")

    _PyGameView.process_confirm_input = _patched_process_confirm
    log("  Confirm dialog voicing installed")

    # ---- STATE_TITLE (main menu) ----
    _orig_process_title = _PyGameView.process_title_input
    _sr_title_entered = [False]
    _sr_title_labels = {
        0: "Continue Run",
        1: "Abandon Run",
        2: "New Game",
        3: "Options",
        4: "Bestiary",
        5: "Discord",
        6: "Quit",
    }

    def _patched_process_title(self):
        if not _sr_title_entered[0]:
            _sr_title_entered[0] = True
            async_tts.speak("Rift Wizard 2")
            log("[State] TITLE entered")

        prev_sel = self.examine_target
        _orig_process_title(self)

        if self.state != _STATE_TITLE:
            _sr_title_entered[0] = False
        elif self.examine_target != prev_sel and self.examine_target is not None:
            label = _sr_title_labels.get(self.examine_target, f"Option {self.examine_target}")
            async_tts.speak(label)
            log(f"[State] TITLE: {label}")

    _PyGameView.process_title_input = _patched_process_title
    log("  Title menu voicing installed")

    # ---- STATE_PICK_MODE (game mode selection) ----
    _orig_process_pick_mode = _PyGameView.process_pick_mode_input
    _sr_pick_mode_entered = [False]
    _sr_mode_labels = {
        0: "Normal Game",
        1: "Archmage Trials",
        2: "Weekly Run",
        3: "Mutated Run",
        4: "Custom Run",
    }

    def _patched_process_pick_mode(self):
        if not _sr_pick_mode_entered[0]:
            _sr_pick_mode_entered[0] = True
            label = _sr_mode_labels.get(self.examine_target, "")
            async_tts.speak(f"Select Game Mode. {label}" if label else "Select Game Mode")
            log("[State] PICK_MODE entered")

        prev_sel = self.examine_target
        _orig_process_pick_mode(self)

        if self.state != _STATE_PICK_MODE:
            _sr_pick_mode_entered[0] = False
        elif self.examine_target != prev_sel and self.examine_target is not None:
            label = _sr_mode_labels.get(self.examine_target, f"Mode {self.examine_target}")
            async_tts.speak(label)
            log(f"[State] PICK_MODE: {label}")

    _PyGameView.process_pick_mode_input = _patched_process_pick_mode
    log("  Pick mode voicing installed")

    # ---- STATE_PICK_TRIAL (trial picker) ----
    _orig_process_pick_trial = _PyGameView.process_pick_trial_input
    _sr_pick_trial_entered = [False]

    def _patched_process_pick_trial(self):
        if not _sr_pick_trial_entered[0]:
            _sr_pick_trial_entered[0] = True
            name = getattr(self.examine_target, 'name', '') if self.examine_target else ''
            async_tts.speak(f"Select Trial. {name}" if name else "Select Trial")
            log("[State] PICK_TRIAL entered")

        prev_sel = self.examine_target
        _orig_process_pick_trial(self)

        if self.state != _STATE_PICK_TRIAL:
            _sr_pick_trial_entered[0] = False
        elif self.examine_target != prev_sel and self.examine_target is not None:
            name = getattr(self.examine_target, 'name', str(self.examine_target))
            desc = ''
            try:
                desc = self.examine_target.get_description()
            except:
                pass
            msg = f"{name}. {desc}" if desc else name
            async_tts.speak(msg)
            log(f"[State] PICK_TRIAL: {name}")

    _PyGameView.process_pick_trial_input = _patched_process_pick_trial
    log("  Pick trial voicing installed")

    # ---- STATE_MESSAGE (intro text, help text) ----
    # Splits large text blocks into buffer-navigable chunks so [/] can
    # step through individual keybindings, status effects, etc.
    import re as _re

    def _split_message_for_speech(msg):
        """Split message text into buffer-navigable chunks.
        Keybinding lines and status effects become individual entries.
        Narrative paragraphs stay grouped."""
        chunks = []
        paragraphs = _re.split(r'\n\s*\n', msg.strip())

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            lines = [l.strip() for l in para.split('\n') if l.strip()]

            binding_entries = []
            for line in lines:
                # Skip numpad grid visual lines (just digits and spaces)
                if _re.match(r'^[\d\s]+$', line):
                    continue
                # Numpad layout "4   6  ->" line: extract description
                if '->' in line and _re.match(r'^\d', line):
                    desc = line.split('->')[-1].strip()
                    if desc:
                        binding_entries.append(f"Numpad: {desc}")
                    continue
                # Multi-binding lines (3+ spaces between entries)
                parts = _re.split(r'\s{3,}', line)
                if len(parts) > 1 and all(':' in p for p in parts if p.strip()):
                    for p in parts:
                        p = p.strip()
                        if p:
                            binding_entries.append(p)
                else:
                    binding_entries.append(line)

            # Decide: individual entries (keybinding/status block) vs one chunk
            has_colons = sum(1 for e in binding_entries if ':' in e)
            if has_colons >= 2 and len(binding_entries) > 1:
                # Keybinding or status effect block: each entry is a chunk
                chunks.extend(binding_entries)
            else:
                # Narrative paragraph: collapse to one chunk
                chunks.append(' '.join(binding_entries) if binding_entries else para)

        return chunks if len(chunks) > 1 else [msg]

    def _speak_message(msg):
        """Speak a message screen, batching into history chunks if multi-part."""
        chunks = _split_message_for_speech(msg)
        if len(chunks) > 1:
            async_tts.speak_batched(chunks)
            log(f"[State] MESSAGE batched: {len(chunks)} chunks")
        else:
            async_tts.speak(msg)

    _orig_process_message = _PyGameView.process_message_input
    _sr_message_entered = [False]
    _sr_last_message = [None]

    def _patched_process_message(self):
        msg = getattr(self, 'message', '') or ''
        if not _sr_message_entered[0]:
            _sr_message_entered[0] = True
            _sr_last_message[0] = msg
            if msg:
                _speak_message(msg)
            log(f"[State] MESSAGE entered ({len(msg)} chars)")

        _orig_process_message(self)

        if self.state != _STATE_MESSAGE:
            _sr_message_entered[0] = False
            _sr_last_message[0] = None
        else:
            new_msg = getattr(self, 'message', '') or ''
            if new_msg != _sr_last_message[0]:
                _sr_last_message[0] = new_msg
                if new_msg:
                    _speak_message(new_msg)
                log(f"[State] MESSAGE advanced ({len(new_msg)} chars)")

    _PyGameView.process_message_input = _patched_process_message
    log("  Message screen voicing installed")

    # ---- STATE_OPTIONS (settings menu) ----
    _orig_process_options = _PyGameView.process_options_input
    _sr_options_entered = [False]
    _OPTION_HELP = 0
    _OPTION_SOUND_VOLUME = 1
    _OPTION_MUSIC_VOLUME = 2
    _OPTION_SPELL_SPEED = 3
    _OPTION_CONTROLS = 4
    _OPTION_RETURN = 5
    _OPTION_EXIT = 6

    def _options_label(view, idx):
        """Build spoken label for an options menu item, including current value."""
        if idx == _OPTION_HELP:
            return "How to Play"
        elif idx == _OPTION_SOUND_VOLUME:
            vol = view.options.get('sound_volume', 0)
            return f"Sound Volume {vol}"
        elif idx == _OPTION_MUSIC_VOLUME:
            vol = view.options.get('music_volume', 0)
            return f"Music Volume {vol}"
        elif idx == _OPTION_SPELL_SPEED:
            speed = view.options.get('spell_speed', 0)
            names = {0: 'normal', 1: 'fast', 2: 'turbo', 3: 'Xturbo'}
            return f"Animation Speed {names.get(speed, speed)}"
        elif idx == _OPTION_CONTROLS:
            return "Rebind Controls"
        elif idx == _OPTION_RETURN:
            return "Return to Game"
        elif idx == _OPTION_EXIT:
            if view.game:
                return "Save and Exit"
            else:
                return "Back to Title"
        return f"Option {idx}"

    def _patched_process_options(self):
        if not _sr_options_entered[0]:
            _sr_options_entered[0] = True
            label = _options_label(self, self.examine_target) if self.examine_target is not None else ""
            async_tts.speak(f"Options. {label}" if label else "Options")
            log("[State] OPTIONS entered")

        prev_sel = self.examine_target
        prev_sound = self.options.get('sound_volume', 0)
        prev_music = self.options.get('music_volume', 0)
        prev_speed = self.options.get('spell_speed', 0)
        _orig_process_options(self)

        if self.state != _STATE_OPTIONS:
            _sr_options_entered[0] = False
        elif self.examine_target != prev_sel and self.examine_target is not None:
            async_tts.speak(_options_label(self, self.examine_target))
            log(f"[State] OPTIONS: {_options_label(self, self.examine_target)}")
        else:
            # Check if a value changed (Left/Right on volume/speed)
            cur_sound = self.options.get('sound_volume', 0)
            cur_music = self.options.get('music_volume', 0)
            cur_speed = self.options.get('spell_speed', 0)
            if cur_sound != prev_sound or cur_music != prev_music or cur_speed != prev_speed:
                async_tts.speak(_options_label(self, self.examine_target))
                log(f"[State] OPTIONS value: {_options_label(self, self.examine_target)}")

    _PyGameView.process_options_input = _patched_process_options
    log("  Options menu voicing installed")

    # ---- STATE_REMINISCE (post-game slideshow) ----
    _orig_process_reminisce = _PyGameView.process_reminisce_input
    _sr_reminisce_entered = [False]

    def _reminisce_slide_label(view):
        """Describe current reminisce slide from filename."""
        try:
            imgs = view.reminisce_imgs
            idx = view.reminisce_index
            total = len(imgs)
            fn = os.path.basename(imgs[idx])
            # Filenames: level_N_begin.png, level_N_finish.png
            fn_clean = fn.replace('.png', '').replace('level_', '')
            if '_begin' in fn_clean:
                level = fn_clean.replace('_begin', '')
                return f"Level {level} start. Slide {idx + 1} of {total}"
            elif '_finish' in fn_clean:
                level = fn_clean.replace('_finish', '')
                return f"Level {level} end. Slide {idx + 1} of {total}"
            else:
                return f"Slide {idx + 1} of {total}"
        except:
            return "Slide"

    def _patched_process_reminisce(self):
        if not _sr_reminisce_entered[0]:
            _sr_reminisce_entered[0] = True
            async_tts.speak(f"Run Complete. {_reminisce_slide_label(self)}")
            log("[State] REMINISCE entered")

        prev_idx = self.reminisce_index
        _orig_process_reminisce(self)

        if self.state != _STATE_REMINISCE:
            _sr_reminisce_entered[0] = False
        elif self.reminisce_index != prev_idx:
            async_tts.speak(_reminisce_slide_label(self))
            log(f"[State] REMINISCE: slide {self.reminisce_index}")

    _PyGameView.process_reminisce_input = _patched_process_reminisce
    log("  Reminisce slideshow voicing installed")

    # ---- STATE_COMBAT_LOG (combat log viewer) ----
    _orig_process_combat_log = _PyGameView.process_combat_log_input
    _sr_combat_log_entered = [False]

    def _combat_log_header(view):
        return f"Level {view.combat_log_level}, Turn {view.combat_log_turn}"

    def _combat_log_current_line(view):
        """Get the line at the current scroll offset."""
        try:
            lines = view.combat_log_lines
            idx = 1 + view.combat_log_offset
            if 0 <= idx < len(lines):
                return lines[idx]
        except:
            pass
        return ""

    def _patched_process_combat_log(self):
        if not _sr_combat_log_entered[0]:
            _sr_combat_log_entered[0] = True
            header = _combat_log_header(self)
            line = _combat_log_current_line(self)
            msg = f"Combat Log. {header}. {line}" if line else f"Combat Log. {header}"
            async_tts.speak(msg)
            log(f"[State] COMBAT_LOG entered: {header}")

        prev_offset = self.combat_log_offset
        prev_turn = self.combat_log_turn
        prev_level = self.combat_log_level
        _orig_process_combat_log(self)

        if self.state != _STATE_COMBAT_LOG:
            _sr_combat_log_entered[0] = False
        elif self.combat_log_turn != prev_turn or self.combat_log_level != prev_level:
            # Turn or level changed (Left/Right)
            header = _combat_log_header(self)
            line = _combat_log_current_line(self)
            msg = f"{header}. {line}" if line else header
            async_tts.speak(msg)
            log(f"[State] COMBAT_LOG: {header}")
        elif self.combat_log_offset != prev_offset:
            # Scrolled within same turn
            line = _combat_log_current_line(self)
            if line:
                async_tts.speak(line)
                log(f"[State] COMBAT_LOG line: {line}")

    _PyGameView.process_combat_log_input = _patched_process_combat_log
    log("  Combat log voicing installed")

    log("  State screen voicing: 8 states with full navigation + centralized transition detector for all 15")

else:
    log("[WARNING] Could not find PyGameView class - UI hooks not installed")

# ============================================================================

log("=" * 60)
log(f"Screen Reader Mod - ACTIVE | NVDA: {tts.enabled} | Batching: 3-tier | Hotkeys: F E Q G D T B Z [/] 1-5")
log("=" * 60)
