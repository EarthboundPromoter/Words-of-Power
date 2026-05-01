"""
Journal — capture stage for the new data-model pipeline (phase 2).

Captures every game event flowing through Level.act_cast and EventHandler.raise_event
into structured records with monotonic sequence + causation parent links. The journal
is module-level (never pickled), bounded by level transitions (reset on each new level),
and currently has no consumers — it is silent infrastructure for phase 3+ features
(direct-action digest, death summary, level-end summary, etc.).

See mods/screen_reader/memory_pointers in MEMORY.md:
- design_rw2_data_model.md — phase 0+1 design spec
- plan_data_model_overhaul.md — multi-phase strangler-fig plan

Phase 2 ships the journal silently with no behavior change. Verify via
journal_debug.log (toggleable via settings.ini → journal_log_enabled).
"""

import json
import os
import time

import Level


class _Journal:
    def __init__(self):
        self.records = []
        self.cause_stack = []
        self.sequence = 0
        self.action_chain_id = 0
        self.level_id = None
        self._fp = None
        self._hooks_installed = False

    def reset(self, level_id):
        self.records = []
        self.cause_stack = []
        self.level_id = level_id
        if self._fp:
            self._emit({"__meta__": "level_reset", "level_id": level_id, "seq": self.sequence})

    def open_log(self, path):
        try:
            self._fp = open(path, "w", encoding="utf-8")
            self._emit({"__meta__": "journal_log_opened", "ts": time.time()})
        except Exception:
            self._fp = None

    def close_log(self):
        if self._fp:
            try:
                self._fp.close()
            except Exception:
                pass
            self._fp = None

    def push(self, record):
        self.cause_stack.append(record)

    def pop(self):
        if self.cause_stack:
            self.cause_stack.pop()

    def record(self, event_type, payload):
        self.sequence += 1
        parent = self.cause_stack[-1]["sequence"] if self.cause_stack else None
        rec = {
            "sequence": self.sequence,
            "action_chain_id": self.action_chain_id,
            "level_id": self.level_id,
            "event_type": event_type,
            "parent": parent,
            "timestamp": time.time(),
            "payload": payload,
            "marks": [],
        }
        self.records.append(rec)
        if self._fp:
            self._emit(rec)
        return rec

    def begin_chain(self, payload):
        self.action_chain_id += 1
        return self.record("cast_begin", payload)

    def _emit(self, obj):
        try:
            self._fp.write(json.dumps(obj, default=str, separators=(",", ":")) + "\n")
            self._fp.flush()
        except Exception:
            pass


journal = _Journal()


def _serialize(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    name = getattr(value, "name", None)
    if isinstance(name, str):
        return name
    return repr(value)[:200]


def _to_payload(event):
    if not hasattr(event, "_fields"):
        return {"_raw": repr(event)[:200]}
    return {f: _serialize(getattr(event, f)) for f in event._fields}


def _wrap_with_cause(inner_gen, cause_record):
    """Wrap a spell-cast generator so the given cause is on the cause stack
    during each iteration step. Spell effects (damage, heals, summons) that
    fire from inside next(inner_gen) inherit cause_record as their parent."""
    try:
        while True:
            journal.push(cause_record)
            try:
                value = next(inner_gen)
            except StopIteration:
                return
            finally:
                journal.pop()
            yield value
    except GeneratorExit:
        return


def install_hooks():
    """Monkeypatch Level.act_cast, Level.queue_spell, and EventHandler.raise_event
    to populate the journal. Idempotent — safe to call multiple times."""
    if journal._hooks_installed:
        return

    original_act_cast = Level.Level.act_cast
    original_queue_spell = Level.Level.queue_spell
    original_raise_event = Level.EventHandler.raise_event

    def patched_act_cast(self, unit, spell, x, y, pay_costs=True, queue=True, is_echo=False):
        cast_record = journal.begin_chain({
            "spell_name": getattr(spell, "name", None),
            "caster": getattr(unit, "name", None),
            "caster_x": getattr(unit, "x", None),
            "caster_y": getattr(unit, "y", None),
            "target_x": x,
            "target_y": y,
            "is_echo": is_echo,
            "is_player": bool(getattr(unit, "is_player_controlled", False)),
        })
        journal.push(cast_record)
        try:
            return original_act_cast(self, unit, spell, x, y,
                                     pay_costs=pay_costs, queue=queue, is_echo=is_echo)
        finally:
            journal.pop()

    def patched_queue_spell(self, gen):
        cause = journal.cause_stack[-1] if journal.cause_stack else None
        if cause is not None:
            gen = _wrap_with_cause(gen, cause)
        return original_queue_spell(self, gen)

    def patched_raise_event(self, event, entity=None):
        rec = journal.record(type(event).__name__, _to_payload(event))
        journal.push(rec)
        try:
            return original_raise_event(self, event, entity)
        finally:
            journal.pop()

    Level.Level.act_cast = patched_act_cast
    Level.Level.queue_spell = patched_queue_spell
    Level.EventHandler.raise_event = patched_raise_event
    journal._hooks_installed = True
