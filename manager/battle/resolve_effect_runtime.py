import manager.utils as _utils_mod
from extensions import all_skill_data as _default_all_skill_data
from extensions import socketio as _default_socketio
from manager.buff_catalog import get_buff_effect
from manager.constants import DamageSource as _DamageSource
from manager.logs import setup_logger
from manager.room_manager import (
    get_room_state as _default_get_room_state,
    broadcast_log as _default_broadcast_log,
    _update_char_stat as _default_update_char_stat,
)
from manager.summons.service import apply_summon_change as _default_apply_summon_change
from manager.granted_skills.service import (
    apply_grant_skill_change as _default_apply_grant_skill_change,
    consume_granted_skill_use as _default_consume_granted_skill_use,
)
from manager.bleed_logic import consume_bleed_maintenance_stack as _default_consume_bleed_maintenance_stack
from manager.game_logic import (
    process_skill_effects as _default_process_skill_effects,
    apply_buff as _default_apply_buff,
    remove_buff as _default_remove_buff,
    get_status_value as _default_get_status_value,
)
from manager.battle.skill_rules import (
    _extract_rule_data_from_skill,
    _extract_skill_cost_entries,
)

logger = setup_logger(__name__)
all_skill_data = _default_all_skill_data
socketio = _default_socketio
get_room_state = _default_get_room_state
broadcast_log = _default_broadcast_log
_update_char_stat = _default_update_char_stat
apply_summon_change = _default_apply_summon_change
apply_grant_skill_change = _default_apply_grant_skill_change
consume_granted_skill_use = _default_consume_granted_skill_use
consume_bleed_maintenance_stack = _default_consume_bleed_maintenance_stack
process_skill_effects = _default_process_skill_effects
apply_buff = _default_apply_buff
remove_buff = _default_remove_buff
get_status_value = _default_get_status_value
DamageSource = _DamageSource

set_status_value = getattr(_utils_mod, "set_status_value", lambda *_args, **_kwargs: None)
COST_CONSUME_POLICY = "on_execute"


def _extract_skill_id_from_data(skill_data):
    if not isinstance(skill_data, dict):
        return None
    return skill_data.get("id")


def process_on_damage_buffs(_room, _target_char, _incoming_damage, _source, _log_snippets):
    return 0


def _collect_intrinsic_cancelled_single_slots(_state, _battle_state, intents_override=None):
    return set()


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default

def _apply_cost(attacker, skill, policy):
    consumed = {'mp': 0, 'hp': 0, 'fp': 0}
    if not isinstance(attacker, dict):
        return consumed
    if policy != COST_CONSUME_POLICY:
        return consumed

    used_skill_id = _extract_skill_id_from_data(skill)
    if used_skill_id:
        consume_granted_skill_use(attacker, used_skill_id)

    def _safe_set_status_value_local(char_obj, stat_name, stat_value):
        try:
            set_status_value(char_obj, stat_name, stat_value)
            return
        except Exception:
            pass
        states = char_obj.setdefault('states', [])
        if not isinstance(states, list):
            states = []
            char_obj['states'] = states
        hit = next((s for s in states if isinstance(s, dict) and s.get('name') == stat_name), None)
        if hit is None:
            states.append({'name': stat_name, 'value': int(stat_value or 0)})
        else:
            hit['value'] = int(stat_value or 0)

    for entry in _extract_skill_cost_entries(skill):
        if not isinstance(entry, dict):
            continue
        c_type = str(entry.get('type', '')).strip()
        if not c_type:
            continue
        try:
            c_val = int(entry.get('value', 0))
        except (TypeError, ValueError):
            c_val = 0
        if c_val <= 0:
            continue

        curr = int(get_status_value(attacker, c_type))
        new_val = max(0, curr - c_val)
        spent = max(0, curr - new_val)
        c_norm = c_type.upper()
        if c_norm == 'HP':
            attacker['hp'] = new_val
            consumed['hp'] += spent
        elif c_norm == 'MP':
            attacker['mp'] = new_val
            consumed['mp'] += spent
        elif c_norm == 'FP':
            if 'fp' in attacker:
                attacker['fp'] = new_val
            _safe_set_status_value_local(attacker, 'FP', new_val)
            consumed['fp'] += spent
        else:
            _safe_set_status_value_local(attacker, c_type, new_val)

    return consumed


def _apply_damage(defender, amount, damage_type=None):
    if not isinstance(defender, dict):
        return {'target_id': None, 'hp': 0, 'damage_type': damage_type}
    try:
        dmg = int(amount)
    except (TypeError, ValueError):
        dmg = 0
    if dmg <= 0:
        return {'target_id': defender.get('id'), 'hp': 0, 'damage_type': damage_type}

    before = int(defender.get('hp', 0))
    after = max(0, before - dmg)
    defender['hp'] = after
    return {
        'target_id': defender.get('id'),
        'hp': before - after,
        'damage_type': damage_type,
    }


def _apply_status(defender, status_payload):
    if not isinstance(defender, dict):
        return []
    if not status_payload:
        return []

    entries = status_payload if isinstance(status_payload, list) else [status_payload]
    applied = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get('name') or entry.get('type')
        if not name:
            continue
        mode = str(entry.get('mode', 'add'))
        try:
            value = int(entry.get('value', 0))
        except (TypeError, ValueError):
            value = 0
        before = int(get_status_value(defender, name))
        after = max(0, value) if mode == 'set' else max(0, before + value)
        set_status_value(defender, name, after)
        applied.append({'target_id': defender.get('id'), 'name': name, 'before': before, 'after': after, 'delta': after - before})
    return applied


def _record_used_skill_for_actor(actor, skill_id):
    """Track resolved skill usage for END_ROUND effects."""
    if not isinstance(actor, dict):
        return
    sid = str(skill_id or '').strip()
    if not sid:
        return
    used = actor.get('used_skills_this_round')
    if not isinstance(used, list):
        used = []
        actor['used_skills_this_round'] = used
    used.append(sid)


def _apply_outcome_to_state(outcome, characters_by_id):
    applied = {'cost': {'mp': 0, 'hp': 0, 'fp': 0}, 'damage': [], 'statuses': [], 'flags': [], 'log_lines': []}
    if not isinstance(outcome, dict):
        return applied
    if isinstance(outcome.get('log_lines'), list):
        applied['log_lines'] = [str(x) for x in outcome.get('log_lines') if x is not None]

    attacker_id = outcome.get('attacker_id')
    attacker = characters_by_id.get(attacker_id) if attacker_id else None
    if outcome.get('apply_cost', False):
        applied['cost'] = _apply_cost(attacker, outcome.get('skill', {}) or {}, outcome.get('cost_policy', COST_CONSUME_POLICY))

    if outcome.get('delegate_applied', False):
        delegate = outcome.get('delegate_summary', {})
        if isinstance(delegate, dict):
            for key in ['damage', 'statuses', 'flags']:
                if isinstance(delegate.get(key), list):
                    applied[key] = delegate.get(key, [])
            if isinstance(delegate.get('cost'), dict):
                for k in ['mp', 'hp', 'fp']:
                    applied['cost'][k] = int(applied['cost'].get(k, 0)) + int(delegate['cost'].get(k, 0))
        return applied

    for dmg in outcome.get('damage', []) if isinstance(outcome.get('damage', []), list) else [outcome.get('damage', {})]:
        if not isinstance(dmg, dict):
            continue
        target_id = dmg.get('target_id') or outcome.get('target_id')
        defender = characters_by_id.get(target_id) if target_id else None
        applied['damage'].append(_apply_damage(defender, dmg.get('amount', 0), dmg.get('damage_type')))

    for status in outcome.get('statuses', []) if isinstance(outcome.get('statuses', []), list) else [outcome.get('statuses', {})]:
        if not isinstance(status, dict):
            continue
        target_id = status.get('target_id') or outcome.get('target_id')
        defender = characters_by_id.get(target_id) if target_id else None
        payload = status.get('payload') if isinstance(status.get('payload'), dict) else status
        applied['statuses'].extend(_apply_status(defender, payload))

    return applied


def _snapshot_characters_for_timing(state):
    if not isinstance(state, dict):
        return {}
    out = {}
    for char in state.get('characters', []) or []:
        if not isinstance(char, dict):
            continue
        cid = char.get('id')
        if not cid:
            continue
        out[cid] = _snapshot_for_outcome(char)
    return out


def _diff_timing_snapshots(before_map, after_map, damage_source='timing_effect'):
    merged = {'damage': [], 'statuses': [], 'flags': []}
    if not isinstance(before_map, dict) or not isinstance(after_map, dict):
        return merged
    for cid, before in before_map.items():
        after = after_map.get(cid)
        if not before or not after:
            continue
        diff = _diff_snapshot(before, after, damage_source=damage_source)
        merged['damage'].extend(diff.get('damage', []) or [])
        merged['statuses'].extend(diff.get('statuses', []) or [])
        merged['flags'].extend(diff.get('flags', []) or [])
    return merged


def _run_skill_timing_effects(
    room,
    state,
    actor_char,
    target_char,
    skill_data,
    timing,
    target_skill_data=None,
    base_damage=0
):
    result = {
        'bonus_damage': 0,
        'extra_primary_damage': 0,
        'logs': [],
        'changes': [],
        'damage': [],
        'statuses': [],
        'flags': [],
    }
    if not isinstance(actor_char, dict):
        return result
    if not isinstance(skill_data, dict):
        return result

    rule_data = _extract_rule_data_from_skill(skill_data)
    effects_array = rule_data.get('effects', []) if isinstance(rule_data, dict) else []
    if not isinstance(effects_array, list) or not effects_array:
        return result

    before_map = _snapshot_characters_for_timing(state)
    context = {
        'timeline': (state.get('timeline', []) if isinstance(state, dict) else []),
        'characters': (state.get('characters', []) if isinstance(state, dict) else []),
        'room': room,
    }
    try:
        bonus_damage, logs, changes = process_skill_effects(
            effects_array,
            timing,
            actor_char,
            target_char,
            target_skill_data,
            context=context,
            base_damage=base_damage
        )
    except Exception as e:
        logger.warning(
            "[timing_effect] timing=%s actor=%s failed: %s",
            timing,
            actor_char.get('id'),
            e
        )
        return result

    result['bonus_damage'] = int(bonus_damage or 0)
    result['logs'] = list(logs or [])
    result['changes'] = list(changes or [])
    result['extra_primary_damage'] = int(
        _apply_effect_changes_like_duel(
            room,
            state,
            result['changes'],
            actor_char,
            target_char,
            int(base_damage or 0),
            result['logs']
        ) or 0
    )

    after_map = _snapshot_characters_for_timing(state)
    diff = _diff_timing_snapshots(
        before_map,
        after_map,
        damage_source=f"{str(timing).lower()}_effect"
    )
    result['damage'] = diff.get('damage', []) or []
    result['statuses'] = diff.get('statuses', []) or []
    result['flags'] = diff.get('flags', []) or []
    return result


def _trigger_skill_timing_effects(
    room,
    state,
    characters_by_id,
    timing,
    actor_char,
    target_char,
    skill_data,
    target_skill_data=None,
    base_damage=0,
    emit_source='select_resolve_timing'
):
    res = _run_skill_timing_effects(
        room=room,
        state=state,
        actor_char=actor_char,
        target_char=target_char,
        skill_data=skill_data,
        timing=timing,
        target_skill_data=target_skill_data,
        base_damage=base_damage
    )
    if res.get('damage') or res.get('statuses'):
        _emit_stat_updates_from_applied(
            room,
            {
                'damage': res.get('damage', []),
                'statuses': res.get('statuses', []),
                'flags': res.get('flags', []),
            },
            characters_by_id if isinstance(characters_by_id, dict) else {},
            source=emit_source
        )
    if res.get('logs'):
        logger.info(
            "[timing_effect] timing=%s actor=%s target=%s logs=%d",
            timing,
            actor_char.get('id') if isinstance(actor_char, dict) else None,
            target_char.get('id') if isinstance(target_char, dict) else None,
            len(res.get('logs') or [])
        )
    return res


def _apply_phase_timing_for_committed_intents(
    room,
    state,
    battle_state,
    characters_by_id,
    timing,
    intents_override=None
):
    if not isinstance(state, dict) or not isinstance(battle_state, dict):
        return 0
    intents = intents_override if isinstance(intents_override, dict) else battle_state.get('intents', {})
    slots = battle_state.get('slots', {}) if isinstance(battle_state.get('slots'), dict) else {}
    resolve_ctx = battle_state.setdefault('resolve', {})
    marks = resolve_ctx.setdefault('timing_marks', {})
    cancelled_slots = resolve_ctx.get('cancelled_slots', [])
    cancelled_slot_set = set(cancelled_slots if isinstance(cancelled_slots, list) else [])
    if str(timing) == 'RESOLVE_START':
        intrinsic_cancelled = _collect_intrinsic_cancelled_single_slots(
            state,
            battle_state,
            intents_override=intents
        )
        if intrinsic_cancelled:
            cancelled_slot_set.update(intrinsic_cancelled)
            resolve_ctx['cancelled_slots'] = list(cancelled_slot_set)
    applied_count = 0

    for slot_id, intent in (intents or {}).items():
        if not isinstance(intent, dict):
            continue
        if not intent.get('committed', False):
            continue
        if intent.get('tags', {}).get('instant', False):
            continue
        skill_id = intent.get('skill_id')
        if not skill_id:
            continue
        mark_key = f"{timing}:{slot_id}"
        if marks.get(mark_key):
            continue
        if slot_id in cancelled_slot_set:
            marks[mark_key] = True
            continue

        slot_data = slots.get(slot_id, {}) if isinstance(slots, dict) else {}
        attacker_actor_id = slot_data.get('actor_id') or intent.get('actor_id')
        attacker_char = characters_by_id.get(attacker_actor_id) if isinstance(characters_by_id, dict) else None
        if not isinstance(attacker_char, dict):
            marks[mark_key] = True
            continue

        skill_data = all_skill_data.get(skill_id, {}) if isinstance(all_skill_data, dict) else {}
        if not isinstance(skill_data, dict):
            marks[mark_key] = True
            continue

        target = intent.get('target', {}) if isinstance(intent.get('target'), dict) else {}
        target_slot_id = target.get('slot_id') if target.get('type') == 'single_slot' else None
        target_slot_data = slots.get(target_slot_id, {}) if target_slot_id and isinstance(slots, dict) else {}
        target_actor_id = target_slot_data.get('actor_id')
        target_char = characters_by_id.get(target_actor_id) if target_actor_id else None
        target_skill_data = None
        if target_slot_id and isinstance(intents.get(target_slot_id), dict):
            t_skill_id = intents.get(target_slot_id, {}).get('skill_id')
            if t_skill_id:
                target_skill_data = all_skill_data.get(t_skill_id, {}) if isinstance(all_skill_data, dict) else None

        _trigger_skill_timing_effects(
            room=room,
            state=state,
            characters_by_id=characters_by_id,
            timing=timing,
            actor_char=attacker_char,
            target_char=target_char,
            skill_data=skill_data,
            target_skill_data=target_skill_data,
            base_damage=0,
            emit_source=f"resolve_{str(timing).lower()}"
        )
        marks[mark_key] = True
        applied_count += 1
    return applied_count


def _apply_step_end_timing_from_trace(room, battle_state, trace_entry):
    if not isinstance(battle_state, dict) or not isinstance(trace_entry, dict):
        return 0
    kind = str(trace_entry.get('kind') or '')
    if kind not in {'clash', 'one_sided', 'hard_attack', 'mass_individual', 'mass_summation'}:
        return 0

    state = battle_state.get('__room_state_ref__')
    if not isinstance(state, dict):
        room_name = battle_state.get('__room_name')
        if room_name:
            state = get_room_state(room_name)
    if not isinstance(state, dict):
        return 0
    slots = battle_state.get('slots', {}) if isinstance(battle_state.get('slots'), dict) else {}
    intents = battle_state.get('__resolve_intents_override')
    if not isinstance(intents, dict):
        intents = battle_state.get('intents', {})
    chars = state.get('characters', []) if isinstance(state.get('characters'), list) else []
    characters_by_id = {c.get('id'): c for c in chars if isinstance(c, dict) and c.get('id')}

    attacker_slot_id = trace_entry.get('attacker_slot_id') or trace_entry.get('attacker_slot')
    defender_slot_id = trace_entry.get('defender_slot_id') or trace_entry.get('defender_slot')
    attacker_actor_id = trace_entry.get('attacker_actor_id') or (slots.get(attacker_slot_id, {}) or {}).get('actor_id')
    defender_actor_id = trace_entry.get('defender_actor_id') or trace_entry.get('target_actor_id') or (slots.get(defender_slot_id, {}) or {}).get('actor_id')
    attacker_char = characters_by_id.get(attacker_actor_id)
    defender_char = characters_by_id.get(defender_actor_id)

    attacker_intent = intents.get(attacker_slot_id, {}) if attacker_slot_id and isinstance(intents, dict) else {}
    defender_intent = intents.get(defender_slot_id, {}) if defender_slot_id and isinstance(intents, dict) else {}
    attacker_skill_id = attacker_intent.get('skill_id')
    defender_skill_id = defender_intent.get('skill_id')
    attacker_skill_data = all_skill_data.get(attacker_skill_id, {}) if attacker_skill_id and isinstance(all_skill_data, dict) else None
    defender_skill_data = all_skill_data.get(defender_skill_id, {}) if defender_skill_id and isinstance(all_skill_data, dict) else None

    rolls = trace_entry.get('rolls', {}) if isinstance(trace_entry.get('rolls'), dict) else {}
    base_damage = int(
        rolls.get('total_damage')
        or rolls.get('final_damage')
        or rolls.get('base_damage')
        or rolls.get('delta')
        or 0
    )

    applied = 0
    if isinstance(attacker_char, dict) and isinstance(attacker_skill_data, dict):
        _trigger_skill_timing_effects(
            room=room,
            state=state,
            characters_by_id=characters_by_id,
            timing='RESOLVE_STEP_END',
            actor_char=attacker_char,
            target_char=defender_char,
            skill_data=attacker_skill_data,
            target_skill_data=defender_skill_data,
            base_damage=base_damage,
            emit_source='resolve_step_end'
        )
        applied += 1
    if isinstance(defender_char, dict) and isinstance(defender_skill_data, dict):
        _trigger_skill_timing_effects(
            room=room,
            state=state,
            characters_by_id=characters_by_id,
            timing='RESOLVE_STEP_END',
            actor_char=defender_char,
            target_char=attacker_char,
            skill_data=defender_skill_data,
            target_skill_data=attacker_skill_data,
            base_damage=base_damage,
            emit_source='resolve_step_end'
        )
        applied += 1
    return applied


def _emit_char_stat_update(room, char_obj, stat_name, old_value, new_value, source='select_resolve'):
    if not isinstance(char_obj, dict):
        return False
    if old_value is None or new_value is None:
        return False
    if str(old_value) == str(new_value):
        return False
    max_value = None
    if stat_name == 'HP':
        max_value = char_obj.get('maxHp', 0)
    elif stat_name == 'MP':
        max_value = char_obj.get('maxMp', 0)
    socketio.emit('char_stat_updated', {
        'room': room,
        'char_id': char_obj.get('id'),
        'stat': stat_name,
        'new_value': new_value,
        'old_value': old_value,
        'max_value': max_value,
        'log_message': None,
        'source': source
    }, to=room)
    return True


def _emit_stat_updates_from_applied(room, applied, characters_by_id, source='select_resolve_delegate'):
    if not isinstance(applied, dict):
        return 0
    emitted = 0

    for damage in (applied.get('damage', []) or []):
        if not isinstance(damage, dict):
            continue
        target_id = damage.get('target_id')
        if not target_id:
            continue
        char_obj = characters_by_id.get(target_id) if isinstance(characters_by_id, dict) else None
        if not isinstance(char_obj, dict):
            continue
        try:
            hp_delta = int(damage.get('hp', 0) or 0)
        except (TypeError, ValueError):
            hp_delta = 0
        if hp_delta == 0:
            continue
        new_hp = int(char_obj.get('hp', 0))
        old_hp = int(new_hp + hp_delta)
        if _emit_char_stat_update(room, char_obj, 'HP', old_hp, new_hp, source=source):
            emitted += 1

    for status in (applied.get('statuses', []) or []):
        if not isinstance(status, dict):
            continue
        target_id = status.get('target_id')
        stat_name = status.get('name')
        if (not target_id) or (not stat_name):
            continue
        stat_name = str(stat_name)
        if stat_name.startswith('buff:'):
            continue
        char_obj = characters_by_id.get(target_id) if isinstance(characters_by_id, dict) else None
        if not isinstance(char_obj, dict):
            continue
        old_value = status.get('before')
        new_value = status.get('after')
        if old_value is None or new_value is None:
            continue
        if _emit_char_stat_update(room, char_obj, stat_name, old_value, new_value, source=source):
            emitted += 1

    return emitted



def _snapshot_for_outcome(actor):
    if not isinstance(actor, dict):
        return None
    states_map = {}
    for s in actor.get('states', []) or []:
        if not isinstance(s, dict):
            continue
        n = s.get('name')
        if not n:
            continue
        try:
            states_map[n] = int(s.get('value', 0))
        except (TypeError, ValueError):
            states_map[n] = 0
    # Some legacy effects are stored outside states[].
    bad_states_map = {}
    for bs in actor.get('bad_states', []) or actor.get('迥ｶ諷狗焚蟶ｸ', []) or []:
        if isinstance(bs, dict):
            name = bs.get('name') or bs.get('type')
            if not name:
                continue
            try:
                bad_states_map[str(name)] = int(bs.get('value', 1))
            except (TypeError, ValueError):
                bad_states_map[str(name)] = 1
        elif isinstance(bs, str):
            bad_states_map[bs] = bad_states_map.get(bs, 0) + 1

    buffs_map = {}
    for b in actor.get('special_buffs', []) or []:
        if not isinstance(b, dict):
            continue
        name = b.get('name')
        if not name:
            continue
        buffs_map[str(name)] = buffs_map.get(str(name), 0) + 1

    fp_value = None
    for n, v in states_map.items():
        if str(n or '').strip().upper() == 'FP':
            try:
                fp_value = int(v)
            except Exception:
                fp_value = 0
            break
    if fp_value is None:
        fp_value = int(get_status_value(actor, 'FP') or 0)

    return {
        'id': actor.get('id'),
        'hp': int(actor.get('hp', 0)),
        'mp': int(actor.get('mp', 0)),
        'fp': int(fp_value),
        'states': states_map,
        'bad_states': bad_states_map,
        'buffs': buffs_map,
        'flags': dict(actor.get('flags', {}) or {}),
    }


def _diff_snapshot(before, after, damage_source='繝繝｡繝ｼ繧ｸ'):
    if not before or not after:
        return {'damage': [], 'statuses': [], 'flags': []}
    actor_id = after.get('id')
    damage = []
    statuses = []
    flags = []

    hp_loss = int(before.get('hp', 0)) - int(after.get('hp', 0))
    if hp_loss > 0:
        damage.append({'target_id': actor_id, 'hp': hp_loss, 'source': str(damage_source or '繝繝｡繝ｼ繧ｸ')})

    state_names = set(before.get('states', {}).keys()) | set(after.get('states', {}).keys())
    for name in state_names:
        b = int(before.get('states', {}).get(name, 0))
        a = int(after.get('states', {}).get(name, 0))
        if a != b:
            statuses.append({'target_id': actor_id, 'name': name, 'before': b, 'after': a, 'delta': a - b})

    # FP can be stored via params/get_status_value without an explicit states[] row.
    # Capture that top-level diff too so delegated clash summaries don't miss an
    # already-applied match-win FP gain and re-grant it in select/resolve.
    before_fp = int(before.get('fp', 0))
    after_fp = int(after.get('fp', 0))
    if before_fp != after_fp:
        has_fp_status = any(str(row.get('name') or '').strip().upper() == 'FP' for row in statuses if isinstance(row, dict))
        if not has_fp_status:
            statuses.append({'target_id': actor_id, 'name': 'FP', 'before': before_fp, 'after': after_fp, 'delta': after_fp - before_fp})

    bad_state_names = set(before.get('bad_states', {}).keys()) | set(after.get('bad_states', {}).keys())
    for name in bad_state_names:
        b = int(before.get('bad_states', {}).get(name, 0))
        a = int(after.get('bad_states', {}).get(name, 0))
        if a != b:
            statuses.append({'target_id': actor_id, 'name': name, 'before': b, 'after': a, 'delta': a - b})

    buff_names = set(before.get('buffs', {}).keys()) | set(after.get('buffs', {}).keys())
    for name in buff_names:
        b = int(before.get('buffs', {}).get(name, 0))
        a = int(after.get('buffs', {}).get(name, 0))
        if a != b:
            statuses.append({'target_id': actor_id, 'name': f"buff:{name}", 'before': b, 'after': a, 'delta': a - b})

    flag_names = set(before.get('flags', {}).keys()) | set(after.get('flags', {}).keys())
    for name in flag_names:
        b = before.get('flags', {}).get(name)
        a = after.get('flags', {}).get(name)
        if a != b:
            flags.append({'target_id': actor_id, 'name': name, 'before': b, 'after': a})

    return {'damage': damage, 'statuses': statuses, 'flags': flags}


def _apply_effect_changes_like_duel(
    room,
    state,
    changes,
    attacker_char,
    defender_char,
    base_damage,
    log_snippets,
    reuse_requests=None
):
    extra_primary_damage = 0
    for (char, effect_type, name, value) in changes:
        if not isinstance(char, dict):
            continue
        if effect_type == "APPLY_STATE":
            base_curr = 0
            if name == 'HP':
                base_curr = int(char.get('hp', 0))
            elif name == 'MP':
                base_curr = int(char.get('mp', 0))
            else:
                state_obj = next((s for s in char.get('states', []) if s.get('name') == name), None)
                if state_obj:
                    try:
                        base_curr = int(state_obj.get('value', 0))
                    except ValueError:
                        base_curr = 0
            _update_char_stat(room, char, name, base_curr + value, username=f"[{name}]")
        elif effect_type == "SET_STATUS":
            _update_char_stat(room, char, name, int(value), username=f"[{name}]")
        elif effect_type == "APPLY_BUFF":
            apply_buff(char, name, value.get("lasting", 0), value.get("delay", 0), data=value.get("data"), count=value.get("count"))
            log_snippets.append(f"[{name}] が {char.get('name', char.get('id', ''))} に付与されました。")
        elif effect_type == "REMOVE_BUFF":
            remove_buff(char, name)
            log_snippets.append(f"[{name}] が {char.get('name', char.get('id', ''))} から解除されました。")
        elif effect_type == "CUSTOM_DAMAGE":
            if defender_char and char.get('id') == defender_char.get('id'):
                extra_primary_damage += int(value)
            else:
                curr_hp = int(get_status_value(char, 'HP'))
                _update_char_stat(room, char, 'HP', max(0, curr_hp - int(value)), username=f"[{name}]", source=DamageSource.SKILL_EFFECT)
        elif effect_type == "CONSUME_BLEED_MAINTENANCE":
            consumed, remaining = consume_bleed_maintenance_stack(char, amount=int(value or 1))
            if consumed > 0:
                log_snippets.append(f"[出血維持] 1消費 (残{remaining})")
        elif effect_type == "APPLY_SKILL_DAMAGE_AGAIN":
            if base_damage > 0:
                _update_char_stat(room, char, 'HP', int(char.get('hp', 0)) - int(base_damage), username="[霑ｽ謦ゾ", source=DamageSource.SKILL_EFFECT)
                temp_logs = []
                b_dmg = process_on_damage_buffs(room, char, int(base_damage), "[select_resolve_one_sided]", temp_logs)
                log_snippets.extend(temp_logs)
                extra_primary_damage += int(base_damage) + int(b_dmg)
        elif effect_type == "USE_SKILL_AGAIN":
            payload = value if isinstance(value, dict) else {}
            max_reuses = _safe_int(payload.get('max_reuses', 1), 1)
            if max_reuses <= 0:
                max_reuses = 1
            raw_reuse_cost = payload.get('reuse_cost', [])
            if isinstance(raw_reuse_cost, dict):
                raw_reuse_cost = [raw_reuse_cost]
            reuse_cost = []
            if isinstance(raw_reuse_cost, list):
                for entry in raw_reuse_cost:
                    if not isinstance(entry, dict):
                        continue
                    c_type = str(entry.get('type', '')).strip()
                    c_val = _safe_int(entry.get('value', 0), 0)
                    if not c_type or c_val <= 0:
                        continue
                    reuse_cost.append({'type': c_type, 'value': c_val})
            req = {
                'max_reuses': int(max_reuses),
                'consume_cost': bool(payload.get('consume_cost', False))
            }
            if reuse_cost:
                req['reuse_cost'] = reuse_cost
            if isinstance(char, dict) and char.get('id'):
                req['target_id'] = char.get('id')
            if isinstance(reuse_requests, list):
                reuse_requests.append(req)
        elif effect_type == "MODIFY_BASE_POWER":
            char['_base_power_bonus'] = int(char.get('_base_power_bonus', 0) or 0) + int(value or 0)
        elif effect_type == "MODIFY_FINAL_POWER":
            char['_final_power_bonus'] = int(char.get('_final_power_bonus', 0) or 0) + int(value or 0)
        elif effect_type == "SET_FLAG":
            if 'flags' not in char:
                char['flags'] = {}
            char['flags'][name] = value
        elif effect_type == "SUMMON_CHARACTER":
            res = apply_summon_change(room, state, char, value)
            if res.get("ok"):
                broadcast_log(room, res.get("message", "召喚が発生した。"), "state-change")
            else:
                logger.warning("[select_resolve summon failed] %s", res.get("message"))
        elif effect_type == "GRANT_SKILL":
            grant_payload = dict(value) if isinstance(value, dict) else {}
            if "skill_id" not in grant_payload:
                grant_payload["skill_id"] = name
            res = apply_grant_skill_change(room, state, attacker_char, char, grant_payload)
            if res.get("ok"):
                broadcast_log(room, res.get("message", "スキル付与が発生した。"), "state-change")
            else:
                logger.warning("[select_resolve grant_skill failed] %s", res.get("message"))
    return extra_primary_damage


