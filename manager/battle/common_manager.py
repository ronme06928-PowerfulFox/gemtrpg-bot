import copy
import json
import time
import uuid
import threading
from flask_socketio import emit
from extensions import socketio, all_skill_data
from plugins.buffs.registry import buff_registry
import manager.room_manager as room_manager
from manager.constants import DamageSource
from manager.battle.core import proceed_next_turn
from manager.battle.battle_ai import ai_select_targets, ai_suggest_skill, list_usable_skill_ids
from manager.dice_roller import roll_dice
from manager.logs import setup_logger
from manager.summons.service import apply_summon_change, process_summon_round_end
from manager.granted_skills.service import process_granted_skill_round_end, apply_grant_skill_change

logger = setup_logger(__name__)


_ROUND_TRANSITION_LOCKS = {}
_ROUND_TRANSITION_LOCKS_GUARD = threading.Lock()


def _get_round_transition_lock(room):
    room_key = str(room or "").strip() or "__default__"
    with _ROUND_TRANSITION_LOCKS_GUARD:
        lock = _ROUND_TRANSITION_LOCKS.get(room_key)
        if lock is None:
            lock = threading.RLock()
            _ROUND_TRANSITION_LOCKS[room_key] = lock
        return lock


def _safe_emit(event_name, payload, **kwargs):
    emit_fn = getattr(socketio, "emit", None)
    if callable(emit_fn):
        try:
            emit_fn(event_name, payload, **kwargs)
        except Exception:
            return


get_room_state = getattr(room_manager, "get_room_state", lambda *_args, **_kwargs: None)
save_specific_room_state = getattr(room_manager, "save_specific_room_state", lambda *_args, **_kwargs: None)
broadcast_log = getattr(room_manager, "broadcast_log", lambda *_args, **_kwargs: None)
broadcast_state_update = getattr(room_manager, "broadcast_state_update", lambda *_args, **_kwargs: None)
emit_select_resolve_events = getattr(room_manager, "emit_select_resolve_events", lambda *_args, **_kwargs: None)
_update_char_stat = getattr(room_manager, "_update_char_stat", lambda *_args, **_kwargs: None)
is_authorized_for_character = getattr(room_manager, "is_authorized_for_character", lambda *_args, **_kwargs: True)
get_users_in_room = getattr(room_manager, "get_users_in_room", lambda *_args, **_kwargs: {})


def _is_select_resolve_active(state):
    if not isinstance(state, dict):
        return False
    battle_state = state.get('battle_state') or {}
    if not isinstance(battle_state, dict):
        return False
    phase = battle_state.get('phase')
    if phase not in ['select', 'resolve_mass', 'resolve_single']:
        return False
    slots = battle_state.get('slots', {})
    return isinstance(slots, dict) and len(slots) > 0


from manager.game_logic import (
    get_status_value, process_skill_effects, apply_buff, remove_buff, process_battle_start
)
from manager.field_effects import get_stage_speed_roll_mod
from manager.bleed_logic import resolve_bleed_tick, get_bleed_maintenance_count_from_buff
import manager.utils as _utils_mod
from manager.battle.enemy_behavior import (
    normalize_behavior_profile,
    initialize_behavior_runtime_entry,
    evaluate_transitions,
    pick_step_actions,
    advance_step_pointer,
    choose_action_plans_for_slot_count,
    BEHAVIOR_TARGET_POLICY_DEFAULT,
)
import random

BEHAVIOR_RANDOM_USABLE_SKILL_TOKEN = "__RANDOM_USABLE__"
BEHAVIOR_RANDOM_USABLE_SKILL_ALIASES = {
    "__random_usable__",
    "random_usable",
    "__random_skill__",
    "random_skill",
    "__random__",
    "random",
}

get_effective_origin_id = getattr(_utils_mod, 'get_effective_origin_id', lambda *_args, **_kwargs: 0)
apply_origin_bonus_buffs = getattr(_utils_mod, 'apply_origin_bonus_buffs', lambda *_args, **_kwargs: None)
clear_newly_applied_flags = getattr(_utils_mod, 'clear_newly_applied_flags', lambda *_args, **_kwargs: 0)
clear_round_limited_flags = getattr(_utils_mod, 'clear_round_limited_flags', lambda *_args, **_kwargs: 0)
get_round_end_origin_recoveries = getattr(_utils_mod, 'get_round_end_origin_recoveries', lambda *_args, **_kwargs: {})

import manager.battle.pve_intent_planner as _pve_planner_mod
from manager.battle.pve_intent_planner import (
    _canonical_team,
    _is_pve_actionable_character,
    _is_summon_action_locked,
    _remove_summoned_characters,
    _extract_skill_rule_data,
    _extract_skill_tags,
    _coerce_mass_type,
    _infer_mass_type_from_text,
    _infer_mass_type_from_skill,
    _normalize_target_scope,
    _infer_target_scope_from_skill,
    _default_intent_tags,
    _build_pve_intent_tags,
    _resolve_skill_display_name,
    _is_random_usable_skill_token,
    _resolve_behavior_chart_skill_id,
    _format_slot_actor_label,
    _broadcast_pve_round_start_preview_log as _broadcast_pve_round_start_preview_log_impl,
    _group_enemy_slots_by_actor,
    _read_behavior_profile_from_actor,
    _apply_pve_auto_enemy_intents as _apply_pve_auto_enemy_intents_impl,
)
import manager.battle.select_resolve_state as _select_resolve_state_mod
from manager.battle.select_resolve_state import (
    _build_select_resolve_slots_from_timeline as _build_select_resolve_slots_from_timeline_impl,
    _build_select_resolve_timeline_from_room as _build_select_resolve_timeline_from_room_impl,
    ensure_battle_state_vNext as _ensure_battle_state_vnext_impl,
    get_or_create_select_resolve_state as _get_or_create_select_resolve_state_impl,
    build_select_resolve_state_payload as _build_select_resolve_state_payload_impl,
    process_select_resolve_round_start as _process_select_resolve_round_start_impl,
)
import manager.battle.evade_slot_selector as _evade_slot_selector_mod
from manager.battle.evade_slot_selector import (
    _get_character_by_id as _get_character_by_id_impl,
    is_dodge_lock_active as _is_dodge_lock_active_impl,
    get_dodge_lock_skill_id as _get_dodge_lock_skill_id_impl,
    _is_evade_skill as _is_evade_skill_impl,
    _choose_highest_initiative_slot as _choose_highest_initiative_slot_impl,
    select_evade_insert_slot as _select_evade_insert_slot_impl,
    select_hard_followup_evade_slot as _select_hard_followup_evade_slot_impl,
)


def _sync_pve_planner_refs():
    _pve_planner_mod.all_skill_data = all_skill_data
    _pve_planner_mod.list_usable_skill_ids = list_usable_skill_ids
    _pve_planner_mod.ai_suggest_skill = ai_suggest_skill
    _pve_planner_mod.broadcast_log = broadcast_log


def _broadcast_pve_round_start_preview_log(state, room, preview_rows, round_value=None):
    _sync_pve_planner_refs()
    return _broadcast_pve_round_start_preview_log_impl(state, room, preview_rows, round_value=round_value)


def _apply_pve_auto_enemy_intents(state, battle_state, room):
    _sync_pve_planner_refs()
    return _apply_pve_auto_enemy_intents_impl(state, battle_state, room)


def _sync_select_resolve_state_refs():
    _select_resolve_state_mod.get_room_state = get_room_state
    _select_resolve_state_mod.save_specific_room_state = save_specific_room_state
    _select_resolve_state_mod.broadcast_log = broadcast_log
    _select_resolve_state_mod.clear_newly_applied_flags = clear_newly_applied_flags
    _select_resolve_state_mod.clear_round_limited_flags = clear_round_limited_flags
    _select_resolve_state_mod.get_status_value = get_status_value
    _select_resolve_state_mod.roll_dice = roll_dice
    _select_resolve_state_mod._apply_pve_auto_enemy_intents = _apply_pve_auto_enemy_intents
    _select_resolve_state_mod._broadcast_pve_round_start_preview_log = _broadcast_pve_round_start_preview_log


def _build_select_resolve_slots_from_timeline(room_state):
    _sync_select_resolve_state_refs()
    return _build_select_resolve_slots_from_timeline_impl(room_state)


def _build_select_resolve_timeline_from_room(room_state, slots):
    _sync_select_resolve_state_refs()
    return _build_select_resolve_timeline_from_room_impl(room_state, slots)


def ensure_battle_state_vNext(room_state, battle_id=None, round_value=None, rebuild_slots=False):
    _sync_select_resolve_state_refs()
    return _ensure_battle_state_vnext_impl(
        room_state,
        battle_id=battle_id,
        round_value=round_value,
        rebuild_slots=rebuild_slots,
    )


def get_or_create_select_resolve_state(room, battle_id=None, round_value=None, rebuild_slots=False):
    _sync_select_resolve_state_refs()
    return _get_or_create_select_resolve_state_impl(
        room,
        battle_id=battle_id,
        round_value=round_value,
        rebuild_slots=rebuild_slots,
    )


def build_select_resolve_state_payload(room, battle_id=None):
    _sync_select_resolve_state_refs()
    return _build_select_resolve_state_payload_impl(room, battle_id=battle_id)


def process_select_resolve_round_start(room, battle_id, round_value):
    _sync_select_resolve_state_refs()
    return _process_select_resolve_round_start_impl(room, battle_id, round_value)


def _sync_evade_selector_refs():
    _evade_slot_selector_mod.all_skill_data = all_skill_data


def _get_character_by_id(state, actor_id):
    _sync_evade_selector_refs()
    return _get_character_by_id_impl(state, actor_id)


def is_dodge_lock_active(state, actor_id):
    _sync_evade_selector_refs()
    return _is_dodge_lock_active_impl(state, actor_id)


def get_dodge_lock_skill_id(state, actor_id):
    _sync_evade_selector_refs()
    return _get_dodge_lock_skill_id_impl(state, actor_id)


def _is_evade_skill(skill_id):
    _sync_evade_selector_refs()
    return _is_evade_skill_impl(skill_id)


def _choose_highest_initiative_slot(slot_ids, slots):
    _sync_evade_selector_refs()
    return _choose_highest_initiative_slot_impl(slot_ids, slots)


def select_evade_insert_slot(state, battle_state, defender_actor_id, attacker_slot):
    _sync_evade_selector_refs()
    _evade_slot_selector_mod.is_dodge_lock_active = is_dodge_lock_active
    _evade_slot_selector_mod.get_dodge_lock_skill_id = get_dodge_lock_skill_id
    return _select_evade_insert_slot_impl(state, battle_state, defender_actor_id, attacker_slot)


def select_hard_followup_evade_slot(state, battle_state, defender_actor_id, attacker_slot):
    _sync_evade_selector_refs()
    _evade_slot_selector_mod.is_dodge_lock_active = is_dodge_lock_active
    return _select_hard_followup_evade_slot_impl(state, battle_state, defender_actor_id, attacker_slot)











































def process_full_round_end(room, username):
    lock = _get_round_transition_lock(room)
    with lock:
        return _process_full_round_end_impl(room, username)


def _process_full_round_end_impl(room, username):
    state = get_room_state(room)
    if not state:
        return False

    if state.get('is_round_ended', False):
        emit('new_log', {"message": "Round end has already been processed.", "type": "error"})
        return False

    broadcast_log(room, f"--- {username} が Round {state.get('round', 0)} の終了処理を実行しました ---", 'info')
    characters_to_process = state.get('characters', [])


    from plugins.buffs.confusion import ConfusionBuff
    current_round = int(state.get('round', 0) or 0)
    not_acted_chars = []
    for c in characters_to_process:
        is_dead = c.get('hp', 0) <= 0
        is_escaped = c.get('is_escaped', False)
        is_incapacitated = ConfusionBuff.is_incapacitated(c)
        is_action_locked_summon = _is_summon_action_locked(c, current_round)
        should_act = (
            not is_dead
            and not is_escaped
            and not is_incapacitated
            and not is_action_locked_summon
        )

        if should_act and not c.get('hasActed', False):
            not_acted_chars.append(c.get('name', 'Unknown'))

    if not_acted_chars:
        msg = f"まだ行動していないキャラクターがいます: {', '.join(not_acted_chars)}"
        emit('new_log', {"message": msg, "type": "error"})
        return False


    for char in characters_to_process:
        used_skill_ids = char.get('used_skills_this_round', [])
        all_changes = []

        for skill_id in set(used_skill_ids):
            skill_data = all_skill_data.get(skill_id)
            if not skill_data: continue

            try:
                rule_json_str = (
                    skill_data.get("rule_data_json")
                    or skill_data.get("special_rule")
                    or skill_data.get("特記処理")
                    or "{}"
                )
                rule_data = rule_json_str if isinstance(rule_json_str, dict) else json.loads(str(rule_json_str))
                effects_array = rule_data.get("effects", [])
                if effects_array:
                    _, logs, changes = process_skill_effects(effects_array, "END_ROUND", char, char, None, context={'timeline': state.get('timeline', []), 'characters': state['characters'], 'room': room})
                    all_changes.extend(changes)
            except Exception:
                pass

        for (c, type, name, value) in all_changes:
            if type == "APPLY_STATE":
                current_val = get_status_value(c, name)
                _update_char_stat(room, c, name, current_val + value, username=f"[{state.get('round')}R終了時]")
            elif type == "APPLY_BUFF":
                apply_buff(c, name, value["lasting"], value["delay"], data=value.get("data"), count=value.get("count"))
                broadcast_log(room, f"[{name}] applied to {c['name']}", "state-change")
            elif type == "GRANT_SKILL":
                grant_payload = dict(value) if isinstance(value, dict) else {}
                if "skill_id" not in grant_payload:
                    grant_payload["skill_id"] = name
                res = apply_grant_skill_change(room, state, char, c, grant_payload)
                if res.get("ok"):
                    broadcast_log(room, res.get("message", "Grant skill applied"), "state-change")
                else:
                    logger.warning("[end_round grant_skill failed] %s", res.get("message"))
            elif type == "SUMMON_CHARACTER":
                res = apply_summon_change(room, state, c, value)
                if res.get("ok"):
                    broadcast_log(room, res.get("message", "Summon applied"), "state-change")
                else:
                    logger.warning("[end_round summon failed] %s", res.get("message"))


        bleed_tick = resolve_bleed_tick(char, consume_maintenance=True)
        if bleed_tick.get("damage", 0) > 0:
            _update_char_stat(
                room,
                char,
                'HP',
                char['hp'] - int(bleed_tick["damage"]),
                username="[出血]",
                source=DamageSource.BLEED
            )

            if int(bleed_tick.get("bleed_after", 0)) != int(bleed_tick.get("bleed_before", 0)):
                _update_char_stat(room, char, '出血', int(bleed_tick["bleed_after"]), username="[出血]")

            if int(bleed_tick.get("maintenance_consumed", 0)) > 0:
                remaining = int(bleed_tick.get("maintenance_remaining", 0))
                broadcast_log(room, f"[出血遷延] {char.get('name', '')} consumed 1 stack (remaining {remaining})", "state-change")


        thorns_value = get_status_value(char, "荊棘")
        if thorns_value > 0:
            _update_char_stat(room, char, "荊棘", thorns_value - 1, username="[荊棘減少]")


        if "special_buffs" in char:
            active_buffs = []
            buffs_to_remove = []

            for buff in char['special_buffs']:
                buff_name = buff.get("name")
                delay = buff.get("delay", 0)
                lasting = buff.get("lasting", 0)


                if buff.get("buff_id") == "Bu-08":
                    if delay > 0:
                        buff["delay"] = delay - 1
                        if buff["delay"] == 0:
                            broadcast_log(room, f"[{buff_name}] is now active on {char['name']}.", "state-change")
                        if buff["delay"] >= 0:
                            active_buffs.append(buff)
                        continue

                    buff["is_permanent"] = True
                    buff["lasting"] = -1
                    if get_bleed_maintenance_count_from_buff(buff) > 0:
                        active_buffs.append(buff)
                    else:
                        buffs_to_remove.append(buff_name)
                    continue

                if delay > 0:
                    buff["delay"] = delay - 1
                    if buff["delay"] == 0:
                        broadcast_log(room, f"[{buff_name}] is now active on {char['name']}.", "state-change")


                        BuffClass = buff_registry.get_handler(buff.get('buff_id'))
                        if BuffClass:
                            plugin = BuffClass(buff)
                            if hasattr(plugin, 'on_delay_zero'):
                                res = plugin.on_delay_zero(char, {'room': room})
                                for log in res.get('logs', []):
                                    broadcast_log(room, log.get('message', ''), log.get('type', 'info'))
                                for change in res.get('changes', []):
                                    if len(change) >= 4:
                                        c_target, c_type, c_name, c_val = change
                                        if c_type == "CUSTOM_DAMAGE":
                                            curr = c_target.get('hp', 0)
                                            _update_char_stat(room, c_target, 'HP', curr - c_val, username=f"[{c_name}]")

                        if lasting > 0: active_buffs.append(buff)
                        else:
                            if buff.get("buff_id") == "Bu-Fissure":
                                remove_count = int(buff.get("count", 0) or 0)
                                if remove_count > 0:
                                    current_fissure = int(get_status_value(char, "亀裂") or 0)
                                    _update_char_stat(
                                        room,
                                        char,
                                        "亀裂",
                                        max(0, current_fissure - remove_count),
                                        username="[亀裂期限切れ]"
                                    )
                            buffs_to_remove.append(buff_name)
                    else:
                        active_buffs.append(buff)
                elif lasting > 0:
                    buff["lasting"] = lasting - 1
                    if buff["lasting"] > 0:
                        if buff.get("buff_id") == "Bu-Fissure":
                            buff["name"] = f"亀裂_R{buff['lasting']}"
                        active_buffs.append(buff)
                    else:
                        if buff.get("buff_id") == "Bu-Fissure":
                            remove_count = int(buff.get("count", 0) or 0)
                            if remove_count > 0:
                                current_fissure = int(get_status_value(char, "亀裂") or 0)
                                _update_char_stat(
                                    room,
                                    char,
                                    "亀裂",
                                    max(0, current_fissure - remove_count),
                                    username="[亀裂期限切れ]"
                                )
                        broadcast_log(room, f"[{buff_name}]が[{char['name']}]から消失した。", "state-change")
                        buffs_to_remove.append(buff_name)
                        if buff_name in ("混乱", "混乱(戦慄殺到)"):
                            _update_char_stat(room, char, 'MP', int(char.get('maxMp', 0)), username="[混乱解除]")
                            broadcast_log(room, f"{char['name']} は意識を取り戻した (MP全回復)", 'state-change')
                elif buff.get('is_permanent', False):
                    active_buffs.append(buff)

            char['special_buffs'] = active_buffs
            apply_origin_bonus_buffs(char)


        if 'round_item_usage' in char: char['round_item_usage'] = {}
        if 'used_immediate_skills_this_round' in char: char['used_immediate_skills_this_round'] = []
        if 'used_skills_this_round' in char: char['used_skills_this_round'] = []

    removed_summons = process_summon_round_end(state, room=room)
    for summoned in removed_summons:
        broadcast_log(room, f"{summoned.get('name', 'summon')} expired and was removed.", "state-change")
    expired_granted = process_granted_skill_round_end(state, room=room)
    for row in expired_granted:
        char_name = row.get("char_name") or "キャラクター"
        skill_id = row.get("skill_id") or "UNKNOWN"
        broadcast_log(room, f"{char_name} lost granted skill {skill_id}.", "state-change")

    round_end_origin_targets = {}
    for char in state.get('characters', []):
        if char.get('hp', 0) <= 0: continue
        recoveries = get_round_end_origin_recoveries(char)
        for status_name, amount in recoveries.items():
            if int(amount or 0) <= 0:
                continue
            new_value = int(get_status_value(char, status_name)) + int(amount)
            _update_char_stat(room, char, status_name, new_value, username=f"[ラウンド終了ボーナス:{status_name}]")
            round_end_origin_targets.setdefault(status_name, []).append(char['name'])

    if round_end_origin_targets.get('HP'):
        broadcast_log(room, f"[Round End Bonus] HP recovered: {', '.join(round_end_origin_targets['HP'])}", "info")
    if round_end_origin_targets.get('MP'):
        broadcast_log(room, f"[Round End Bonus] MP recovered: {', '.join(round_end_origin_targets['MP'])}", "info")

    state['is_round_ended'] = True
    state['turn_char_id'] = None
    state['active_match'] = None

    battle_state = ensure_battle_state_vNext(
        state,
        battle_id=f"battle_{room}",
        round_value=state.get('round', 0),
        rebuild_slots=True
    )
    if battle_state:
        battle_state['phase'] = 'round_end'
        battle_state['intents'] = {}
        battle_state['resolve_snapshot_intents'] = {}
        battle_state['resolve_snapshot_at'] = None
        battle_state['redirects'] = []
        battle_state['resolve_ready'] = False
        battle_state['resolve_ready_info'] = {}
        battle_state['resolve']['mass_queue'] = []
        battle_state['resolve']['single_queue'] = []
        battle_state['resolve']['resolved_slots'] = []
        battle_state['resolve']['trace'] = []

    broadcast_state_update(room)
    save_specific_room_state(room)
    return True

def reset_battle_logic(room, mode, username, reset_options=None):
    state = get_room_state(room)
    if not state: return

    if mode == 'logs':
        state['logs'] = []
        broadcast_state_update(room)
        save_specific_room_state(room)
        return


    if reset_options is None:
        reset_options = {
            'hp': True,
            'mp': True,
            'fp': True,
            'states': True,
            'bad_states': True,
            'buffs': True,
            'timeline': True
        }

    log_msg = f"\n--- {username} が戦闘をリセットしました (Mode: {mode}) ---\n"

    broadcast_log(room, log_msg, 'round')


    state['ai_target_arrows'] = []

    if mode == 'full':
        state['characters'] = []
        state['timeline'] = []
        state['round'] = 0
        state['is_round_ended'] = False
        state['turn_char_id'] = None
        state['turn_entry_id'] = None
    elif mode == 'status':

        state['round'] = 0
        state['is_round_ended'] = False
        state['ai_target_arrows'] = []


        state['timeline'] = []

        removed_summon_count = _remove_summoned_characters(state)
        if removed_summon_count > 0:
            broadcast_log(room, f"[Reset] Removed {removed_summon_count} summoned characters.", "info")

        for char in state.get('characters', []):
            initial = char.get('initial_state', {})



            is_unplaced = char.get('x', -1) < 0
            is_dead = char.get('hp', 0) <= 0

            if is_unplaced and not is_dead:

                continue


            if reset_options.get('hp'):
                max_hp = int(initial.get('maxHp', char.get('maxHp', 0)))

                char['maxHp'] = max_hp
                char['hp'] = max_hp


            if reset_options.get('mp'):
                max_mp = int(initial.get('maxMp', char.get('maxMp', 0)))
                char['maxMp'] = max_mp
                char['mp'] = max_mp


            if reset_options.get('fp') or reset_options.get('states'):






                new_states = []

                default_states = {
                    "FP": 0,
                    "出血": 0,
                    "亀裂": 0,
                    "破裂": 0,
                    "戦慄": 0,
                    "荊棘": 0,
                }


                current_states = {s['name']: s['value'] for s in char.get('states', [])}

                for s_name, def_val in default_states.items():

                    if s_name == 'FP':
                        if reset_options.get('fp'):





                            char['FP'] = char.get('maxFp', 0)
                            new_states.append({"name": "FP", "value": 0})
                        else:

                            val = current_states.get(s_name, def_val)
                            new_states.append({"name": s_name, "value": val})


                    else:
                        if reset_options.get('states'):
                            new_states.append({"name": s_name, "value": 0})
                        else:
                            val = current_states.get(s_name, def_val)
                            new_states.append({"name": s_name, "value": val})

                char['states'] = new_states


            if reset_options.get('bad_states'):
                char['状態異常'] = []


            if reset_options.get('buffs'):


                raw_initial_buffs = initial.get('special_buffs', [])
                char['special_buffs'] = [dict(b) for b in raw_initial_buffs]



            if 'round_item_usage' in char: char['round_item_usage'] = {}
            if 'used_immediate_skills_this_round' in char: char['used_immediate_skills_this_round'] = []
            if 'used_gem_protect_this_battle' in char: char['used_gem_protect_this_battle'] = False
            if 'used_skills_this_round' in char: char['used_skills_this_round'] = []

            char['hasActed'] = False
            char['speedRoll'] = 0
            char['isWideUser'] = False






            if reset_options.get('hp') or reset_options.get('mp') or reset_options.get('fp'):
                 try:
                     process_battle_start(room, char)
                 except Exception as e:
                     logger.error(f"process_battle_start in reset failed: {e}")


            if reset_options.get('buffs'):
                apply_origin_bonus_buffs(char)

        state['turn_char_id'] = None
        state['turn_entry_id'] = None



    should_clear_select_resolve = (mode == 'full') or (mode == 'status')
    if should_clear_select_resolve:
        battle_state = ensure_battle_state_vNext(
            state,
            battle_id=f"battle_{room}",
            round_value=state.get('round', 0),
            rebuild_slots=False
        )
        if battle_state:
            battle_state['phase'] = 'round_end'
            battle_state['slots'] = {}
            battle_state['timeline'] = []
            battle_state['tiebreak'] = []
            battle_state['intents'] = {}
            battle_state['redirects'] = []
            battle_state['resolve_ready'] = False
            battle_state['resolve_ready_info'] = {}
            battle_state['resolve']['mass_queue'] = []
            battle_state['resolve']['single_queue'] = []
            battle_state['resolve']['resolved_slots'] = []
            battle_state['resolve']['trace'] = []
            logger.info("[reset] cleared select_resolve snapshot room=%s mode=%s", room, mode)

    state['active_match'] = None
    broadcast_state_update(room)
    if should_clear_select_resolve:
        emit_select_resolve_events(room, include_round_started=False)
    save_specific_room_state(room)

def force_end_match_logic(room, username):
    state = get_room_state(room)
    if not state: return

    if not state.get('active_match') and not state.get('pending_wide_ids'):
        emit('new_log', {"message": "There is no active match to force-end.", "type": "error"})
        return


    state['active_match'] = None
    state['pending_wide_ids'] = []

    save_specific_room_state(room)
    broadcast_state_update(room)


    _safe_emit('match_modal_closed', {}, to=room)
    _safe_emit('force_close_wide_modal', {}, to=room)

    broadcast_log(room, f"[Force End] GM {username} force-ended the current match.", "match-end")

def move_token_logic(room, char_id, x, y, username, attribute):
    state = get_room_state(room)
    if not state: return

    target_char = next((c for c in state["characters"] if c.get('id') == char_id), None)
    if not target_char: return

    play_mode = str(state.get('play_mode') or 'normal').strip().lower()
    is_battle_only = (play_mode == 'battle_only')
    if not is_battle_only and not is_authorized_for_character(room, char_id, username, attribute):
        emit('move_denied', {'message': '権限がありません。'})
        return

    target_char["x"] = float(x)
    target_char["y"] = float(y)

    save_specific_room_state(room)
    broadcast_state_update(room)

def open_match_modal_logic(room, data, username):
    state = get_room_state(room)
    if not state: return

    match_type = data.get('match_type')
    attacker_id = data.get('attacker_id')
    defender_id = data.get('defender_id')
    targets = data.get('targets', [])


    if match_type == 'duel':
        attacker_char = next((c for c in state["characters"] if c.get('id') == attacker_id), None)
        if attacker_char:
            attacker_type = attacker_char.get('type', 'ally')
            provoking_enemies = []
            for c in state["characters"]:
                if c.get('type') != attacker_type and c.get('hp', 0) > 0:
                    for buff in c.get('special_buffs', []):
                         if (buff.get('name') in ['挑発中', '挑発'] or buff.get('buff_id') in ['Bu-Provoke', 'Bu-01']) and buff.get('delay', 0) == 0:
                             provoking_enemies.append(c['id'])
                             break

            if provoking_enemies and defender_id not in provoking_enemies:
                emit('match_error', {'error': '挑発中の敵がいるため、他のキャラクターを攻撃できません。'}, to=request.sid)
                return


    current_match = state.get('active_match')
    is_resume = False

    if current_match and\
       current_match.get('attacker_id') == attacker_id and\
       current_match.get('defender_id') == defender_id and\
       current_match.get('match_type') == match_type:
           state['active_match']['is_active'] = True
           state['active_match']['opened_by'] = username
           is_resume = True
    else:

        defender_char = next((c for c in state["characters"] if c.get('id') == defender_id), None)
        is_one_sided = False
        if defender_char:
            from plugins.buffs.dodge_lock import DodgeLockBuff
            if defender_char.get('hasActed', False) and not DodgeLockBuff.has_re_evasion(defender_char):
                is_one_sided = True

        attacker_char = next((c for c in state["characters"] if c.get('id') == attacker_id), None)

        state['active_match'] = {
            'is_active': True,
            'match_type': match_type,
            'attacker_id': attacker_id,
            'defender_id': defender_id,
            'targets': targets,
            'attacker_data': {},
            'defender_data': {},
            'opened_by': username,
            'attacker_declared': False,
            'defender_declared': False,
            'is_one_sided_attack': is_one_sided,
            'attacker_snapshot': copy.deepcopy(attacker_char),
            'defender_snapshot': copy.deepcopy(defender_char),
            'match_id': str(uuid.uuid4())
        }

    save_specific_room_state(room)
    _safe_emit('match_modal_opened', {
        'match_type': match_type,
        'attacker_id': attacker_id,
        'defender_id': defender_id,
        'targets': targets,
        'is_resume': is_resume
    }, to=room)
    broadcast_state_update(room)

def close_match_modal_logic(room):
    state = get_room_state(room)
    if not state: return

    if 'active_match' in state:
        state['active_match']['is_active'] = False

    save_specific_room_state(room)
    _safe_emit('match_modal_closed', {}, to=room)
    broadcast_state_update(room)

def sync_match_data_logic(room, side, data, username, attribute):
    state = get_room_state(room)
    if not state: return
    active_match = state.get('active_match', {})

    if not active_match.get('is_active') or active_match.get('match_type') != 'duel':
        return


    target_char_id = None
    if side == 'attacker':
        target_char_id = active_match.get('attacker_id')
    elif side == 'defender':
        target_char_id = active_match.get('defender_id')


    allowed = False
    if attribute == 'GM':
        allowed = True
    elif target_char_id:
        owners = state.get('character_owners', {})
        if owners.get(target_char_id) == username:
            allowed = True

    if not allowed:

        logger.warning(f"Unauthorized sync attempt by {username} for side {side} (CharID: {target_char_id})")
        return

    if side == 'attacker':
        state['active_match']['attacker_data'] = data
    elif side == 'defender':
        state['active_match']['defender_data'] = data

    save_specific_room_state(room)
    _safe_emit('match_data_updated', {'side': side, 'data': data}, to=room)

def process_round_start(room, username):
    lock = _get_round_transition_lock(room)
    with lock:
        return _process_round_start_impl(room, username)


def _process_round_start_impl(room, username):
    logger.debug(f"process_round_start called for room: {room} by {username}")
    state = get_room_state(room)
    if not state:
        logger.debug(f"Room state not found for {room}")
        return False
    clear_newly_applied_flags(state)
    clear_round_limited_flags(state)


    if state.get('round', 0) > 0 and not state.get('is_round_ended', False):
        if str(username or '').strip() != '戦闘専用モード':
            emit('new_log', {'message': '前ラウンドの終了処理が未完了です。先にラウンド終了を実行してください。', 'type': 'error'}, room=room)
        return False


    state['round'] = state.get('round', 0) + 1
    state['is_round_ended'] = False

    broadcast_log(room, f"--- {username} が Round {state['round']} を開始しました ---", 'round')


    timeline_unsorted = []
    import uuid


    logger.info(f"[Timeline] Starting generation for Round {state.get('round')}. Total chars: {len(state.get('characters', []))}")

    for char in state.get('characters', []):

        char['isWideUser'] = False



        try:
            hp = int(char.get('hp', 0))
            x_val = float(char.get('x', -1))
            escaped = bool(char.get('is_escaped', False))
        except (ValueError, TypeError):
            logger.warning(f"[Timeline] Type mismatch for char {char.get('name', 'Unknown')}. Skipping.")
            continue

        if hp <= 0:
            logger.debug(f"[Timeline] Skip {char.get('name')} (HP<=0)")
            continue
        if escaped:
             logger.debug(f"[Timeline] Skip {char.get('name')} (Escaped)")
             continue
        if x_val < 0:
             logger.debug(f"[Timeline] Skip {char.get('name')} (Unplaced x={x_val})")
             continue
        can_act_from_round = int(char.get('can_act_from_round', 0) or 0)
        if bool(char.get('is_summoned', False)) and can_act_from_round > int(state.get('round', 0)):
            logger.debug(
                "[Timeline] Skip %s (summon lock: can_act_from=%s current=%s)",
                char.get('name'),
                can_act_from_round,
                state.get('round', 0),
            )
            continue



        char['totalSpeed'] = None

        speed_val = 0
        try:
            speed_val = int(get_status_value(char, "速度"))
        except Exception:
            speed_val = 0
        if speed_val <= 0:
            try:
                speed_val = int(get_status_value(char, '速度'))
            except Exception:
                speed_val = 0


        from plugins.buffs.speed_mod import SpeedModBuff
        speed_modifier = SpeedModBuff.get_speed_modifier(char)
        stage_speed_modifier = get_stage_speed_roll_mod(state, char)
        total_speed_modifier = speed_modifier + stage_speed_modifier

        initiative = (speed_val // 6) + total_speed_modifier

        if speed_modifier != 0:
            mod_text = f"+{speed_modifier}" if speed_modifier > 0 else str(speed_modifier)
            broadcast_log(room, f"{char['name']} の速度補正: {mod_text} (基礎速度に加算)", 'info')
        if stage_speed_modifier != 0:
            mod_text = f"+{stage_speed_modifier}" if stage_speed_modifier > 0 else str(stage_speed_modifier)
            broadcast_log(room, f"{char['name']} のステージ速度補正: {mod_text} (source=stage)", 'info')


        try:
             action_count = int(get_status_value(char, "行動回数"))
        except Exception:
             action_count = 0
        if action_count <= 0:
            try:
                action_count = int(get_status_value(char, '行動回数'))
            except Exception:
                action_count = 1
        action_count = max(1, action_count)

        logger.debug(f"[SPEED ROLL] {char['name']}: speed={speed_val} (init={initiative}), count={action_count}")

        for i in range(action_count):
            roll = random.randint(1, 6)
            total_speed = initiative + roll


            total_speed = max(1, total_speed)

            entry_id = str(uuid.uuid4())
            timeline_unsorted.append({
                'id': entry_id,
                'char_id': char['id'],
                'speed': total_speed,
                'stat_speed': initiative,
                'roll': roll,
                'acted': False,
                'is_extra': (i > 0)
            })


            if i == 0:
                char['speedRoll'] = roll
                char['totalSpeed'] = total_speed


        char['hasActed'] = False


    timeline_unsorted.sort(key=lambda x: x['speed'], reverse=True)


    state['timeline'] = timeline_unsorted
    logger.info(f"[Timeline] Generated {len(timeline_unsorted)} entries.")

    state['turn_char_id'] = None
    state['turn_entry_id'] = None


    log_msg = "行動順が決まりました:<br>"
    for idx, item in enumerate(timeline_unsorted):
        char = next((c for c in state['characters'] if c['id'] == item['char_id']), None)
        if char:
            roll = item.get('roll', 0)
            stat = item.get('stat_speed', 0)
            total = item.get('speed', 0)
            sign = "+" if stat >= 0 else ""


            breakdown = f"1d6({roll}){sign}{stat} = {total}"

            log_msg += f"{idx+1}. {char['name']} ({breakdown})<br>"

    broadcast_log(room, log_msg, 'info')



    latium_gain_targets = []
    latium_no_gain_targets = []
    for char in state.get('characters', []):
        if char.get('hp', 0) <= 0: continue
        if get_effective_origin_id(char) == 3:
            if random.random() < 0.5:
                current_fp = get_status_value(char, 'FP')
                _update_char_stat(room, char, 'FP', current_fp + 1, username="[ラティウム恩恵]")
                latium_gain_targets.append(char['name'])
            else:
                latium_no_gain_targets.append(char['name'])

    if latium_gain_targets:
        broadcast_log(room, f"[ラティウム恩恵] FP +1: {', '.join(latium_gain_targets)}", "info")
    if latium_no_gain_targets:
        broadcast_log(room, f"[ラティウム恩恵] 増加なし: {', '.join(latium_no_gain_targets)}", "info")









    state['wide_modal_confirms'] = []
    state['pending_wide_ids'] = []

    battle_state = ensure_battle_state_vNext(
        state,
        battle_id=f"battle_{room}",
        round_value=state.get('round', 0),
        rebuild_slots=True
    )
    if battle_state:
        battle_state['phase'] = 'select'
        battle_state['intents'] = {}
        battle_state['redirects'] = []
        battle_state['resolve_ready'] = False
        battle_state['resolve_ready_info'] = {}
        battle_state['resolve']['mass_queue'] = []
        battle_state['resolve']['single_queue'] = []
        battle_state['resolve']['resolved_slots'] = []
        battle_state['resolve']['trace'] = []
        pve_auto_result = _apply_pve_auto_enemy_intents(state, battle_state, room)
        _broadcast_pve_round_start_preview_log(
            state,
            room,
            pve_auto_result.get('preview_rows', []) if isinstance(pve_auto_result, dict) else [],
            round_value=battle_state.get('round')
        )


    broadcast_state_update(room)
    save_specific_room_state(room)

    if battle_state:
        emit_select_resolve_events(room, include_round_started=True)


    if _is_select_resolve_active(state):
        logger.info("[round_start] skip legacy wide modal room=%s reason=select_resolve_active", room)
    else:
        _safe_emit('open_wide_declaration_modal', {}, to=room)
    return True

def process_wide_declarations(room, wide_user_ids):
    state = get_room_state(room)
    if not state: return


    if _is_select_resolve_active(state):
        logger.info("[wide_declarations] ignored room=%s reason=select_resolve_active ids=%s", room, wide_user_ids)
        return


    for char in state.get('characters', []):
        char['isWideUser'] = False


    names = []
    logger.debug(f"[DEBUG] process_wide_declarations ids: {wide_user_ids}")
    for uid in wide_user_ids:
        char = next((c for c in state['characters'] if str(c['id']) == str(uid)), None)
        if char:
            char['isWideUser'] = True
            names.append(char['name'])
            logger.debug(f"[DEBUG] Set isWideUser=True for {char['name']} ({char['id']})")
        else:
            logger.debug(f"[DEBUG] Character not found for uid: {uid}")

    if names:
        broadcast_log(room, f"広域宣言を適用: {', '.join(names)}", 'info')

        current_timeline = state.get('timeline', [])


        valid_wide_char_ids = [str(uid) for uid in wide_user_ids if any(str(c['id']) == str(uid) for c in state['characters'])]

        wide_entries = [entry for entry in current_timeline if str(entry['char_id']) in valid_wide_char_ids]
        remaining_entries = [entry for entry in current_timeline if str(entry['char_id']) not in valid_wide_char_ids]


        state['timeline'] = wide_entries + remaining_entries
        logger.debug(f"[DEBUG] New timeline len: {len(state['timeline'])}")
    else:
        broadcast_log(room, "No pending wide match entries.", "info")

    save_specific_room_state(room)
    broadcast_state_update(room)







    if _is_select_resolve_active(state):
        logger.info("[wide_declarations] skip legacy proceed_next_turn room=%s reason=select_resolve_active", room)
        return


    ai_select_targets(state, room)
    proceed_next_turn(room)

def process_wide_modal_confirm(room, user_id, attribute, wide_ids):
    state = get_room_state(room)
    if not state: return


    if _is_select_resolve_active(state):
        logger.info(
            "[wide_modal_confirm] ignored room=%s user=%s reason=select_resolve_active ids=%s",
            room, user_id, wide_ids
        )
        return


    if 'wide_modal_confirms' not in state: state['wide_modal_confirms'] = []
    if 'pending_wide_ids' not in state: state['pending_wide_ids'] = []



    for wid in wide_ids:
        if wid not in state['pending_wide_ids']:
            state['pending_wide_ids'].append(wid)


    if attribute == 'GM':
        logger.info(f"[WideModal] GM {user_id} Forced Confirm. IDs: {wide_ids}")


        process_wide_declarations(room, state['pending_wide_ids'])


        _safe_emit('close_wide_declaration_modal', {}, to=room)

        broadcast_log(room, "GM requested wide declaration processing.", "info")
        return


    if user_id not in state['wide_modal_confirms']:
        state['wide_modal_confirms'].append(user_id)
        broadcast_log(room, f"{user_id} confirmed wide declaration.", "info")



    current_room_users = get_users_in_room(room)


    non_gm_users = set()
    for sid, u_info in current_room_users.items():
        if u_info.get('attribute') != 'GM':
            non_gm_users.add(u_info.get('username'))


    confirmed_users = set(state['wide_modal_confirms'])




    all_confirmed = False
    if len(non_gm_users) > 0:
        if non_gm_users.issubset(confirmed_users):
            all_confirmed = True

    if all_confirmed:
        logger.info("[WideModal] All players confirmed. Executing.")
        process_wide_declarations(room, state['pending_wide_ids'])
        _safe_emit('close_wide_declaration_modal', {}, to=room)
    else:

        logger.info(f"Player {user_id} confirmed. Waiting... ({len(confirmed_users)}/{len(non_gm_users)})")
        save_specific_room_state(room)



def update_battle_background_logic(room, image_url, scale, offset_x, offset_y, username, attribute):
    """
    戦闘画面の背景画像を更新するロジチけ
    """
    if attribute != 'GM':
        emit('new_log', {'message': '背景設定はGMのみ変更できます。', 'type': 'error'})
        return

    state = get_room_state(room)
    if not state: return


    if 'battle_map_data' not in state:
        state['battle_map_data'] = {}


    state['battle_map_data']['background_image'] = image_url
    if scale is not None:
        state['battle_map_data']['background_scale'] = scale
    if offset_x is not None:
        state['battle_map_data']['background_offset_x'] = offset_x
    if offset_y is not None:
        state['battle_map_data']['background_offset_y'] = offset_y

    broadcast_state_update(room)
    broadcast_log(room, "Battle map background updated.", "system")


def process_switch_battle_mode(room, mode, username):
    state = get_room_state(room)
    if not state: return

    old_mode = state.get('battle_mode', 'pvp')
    if old_mode == mode:
        return

    state['battle_mode'] = mode
    broadcast_log(room, f"戦闘モードを変更しました: {old_mode.upper()} -> {mode.upper()}", 'system')







    save_specific_room_state(room)
    broadcast_state_update(room)


def process_ai_suggest_skill(room, char_id):


    state = get_room_state(room)
    if not state: return None

    char = next((c for c in state['characters'] if c['id'] == char_id), None)
    if not char: return None

    return ai_suggest_skill(char)






























