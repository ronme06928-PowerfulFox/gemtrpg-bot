"""Dispatch the opt-in timing rows of active buffs."""
from contextlib import contextmanager
from contextvars import ContextVar

from manager.battle.action_slot_mode import is_character_targetable
from manager.buff_catalog import get_buff_by_id, get_buff_effect
from manager.logs import setup_logger
from manager.json_rule_v2 import BUFF_SKILL_TIMINGS

MAX_KILL_TRIGGERS = 32
_kill_budget = ContextVar("timed_buff_kill_budget", default=None)
_entry_depth = ContextVar("timed_buff_entry_depth", default=0)
_deferred_logs = ContextVar("timed_buff_logs", default=None)
logger = setup_logger(__name__)


@contextmanager
def collect_timed_buff_logs():
    """Keep log lines while the delegated match suppresses legacy broadcasts."""
    lines = []
    token = _deferred_logs.set(lines)
    try:
        yield lines
    finally:
        _deferred_logs.reset(token)


def log_timed_buff_effect(room, lines):
    if not room:
        return
    pending = _deferred_logs.get()
    if pending is not None:
        pending.extend(lines)
        return
    from manager.room_manager import broadcast_log

    for line in lines:
        broadcast_log(room, line, "skill-effect")


def buff_rows(actor, timing):
    for buff in actor.get("special_buffs") or ():
        if not isinstance(buff, dict):
            continue
        try:
            delayed = int(buff.get("delay", 0) or 0) > 0
        except (TypeError, ValueError):
            delayed = True
        if delayed:
            continue
        name = buff.get("name")
        data = buff.get("data") or {}
        key = buff.get("buff_id") or (data.get("buff_id") if isinstance(data, dict) else None)
        rows = data.get("effects") if isinstance(data, dict) else None
        if rows is None:
            record = get_buff_by_id(key) if isinstance(key, str) else None
            effect = record.get("effect") if record else get_buff_effect(name)
            rows = effect.get("effects") if isinstance(effect, dict) else None
        for row in rows if isinstance(rows, list) else ():
            if isinstance(row, dict) and row.get("timing") == timing:
                effect_type = str(row.get("type", "")).strip().upper()
                resolved = {**row, "type": effect_type, "_buff_timing_name": name or key or "バフ"}
                if effect_type in {"APPLY_BUFF", "REMOVE_BUFF", "APPLY_BUFF_PER_N"} and row.get("buff_id") and not row.get("buff_name"):
                    referenced = get_buff_by_id(row["buff_id"])
                    if referenced:
                        resolved["buff_name"] = referenced.get("name")
                yield resolved


def run_timed_buffs(room, state, actor, timing, *, target=None, skill=None, target_skill=None,
                   base_damage=0, on_summon=None):
    """Apply on the live room or on the isolated battle-entry candidate."""
    from manager.battle.effect_presentation import step_effects_collector
    from manager.battle.resolve_effect_runtime import _apply_effect_changes_like_duel
    from manager.game_logic import process_skill_effects

    if not isinstance(actor, dict):
        return [], 0
    rows = list(buff_rows(actor, timing))
    if not rows or (timing not in BUFF_SKILL_TIMINGS and timing != "ON_KILL" and not is_character_targetable(actor)):
        return [], 0
    context = {"room": room, "room_state": state, "characters": state.get("characters", []),
               "timeline": state.get("timeline", []), "round": state.get("round", 0),
               "trigger_target": target, "fired_effects": step_effects_collector(),
               "only_timed_buffs": True}
    destination = "target" if timing in BUFF_SKILL_TIMINGS or timing == "ON_KILL" else "self"
    rows = [{**row, "target": row.get("target") or destination} for row in rows]
    depth = _entry_depth.get()
    if timing == "BATTLE_START" and depth >= MAX_KILL_TRIGGERS:
        logger.warning("戦闘突入時のバフ連鎖の上限に到達 room=%s", room)
        return [], 0
    token = _entry_depth.set(depth + 1) if timing == "BATTLE_START" else None
    try:
        bonus, logs, changes = process_skill_effects(rows, timing, actor, target, target_skill, context=context,
                                                    actor_skill_data=skill, base_damage=base_damage)
        _apply_effect_changes_like_duel(room, state, changes, actor, None, base_damage, logs,
                                       attacker_skill_data=skill, on_summon=on_summon, timed_buff=True)
    finally:
        if token is not None:
            _entry_depth.reset(token)
    return logs, bonus


def process_kill(room, state, victim, cause):
    from manager.constants import DamageSource

    if not isinstance(cause, dict) or not isinstance(state, dict):
        return
    actor = cause.get("actor")
    if not isinstance(actor, dict) or actor is victim or actor.get("type") == victim.get("type"):
        return
    if cause.get("damage_type") == DamageSource.THORNS:
        return
    skill = cause.get("skill_data")
    if not (skill or cause.get("skill_id") or cause.get("damage_type") == "timed_buff"):
        return
    if not any(buff_rows(actor, "ON_KILL")):
        return
    inherited = _kill_budget.get()
    budget = inherited if inherited is not None else [MAX_KILL_TRIGGERS]
    if budget[0] <= 0:
        logger.warning("ON_KILL 連鎖の上限に到達 room=%s", room)
        return
    budget[0] -= 1
    token = _kill_budget.set(budget) if inherited is None else None
    try:
        run_timed_buffs(room, state, actor, "ON_KILL", target=victim, skill=skill)
    finally:
        if token is not None:
            _kill_budget.reset(token)
