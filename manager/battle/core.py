import re
import json
import time
import html
import copy
from extensions import all_skill_data
from extensions import socketio
from manager.dice_roller import roll_dice

from manager.game_logic import (
    process_skill_effects, apply_buff, remove_buff, get_status_value,
    calculate_skill_preview, calculate_damage_multiplier, compute_damage_multipliers,
    build_power_result_snapshot
)
import manager.utils as _utils_mod
from models import Room
from manager.buff_catalog import get_buff_effect
from manager.room_manager import (
    get_room_state, broadcast_log, broadcast_state_update,
    save_specific_room_state, _update_char_stat
)
from manager.constants import DamageSource
from manager.logs import setup_logger
from manager.summons.service import apply_summon_change, process_summon_round_end
from manager.granted_skills.service import (
    apply_grant_skill_change,
    process_granted_skill_round_end,
    consume_granted_skill_use,
)
from manager.bleed_logic import consume_bleed_maintenance_stack
from manager.battle.duel_log_utils import (
    _resolve_actor_name,
    _resolve_skill_name,
    _extract_skill_id_from_data,
    _format_damage_lines,
    _format_status_lines,
    _build_match_log_lines,
    _log_match_result,
    _is_dice_damage_source,
    _split_damage_entries_for_display,
    _extract_damage_parts_from_legacy_lines,
    format_duel_result_lines,
)
from manager.battle.skill_rules import (
    _extract_rule_data_from_skill,
    _extract_skill_cost_entries,
    _has_skill_tag,
    _skill_deals_damage,
    _is_hard_skill,
    _is_feint_skill,
    _is_normal_skill,
    _collect_skill_tags,
    _resolve_skill_category,
    _normalize_target_scope,
    _infer_target_scope_from_skill_data,
    _is_ally_target_skill_data,
    _canonical_slot_team,
    _is_same_team_slot_pair,
    _is_non_clashable_ally_support_pair,
    _resolve_skill_role,
    _get_forced_clash_no_effect_reason,
    _get_inherent_skill_cancel_reason,
    _normalize_effect_timing,
    _effect_targets_self,
    _estimate_immediate_self_fp_gain,
    _skill_has_direct_fp_gain,
)

from manager.battle.fp_summary import (
    _sanitize_forced_no_match_clash_summary,
    _should_grant_clash_win_fp,
    _summary_has_positive_fp_gain,
    _summary_fp_gain_total,
    _summary_has_match_win_fp_gain,
    _iter_summary_log_lines,
    _extract_fp_transition_delta_from_line,
    _summary_logs_has_positive_fp_gain,
    _summary_logs_fp_gain_total,
    _summary_logs_has_match_win_fp_gain,
    _set_actor_status_local,
    _ensure_clash_winner_fp_gain,
)
from manager.battle.trace_helpers import (
    _trace_kind_label,
    _trace_outcome_label,
    _trace_actor_name,
    _trace_damage_total,
    _format_power_snapshot_line,
    _build_trace_compact_log_message_legacy,
    _sanitize_power_snapshot,
    _sanitize_power_breakdown,
    _build_trace_compact_log_message,
)
from manager.battle.timeline_helpers import (
    _consume_legacy_timeline_entries_for_slots,
    _sync_legacy_has_acted_flags_from_timeline,
    _snapshot_legacy_timeline_state,
    _is_actor_placed,
)

from manager.battle.resolve_snapshot_utils import (
    _extract_power_pair_from_match_log,
    _estimate_roll_breakdown_from_command_and_total,
    _build_clash_power_snapshot,
    _extract_step_aux_log_lines,
    _estimate_cost_for_skill_from_snapshot,
)

from manager.battle.runtime_actions import (
    calculate_opponent_skill_modifiers,
    extract_cost_from_text,
    extract_custom_skill_name,
    format_skill_name_for_log,
    format_skill_display_from_command,
    verify_skill_cost,
    process_on_damage_buffs,
    process_on_hit_buffs,
    execute_pre_match_effects,
    proceed_next_turn,
    process_simple_round_end,
)

from manager.battle.resolve_queue_helpers import (
    _build_resolve_queues,
    _enemy_actor_ids_for_team,
    _estimate_mass_trace_steps,
    _intent_single_target_slot,
    _compute_single_contention,
    _estimate_single_trace_steps,
    _consume_resolve_slot,
    _compare_outcome,
    _gather_slots_targeting_slot_s,
)
import manager.battle.resolve_trace_runtime as _resolve_trace_runtime_mod
import manager.battle.resolve_effect_runtime as _resolve_effect_runtime_mod
import manager.battle.resolve_legacy_log_adapter as _resolve_legacy_log_adapter_mod
import manager.battle.resolve_match_runtime as _resolve_match_runtime_mod
import manager.battle.resolve_auto_runtime as _resolve_auto_runtime_mod

logger = setup_logger(__name__)

get_effective_origin_id = getattr(_utils_mod, 'get_effective_origin_id', lambda *_args, **_kwargs: 0)
set_status_value = getattr(_utils_mod, 'set_status_value', lambda *_args, **_kwargs: None)
clear_newly_applied_flags = getattr(_utils_mod, 'clear_newly_applied_flags', lambda *_args, **_kwargs: 0)
get_round_end_origin_recoveries = getattr(_utils_mod, 'get_round_end_origin_recoveries', lambda *_args, **_kwargs: {})
apply_origin_bonus_buffs = getattr(_utils_mod, 'apply_origin_bonus_buffs', lambda *_args, **_kwargs: None)

COST_CONSUME_POLICY = "on_execute"
MAX_USE_SKILL_AGAIN_CHAIN_HARD_CAP = 20


def _sync_resolve_trace_runtime_deps():
    _resolve_trace_runtime_mod.logger = logger
    _resolve_trace_runtime_mod.socketio = socketio
    _resolve_trace_runtime_mod.all_skill_data = all_skill_data
    _resolve_trace_runtime_mod.get_room_state = get_room_state
    _resolve_trace_runtime_mod.save_specific_room_state = save_specific_room_state
    _resolve_trace_runtime_mod._build_trace_compact_log_message = _build_trace_compact_log_message
    _resolve_trace_runtime_mod._extract_step_aux_log_lines = _extract_step_aux_log_lines
    _resolve_trace_runtime_mod._trace_kind_label = _trace_kind_label
    _resolve_trace_runtime_mod._trace_outcome_label = _trace_outcome_label
    _resolve_trace_runtime_mod._trace_actor_name = _trace_actor_name
    _resolve_trace_runtime_mod._trace_damage_total = _trace_damage_total
    _resolve_trace_runtime_mod._sanitize_power_snapshot = _sanitize_power_snapshot
    _resolve_trace_runtime_mod._sanitize_power_breakdown = _sanitize_power_breakdown
    _resolve_trace_runtime_mod._apply_step_end_timing_from_trace = _apply_step_end_timing_from_trace


def _sync_resolve_effect_runtime_deps():
    _resolve_effect_runtime_mod.logger = logger
    _resolve_effect_runtime_mod.all_skill_data = all_skill_data
    _resolve_effect_runtime_mod.socketio = socketio
    _resolve_effect_runtime_mod.get_room_state = get_room_state
    _resolve_effect_runtime_mod.broadcast_log = broadcast_log
    _resolve_effect_runtime_mod._update_char_stat = _update_char_stat
    _resolve_effect_runtime_mod.apply_summon_change = apply_summon_change
    _resolve_effect_runtime_mod.apply_grant_skill_change = apply_grant_skill_change
    _resolve_effect_runtime_mod.consume_granted_skill_use = consume_granted_skill_use
    _resolve_effect_runtime_mod.consume_bleed_maintenance_stack = consume_bleed_maintenance_stack
    _resolve_effect_runtime_mod.process_skill_effects = process_skill_effects
    _resolve_effect_runtime_mod.apply_buff = apply_buff
    _resolve_effect_runtime_mod.remove_buff = remove_buff
    _resolve_effect_runtime_mod.get_status_value = get_status_value
    _resolve_effect_runtime_mod.set_status_value = set_status_value
    _resolve_effect_runtime_mod.DamageSource = DamageSource
    _resolve_effect_runtime_mod._extract_skill_id_from_data = _extract_skill_id_from_data
    _resolve_effect_runtime_mod._collect_intrinsic_cancelled_single_slots = _collect_intrinsic_cancelled_single_slots
    _resolve_effect_runtime_mod._safe_int = _safe_int
    _resolve_effect_runtime_mod.COST_CONSUME_POLICY = COST_CONSUME_POLICY
    _resolve_effect_runtime_mod.process_on_damage_buffs = process_on_damage_buffs


def _sync_resolve_legacy_log_adapter_deps():
    _resolve_legacy_log_adapter_mod.all_skill_data = all_skill_data
    _resolve_legacy_log_adapter_mod.format_skill_name_for_log = format_skill_name_for_log
    _resolve_legacy_log_adapter_mod.format_skill_display_from_command = format_skill_display_from_command
    _resolve_legacy_log_adapter_mod._extract_damage_parts_from_legacy_lines = _extract_damage_parts_from_legacy_lines
    _resolve_legacy_log_adapter_mod._is_dice_damage_source = _is_dice_damage_source
    _resolve_legacy_log_adapter_mod._humanize_resolve_reason = _humanize_resolve_reason


def _sync_resolve_match_runtime_deps():
    _resolve_match_runtime_mod.logger = logger
    _resolve_match_runtime_mod.all_skill_data = all_skill_data
    _resolve_match_runtime_mod.get_room_state = get_room_state
    _resolve_match_runtime_mod.calculate_skill_preview = calculate_skill_preview
    _resolve_match_runtime_mod.process_skill_effects = process_skill_effects
    _resolve_match_runtime_mod.get_status_value = get_status_value
    _resolve_match_runtime_mod.compute_damage_multipliers = compute_damage_multipliers
    _resolve_match_runtime_mod.build_power_result_snapshot = build_power_result_snapshot
    _resolve_match_runtime_mod.roll_dice = roll_dice
    _resolve_match_runtime_mod._update_char_stat = _update_char_stat
    _resolve_match_runtime_mod._extract_rule_data_from_skill = _extract_rule_data_from_skill
    _resolve_match_runtime_mod._skill_deals_damage = _skill_deals_damage
    _resolve_match_runtime_mod._extract_skill_id_from_data = _extract_skill_id_from_data
    _resolve_match_runtime_mod._extract_power_pair_from_match_log = _extract_power_pair_from_match_log
    _resolve_match_runtime_mod._build_clash_power_snapshot = _build_clash_power_snapshot
    _resolve_match_runtime_mod._estimate_cost_for_skill_from_snapshot = _estimate_cost_for_skill_from_snapshot
    _resolve_match_runtime_mod._record_used_skill_for_actor = _record_used_skill_for_actor
    _resolve_match_runtime_mod._snapshot_for_outcome = _snapshot_for_outcome
    _resolve_match_runtime_mod._trigger_skill_timing_effects = _trigger_skill_timing_effects
    _resolve_match_runtime_mod._apply_effect_changes_like_duel = _apply_effect_changes_like_duel
    _resolve_match_runtime_mod._diff_snapshot = _diff_snapshot
    _resolve_match_runtime_mod._append_multiplier_logs = _append_multiplier_logs
    _resolve_match_runtime_mod.process_on_damage_buffs = process_on_damage_buffs
    _resolve_match_runtime_mod.process_on_hit_buffs = process_on_hit_buffs
    _resolve_match_runtime_mod._resolve_server_ts = _resolve_server_ts
    _resolve_match_runtime_mod._safe_int = _safe_int


def _resolve_server_ts():
    return int(time.time())


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _humanize_resolve_reason_token(token):
    key = str(token or '').strip()
    if not key:
        return ''
    mapping = {
        'feint_blocked': 'フェイントにより強硬攻撃不成立',
        'hard_evaded': '回避成功により強硬攻撃不成立',
        'defense_evade_no_match': '防御と回避のためマッチ不成立',
        'evade_evade_no_match': '回避どうしのためマッチ不成立',
        'defense_evade_fizzle': '防御と回避のためスキル不発',
        'evade_evade_fizzle': '回避どうしのためスキル不発',
    }
    return mapping.get(key, key)


def _mark_slot_cancelled_without_use(battle_state, slot_id):
    if not isinstance(battle_state, dict) or not slot_id:
        return
    resolve = battle_state.setdefault('resolve', {})
    cancelled_slots = resolve.get('cancelled_slots', [])
    if not isinstance(cancelled_slots, list):
        cancelled_slots = []
    if slot_id not in cancelled_slots:
        cancelled_slots.append(slot_id)
    resolve['cancelled_slots'] = cancelled_slots

    slot_data = (battle_state.get('slots', {}) or {}).get(slot_id)
    if isinstance(slot_data, dict):
        slot_data['cancelled_without_use'] = True


def _collect_intrinsic_cancelled_single_slots(state, battle_state, intents_override=None):
    if not isinstance(state, dict) or not isinstance(battle_state, dict):
        return set()
    intents = intents_override if isinstance(intents_override, dict) else battle_state.get('intents', {})
    if not isinstance(intents, dict):
        return set()
    slots = battle_state.get('slots', {}) if isinstance(battle_state.get('slots'), dict) else {}
    single_queue = battle_state.get('resolve', {}).get('single_queue', []) or []
    if not isinstance(single_queue, list) or not single_queue:
        return set()

    contention = _compute_single_contention(intents, single_queue)
    contested_losers = set(contention.get('contested_losers', set()) or set())
    cancelled = set()

    for slot_id in single_queue:
        intent_a = intents.get(slot_id, {})
        skill_id_a = intent_a.get('skill_id') if isinstance(intent_a, dict) else None
        if not skill_id_a or slot_id in contested_losers:
            continue

        target = intent_a.get('target', {}) if isinstance(intent_a.get('target'), dict) else {}
        target_slot = target.get('slot_id') if target.get('type') == 'single_slot' else None
        if not target_slot:
            continue

        target_actor_id = (slots.get(target_slot, {}) or {}).get('actor_id')
        if not target_actor_id or not _is_actor_placed(state, target_actor_id):
            continue

        intent_b = intents.get(target_slot, {})
        skill_id_b = intent_b.get('skill_id') if isinstance(intent_b, dict) else None
        if not skill_id_b:
            continue

        skill_data_a = all_skill_data.get(skill_id_a, {}) if isinstance(all_skill_data, dict) else {}
        skill_data_b = all_skill_data.get(skill_id_b, {}) if isinstance(all_skill_data, dict) else {}
        if _is_non_clashable_ally_support_pair(slots, slot_id, target_slot, skill_data_a, skill_data_b):
            continue
        if intent_b.get('target', {}).get('type') != 'single_slot' or intent_b.get('target', {}).get('slot_id') != slot_id:
            continue

        if _get_inherent_skill_cancel_reason(skill_data_a, skill_data_b):
            cancelled.add(slot_id)
            cancelled.add(target_slot)

    return cancelled


def _humanize_resolve_reason(notes):
    raw = str(notes or '').strip()
    if not raw:
        return ''
    parts = [p.strip() for p in raw.split('/') if str(p).strip()]
    if not parts:
        return raw
    humanized = [_humanize_resolve_reason_token(p) for p in parts]
    return " / ".join([h for h in humanized if str(h).strip()])


def _append_multiplier_logs(log_snippets, mult_info, incoming_label='髦ｲ', outgoing_label='謾ｻ'):
    if not isinstance(log_snippets, list):
        return
    if not isinstance(mult_info, dict):
        return
    incoming_logs = mult_info.get('incoming_logs', []) or []
    outgoing_logs = mult_info.get('outgoing_logs', []) or []
    incoming = float(mult_info.get('incoming', 1.0) or 1.0)
    outgoing = float(mult_info.get('outgoing', 1.0) or 1.0)
    if incoming_logs:
        log_snippets.append(f"({incoming_label}:{'/'.join(incoming_logs)} x{incoming:.2f})")
    if outgoing_logs:
        log_snippets.append(f"({outgoing_label}:{'/'.join(outgoing_logs)} x{outgoing:.2f})")


def _apply_self_destruct_if_needed(room, actor_char, skill_data):
    if not isinstance(actor_char, dict):
        return False
    if int(actor_char.get('hp', 0) or 0) <= 0:
        return False
    if not (_has_skill_tag(skill_data, "自滅") or _has_skill_tag(skill_data, "自壊")):
        return False

    _update_char_stat(
        room,
        actor_char,
        'HP',
        0,
        username='[自滅]',
        source=DamageSource.SKILL_EFFECT
    )
    broadcast_log(room, f"{actor_char.get('name', 'Unknown')} は自滅した。", "state-change")
    return True


def _log_battle_emit(event_name, room_id, battle_id, payload):
    _sync_resolve_trace_runtime_deps()
    return _resolve_trace_runtime_mod._log_battle_emit(event_name, room_id, battle_id, payload)


def _build_trace_popup_payload(trace_entry, room_state):
    _sync_resolve_trace_runtime_deps()
    return _resolve_trace_runtime_mod._build_trace_popup_payload(trace_entry, room_state)


def _emit_battle_trace(room, battle_id, battle_state, trace_entry):
    _sync_resolve_trace_runtime_deps()
    return _resolve_trace_runtime_mod._emit_battle_trace(room, battle_id, battle_state, trace_entry)


def _append_trace(
    room,
    battle_id,
    battle_state,
    kind,
    attacker_slot,
    defender_slot=None,
    target_actor_id=None,
    notes=None,
    outcome='no_effect',
    cost=None,
    rolls=None,
    extra_fields=None
):
    _sync_resolve_trace_runtime_deps()
    return _resolve_trace_runtime_mod._append_trace(
        room,
        battle_id,
        battle_state,
        kind,
        attacker_slot,
        defender_slot=defender_slot,
        target_actor_id=target_actor_id,
        notes=notes,
        outcome=outcome,
        cost=cost,
        rolls=rolls,
        extra_fields=extra_fields,
    )
def _apply_cost(attacker, skill, policy):
    _sync_resolve_effect_runtime_deps()
    return _resolve_effect_runtime_mod._apply_cost(attacker, skill, policy)


def _apply_damage(defender, amount, damage_type=None):
    _sync_resolve_effect_runtime_deps()
    return _resolve_effect_runtime_mod._apply_damage(defender, amount, damage_type=damage_type)


def _apply_status(defender, status_payload):
    _sync_resolve_effect_runtime_deps()
    return _resolve_effect_runtime_mod._apply_status(defender, status_payload)


def _record_used_skill_for_actor(actor, skill_id):
    _sync_resolve_effect_runtime_deps()
    return _resolve_effect_runtime_mod._record_used_skill_for_actor(actor, skill_id)


def _apply_outcome_to_state(outcome, characters_by_id):
    _sync_resolve_effect_runtime_deps()
    return _resolve_effect_runtime_mod._apply_outcome_to_state(outcome, characters_by_id)


def _snapshot_characters_for_timing(state):
    _sync_resolve_effect_runtime_deps()
    return _resolve_effect_runtime_mod._snapshot_characters_for_timing(state)


def _diff_timing_snapshots(before_map, after_map, damage_source='timing_effect'):
    _sync_resolve_effect_runtime_deps()
    return _resolve_effect_runtime_mod._diff_timing_snapshots(before_map, after_map, damage_source=damage_source)


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
    _sync_resolve_effect_runtime_deps()
    return _resolve_effect_runtime_mod._run_skill_timing_effects(
        room,
        state,
        actor_char,
        target_char,
        skill_data,
        timing,
        target_skill_data=target_skill_data,
        base_damage=base_damage,
    )


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
    _sync_resolve_effect_runtime_deps()
    return _resolve_effect_runtime_mod._trigger_skill_timing_effects(
        room,
        state,
        characters_by_id,
        timing,
        actor_char,
        target_char,
        skill_data,
        target_skill_data=target_skill_data,
        base_damage=base_damage,
        emit_source=emit_source,
    )


def _apply_phase_timing_for_committed_intents(
    room,
    state,
    battle_state,
    characters_by_id,
    timing,
    intents_override=None
):
    _sync_resolve_effect_runtime_deps()
    return _resolve_effect_runtime_mod._apply_phase_timing_for_committed_intents(
        room,
        state,
        battle_state,
        characters_by_id,
        timing,
        intents_override=intents_override,
    )


def _apply_step_end_timing_from_trace(room, battle_state, trace_entry):
    _sync_resolve_effect_runtime_deps()
    return _resolve_effect_runtime_mod._apply_step_end_timing_from_trace(room, battle_state, trace_entry)


def _emit_char_stat_update(room, char_obj, stat_name, old_value, new_value, source='select_resolve'):
    _sync_resolve_effect_runtime_deps()
    return _resolve_effect_runtime_mod._emit_char_stat_update(
        room,
        char_obj,
        stat_name,
        old_value,
        new_value,
        source=source,
    )


def _emit_stat_updates_from_applied(room, applied, characters_by_id, source='select_resolve_delegate'):
    _sync_resolve_effect_runtime_deps()
    return _resolve_effect_runtime_mod._emit_stat_updates_from_applied(
        room,
        applied,
        characters_by_id,
        source=source,
    )
def to_legacy_duel_log_input(outcome_payload, state, intents, attacker_slot, defender_slot, applied=None, kind='one_sided', outcome='no_effect', notes=None):
    _sync_resolve_legacy_log_adapter_deps()
    return _resolve_legacy_log_adapter_mod.to_legacy_duel_log_input(
        outcome_payload,
        state,
        intents,
        attacker_slot,
        defender_slot,
        applied=applied,
        kind=kind,
        outcome=outcome,
        notes=notes,
    )
def _snapshot_for_outcome(actor):
    _sync_resolve_effect_runtime_deps()
    return _resolve_effect_runtime_mod._snapshot_for_outcome(actor)


def _diff_snapshot(before, after, damage_source='ダメージ'):
    _sync_resolve_effect_runtime_deps()
    return _resolve_effect_runtime_mod._diff_snapshot(before, after, damage_source=damage_source)


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
    _sync_resolve_effect_runtime_deps()
    return _resolve_effect_runtime_mod._apply_effect_changes_like_duel(
        room,
        state,
        changes,
        attacker_char,
        defender_char,
        base_damage,
        log_snippets,
        reuse_requests=reuse_requests,
    )
def _resolve_one_sided_by_existing_logic(room, state, attacker_char, defender_char, attacker_skill_data, defender_skill_data):
    _sync_resolve_match_runtime_deps()
    return _resolve_match_runtime_mod._resolve_one_sided_by_existing_logic(
        room,
        state,
        attacker_char,
        defender_char,
        attacker_skill_data,
        defender_skill_data,
    )


def _resolve_clash_by_existing_logic(
    room,
    state,
    attacker_char,
    defender_char,
    attacker_skill_data,
    defender_skill_data
):
    _sync_resolve_match_runtime_deps()
    return _resolve_match_runtime_mod._resolve_clash_by_existing_logic(
        room,
        state,
        attacker_char,
        defender_char,
        attacker_skill_data,
        defender_skill_data,
    )


def _resolve_hard_attack_followup(
    room,
    state,
    attacker_char,
    defender_char,
    attacker_skill_data,
    defender_skill_data=None,
):
    _sync_resolve_match_runtime_deps()
    return _resolve_match_runtime_mod._resolve_hard_attack_followup(
        room,
        state,
        attacker_char,
        defender_char,
        attacker_skill_data,
        defender_skill_data=defender_skill_data,
    )


def _roll_power_for_slot(battle_state, slot_id, intents_override=None):
    _sync_resolve_match_runtime_deps()
    return _resolve_match_runtime_mod._roll_power_for_slot(
        battle_state,
        slot_id,
        intents_override=intents_override,
    )
def run_select_resolve_auto(room, battle_id):
    return _resolve_auto_runtime_mod.run_select_resolve_auto(room, battle_id)
