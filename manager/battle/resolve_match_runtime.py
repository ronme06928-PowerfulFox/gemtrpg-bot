import copy
import time

from extensions import all_skill_data as _default_all_skill_data
from manager.dice_roller import roll_dice as _default_roll_dice
from manager.game_logic import (
    calculate_skill_preview as _default_calculate_skill_preview,
    process_skill_effects as _default_process_skill_effects,
    get_status_value as _default_get_status_value,
    compute_damage_multipliers as _default_compute_damage_multipliers,
    build_power_result_snapshot as _default_build_power_result_snapshot,
)
from manager.room_manager import (
    _update_char_stat as _default_update_char_stat,
    get_room_state as _default_get_room_state,
)
from manager.logs import setup_logger
from manager.battle.skill_rules import _extract_rule_data_from_skill, _skill_deals_damage
from manager.battle.duel_log_utils import _extract_skill_id_from_data
from manager.battle.resolve_snapshot_utils import (
    _extract_power_pair_from_match_log,
    _build_clash_power_snapshot,
    _estimate_cost_for_skill_from_snapshot,
)

logger = setup_logger(__name__)
all_skill_data = _default_all_skill_data
calculate_skill_preview = _default_calculate_skill_preview
process_skill_effects = _default_process_skill_effects
get_status_value = _default_get_status_value
compute_damage_multipliers = _default_compute_damage_multipliers
build_power_result_snapshot = _default_build_power_result_snapshot
roll_dice = _default_roll_dice
_update_char_stat = _default_update_char_stat
get_room_state = _default_get_room_state

# Dependency placeholders are rebound from core at runtime.
# This keeps behavior aligned with core-level monkeypatches in tests.

def _record_used_skill_for_actor(_actor, _skill_id):
    return None


def _snapshot_for_outcome(_actor):
    return None


def _trigger_skill_timing_effects(*_args, **_kwargs):
    return {}


def _apply_effect_changes_like_duel(*_args, **_kwargs):
    return 0


def _diff_snapshot(_before, _after, damage_source='ダメージ'):
    return {'damage': [], 'statuses': [], 'flags': []}


def _append_multiplier_logs(_log_snippets, _mult_info, incoming_label='防', outgoing_label='攻'):
    return None


def process_on_damage_buffs(_room, _target_char, _incoming_damage, _source, _log_snippets):
    return 0


def process_on_hit_buffs(_attacker_char, _defender_char, _base_damage, _log_snippets):
    return 0


def _resolve_server_ts():
    return int(time.time())


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default

def _resolve_one_sided_by_existing_logic(room, state, attacker_char, defender_char, attacker_skill_data, defender_skill_data):
    """
    Delegate to existing match processing primitives (do not invent formula):
    - manager/game_logic.py::calculate_skill_preview
    - manager/game_logic.py::process_skill_effects (UNOPPOSED/HIT)
    - manager/battle/core.py::process_on_hit_buffs
    - manager/game_logic.py::calculate_damage_multiplier
    - manager/battle/core.py::process_on_damage_buffs
    """
    if not attacker_char or not defender_char or not attacker_skill_data:
        return {'ok': False, 'reason': 'missing_actor_or_skill'}

    # Select/Resolve path must track used skills so END_ROUND effects can resolve.
    _record_used_skill_for_actor(attacker_char, _extract_skill_id_from_data(attacker_skill_data))

    before_a = _snapshot_for_outcome(attacker_char)
    before_d = _snapshot_for_outcome(defender_char)

    context = {'timeline': state.get('timeline', []), 'characters': state.get('characters', []), 'room': room}
    characters_by_id = {
        c.get('id'): c for c in state.get('characters', [])
        if isinstance(c, dict) and c.get('id')
    }
    attacker_char['_base_power_bonus'] = 0
    attacker_char['_final_power_bonus'] = 0
    defender_char['_base_power_bonus'] = 0
    defender_char['_final_power_bonus'] = 0
    attacker_rule = _extract_rule_data_from_skill(attacker_skill_data)
    effects_array_a = attacker_rule.get('effects', []) if isinstance(attacker_rule, dict) else []
    log_snippets = []
    reuse_requests = []

    # Select/Resolve one-sided now aligns with duel order: PRE_MATCH first.
    pre_a = _trigger_skill_timing_effects(
        room=room,
        state=state,
        characters_by_id=characters_by_id,
        timing='PRE_MATCH',
        actor_char=attacker_char,
        target_char=defender_char,
        skill_data=attacker_skill_data,
        target_skill_data=defender_skill_data,
        base_damage=0,
        emit_source='one_sided_pre_match'
    )
    if pre_a.get('logs'):
        log_snippets.extend(pre_a.get('logs', []))
    # One-sided resolution must not execute the defender's own PRE_MATCH effects here.
    # The defender skill (if any) is only used as conditional context for attacker effects.

    _trigger_skill_timing_effects(
        room=room,
        state=state,
        characters_by_id=characters_by_id,
        timing='BEFORE_POWER_ROLL',
        actor_char=attacker_char,
        target_char=defender_char,
        skill_data=attacker_skill_data,
        target_skill_data=defender_skill_data,
        base_damage=0,
        emit_source='before_power_roll'
    )

    preview = calculate_skill_preview(attacker_char, defender_char, attacker_skill_data, context=context)
    final_command = (preview or {}).get('final_command') or "0"
    roll_result = roll_dice(final_command)
    base_damage = int(roll_result.get('total', 0))
    power_snapshot = build_power_result_snapshot(preview, roll_result)

    bd_un, log_un, chg_un = process_skill_effects(
        effects_array_a, "UNOPPOSED", attacker_char, defender_char, defender_skill_data, context=context
    )
    extra_un = _apply_effect_changes_like_duel(
        room, state, chg_un, attacker_char, defender_char, base_damage, log_snippets, reuse_requests=reuse_requests
    )

    bd_hit, log_hit, chg_hit = process_skill_effects(
        effects_array_a, "HIT", attacker_char, defender_char, defender_skill_data, context=context
    )
    extra_hit_from_changes = _apply_effect_changes_like_duel(
        room, state, chg_hit, attacker_char, defender_char, base_damage, log_snippets, reuse_requests=reuse_requests
    )

    try:
        kiretsu = int(get_status_value(defender_char, '亀裂'))
    except Exception:
        kiretsu = 0

    bonus_damage = int(bd_un) + int(bd_hit)
    extra_skill_damage = int(extra_un) + int(extra_hit_from_changes)
    log_snippets.extend(log_un or [])
    log_snippets.extend(log_hit or [])

    extra_on_hit = int(process_on_hit_buffs(
        attacker_char,
        defender_char,
        base_damage + kiretsu + bonus_damage + extra_skill_damage,
        log_snippets
    ))

    skill_deals_damage = _skill_deals_damage(attacker_skill_data)
    final_damage = base_damage + kiretsu + bonus_damage + extra_skill_damage + extra_on_hit
    if skill_deals_damage:
        mult_info = compute_damage_multipliers(attacker_char, defender_char, context=context)
        final_damage = int(final_damage * float(mult_info.get('final', 1.0) or 1.0))
        _append_multiplier_logs(log_snippets, mult_info)

        # Keep one-sided resolve logs consistent with the formatted resolve output.
        # Direct _update_char_stat logging here creates out-of-band lines such as
        # "[select_resolve_one_sided]: ...", so apply HP locally and let the
        # synthesized resolve log render the state transition.
        curr_hp = int(defender_char.get('hp', 0) or 0)
        defender_char['hp'] = max(0, curr_hp - int(final_damage or 0))
        on_damage_extra = int(process_on_damage_buffs(room, defender_char, final_damage, "[select_resolve_one_sided]", log_snippets))
    else:
        final_damage = 0
        on_damage_extra = 0
        log_snippets.append("[効果スキル]")
    total_damage = int(final_damage) + int(on_damage_extra)

    _trigger_skill_timing_effects(
        room=room,
        state=state,
        characters_by_id=characters_by_id,
        timing='AFTER_DAMAGE_APPLY',
        actor_char=attacker_char,
        target_char=defender_char,
        skill_data=attacker_skill_data,
        target_skill_data=defender_skill_data,
        base_damage=total_damage,
        emit_source='after_damage_apply'
    )
    if isinstance(defender_skill_data, dict):
        _trigger_skill_timing_effects(
            room=room,
            state=state,
            characters_by_id=characters_by_id,
            timing='AFTER_DAMAGE_APPLY',
            actor_char=defender_char,
            target_char=attacker_char,
            skill_data=defender_skill_data,
            target_skill_data=attacker_skill_data,
            base_damage=total_damage,
            emit_source='after_damage_apply'
        )

    after_a = _snapshot_for_outcome(attacker_char)
    after_d = _snapshot_for_outcome(defender_char)
    delta_a = _diff_snapshot(before_a, after_a, damage_source='一方攻撃')
    delta_d = _diff_snapshot(before_d, after_d, damage_source='一方攻撃')

    summary = {
        'damage': delta_a.get('damage', []) + delta_d.get('damage', []),
        'statuses': delta_a.get('statuses', []) + delta_d.get('statuses', []),
        'flags': delta_a.get('flags', []) + delta_d.get('flags', []),
        'cost': {'mp': 0, 'hp': 0, 'fp': 0},
        'hit': bool(total_damage > 0),
        'win': True,
        'logs': log_snippets,
        'reuse_requests': reuse_requests,
        'rolls': {
            'command': final_command,
            'min_damage': (preview or {}).get('min_damage'),
            'max_damage': (preview or {}).get('max_damage'),
            'power_breakdown': (preview or {}).get('power_breakdown', {}),
            'power_snapshot': power_snapshot,
            'roll_breakdown': (roll_result or {}).get('breakdown', {}),
            'base_damage': base_damage,
            'kiretsu': kiretsu,
            'bonus_damage': bonus_damage,
            'extra_skill_damage': extra_skill_damage,
            'extra_on_hit': extra_on_hit,
            'final_damage': final_damage,
            'on_damage_extra': on_damage_extra,
            'total_damage': total_damage,
            'deals_damage': bool(skill_deals_damage),
        },
    }
    logger.info(
        "[one_sided_apply] attacker=%s defender=%s command=%s base=%d final=%d extra_on_damage=%d hp_after=%d",
        attacker_char.get('id'), defender_char.get('id'), final_command, base_damage, final_damage, on_damage_extra, int(defender_char.get('hp', 0))
    )
    return {'ok': True, 'summary': summary}












def _resolve_clash_by_existing_logic(
    room,
    state,
    attacker_char,
    defender_char,
    attacker_skill_data,
    defender_skill_data
):
    """
    Delegate clash resolution to existing duel solver:
    - manager/battle/duel_solver.py::execute_duel_match
    - Existing tie handling / win conditions / hit+win effects are preserved there.
    """
    if not attacker_char or not defender_char:
        return {'ok': False, 'reason': 'missing_actor'}
    if not attacker_skill_data or not defender_skill_data:
        return {'ok': False, 'reason': 'missing_skill'}

    from manager.battle import duel_solver as duel_solver_mod
    from manager.battle import core as core_mod
    from manager import room_manager as room_manager_mod
    from manager import skill_effects as skill_effects_mod

    before_a = _snapshot_for_outcome(attacker_char)
    before_d = _snapshot_for_outcome(defender_char)

    context = {'timeline': state.get('timeline', []), 'characters': state.get('characters', []), 'room': room}
    characters_by_id = {
        c.get('id'): c for c in state.get('characters', [])
        if isinstance(c, dict) and c.get('id')
    }
    attacker_char['_base_power_bonus'] = 0
    attacker_char['_final_power_bonus'] = 0
    defender_char['_base_power_bonus'] = 0
    defender_char['_final_power_bonus'] = 0
    _trigger_skill_timing_effects(
        room=room,
        state=state,
        characters_by_id=characters_by_id,
        timing='PRE_MATCH',
        actor_char=attacker_char,
        target_char=defender_char,
        skill_data=attacker_skill_data,
        target_skill_data=defender_skill_data,
        base_damage=0,
        emit_source='select_resolve_pre_match'
    )
    _trigger_skill_timing_effects(
        room=room,
        state=state,
        characters_by_id=characters_by_id,
        timing='PRE_MATCH',
        actor_char=defender_char,
        target_char=attacker_char,
        skill_data=defender_skill_data,
        target_skill_data=attacker_skill_data,
        base_damage=0,
        emit_source='select_resolve_pre_match'
    )
    _trigger_skill_timing_effects(
        room=room,
        state=state,
        characters_by_id=characters_by_id,
        timing='BEFORE_POWER_ROLL',
        actor_char=attacker_char,
        target_char=defender_char,
        skill_data=attacker_skill_data,
        target_skill_data=defender_skill_data,
        base_damage=0,
        emit_source='before_power_roll'
    )
    _trigger_skill_timing_effects(
        room=room,
        state=state,
        characters_by_id=characters_by_id,
        timing='BEFORE_POWER_ROLL',
        actor_char=defender_char,
        target_char=attacker_char,
        skill_data=defender_skill_data,
        target_skill_data=attacker_skill_data,
        base_damage=0,
        emit_source='before_power_roll'
    )
    preview_a = calculate_skill_preview(attacker_char, defender_char, attacker_skill_data, context=context)
    preview_d = calculate_skill_preview(defender_char, attacker_char, defender_skill_data, context=context)
    command_a = (preview_a or {}).get('final_command') or "0"
    command_d = (preview_d or {}).get('final_command') or "0"

    actor_a_id = attacker_char.get('id')
    actor_d_id = defender_char.get('id')
    actor_a_name = attacker_char.get('name', str(actor_a_id))
    actor_d_name = defender_char.get('name', str(actor_d_id))
    skill_id_a = _extract_skill_id_from_data(attacker_skill_data)
    skill_id_d = _extract_skill_id_from_data(defender_skill_data)

    captured = {
        'match_log': None,
        'damage_logs': [],
        'effect_logs': [],
    }
    synthetic_timeline = [
        {'id': f"select_resolve_a_{actor_a_id}", 'char_id': actor_a_id, 'acted': False},
        {'id': f"select_resolve_d_{actor_d_id}", 'char_id': actor_d_id, 'acted': False},
    ]
    match_id = f"select_resolve_clash_{actor_a_id}_{actor_d_id}_{_resolve_server_ts()}"
    exec_data = {
        'room': room,
        'match_id': match_id,
        'actorIdA': actor_a_id,
        'actorIdD': actor_d_id,
        'actorNameA': actor_a_name,
        'actorNameD': actor_d_name,
        'commandA': command_a,
        'commandD': command_d,
        'skillIdA': skill_id_a,
        'skillIdD': skill_id_d,
        'senritsuPenaltyA': int((preview_a or {}).get('senritsu_dice_reduction', 0)),
        'senritsuPenaltyD': int((preview_d or {}).get('senritsu_dice_reduction', 0)),
    }

    had_active_match = 'active_match' in state
    old_active_match = state.get('active_match')
    old_timeline = state.get('timeline')
    old_turn_entry = state.get('turn_entry_id')
    old_turn_char = state.get('turn_char_id')
    had_last_exec = 'last_executed_match_id' in state
    old_last_exec = state.get('last_executed_match_id')
    had_sr_delegate_flag = '__select_resolve_delegate__' in state
    old_sr_delegate_flag = state.get('__select_resolve_delegate__')
    old_has_acted_a = attacker_char.get('hasActed')
    old_has_acted_d = defender_char.get('hasActed')

    orig_proceed = duel_solver_mod.proceed_next_turn
    orig_save = duel_solver_mod.save_specific_room_state
    orig_state_update = duel_solver_mod.broadcast_state_update
    orig_emit = duel_solver_mod.socketio.emit
    orig_blog = duel_solver_mod.broadcast_log
    orig_core_blog = core_mod.broadcast_log
    orig_room_blog = room_manager_mod.broadcast_log
    orig_skill_effects_blog = getattr(skill_effects_mod, 'broadcast_log', None)
    orig_roll_dice = getattr(duel_solver_mod, 'roll_dice', None)
    captured_roll_results = []

    def _capture_broadcast_log(room_name, message, log_type='system', save=True):
        if isinstance(message, str):
            if log_type == 'match':
                captured['match_log'] = message
            elif log_type == 'damage':
                captured['damage_logs'].append(message)
            else:
                captured['effect_logs'].append(message)
        # In select/resolve clash delegation, capture only; do not emit legacy duel logs.
        return None

    def _capture_roll_dice(command_text):
        if not callable(orig_roll_dice):
            return {'total': 0, 'details': '', 'breakdown': {'dice_total': 0, 'constant_total': 0, 'final_total': 0}}
        result = orig_roll_dice(command_text)
        try:
            captured_roll_results.append({
                'command': str(command_text or ''),
                'result': copy.deepcopy(result) if isinstance(result, dict) else {'total': _safe_int(result, 0)}
            })
        except Exception:
            pass
        return result

    try:
        # Isolation for select/resolve mode:
        # keep duel math intact but suppress turn progression and legacy emissions.
        state['timeline'] = synthetic_timeline
        state['turn_entry_id'] = synthetic_timeline[0]['id']
        state['turn_char_id'] = actor_a_id
        state['active_match'] = {}
        state['__select_resolve_delegate__'] = True
        if 'last_executed_match_id' in state:
            del state['last_executed_match_id']
        attacker_char['hasActed'] = False
        defender_char['hasActed'] = False

        duel_solver_mod.proceed_next_turn = lambda *_args, **_kwargs: None
        duel_solver_mod.save_specific_room_state = lambda *_args, **_kwargs: None
        duel_solver_mod.broadcast_state_update = lambda *_args, **_kwargs: None
        duel_solver_mod.socketio.emit = lambda *_args, **_kwargs: None
        duel_solver_mod.broadcast_log = _capture_broadcast_log
        core_mod.broadcast_log = _capture_broadcast_log
        room_manager_mod.broadcast_log = _capture_broadcast_log
        if callable(orig_skill_effects_blog):
            skill_effects_mod.broadcast_log = _capture_broadcast_log
        if callable(orig_roll_dice):
            duel_solver_mod.roll_dice = _capture_roll_dice

        duel_solver_mod.execute_duel_match(room, exec_data, "[select_resolve_clash]")
    except Exception as e:
        logger.exception("[clash_delegate] execute_duel_match failed: %s", e)
        return {'ok': False, 'reason': f'delegate_error:{e}'}
    finally:
        duel_solver_mod.proceed_next_turn = orig_proceed
        duel_solver_mod.save_specific_room_state = orig_save
        duel_solver_mod.broadcast_state_update = orig_state_update
        duel_solver_mod.socketio.emit = orig_emit
        duel_solver_mod.broadcast_log = orig_blog
        core_mod.broadcast_log = orig_core_blog
        room_manager_mod.broadcast_log = orig_room_blog
        if callable(orig_skill_effects_blog):
            skill_effects_mod.broadcast_log = orig_skill_effects_blog
        if callable(orig_roll_dice):
            duel_solver_mod.roll_dice = orig_roll_dice

        state['timeline'] = old_timeline
        state['turn_entry_id'] = old_turn_entry
        state['turn_char_id'] = old_turn_char
        if had_active_match:
            state['active_match'] = old_active_match
        else:
            state.pop('active_match', None)
        if had_last_exec:
            state['last_executed_match_id'] = old_last_exec
        else:
            state.pop('last_executed_match_id', None)
        if had_sr_delegate_flag:
            state['__select_resolve_delegate__'] = old_sr_delegate_flag
        else:
            state.pop('__select_resolve_delegate__', None)
        attacker_char['hasActed'] = old_has_acted_a
        defender_char['hasActed'] = old_has_acted_d

    _trigger_skill_timing_effects(
        room=room,
        state=state,
        characters_by_id=characters_by_id,
        timing='AFTER_DAMAGE_APPLY',
        actor_char=attacker_char,
        target_char=defender_char,
        skill_data=attacker_skill_data,
        target_skill_data=defender_skill_data,
        base_damage=0,
        emit_source='after_damage_apply'
    )
    _trigger_skill_timing_effects(
        room=room,
        state=state,
        characters_by_id=characters_by_id,
        timing='AFTER_DAMAGE_APPLY',
        actor_char=defender_char,
        target_char=attacker_char,
        skill_data=defender_skill_data,
        target_skill_data=attacker_skill_data,
        base_damage=0,
        emit_source='after_damage_apply'
    )

    after_a = _snapshot_for_outcome(attacker_char)
    after_d = _snapshot_for_outcome(defender_char)
    delta_a = _diff_snapshot(before_a, after_a, damage_source='ダメージ')
    delta_d = _diff_snapshot(before_d, after_d, damage_source='ダメージ')

    try:
        burst_before = int((before_d or {}).get('states', {}).get('裂傷', 0))
        burst_after = int((after_d or {}).get('states', {}).get('裂傷', 0))
    except Exception:
        burst_before, burst_after = None, None
    logger.info(
        "[clash_status_probe] attacker=%s defender=%s burst_before=%s burst_after=%s status_events_a=%d status_events_d=%d",
        actor_a_id,
        actor_d_id,
        str(burst_before),
        str(burst_after),
        len(delta_a.get('statuses', []) or []),
        len(delta_d.get('statuses', []) or [])
    )

    power_a, power_d = _extract_power_pair_from_match_log(captured.get('match_log'))
    outcome = 'no_effect'
    tie_break = None
    match_log = captured.get('match_log') or ""
    if power_a is not None and power_d is not None:
        if power_a > power_d:
            outcome = 'attacker_win'
        elif power_a < power_d:
            outcome = 'defender_win'
        else:
            tie_break = 'draw'
            if ('引き分け' in match_log) or ('蠑輔″蛻・￠' in match_log):
                outcome = 'draw'
            elif (f"{actor_a_name} の勝利" in match_log) or (f"{actor_a_name} 縺ｮ蜍晏茜" in match_log):
                outcome = 'attacker_win'
                tie_break = 'existing_rule_attacker'
            elif (f"{actor_d_name} の勝利" in match_log) or (f"{actor_d_name} 縺ｮ蜍晏茜" in match_log):
                outcome = 'defender_win'
                tie_break = 'existing_rule_defender'
            else:
                outcome = 'draw'
    else:
        if delta_d.get('damage') and not delta_a.get('damage'):
            outcome = 'attacker_win'
        elif delta_a.get('damage') and not delta_d.get('damage'):
            outcome = 'defender_win'
        elif delta_a.get('damage') or delta_d.get('damage'):
            outcome = 'draw'

    if outcome == 'attacker_win' and not _skill_deals_damage(attacker_skill_data):
        defender_char['hp'] = int((before_d or {}).get('hp', defender_char.get('hp', 0)))
        after_d = _snapshot_for_outcome(defender_char)
        delta_d = _diff_snapshot(before_d, after_d, damage_source='ダメージ')
        captured['effect_logs'].append('[効果スキル] 攻撃側のHP差分を補正')
    elif outcome == 'defender_win' and not _skill_deals_damage(defender_skill_data):
        attacker_char['hp'] = int((before_a or {}).get('hp', attacker_char.get('hp', 0)))
        after_a = _snapshot_for_outcome(attacker_char)
        delta_a = _diff_snapshot(before_a, after_a, damage_source='ダメージ')
        captured['effect_logs'].append('[効果スキル] 防御側のHP差分を補正')

    roll_a_entry = captured_roll_results[0] if len(captured_roll_results) > 0 else {}
    roll_d_entry = captured_roll_results[1] if len(captured_roll_results) > 1 else {}
    roll_result_a = roll_a_entry.get('result') if isinstance(roll_a_entry, dict) else None
    roll_result_d = roll_d_entry.get('result') if isinstance(roll_d_entry, dict) else None
    command_a_used = str((roll_a_entry.get('command') if isinstance(roll_a_entry, dict) else None) or command_a or '')
    command_d_used = str((roll_d_entry.get('command') if isinstance(roll_d_entry, dict) else None) or command_d or '')

    snapshot_a = _build_clash_power_snapshot(
        preview_a,
        command_a_used,
        power_a if power_a is not None else _safe_int((roll_result_a or {}).get('total', 0), 0),
        roll_result=roll_result_a
    )
    snapshot_d = _build_clash_power_snapshot(
        preview_d,
        command_d_used,
        power_d if power_d is not None else _safe_int((roll_result_d or {}).get('total', 0), 0),
        roll_result=roll_result_d
    )
    if power_a is None and isinstance(snapshot_a, dict):
        power_a = _safe_int(snapshot_a.get('final_power', 0), 0)
    if power_d is None and isinstance(snapshot_d, dict):
        power_d = _safe_int(snapshot_d.get('final_power', 0), 0)

    cost_a = _estimate_cost_for_skill_from_snapshot(before_a, attacker_skill_data)
    cost_d = _estimate_cost_for_skill_from_snapshot(before_d, defender_skill_data)
    total_cost = {
        'mp': int(cost_a.get('mp', 0)) + int(cost_d.get('mp', 0)),
        'hp': int(cost_a.get('hp', 0)) + int(cost_d.get('hp', 0)),
        'fp': int(cost_a.get('fp', 0)) + int(cost_d.get('fp', 0)),
    }

    summary = {
        'damage': delta_a.get('damage', []) + delta_d.get('damage', []),
        'statuses': delta_a.get('statuses', []) + delta_d.get('statuses', []),
        'flags': delta_a.get('flags', []) + delta_d.get('flags', []),
        'cost': total_cost,
        'hit': bool(delta_a.get('damage') or delta_d.get('damage')),
        'win': outcome in ['attacker_win', 'defender_win'],
        'rolls': {
            'power_a': power_a,
            'power_b': power_d,
            'tie_break': tie_break,
            'command': command_a_used or command_a,
            'command_b': command_d_used or command_d,
            'min_damage_a': (preview_a or {}).get('min_damage'),
            'max_damage_a': (preview_a or {}).get('max_damage'),
            'min_damage_b': (preview_d or {}).get('min_damage'),
            'max_damage_b': (preview_d or {}).get('max_damage'),
            'power_breakdown_a': (preview_a or {}).get('power_breakdown', {}),
            'power_breakdown_b': (preview_d or {}).get('power_breakdown', {}),
            'power_snapshot_a': snapshot_a,
            'power_snapshot_b': snapshot_d,
            'roll_breakdown_a': ((snapshot_a or {}).get('raw', {}) or {}).get('roll_breakdown', {}),
            'roll_breakdown_b': ((snapshot_d or {}).get('raw', {}) or {}).get('roll_breakdown', {}),
        },
        'match_log': captured.get('match_log'),
        'legacy_log_lines': (
            ([captured.get('match_log')] if captured.get('match_log') else [])
            + list(captured.get('damage_logs', []) or [])
            + list(captured.get('effect_logs', []) or [])
        ),
    }
    logger.info(
        "[clash_apply] attacker=%s defender=%s power_a=%s power_b=%s tie_break=%s outcome=%s",
        actor_a_id, actor_d_id, str(power_a), str(power_d), str(tie_break), outcome
    )
    return {'ok': True, 'summary': summary, 'outcome': outcome}


def _resolve_hard_attack_followup(
    room,
    state,
    attacker_char,
    defender_char,
    attacker_skill_data,
    defender_skill_data=None,
):
    if not isinstance(attacker_char, dict) or not isinstance(defender_char, dict):
        return {"ok": False, "reason": "missing_actor"}
    if not isinstance(attacker_skill_data, dict):
        return {"ok": False, "reason": "missing_skill"}

    before_a = _snapshot_for_outcome(attacker_char)
    before_d = _snapshot_for_outcome(defender_char)
    context = {'timeline': state.get('timeline', []), 'characters': state.get('characters', []), 'room': room}
    attacker_rule = _extract_rule_data_from_skill(attacker_skill_data)
    effects_array_a = attacker_rule.get('effects', []) if isinstance(attacker_rule, dict) else []

    preview_a = calculate_skill_preview(attacker_char, defender_char, attacker_skill_data, context=context)
    base_damage = int(((preview_a or {}).get('power_breakdown', {}) or {}).get('final_base_power', 0) or 0)
    if base_damage < 0:
        base_damage = 0

    defense_power = None
    blocked_by_evade = False
    if isinstance(defender_skill_data, dict):
        preview_d = calculate_skill_preview(defender_char, attacker_char, defender_skill_data, context=context)
        command_d = (preview_d or {}).get('final_command') or "0"
        roll_d = roll_dice(command_d)
        try:
            defense_power = int(roll_d.get('total', 0) or 0)
        except Exception:
            defense_power = 0
        blocked_by_evade = defense_power >= base_damage

    log_snippets = []
    reuse_requests = []
    bd_lose, log_lose, chg_lose = process_skill_effects(
        effects_array_a,
        "LOSE",
        attacker_char,
        defender_char,
        defender_skill_data,
        context=context,
        base_damage=base_damage,
    )
    extra_lose = _apply_effect_changes_like_duel(
        room, state, chg_lose, attacker_char, defender_char, base_damage, log_snippets, reuse_requests=reuse_requests
    )

    bd_hit, log_hit, chg_hit = process_skill_effects(
        effects_array_a,
        "HIT",
        attacker_char,
        defender_char,
        defender_skill_data,
        context=context,
        base_damage=base_damage,
    )
    extra_hit = _apply_effect_changes_like_duel(
        room, state, chg_hit, attacker_char, defender_char, base_damage, log_snippets, reuse_requests=reuse_requests
    )
    log_snippets.extend(log_lose or [])
    log_snippets.extend(log_hit or [])

    final_damage = 0
    on_damage_extra = 0
    if not blocked_by_evade and _skill_deals_damage(attacker_skill_data):
        raw_damage = int(base_damage) + int(bd_lose) + int(bd_hit) + int(extra_lose) + int(extra_hit)
        mult_info = compute_damage_multipliers(attacker_char, defender_char, context=context)
        final_damage = int(raw_damage * float(mult_info.get('final', 1.0) or 1.0))
        _append_multiplier_logs(log_snippets, mult_info)
        if final_damage > 0:
            _update_char_stat(room, defender_char, 'HP', int(defender_char.get('hp', 0)) - final_damage, username="[hard_attack]")
            on_damage_extra = int(process_on_damage_buffs(room, defender_char, final_damage, "[hard_attack]", log_snippets))
    elif blocked_by_evade:
        log_snippets.append("[強硬攻撃] 回避されました")
    else:
        log_snippets.append("[強硬攻撃] 効果スキル")

    total_damage = int(final_damage) + int(on_damage_extra)
    after_a = _snapshot_for_outcome(attacker_char)
    after_d = _snapshot_for_outcome(defender_char)
    delta_a = _diff_snapshot(before_a, after_a, damage_source='強硬攻撃')
    delta_d = _diff_snapshot(before_d, after_d, damage_source='強硬攻撃')

    outcome = 'attacker_win' if (not blocked_by_evade and total_damage > 0) else 'defender_win'
    summary = {
        'damage': delta_a.get('damage', []) + delta_d.get('damage', []),
        'statuses': delta_a.get('statuses', []) + delta_d.get('statuses', []),
        'flags': delta_a.get('flags', []) + delta_d.get('flags', []),
        'cost': {'mp': 0, 'hp': 0, 'fp': 0},
        'hit': bool(total_damage > 0),
        'win': bool(outcome == 'attacker_win'),
        'logs': log_snippets,
        'reuse_requests': reuse_requests,
        'rolls': {
            'base_damage': base_damage,
            'defense_power': defense_power,
            'blocked_by_evade': blocked_by_evade,
            'final_damage': final_damage,
            'on_damage_extra': on_damage_extra,
            'total_damage': total_damage,
            'deals_damage': bool(_skill_deals_damage(attacker_skill_data)),
            'hard_attack': True,
        },
    }
    return {'ok': True, 'summary': summary, 'outcome': outcome}


















def _roll_power_for_slot(battle_state, slot_id, intents_override=None):
    if not isinstance(intents_override, dict):
        intents_override = battle_state.get('__resolve_intents_override')
    intents = intents_override if isinstance(intents_override, dict) else battle_state.get('intents', {})
    intent = intents.get(slot_id, {})
    skill_id = intent.get('skill_id')
    if not skill_id:
        return 0

    skill_data = all_skill_data.get(skill_id, {}) if isinstance(all_skill_data, dict) else {}
    slots = battle_state.get('slots', {}) if isinstance(battle_state, dict) else {}
    slot_data = slots.get(slot_id, {}) if isinstance(slots, dict) else {}
    attacker_actor_id = slot_data.get('actor_id')
    target = intent.get('target', {}) if isinstance(intent, dict) else {}

    target_slot_id = None
    if isinstance(target, dict) and target.get('type') == 'single_slot':
        target_slot_id = target.get('slot_id')
    elif isinstance(target, dict) and target.get('type') in ['mass_individual', 'mass_summation']:
        # For mass skills, pick one representative defender (highest initiative) for preview context.
        candidates = []
        attacker_team = slot_data.get('team')
        for defender_slot_id, defender_intent in intents.items():
            if not isinstance(defender_intent, dict) or not defender_intent.get('committed', False):
                continue
            defender_target = defender_intent.get('target', {}) or {}
            if defender_target.get('type') != 'single_slot':
                continue
            if defender_target.get('slot_id') != slot_id:
                continue
            defender_slot_data = slots.get(defender_slot_id, {}) if isinstance(slots, dict) else {}
            if attacker_team and defender_slot_data.get('team') == attacker_team:
                continue
            candidates.append((
                -int(defender_slot_data.get('initiative', 0) or 0),
                str(defender_slot_id),
                defender_slot_id,
            ))
        if candidates:
            candidates.sort()
            target_slot_id = candidates[0][2]

    room_state = battle_state.get('__room_state_ref__') if isinstance(battle_state, dict) else None
    if not isinstance(room_state, dict):
        room_name = battle_state.get('__room_name') if isinstance(battle_state, dict) else None
        if room_name:
            room_state = get_room_state(room_name)
    if isinstance(room_state, dict):
        chars_by_id = {
            c.get('id'): c
            for c in room_state.get('characters', [])
            if isinstance(c, dict) and c.get('id')
        }
        attacker_char = chars_by_id.get(attacker_actor_id)
        defender_char = None
        if target_slot_id and isinstance(slots, dict):
            defender_slot_data = slots.get(target_slot_id, {}) or {}
            defender_char = chars_by_id.get(defender_slot_data.get('actor_id'))
        defender_skill_data = None
        if target_slot_id and isinstance(intents.get(target_slot_id), dict):
            defender_skill_id = intents.get(target_slot_id, {}).get('skill_id')
            if defender_skill_id and isinstance(all_skill_data, dict):
                defender_skill_data = all_skill_data.get(defender_skill_id, {})

        if isinstance(attacker_char, dict) and isinstance(skill_data, dict):
            try:
                attacker_char['_base_power_bonus'] = 0
                attacker_char['_final_power_bonus'] = 0
                if isinstance(defender_char, dict):
                    defender_char['_base_power_bonus'] = 0
                    defender_char['_final_power_bonus'] = 0
                room_name = battle_state.get('__room_name') if isinstance(battle_state, dict) else None
                if room_name:
                    _trigger_skill_timing_effects(
                        room=room_name,
                        state=room_state,
                        characters_by_id=chars_by_id,
                        timing='BEFORE_POWER_ROLL',
                        actor_char=attacker_char,
                        target_char=defender_char or attacker_char,
                        skill_data=skill_data,
                        target_skill_data=defender_skill_data,
                        base_damage=0,
                        emit_source='before_power_roll'
                    )
                context = {
                    'room_state': room_state,
                    'battle_state': room_state.get('battle_state', {}) if isinstance(room_state, dict) else {},
                    'timeline': room_state.get('timeline', []) if isinstance(room_state, dict) else [],
                    'characters': room_state.get('characters', []) if isinstance(room_state, dict) else [],
                }
                preview = calculate_skill_preview(attacker_char, defender_char or attacker_char, skill_data, context=context)
                final_command = (preview or {}).get('final_command') or "0"
                total = int((roll_dice(final_command) or {}).get('total', 0) or 0)
                logger.info(
                    "[roll_power_slot] slot=%s skill=%s command=%s total=%s mode=preview target_slot=%s",
                    slot_id, skill_id, final_command, total, target_slot_id
                )
                return max(0, total)
            except Exception as e:
                logger.warning(
                    "[roll_power_slot] preview roll failed slot=%s skill=%s target_slot=%s error=%s",
                    slot_id, skill_id, target_slot_id, e
                )

    # Fallback: static power expression from skill data.
    try:
        base_power = int(
            skill_data.get(
                '蝓ｺ遉主ｨ∝鴨',
                skill_data.get('base_power', 0)
            ) or 0
        )
    except Exception:
        base_power = 0
    dice_part = str(
        skill_data.get(
            '繝繧､繧ｹ螽∝鴨',
            skill_data.get('dice_power', '')
        ) or ''
    ).strip()
    if base_power and dice_part:
        command = f"{base_power}{dice_part}" if dice_part.startswith(('+', '-')) else f"{base_power}+{dice_part}"
    elif dice_part:
        command = dice_part
    elif base_power:
        command = str(base_power)
    else:
        command = "1d20"

    try:
        total = int((roll_dice(command) or {}).get('total', 0) or 0)
    except Exception:
        total = 0
    logger.info(
        "[roll_power_slot] slot=%s skill=%s command=%s total=%s mode=fallback",
        slot_id, skill_id, command, total
    )
    return max(0, total)




