import copy
import json
import time
import uuid
from flask_socketio import emit
from extensions import socketio, all_skill_data
from plugins.buffs.registry import buff_registry
import manager.room_manager as room_manager
from manager.constants import DamageSource
from manager.battle.core import proceed_next_turn
from manager.battle.battle_ai import ai_select_targets, ai_suggest_skill
from manager.dice_roller import roll_dice
from manager.logs import setup_logger
from manager.summons.service import apply_summon_change, process_summon_round_end
from manager.granted_skills.service import process_granted_skill_round_end, apply_grant_skill_change

logger = setup_logger(__name__)

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
import manager.utils as _utils_mod
from manager.battle.enemy_behavior import (
    normalize_behavior_profile,
    initialize_behavior_runtime_entry,
    evaluate_transitions,
    pick_step_actions,
    advance_step_pointer,
    choose_actions_for_slot_count,
)
import random

get_effective_origin_id = getattr(_utils_mod, 'get_effective_origin_id', lambda *_args, **_kwargs: 0)
apply_origin_bonus_buffs = getattr(_utils_mod, 'apply_origin_bonus_buffs', lambda *_args, **_kwargs: None)
clear_newly_applied_flags = getattr(_utils_mod, 'clear_newly_applied_flags', lambda *_args, **_kwargs: 0)


def _canonical_team(raw_value):
    text = str(raw_value or '').strip().lower()
    if text in ['ally', 'player', 'friend', 'friends']:
        return 'ally'
    if text in ['enemy', 'foe', 'opponent', 'boss', 'npc']:
        return 'enemy'
    return None


def _is_pve_actionable_character(char):
    if not isinstance(char, dict):
        return False
    if int(char.get('hp', 0) or 0) <= 0:
        return False
    if bool(char.get('is_escaped', False)):
        return False
    try:
        x_val = float(char.get('x', -1))
    except (TypeError, ValueError):
        return False
    return x_val >= 0


def _is_summon_action_locked(char, round_value):
    if not isinstance(char, dict):
        return False
    if not bool(char.get('is_summoned', False)):
        return False
    try:
        can_act_from_round = int(char.get('can_act_from_round', 0) or 0)
    except (TypeError, ValueError):
        can_act_from_round = 0
    try:
        current_round = int(round_value or 0)
    except (TypeError, ValueError):
        current_round = 0
    return can_act_from_round > current_round


def _remove_summoned_characters(state):
    if not isinstance(state, dict):
        return 0

    chars = state.get('characters', [])
    if not isinstance(chars, list):
        return 0

    kept = []
    removed_ids = []
    for char in chars:
        if isinstance(char, dict) and bool(char.get('is_summoned', False)):
            removed_ids.append(str(char.get('id', '') or ''))
            continue
        kept.append(char)

    if not removed_ids:
        return 0

    state['characters'] = kept
    owners = state.get('character_owners', {})
    if isinstance(owners, dict):
        for char_id in removed_ids:
            owners.pop(char_id, None)

    return len(removed_ids)


def _extract_skill_rule_data(skill_data):
    if not isinstance(skill_data, dict):
        return {}

    for key in ['rule_data', 'rule_json', 'rule', '特記処理']:
        raw = skill_data.get(key)
        if not raw:
            continue
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            text = raw.strip()
            if not text.startswith('{'):
                continue
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue
    return {}


def _extract_skill_tags(skill_id):
    if not skill_id:
        return []
    skill_data = all_skill_data.get(skill_id, {})
    if not isinstance(skill_data, dict):
        return []

    tags = []
    raw_tags = skill_data.get('tags', [])
    if isinstance(raw_tags, list):
        tags.extend(raw_tags)

    rule_data = _extract_skill_rule_data(skill_data)
    rule_tags = rule_data.get('tags', []) if isinstance(rule_data, dict) else []
    if isinstance(rule_tags, list):
        tags.extend(rule_tags)

    normalized = []
    for tag in tags:
        text = str(tag or '').strip().lower()
        if text:
            normalized.append(text)
    return normalized


def _coerce_mass_type(raw_value):
    text = str(raw_value or '').strip().lower()
    if not text:
        return None
    if text in ['mass_summation', 'summation', 'sum']:
        return 'mass_summation'
    if text in ['mass_individual', 'individual']:
        return 'mass_individual'
    return None


def _infer_mass_type_from_text(text):
    merged = str(text or '').lower()
    if not merged:
        return None
    if (
        'mass_summation' in merged
        or 'summation' in merged
        or 'sum' in merged
        or '広域-合算' in merged
        or '合算' in merged
    ):
        return 'mass_summation'
    if (
        'mass_individual' in merged
        or 'individual' in merged
        or '広域-個別' in merged
        or '個別' in merged
        or '広域' in merged
    ):
        return 'mass_individual'
    return None


def _infer_mass_type_from_skill(skill_id):
    if not skill_id:
        return None
    skill_data = all_skill_data.get(skill_id, {})
    if not isinstance(skill_data, dict):
        return None

    rule_data = _extract_skill_rule_data(skill_data)
    direct_candidates = [
        skill_data.get('mass_type'),
        skill_data.get('target_type'),
        skill_data.get('targeting'),
        skill_data.get('targetType'),
        rule_data.get('mass_type') if isinstance(rule_data, dict) else None,
        rule_data.get('target_type') if isinstance(rule_data, dict) else None,
        rule_data.get('targeting') if isinstance(rule_data, dict) else None,
        rule_data.get('targetType') if isinstance(rule_data, dict) else None,
    ]
    for raw in direct_candidates:
        coerced = _coerce_mass_type(raw)
        if coerced:
            return coerced

    merged_parts = _extract_skill_tags(skill_id)
    for key in [
        'category', 'distance', '分類', 'カテゴリ', '距離', '射程', '範囲',
        'target_scope', 'target', 'target_type', 'targeting', 'mass_type'
    ]:
        if isinstance(skill_data.get(key), str):
            merged_parts.append(skill_data.get(key))
        if isinstance(rule_data, dict) and isinstance(rule_data.get(key), str):
            merged_parts.append(rule_data.get(key))

    return _infer_mass_type_from_text(' '.join(str(v or '') for v in merged_parts))


def _default_intent_tags(existing=None):
    tags = dict(existing or {})
    tags.setdefault('instant', False)
    tags.setdefault('mass_type', None)
    tags.setdefault('no_redirect', False)
    return tags


def _build_pve_intent_tags(skill_id, target_type='single_slot'):
    tags = _extract_skill_tags(skill_id)
    tags_text = ' '.join(tags)
    inferred_mass = _infer_mass_type_from_skill(skill_id)
    if inferred_mass in ['mass_individual', 'mass_summation']:
        mass_type = inferred_mass
    elif target_type in ['mass_individual', 'mass_summation']:
        mass_type = target_type
    else:
        mass_type = None
    return _default_intent_tags({
        'instant': ('instant' in tags or '即時' in tags_text or '即時発動' in tags_text),
        'mass_type': mass_type,
        'no_redirect': ('no_redirect' in tags or '対象変更不可' in tags_text),
    })


def _resolve_skill_display_name(skill_id):
    if not skill_id:
        return None
    skill_data = all_skill_data.get(skill_id, {})
    if not isinstance(skill_data, dict):
        return str(skill_id)
    return (
        skill_data.get('name')
        or skill_data.get('デフォルト名称')
        or skill_data.get('skill_name')
        or str(skill_id)
    )


def _format_slot_actor_label(slot, actor):
    actor_name = (actor or {}).get('name') or (slot or {}).get('actor_id') or 'Unknown'
    try:
        idx = int((slot or {}).get('index_in_actor', 0)) + 1
    except (TypeError, ValueError):
        idx = 1
    return f"{actor_name}#{idx}"


def _broadcast_pve_round_start_preview_log(state, room, preview_rows, round_value=None):
    if not isinstance(state, dict):
        return
    if state.get('battle_mode', 'pvp') != 'pve':
        return
    rows = preview_rows if isinstance(preview_rows, list) else []
    if not rows:
        return

    try:
        normalized_round = int(round_value if round_value is not None else state.get('round', 0) or 0)
    except (TypeError, ValueError):
        normalized_round = int(state.get('round', 0) or 0)
    if int(state.get('_pve_preview_log_round', -1) or -1) == normalized_round:
        return

    lines = []
    for row in rows:
        from_label = row.get('from_label') or 'Enemy'
        target_label = row.get('target_label') or 'Target'
        skill_id = row.get('skill_id')
        if skill_id:
            skill_name = _resolve_skill_display_name(skill_id)
            lines.append(f"{from_label} → {target_label} / 使用予定: [{skill_id}] {skill_name}")
        else:
            lines.append(f"{from_label} → {target_label}")

    if lines:
        msg = "<strong>[PvE行動予告]</strong><br>" + "<br>".join(lines)
        broadcast_log(room, msg, 'info')
        state['_pve_preview_log_round'] = normalized_round


def _group_enemy_slots_by_actor(enemy_slot_ids, slots):
    grouped = {}
    for slot_id in enemy_slot_ids or []:
        slot = slots.get(slot_id, {}) if isinstance(slots, dict) else {}
        actor_id = slot.get('actor_id')
        if not actor_id:
            continue
        grouped.setdefault(str(actor_id), []).append(str(slot_id))

    for actor_id, actor_slots in grouped.items():
        actor_slots.sort(
            key=lambda sid: (
                int((slots.get(sid, {}) or {}).get('index_in_actor', 0)),
                -int((slots.get(sid, {}) or {}).get('initiative', 0)),
                str(sid)
            )
        )
        grouped[actor_id] = actor_slots
    return grouped


def _read_behavior_profile_from_actor(actor):
    if not isinstance(actor, dict):
        return {"enabled": False, "version": 1, "initial_loop_id": None, "loops": {}}
    flags = actor.get('flags')
    if not isinstance(flags, dict):
        flags = {}
        actor['flags'] = flags
    profile = normalize_behavior_profile(flags.get('behavior_profile'))
    flags['behavior_profile'] = profile
    return profile


def _apply_pve_auto_enemy_intents(state, battle_state, room):
    """
    PvE round start helper.
    - Enemies with auto target enabled get target intents per slot.
    - Enemies with auto skill enabled are auto-committed with suggested skill.
    """
    if not isinstance(state, dict) or not isinstance(battle_state, dict):
        return {'applied_slots': 0, 'committed_slots': 0, 'preview_rows': []}
    if state.get('battle_mode', 'pvp') != 'pve':
        return {'applied_slots': 0, 'committed_slots': 0, 'preview_rows': []}

    slots = battle_state.get('slots', {})
    if not isinstance(slots, dict) or len(slots) == 0:
        state['ai_target_arrows'] = []
        return {'applied_slots': 0, 'committed_slots': 0, 'preview_rows': []}

    characters = state.get('characters', [])
    char_by_id = {
        c.get('id'): c for c in characters
        if isinstance(c, dict) and c.get('id')
    }

    def _slot_team(slot):
        slot_team = _canonical_team((slot or {}).get('team'))
        if slot_team:
            return slot_team
        actor_id = (slot or {}).get('actor_id')
        actor = char_by_id.get(actor_id, {})
        return _canonical_team(actor.get('type'))

    def _slot_is_actionable(slot):
        if not isinstance(slot, dict):
            return False
        if bool(slot.get('disabled', False)):
            return False
        actor = char_by_id.get(slot.get('actor_id'))
        return _is_pve_actionable_character(actor)

    ally_target_slots = []
    enemy_slots = []
    for slot_id, slot in slots.items():
        if not _slot_is_actionable(slot):
            continue
        team = _slot_team(slot)
        if team == 'ally':
            ally_target_slots.append(str(slot_id))
        elif team == 'enemy':
            actor = char_by_id.get(slot.get('actor_id'), {})
            flags = actor.get('flags', {}) if isinstance(actor.get('flags'), dict) else {}
            if flags.get('auto_target_select', True):
                enemy_slots.append(str(slot_id))

    if not ally_target_slots or not enemy_slots:
        state['ai_target_arrows'] = []
        return {'applied_slots': 0, 'committed_slots': 0, 'preview_rows': []}

    grouped_enemy_slots = _group_enemy_slots_by_actor(enemy_slots, slots)
    intents = battle_state.get('intents', {})
    if not isinstance(intents, dict):
        intents = {}
    behavior_runtime = battle_state.get('behavior_runtime', {})
    if not isinstance(behavior_runtime, dict):
        behavior_runtime = {}

    now_ms = int(time.time() * 1000)
    seq = int(battle_state.get('intent_revision_seq', 0) or 0)
    arrows = []
    applied_slots = 0
    committed_slots = 0
    preview_rows = []
    round_value = int(battle_state.get('round', state.get('round', 0)) or 0)

    for actor_id, actor_slot_ids in grouped_enemy_slots.items():
        actor = char_by_id.get(actor_id, {})
        if not _is_pve_actionable_character(actor):
            continue

        flags = actor.get('flags', {}) if isinstance(actor.get('flags'), dict) else {}
        auto_skill_select = bool(
            flags.get('auto_skill_select', False)
            or flags.get('show_planned_skill', False)
        )

        behavior_profile = _read_behavior_profile_from_actor(actor)
        use_behavior_chart = bool(behavior_profile.get('enabled', False) and behavior_profile.get('loops'))
        planned_actions = [None for _ in actor_slot_ids]
        runtime_entry = behavior_runtime.get(actor_id) if isinstance(behavior_runtime.get(actor_id), dict) else {}

        if use_behavior_chart:
            runtime_entry = initialize_behavior_runtime_entry(
                behavior_profile,
                runtime_entry=runtime_entry,
                round_value=round_value,
            )
            transition_result = evaluate_transitions(
                behavior_profile,
                runtime_entry,
                actor_char=actor,
                state=state,
                battle_state=battle_state,
            )
            runtime_entry = transition_result.get('runtime', runtime_entry)
            picked = pick_step_actions(behavior_profile, runtime_entry)
            runtime_entry = picked.get('runtime', runtime_entry)
            planned_actions = choose_actions_for_slot_count(
                picked.get('actions', []),
                len(actor_slot_ids),
            )

        committed_skill_ids = []
        for idx, enemy_slot_id in enumerate(actor_slot_ids):
            slot = slots.get(enemy_slot_id, {}) if isinstance(slots, dict) else {}
            target_slot_id = random.choice(ally_target_slots)
            target_slot = slots.get(target_slot_id, {}) if isinstance(slots, dict) else {}
            target_actor_id = target_slot.get('actor_id')

            suggested_skill_id = planned_actions[idx] if idx < len(planned_actions) else None
            if suggested_skill_id and suggested_skill_id not in all_skill_data:
                suggested_skill_id = None
            if (not suggested_skill_id) and auto_skill_select:
                suggested_skill_id = ai_suggest_skill(actor)

            target_type = 'single_slot'
            target_payload = {'type': 'single_slot', 'slot_id': target_slot_id}
            inferred_mass = _infer_mass_type_from_skill(suggested_skill_id)
            if inferred_mass in ['mass_individual', 'mass_summation']:
                target_type = inferred_mass
                target_payload = {'type': inferred_mass, 'slot_id': None}

            committed = bool(suggested_skill_id)
            if committed:
                seq += 1
                committed_slots += 1
                committed_skill_ids.append(str(suggested_skill_id))

            intents[enemy_slot_id] = {
                'slot_id': enemy_slot_id,
                'actor_id': actor_id,
                'skill_id': suggested_skill_id,
                'target': target_payload,
                'tags': _build_pve_intent_tags(suggested_skill_id, target_type=target_type),
                'committed': committed,
                'committed_at': (now_ms + idx) if committed else None,
                'committed_by': 'AI:PVE' if committed else None,
                'intent_rev': seq if committed else int(intents.get(enemy_slot_id, {}).get('intent_rev', 0) or 0),
            }
            applied_slots += 1

            if target_actor_id:
                arrows.append({
                    'from_id': actor_id,
                    'to_id': target_actor_id,
                    'type': 'attack',
                    'visible': True
                })

            from_label = _format_slot_actor_label(slot, actor)
            if target_type in ['mass_individual', 'mass_summation']:
                target_label = '味方全体'
            else:
                target_label = _format_slot_actor_label(target_slot, char_by_id.get(target_actor_id, {}))
            preview_rows.append({
                'from_label': from_label,
                'target_label': target_label,
                'skill_id': suggested_skill_id,
            })

        if use_behavior_chart:
            runtime_entry['last_skill_ids'] = committed_skill_ids
            runtime_entry['last_round'] = round_value
            runtime_entry = advance_step_pointer(behavior_profile, runtime_entry)
            behavior_runtime[actor_id] = runtime_entry
        else:
            behavior_runtime.pop(actor_id, None)

    battle_state['intents'] = intents
    battle_state['intent_revision_seq'] = seq
    battle_state['behavior_runtime'] = behavior_runtime
    state['ai_target_arrows'] = arrows
    logger.info(
        "[pve_auto_intents] room=%s applied=%d committed=%d",
        room, applied_slots, committed_slots
    )
    return {
        'applied_slots': applied_slots,
        'committed_slots': committed_slots,
        'preview_rows': preview_rows,
    }


def process_full_round_end(room, username):
    state = get_room_state(room)
    if not state: return

    if state.get('is_round_ended', False):
        emit('new_log', {"message": "⚠️ 既にラウンド終了処理は完了しています。", "type": "error"})
        return

    broadcast_log(room, f"--- {username} が Round {state.get('round', 0)} の終了処理を実行しました ---", 'info')
    characters_to_process = state.get('characters', [])

    # 全員行動済みかチェック
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
        msg = f"⚠️ まだ行動していないキャラクターがいます: {', '.join(not_acted_chars)}"
        emit('new_log', {"message": msg, "type": "error"})
        return

    # 1. END_ROUND Effects
    for char in characters_to_process:
        used_skill_ids = char.get('used_skills_this_round', [])
        all_changes = []

        for skill_id in set(used_skill_ids):
            skill_data = all_skill_data.get(skill_id)
            if not skill_data: continue

            try:
                rule_json_str = skill_data.get('特記処理', '{}')
                rule_data = json.loads(rule_json_str)
                effects_array = rule_data.get("effects", [])
                if effects_array:
                    _, logs, changes = process_skill_effects(effects_array, "END_ROUND", char, char, None, context={'timeline': state.get('timeline', []), 'characters': state['characters'], 'room': room})
                    all_changes.extend(changes)
            except: pass

        for (c, type, name, value) in all_changes:
            if type == "APPLY_STATE":
                current_val = get_status_value(c, name)
                _update_char_stat(room, c, name, current_val + value, username=f"[{state.get('round')}R終了時]")
            elif type == "APPLY_BUFF":
                apply_buff(c, name, value["lasting"], value["delay"], data=value.get("data"))
                broadcast_log(room, f"[{name}] が {c['name']} に付与されました。", 'state-change')
            elif type == "GRANT_SKILL":
                grant_payload = dict(value) if isinstance(value, dict) else {}
                if "skill_id" not in grant_payload:
                    grant_payload["skill_id"] = name
                res = apply_grant_skill_change(room, state, char, c, grant_payload)
                if res.get("ok"):
                    broadcast_log(room, res.get("message", "スキル付与が発生した。"), "state-change")
                else:
                    logger.warning("[end_round grant_skill failed] %s", res.get("message"))
            elif type == "SUMMON_CHARACTER":
                res = apply_summon_change(room, state, c, value)
                if res.get("ok"):
                    broadcast_log(room, res.get("message", "召喚が発生した。"), "state-change")
                else:
                    logger.warning("[end_round summon failed] %s", res.get("message"))

        # 1c. Bleed
        bleed_value = get_status_value(char, '出血')
        if bleed_value > 0:
            _update_char_stat(room, char, 'HP', char['hp'] - bleed_value, username="[出血]", source=DamageSource.BLEED)

            # 出血維持バフチェック
            from plugins.buffs.bleed_maintenance import BleedMaintenanceBuff
            if BleedMaintenanceBuff.has_bleed_maintenance(char):
                 # 維持する場合、減少処理をスキップ (値は変わらない)
                 pass
            else:
                 # 通常: 半減
                _update_char_stat(room, char, '出血', bleed_value // 2, username="[出血]")

        # 1d. Thorns
        thorns_value = get_status_value(char, '荊棘')
        if thorns_value > 0:
            _update_char_stat(room, char, '荊棘', thorns_value - 1, username="[荊棘]")

        # 2. Buff Timers
        if "special_buffs" in char:
            active_buffs = []
            buffs_to_remove = []

            for buff in char['special_buffs']:
                buff_name = buff.get("name")
                delay = buff.get("delay", 0)
                lasting = buff.get("lasting", 0)

                if delay > 0:
                    buff["delay"] = delay - 1
                    if buff["delay"] == 0:
                        broadcast_log(room, f"[{buff_name}] の効果が {char['name']} で発動可能になった。", 'state-change')

                        # Hook
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
                        else: buffs_to_remove.append(buff_name)
                    else:
                        active_buffs.append(buff)
                elif lasting > 0:
                    buff["lasting"] = lasting - 1
                    if buff["lasting"] > 0:
                        active_buffs.append(buff)
                    else:
                        broadcast_log(room, f"[{buff_name}] の効果が {char['name']} から切れた。", 'state-change')
                        buffs_to_remove.append(buff_name)
                        if buff_name == "混乱":
                            _update_char_stat(room, char, 'MP', int(char.get('maxMp', 0)), username="[混乱解除]")
                            broadcast_log(room, f"{char['name']} は意識を取り戻した！ (MP全回復)", 'state-change')
                elif buff.get('is_permanent', False):
                    active_buffs.append(buff)

            char['special_buffs'] = active_buffs

        # Reset limits
        if 'round_item_usage' in char: char['round_item_usage'] = {}
        if 'used_immediate_skills_this_round' in char: char['used_immediate_skills_this_round'] = []
        if 'used_skills_this_round' in char: char['used_skills_this_round'] = []

    removed_summons = process_summon_round_end(state, room=room)
    for summoned in removed_summons:
        broadcast_log(room, f"{summoned.get('name', '召喚体')} は時間切れで消滅した。", "state-change")
    expired_granted = process_granted_skill_round_end(state, room=room)
    for row in expired_granted:
        char_name = row.get("char_name") or "キャラクター"
        skill_id = row.get("skill_id") or "UNKNOWN"
        broadcast_log(room, f"{char_name} から付与スキル {skill_id} が解除された。", "state-change")

    # ★ 追加: マホロバ (ID: 5) ラウンド終了時一括処理
    mahoroba_targets = []
    for char in state.get('characters', []):
        if char.get('hp', 0) <= 0: continue
        if get_effective_origin_id(char) == 5:
             # HP回復
             _update_char_stat(room, char, 'HP', char['hp'] + 3, username="[マホロバ恩恵]")
             mahoroba_targets.append(char['name'])

    if mahoroba_targets:
        broadcast_log(room, f"[マホロバ恩恵] {', '.join(mahoroba_targets)} のHPが3回復しました。", 'info')

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

def reset_battle_logic(room, mode, username, reset_options=None):
    state = get_room_state(room)
    if not state: return

    if mode == 'logs':
        state['logs'] = []
        broadcast_state_update(room)
        save_specific_room_state(room)
        return

    # Default options if None (Full reset behavior)
    if reset_options is None:
        reset_options = {
            'hp': True,
            'mp': True,
            'fp': True,
            'states': True, # 出血等
            'bad_states': True, # 状態異常 (麻痺など)
            'buffs': True,
            'timeline': True # Force timeline reset for status mode too based on user request
        }

    log_msg = f"\n--- {username} が戦闘をリセットしました (Mode: {mode}) ---\n"
    # log_msg += f"Opt: {json.dumps(reset_options, ensure_ascii=False)}"
    broadcast_log(room, log_msg, 'round')

    # ★ 追加: 矢印は常にリセット
    state['ai_target_arrows'] = []

    if mode == 'full':
        state['characters'] = []
        state['timeline'] = []
        state['round'] = 0
        state['is_round_ended'] = False
        state['turn_char_id'] = None
        state['turn_entry_id'] = None
    elif mode == 'status':
        # ラウンド数はリセットしない要望もあるかもしれないが、一旦デフォルトは0に戻す
        # (Status only reset usually implies starting over but keeping chars)
        state['round'] = 0
        state['is_round_ended'] = False
        state['ai_target_arrows'] = [] # Reset AI arrows

        # Status reset always clears timeline.
        state['timeline'] = []

        removed_summon_count = _remove_summoned_characters(state)
        if removed_summon_count > 0:
            broadcast_log(room, f"[リセット] 召喚体 {removed_summon_count} 体を盤面から除去しました。", 'info')

        for char in state.get('characters', []):
            initial = char.get('initial_state', {})

            # ★ 修正: 未配置(x<0)かつ生存(hp>0)の場合はリセット対象外
            # (戦闘不能キャラは未配置でもリセットして復帰させる)
            is_unplaced = char.get('x', -1) < 0
            is_dead = char.get('hp', 0) <= 0

            if is_unplaced and not is_dead:
                # リセットしない
                continue

            # --- HP ---
            if reset_options.get('hp'):
                max_hp = int(initial.get('maxHp', char.get('maxHp', 0)))
                # 初期値があればそれ、なければ現在のMax
                char['maxHp'] = max_hp
                char['hp'] = max_hp

            # --- MP ---
            if reset_options.get('mp'):
                max_mp = int(initial.get('maxMp', char.get('maxMp', 0)))
                char['maxMp'] = max_mp
                char['mp'] = max_mp

            # --- FP & Stackable States (出血, 破裂 etc) ---
            if reset_options.get('fp') or reset_options.get('states'):
                # これらは 'states' 配列に入っている
                # FPは独立して管理されることも多いが、ここでは states リスト内のもので判断

                # まず既存の states を維持しつつ、対象のものだけリセット
                # ただし、構造上 states はリストなので、全部作り直したほうが安全

                new_states = []
                # デフォルトのステータス定義
                default_states = {
                    "FP": 0, "出血": 0, "破裂": 0, "亀裂": 0, "戦慄": 0, "荊棘": 0
                }

                # 既存の状態を取得
                current_states = {s['name']: s['value'] for s in char.get('states', [])}

                for s_name, def_val in default_states.items():
                    # FP
                    if s_name == 'FP':
                        if reset_options.get('fp'):
                            # 初期FPは 0 ではなく process_battle_start で入るかもしれないが、
                            # ベースとしては 0 (または maxFp?)
                            # 実装では FP = maxFp (初期値) としている箇所が見当たる
                            # ここでは 0 にしてから process_battle_start に任せるか、maxFpにするか
                            # 既存ロジック: char['FP'] = char.get('maxFp', 0)
                            char['FP'] = char.get('maxFp', 0)
                            new_states.append({"name": "FP", "value": 0}) # 表示用?
                        else:
                            # 維持
                            val = current_states.get(s_name, def_val)
                            new_states.append({"name": s_name, "value": val})

                    # 他の蓄積値
                    else:
                        if reset_options.get('states'):
                            new_states.append({"name": s_name, "value": 0})
                        else:
                            val = current_states.get(s_name, def_val)
                            new_states.append({"name": s_name, "value": val})

                char['states'] = new_states

            # --- Status Effects (麻痺, 毒 etc - char['状態異常'] list) ---
            if reset_options.get('bad_states'):
                char['状態異常'] = []

            # --- Buffs ---
            if reset_options.get('buffs'):
                # 初期バフ（パッシブ由来やキャラ作成時バフ）は initial_state にある
                # initial_state の special_buffs を復元
                raw_initial_buffs = initial.get('special_buffs', [])
                char['special_buffs'] = [dict(b) for b in raw_initial_buffs]

            # --- Common Reset (Always) ---
            # これらは「戦闘状態」なのでリセット必須
            if 'round_item_usage' in char: char['round_item_usage'] = {}
            if 'used_immediate_skills_this_round' in char: char['used_immediate_skills_this_round'] = []
            if 'used_gem_protect_this_battle' in char: char['used_gem_protect_this_battle'] = False
            if 'used_skills_this_round' in char: char['used_skills_this_round'] = []

            char['hasActed'] = False
            char['speedRoll'] = 0
            char['isWideUser'] = False

            # ★ 追加: 戦闘開始時効果の再適用 (FPリセットなどが有効な場合のみ)
            # リセットオプションにかかわらず、戦闘開始時処理は走らせるべきか？
            # 例えば「FPリセット」を選んだ場合のみ、初期FP付与などの処理を再度適用したい。
            # しかし process_battle_start は副作用があるかもしれない。
            # ここではシンプルに、「HP/MP/FPのいずれかがリセットされた場合」は再適用する、とする
            if reset_options.get('hp') or reset_options.get('mp') or reset_options.get('fp'):
                 try:
                     process_battle_start(room, char)
                 except Exception as e:
                     logger.error(f"process_battle_start in reset failed: {e}")

            # ★ 追加: 出身国ボーナスバフを再適用 (バフリセット時のみ)
            if reset_options.get('buffs'):
                apply_origin_bonus_buffs(char)

        state['turn_char_id'] = None
        state['turn_entry_id'] = None

    # Keep Select/Resolve snapshot in sync with room reset.
    # Without this, old slots remain in battle_state and slot badges keep rendering.
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
        emit('new_log', {"message": "現在アクティブなマッチまたは広域予約はありません。", "type": "error"})
        return

    # リセット処理
    state['active_match'] = None
    state['pending_wide_ids'] = []  # 広域マッチの予約もクリア

    save_specific_room_state(room)
    broadcast_state_update(room)

    # モーダル閉じるイベントを送信 (広域用とDuel用)
    socketio.emit('match_modal_closed', {}, to=room)
    socketio.emit('force_close_wide_modal', {}, to=room) # 必要であればクライアント側で受ける

    broadcast_log(room, f"⚠️ GM {username} がマッチを強制終了しました。", 'match-end')

def move_token_logic(room, char_id, x, y, username, attribute):
    state = get_room_state(room)
    if not state: return

    target_char = next((c for c in state["characters"] if c.get('id') == char_id), None)
    if not target_char: return

    if not is_authorized_for_character(room, char_id, username, attribute):
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

    # Provoke Check
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

    # Resume Check
    current_match = state.get('active_match')
    is_resume = False

    if current_match and \
       current_match.get('attacker_id') == attacker_id and \
       current_match.get('defender_id') == defender_id and \
       current_match.get('match_type') == match_type:
           state['active_match']['is_active'] = True
           state['active_match']['opened_by'] = username
           is_resume = True
    else:
        # New Match
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
    socketio.emit('match_modal_opened', {
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
    socketio.emit('match_modal_closed', {}, to=room)
    broadcast_state_update(room)

def sync_match_data_logic(room, side, data, username, attribute):
    state = get_room_state(room)
    if not state: return
    active_match = state.get('active_match', {})

    if not active_match.get('is_active') or active_match.get('match_type') != 'duel':
        return

    # ★ 権限チェック: GM または そのキャラクターの所有者のみ許可
    target_char_id = None
    if side == 'attacker':
        target_char_id = active_match.get('attacker_id')
    elif side == 'defender':
        target_char_id = active_match.get('defender_id')

    # 所有者確認
    allowed = False
    if attribute == 'GM':
        allowed = True
    elif target_char_id:
        owners = state.get('character_owners', {})
        if owners.get(target_char_id) == username:
            allowed = True

    if not allowed:
        # 権限がない場合は無視（ログに出しても良いが、頻繁な同期なのでサイレントに無視するか、デバッグログのみ）
        logger.warning(f"Unauthorized sync attempt by {username} for side {side} (CharID: {target_char_id})")
        return

    if side == 'attacker':
        state['active_match']['attacker_data'] = data
    elif side == 'defender':
        state['active_match']['defender_data'] = data

    save_specific_room_state(room)
    socketio.emit('match_data_updated', {'side': side, 'data': data}, to=room)

def process_round_start(room, username):
    logger.debug(f"process_round_start called for room: {room} by {username}")
    state = get_room_state(room)
    if not state:
        logger.debug(f"Room state not found for {room}")
        return
    clear_newly_applied_flags(state)

    # Check previous round end flag
    if state.get('round', 0) > 0 and not state.get('is_round_ended', False):
        emit('new_log', {'message': 'ラウンド終了処理が完了していません。「ラウンド終了」ボタンを押してください。', 'type': 'error'}, room=room)
        return

    # increment round
    state['round'] = state.get('round', 0) + 1
    state['is_round_ended'] = False

    broadcast_log(room, f"--- {username} が Round {state['round']} を開始しました ---", 'round')

    # Update Speed and Create Timeline
    timeline_unsorted = []
    import uuid

    # Debug: Log start of timeline generation
    logger.info(f"[Timeline] Starting generation for Round {state.get('round')}. Total chars: {len(state.get('characters', []))}")

    for char in state.get('characters', []):
        # Reset Wide User Flag (Start of Round)
        char['isWideUser'] = False

        # Type-safe checks

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

        # Calculate Speed (1d6 + Speed/6)
        # Clear previous totalSpeed
        char['totalSpeed'] = None

        speed_val = 0
        try:
            speed_val = int(get_status_value(char, '速度'))
        except:
            speed_val = 0

        # ★ 加速・減速による速度補正
        from plugins.buffs.speed_mod import SpeedModBuff
        speed_modifier = SpeedModBuff.get_speed_modifier(char)

        initiative = (speed_val // 6) + speed_modifier

        if speed_modifier != 0:
            mod_text = f"+{speed_modifier}" if speed_modifier > 0 else str(speed_modifier)
            broadcast_log(room, f"{char['name']} の速度補正: {mod_text} (加速/減速)", 'info')

        # 速度ロール後に加速・減速をクリア
        SpeedModBuff.clear_speed_modifiers(char)

        # 行動回数を取得 (デフォルト1)
        try:
             action_count = int(get_status_value(char, '行動回数'))
        except:
             action_count = 1
        action_count = max(1, action_count)

        logger.debug(f"[SPEED ROLL] {char['name']}: speed={speed_val} (init={initiative}), count={action_count}")

        for i in range(action_count):
            roll = random.randint(1, 6)
            total_speed = initiative + roll

            # ★ 追加: 速度値の下限は1
            total_speed = max(1, total_speed)

            entry_id = str(uuid.uuid4())
            timeline_unsorted.append({
                'id': entry_id,          # UNIQUE ID for this action
                'char_id': char['id'],   # Link to Character
                'speed': total_speed,
                'stat_speed': initiative,
                'roll': roll,
                'acted': False,
                'is_extra': (i > 0)
            })

            # For backward compatibility / display on char token
            if i == 0:
                char['speedRoll'] = roll
                char['totalSpeed'] = total_speed

        # Reset Turn State
        char['hasActed'] = False

    # Sort Timeline (Speed Descending)
    timeline_unsorted.sort(key=lambda x: x['speed'], reverse=True)

    # Store full objects
    state['timeline'] = timeline_unsorted
    logger.info(f"[Timeline] Generated {len(timeline_unsorted)} entries.")

    state['turn_char_id'] = None
    state['turn_entry_id'] = None

    # Broadcast Timeline Info
    log_msg = "行動順が決まりました:<br>"
    for idx, item in enumerate(timeline_unsorted):
        char = next((c for c in state['characters'] if c['id'] == item['char_id']), None)
        if char:
            roll = item.get('roll', 0)
            stat = item.get('stat_speed', 0)
            total = item.get('speed', 0)
            sign = "+" if stat >= 0 else ""

            # ユーザー要望: 1d6(X)+Y の形式で内訳表示
            breakdown = f"1d6({roll}){sign}{stat} = {total}"

            log_msg += f"{idx+1}. {char['name']} ({breakdown})<br>"

    broadcast_log(room, log_msg, 'info')

    # ★ 追加: ラティウム (ID: 3) ラウンド開始時一括処理
    # 全員のFPを+1する
    latium_targets = []
    for char in state.get('characters', []):
        if char.get('hp', 0) <= 0: continue
        if get_effective_origin_id(char) == 3:
            current_fp = get_status_value(char, 'FP')
            _update_char_stat(room, char, 'FP', current_fp + 1, username="[ラティウム恩恵]")
            latium_targets.append(char['name'])

    if latium_targets:
        broadcast_log(room, f"[ラティウム恩恵] {', '.join(latium_targets)} のFPが1増加しました。", 'info')


    # ★ 追加: PvEモードならターゲット抽選 -> 広域予約確定後に一本化
    # if state.get('battle_mode') == 'pve':
    #     from manager.battle.battle_ai import ai_select_targets
    #     ai_select_targets(state, room)
    #     logger.info(f"PvE AI Targets updated for Round {state['round']}")

    # Reset Wide Modal Logic State
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

    # Broadcast after switching to select phase to avoid transient round_end emits.
    broadcast_state_update(room)
    save_specific_room_state(room)

    if battle_state:
        emit_select_resolve_events(room, include_round_started=True)

    # Select/Resolve flow should not invoke legacy wide modal auto path.
    if _is_select_resolve_active(state):
        logger.info("[round_start] skip legacy wide modal room=%s reason=select_resolve_active", room)
    else:
        socketio.emit('open_wide_declaration_modal', {}, to=room)

def process_wide_declarations(room, wide_user_ids):
    state = get_room_state(room)
    if not state: return

    # Legacy wide declaration flow must not mutate state during select/resolve.
    if _is_select_resolve_active(state):
        logger.info("[wide_declarations] ignored room=%s reason=select_resolve_active ids=%s", room, wide_user_ids)
        return

    # Reset wide flags for everyone first (safety)
    for char in state.get('characters', []):
        char['isWideUser'] = False

    # Set new flags
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
        broadcast_log(room, f"広域攻撃予約: {', '.join(names)}", 'info')
        # Reorder timeline: Move wide users to the front
        current_timeline = state.get('timeline', [])

        # New Logic for Object Timeline
        valid_wide_char_ids = [str(uid) for uid in wide_user_ids if any(str(c['id']) == str(uid) for c in state['characters'])]

        wide_entries = [entry for entry in current_timeline if str(entry['char_id']) in valid_wide_char_ids]
        remaining_entries = [entry for entry in current_timeline if str(entry['char_id']) not in valid_wide_char_ids]

        # New timeline: [Wide Entries] + [Remaining Entries]
        state['timeline'] = wide_entries + remaining_entries
        logger.debug(f"[DEBUG] New timeline len: {len(state['timeline'])}")
    else:
        broadcast_log(room, "広域攻撃予約: なし", 'info')

    save_specific_room_state(room)
    broadcast_state_update(room)

    # 状態保存後に少し待機してからターン進行（念のため）
    # proceed_next_turn(room)

    # ★修正: Latium (ID: 3) などのターン開始時効果を確実にするため
    # proceed_next_turn を呼び出し、その結果を確認する
    # In Select/Resolve mode, do not run legacy turn progression.
    if _is_select_resolve_active(state):
        logger.info("[wide_declarations] skip legacy proceed_next_turn room=%s reason=select_resolve_active", room)
        return

    # Also update AI Arrows (for Wide Match visualization)
    ai_select_targets(state, room)
    proceed_next_turn(room)

def process_wide_modal_confirm(room, user_id, attribute, wide_ids):
    state = get_room_state(room)
    if not state: return

    # Ignore legacy wide modal confirms while select/resolve flow is active.
    if _is_select_resolve_active(state):
        logger.info(
            "[wide_modal_confirm] ignored room=%s user=%s reason=select_resolve_active ids=%s",
            room, user_id, wide_ids
        )
        return

    # Init container if missing
    if 'wide_modal_confirms' not in state: state['wide_modal_confirms'] = []
    if 'pending_wide_ids' not in state: state['pending_wide_ids'] = []

    # Merge Wide IDs (from this user)
    # Note: Even if already confirmed, we merge incase they updated selection (though UI locks).
    for wid in wide_ids:
        if wid not in state['pending_wide_ids']:
            state['pending_wide_ids'].append(wid)

    # 1. GM Force Confirm (Overrides waiting)
    if attribute == 'GM':
        logger.info(f"[WideModal] GM {user_id} Forced Confirm. IDs: {wide_ids}")

        # Execute Wide Declarations immediately
        process_wide_declarations(room, state['pending_wide_ids'])

        # Close Modal for everyone
        socketio.emit('close_wide_declaration_modal', {}, to=room)

        broadcast_log(room, f"GMにより広域攻撃予約が確定されました。", 'info')
        return

    # 2. Normal Player Confirm
    if user_id not in state['wide_modal_confirms']:
        state['wide_modal_confirms'].append(user_id)
        broadcast_log(room, f"{user_id} が広域予約を確認しました。", 'info')

    # Check coverage (All non-GM users in room)
    # Check coverage (All non-GM users in room)
    current_room_users = get_users_in_room(room)

    # Filter for active non-GM users
    non_gm_users = set()
    for sid, u_info in current_room_users.items():
        if u_info.get('attribute') != 'GM':
            non_gm_users.add(u_info.get('username'))

    # Check if all non-GM users have confirmed
    confirmed_users = set(state['wide_modal_confirms'])

    # Logic: If there are non-GM users and all of them confirmed, proceed.
    # If there are NO non-GM users (only GM in room), GM confirm handled above.

    all_confirmed = False
    if len(non_gm_users) > 0:
        if non_gm_users.issubset(confirmed_users):
            all_confirmed = True

    if all_confirmed:
        logger.info("[WideModal] All players confirmed. Executing.")
        process_wide_declarations(room, state['pending_wide_ids'])
        socketio.emit('close_wide_declaration_modal', {}, to=room)
    else:
        # Wait
        logger.info(f"Player {user_id} confirmed. Waiting... ({len(confirmed_users)}/{len(non_gm_users)})")
        save_specific_room_state(room)



def update_battle_background_logic(room, image_url, scale, offset_x, offset_y, username, attribute):
    """
    戦闘画面の背景画像を更新するロジック
    """
    if attribute != 'GM':
        emit('new_log', {'message': '背景設定はGMのみ可能です。', 'type': 'error'})
        return

    state = get_room_state(room)
    if not state: return

    # データ構造の初期化
    if 'battle_map_data' not in state:
        state['battle_map_data'] = {}

    # 値の更新
    state['battle_map_data']['background_image'] = image_url
    if scale is not None:
        state['battle_map_data']['background_scale'] = scale
    if offset_x is not None:
        state['battle_map_data']['background_offset_x'] = offset_x
    if offset_y is not None:
        state['battle_map_data']['background_offset_y'] = offset_y

    broadcast_state_update(room)
    broadcast_log(room, f"戦闘マップの背景が変更されました。", 'system')

# ★ 追加: PvEモード切替ロジック
def process_switch_battle_mode(room, mode, username):
    state = get_room_state(room)
    if not state: return

    old_mode = state.get('battle_mode', 'pvp')
    if old_mode == mode:
        return

    state['battle_mode'] = mode
    broadcast_log(room, f"戦闘モードが変更されました: {old_mode.upper()} → {mode.upper()}", 'system')

    # PvEになったらターゲット再抽選 -> ユーザー要望により廃止 (ラウンド開始時のみ)
    # if mode == 'pve':
    #     from manager.battle.battle_ai import ai_select_targets
    #     ai_select_targets(state)
    #     broadcast_log(room, "AIがターゲットを選定しました。", 'info', secret=True)

    save_specific_room_state(room)
    broadcast_state_update(room)

# ★ 追加: AIスキル提案API (Socket経由で呼ばれる想定だが、routesで実装してもいい。ここではロジックのみ)
def process_ai_suggest_skill(room, char_id):
    # これは戻り値を返すタイプなので、Socketのコールバックで返すのが一般的
    # common_managerにおく必要性は薄いかもしれないが、一応
    state = get_room_state(room)
    if not state: return None

    char = next((c for c in state['characters'] if c['id'] == char_id), None)
    if not char: return None

    return ai_suggest_skill(char)


def _build_select_resolve_slots_from_timeline(room_state):
    slots = {}
    timeline = room_state.get('timeline', [])
    characters = room_state.get('characters', [])
    char_map = {c.get('id'): c for c in characters if isinstance(c, dict)}
    actor_slot_count = {}

    for entry in timeline:
        if not isinstance(entry, dict):
            continue
        slot_id = entry.get('id')
        actor_id = entry.get('char_id')
        if not slot_id or not actor_id:
            continue

        char = char_map.get(actor_id, {})
        index_in_actor = actor_slot_count.get(actor_id, 0)
        actor_slot_count[actor_id] = index_in_actor + 1

        slots[slot_id] = {
            'slot_id': slot_id,
            'actor_id': actor_id,
            'team': char.get('type', 'unknown'),
            'index_in_actor': index_in_actor,
            'initiative': entry.get('speed', 0),
            'disabled': False,
            'locked_target': False,
            'status': 'ready' if char.get('hp', 0) > 0 else 'down',
            'is_alive': bool(char.get('hp', 0) > 0)
        }

    return slots


def _build_select_resolve_timeline_from_room(room_state, slots):
    slots = slots if isinstance(slots, dict) else {}
    if not slots:
        return []

    slot_ids = set(slots.keys())
    room_timeline = room_state.get('timeline', []) if isinstance(room_state, dict) else []
    ordered = []

    if isinstance(room_timeline, list) and room_timeline:
        first = room_timeline[0]
        if isinstance(first, dict):
            for entry in room_timeline:
                if not isinstance(entry, dict):
                    continue
                slot_id = entry.get('id')
                if slot_id in slot_ids:
                    ordered.append(slot_id)
        elif isinstance(first, str):
            for slot_id in room_timeline:
                if slot_id in slot_ids:
                    ordered.append(slot_id)

    if not ordered:
        return sorted(
            slots.keys(),
            key=lambda sid: (-int(slots.get(sid, {}).get('initiative', 0)), str(sid))
        )

    seen = set(ordered)
    missing = [sid for sid in slots.keys() if sid not in seen]
    if missing:
        missing.sort(key=lambda sid: (-int(slots.get(sid, {}).get('initiative', 0)), str(sid)))
        ordered.extend(missing)

    return ordered


def ensure_battle_state_vNext(room_state, battle_id=None, round_value=None, rebuild_slots=False):
    if not isinstance(room_state, dict):
        return None

    migrated = room_state.get('select_resolve_battle_state')
    battle_state = room_state.get('battle_state')
    if not isinstance(battle_state, dict):
        battle_state = migrated if isinstance(migrated, dict) else {}

    battle_state['battle_id'] = battle_id or battle_state.get('battle_id') or 'battle_main'
    battle_state['round'] = round_value if isinstance(round_value, int) else battle_state.get('round', room_state.get('round', 0))
    battle_state['phase'] = battle_state.get('phase', 'select')
    battle_state['slots'] = battle_state.get('slots', {})
    battle_state['timeline'] = battle_state.get('timeline', [])
    battle_state['tiebreak'] = battle_state.get('tiebreak', [])
    battle_state['intents'] = battle_state.get('intents', {})
    battle_state['resolve_snapshot_intents'] = battle_state.get('resolve_snapshot_intents', {})
    battle_state['resolve_snapshot_at'] = battle_state.get('resolve_snapshot_at')
    battle_state['behavior_runtime'] = battle_state.get('behavior_runtime', {})
    battle_state['redirects'] = battle_state.get('redirects', [])
    battle_state['resolve_ready'] = bool(battle_state.get('resolve_ready', False))
    battle_state['resolve_ready_info'] = battle_state.get('resolve_ready_info', {})
    battle_state['resolve'] = battle_state.get('resolve', {})
    battle_state['resolve']['mass_queue'] = battle_state['resolve'].get('mass_queue', [])
    battle_state['resolve']['single_queue'] = battle_state['resolve'].get('single_queue', [])
    battle_state['resolve']['resolved_slots'] = battle_state['resolve'].get('resolved_slots', [])
    battle_state['resolve']['trace'] = battle_state['resolve'].get('trace', [])

    if rebuild_slots or not battle_state['slots']:
        battle_state['slots'] = _build_select_resolve_slots_from_timeline(room_state)

    slots = battle_state.get('slots', {})
    slot_ids = set(slots.keys()) if isinstance(slots, dict) else set()

    current_timeline = battle_state.get('timeline', [])
    if not isinstance(current_timeline, list):
        current_timeline = []
    current_timeline = [sid for sid in current_timeline if sid in slot_ids]
    current_set = set(current_timeline)
    desired_timeline = _build_select_resolve_timeline_from_room(room_state, slots)

    # Keep timeline and slots in sync across rounds.
    # Without this, resolve queue can reference stale slot IDs and all actions fizzle as no_intent.
    if rebuild_slots or current_set != slot_ids:
        battle_state['timeline'] = desired_timeline
    else:
        battle_state['timeline'] = current_timeline

    if isinstance(battle_state.get('intents'), dict):
        battle_state['intents'] = {
            sid: intent for sid, intent in battle_state.get('intents', {}).items()
            if sid in slot_ids
        }
    if isinstance(battle_state.get('resolve_snapshot_intents'), dict):
        battle_state['resolve_snapshot_intents'] = {
            sid: intent for sid, intent in battle_state.get('resolve_snapshot_intents', {}).items()
            if sid in slot_ids
        }
    if isinstance(battle_state.get('behavior_runtime'), dict):
        actor_ids = {
            str((slot or {}).get('actor_id'))
            for slot in (slots.values() if isinstance(slots, dict) else [])
            if isinstance(slot, dict) and slot.get('actor_id')
        }
        battle_state['behavior_runtime'] = {
            str(actor_id): runtime
            for actor_id, runtime in battle_state.get('behavior_runtime', {}).items()
            if str(actor_id) in actor_ids and isinstance(runtime, dict)
        }

    resolved_slots = battle_state['resolve'].get('resolved_slots', [])
    if not isinstance(resolved_slots, list):
        resolved_slots = []
    battle_state['resolve']['resolved_slots'] = [sid for sid in resolved_slots if sid in slot_ids]

    for queue_key in ['mass_queue', 'single_queue']:
        queue = battle_state['resolve'].get(queue_key, [])
        if not isinstance(queue, list):
            queue = []
        battle_state['resolve'][queue_key] = [sid for sid in queue if sid in slot_ids]

    room_state['battle_state'] = battle_state
    if 'select_resolve_battle_state' in room_state:
        room_state.pop('select_resolve_battle_state', None)

    logger.debug(
        "[battle_state.ensure] phase=%s slots=%s intents=%s",
        battle_state.get('phase'),
        len(battle_state.get('slots', {})),
        len(battle_state.get('intents', {}))
    )
    return battle_state


def get_or_create_select_resolve_state(room, battle_id=None, round_value=None, rebuild_slots=False):
    room_state = get_room_state(room)
    if not room_state:
        return None
    return ensure_battle_state_vNext(
        room_state,
        battle_id=battle_id,
        round_value=round_value,
        rebuild_slots=rebuild_slots
    )


def build_select_resolve_state_payload(room, battle_id=None):
    battle_state = get_or_create_select_resolve_state(room, battle_id=battle_id)
    if not battle_state:
        return None
    return {
        'room_id': room,
        'battle_id': battle_state.get('battle_id'),
        'round': battle_state.get('round', 0),
        'phase': battle_state.get('phase', 'select'),
        'timeline': battle_state.get('timeline', []),
        'tiebreak': battle_state.get('tiebreak', []),
        'slots': battle_state.get('slots', {}),
        'intents': battle_state.get('intents', {}),
        'redirects': battle_state.get('redirects', []),
        'resolve_ready': bool(battle_state.get('resolve_ready', False)),
        'resolve_ready_info': battle_state.get('resolve_ready_info', {})
    }


def process_select_resolve_round_start(room, battle_id, round_value):
    state = get_room_state(room)
    if not state:
        return None
    clear_newly_applied_flags(state)

    def _roll_1d6():
        result = roll_dice("1d6")
        try:
            return int(result.get('total', 1))
        except Exception:
            return 1

    battle_state = ensure_battle_state_vNext(
        state,
        battle_id=battle_id,
        round_value=round_value,
        rebuild_slots=False
    )
    if not battle_state:
        return None

    characters = state.get('characters', [])
    slot_entries = []
    legacy_timeline_entries = []
    from plugins.buffs.speed_mod import SpeedModBuff

    for char in characters:
        try:
            hp = int(char.get('hp', 0))
            x_val = float(char.get('x', -1))
            escaped = bool(char.get('is_escaped', False))
        except (ValueError, TypeError):
            continue

        if hp <= 0 or escaped or x_val < 0:
            continue
        can_act_from_round = int(char.get('can_act_from_round', 0) or 0)
        if bool(char.get('is_summoned', False)) and can_act_from_round > int(round_value):
            continue

        actor_id = char.get('id')
        if not actor_id:
            continue

        try:
            action_count = int(get_status_value(char, '行動回数'))
        except Exception:
            action_count = 1
        action_count = max(1, action_count)

        char['totalSpeed'] = None

        try:
            speed_val = int(get_status_value(char, '速度'))
        except Exception:
            speed_val = 0
        speed_modifier = SpeedModBuff.get_speed_modifier(char)
        base_initiative = (speed_val // 6) + speed_modifier

        if speed_modifier != 0:
            mod_text = f"+{speed_modifier}" if speed_modifier > 0 else str(speed_modifier)
            broadcast_log(room, f"{char.get('name', actor_id)} の速度補正: {mod_text} (加速/減速)", 'info')

        for i in range(action_count):
            slot_id = f"{actor_id}:r{round_value}:s{i}"
            roll = _roll_1d6()
            initiative = max(1, base_initiative + roll)
            slot_entries.append({
                'slot_id': slot_id,
                'actor_id': actor_id,
                'team': char.get('type', 'unknown'),
                'index_in_actor': i,
                'initiative': initiative,
                'speed_stat': speed_val,
                'speed_base': base_initiative,
                'speed_modifier': speed_modifier,
                'speed_roll': roll,
                'disabled': False,
                'locked_target': False,
                'status': 'ready',
                'is_alive': True,
                '_tie_roll': None
            })
            legacy_timeline_entries.append({
                'id': slot_id,
                'char_id': actor_id,
                'speed': initiative,
                'stat_speed': base_initiative,
                'roll': roll,
                'acted': False,
                'is_extra': (i > 0)
            })
            if i == 0:
                char['speedRoll'] = roll
                char['totalSpeed'] = initiative

        SpeedModBuff.clear_speed_modifiers(char)
        char['hasActed'] = False

    grouped_by_init = {}
    for entry in slot_entries:
        grouped_by_init.setdefault(entry['initiative'], []).append(entry)

    tiebreak_payload = []
    for initiative, group in grouped_by_init.items():
        if len(group) <= 1:
            continue
        rolls = {}
        for slot in group:
            tie_roll = _roll_1d6()
            slot['_tie_roll'] = tie_roll
            rolls[slot['slot_id']] = tie_roll
        tiebreak_payload.append({
            'initiative': initiative,
            'group': sorted([slot['slot_id'] for slot in group]),
            'rolls': rolls
        })

    slot_entries.sort(
        key=lambda x: (
            -x['initiative'],
            -(x['_tie_roll'] if x['_tie_roll'] is not None else -1),
            x['slot_id']
        )
    )

    slots_dict = {}
    timeline = []
    legacy_by_slot_id = {
        str(entry.get('id')): entry for entry in legacy_timeline_entries if isinstance(entry, dict)
    }
    legacy_timeline_sorted = []
    for slot in slot_entries:
        slot_id = slot['slot_id']
        slots_dict[slot_id] = {
            'slot_id': slot_id,
            'actor_id': slot['actor_id'],
            'team': slot['team'],
            'index_in_actor': slot['index_in_actor'],
            'initiative': slot['initiative'],
            'speed_stat': slot['speed_stat'],
            'speed_base': slot['speed_base'],
            'speed_modifier': slot['speed_modifier'],
            'speed_roll': slot['speed_roll'],
            'disabled': slot['disabled'],
            'locked_target': slot['locked_target'],
            'status': slot['status'],
            'is_alive': slot['is_alive']
        }
        timeline.append(slot_id)
        legacy_entry = legacy_by_slot_id.get(slot_id)
        if isinstance(legacy_entry, dict):
            legacy_timeline_sorted.append(legacy_entry)

    battle_state['round'] = round_value
    battle_state['phase'] = 'select'
    battle_state['slots'] = slots_dict
    battle_state['timeline'] = timeline
    battle_state['tiebreak'] = tiebreak_payload
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
    pve_auto_result = _apply_pve_auto_enemy_intents(state, battle_state, room)
    _broadcast_pve_round_start_preview_log(
        state,
        room,
        pve_auto_result.get('preview_rows', []) if isinstance(pve_auto_result, dict) else [],
        round_value=battle_state.get('round')
    )
    state['timeline'] = legacy_timeline_sorted

    save_specific_room_state(room)

    logger.info(
        "[battle_round_start] room=%s battle_id=%s round=%s slots=%s timeline_head=%s tiebreak_groups=%s",
        room,
        battle_id,
        round_value,
        len(slots_dict),
        timeline[:5],
        len(tiebreak_payload)
    )

    return {
        'room_id': room,
        'battle_id': battle_id,
        'round': round_value,
        'phase': 'select',
        'slots': slots_dict,
        'timeline': timeline,
        'tiebreak': tiebreak_payload
    }


def _get_character_by_id(state, actor_id):
    if not state or not actor_id:
        return None
    return next((c for c in state.get('characters', []) if c.get('id') == actor_id), None)


def is_dodge_lock_active(state, actor_id):
    actor = _get_character_by_id(state, actor_id)
    if not actor:
        return False
    try:
        from plugins.buffs.dodge_lock import DodgeLockBuff
        return DodgeLockBuff.has_re_evasion(actor)
    except Exception:
        return False


def get_dodge_lock_skill_id(state, actor_id):
    actor = _get_character_by_id(state, actor_id)
    if not actor:
        return None
    try:
        from plugins.buffs.dodge_lock import DodgeLockBuff
        return DodgeLockBuff.get_locked_skill_id(actor)
    except Exception:
        return None


def _is_evade_skill(skill_id):
    if not skill_id:
        return False
    skill_data = all_skill_data.get(skill_id, {})
    category = str(skill_data.get('分類', ''))
    if category == '回避':
        return True
    for tag in skill_data.get('tags', []) or []:
        if isinstance(tag, str) and '回避' in tag:
            return True
    return False


def _choose_highest_initiative_slot(slot_ids, slots):
    if not slot_ids:
        return None
    return max(
        slot_ids,
        key=lambda s: (int(slots.get(s, {}).get('initiative', 0)), str(s))
    )


def select_evade_insert_slot(state, battle_state, defender_actor_id, attacker_slot):
    if not defender_actor_id or not attacker_slot:
        return None, None
    if not is_dodge_lock_active(state, defender_actor_id):
        return None, None

    slots = battle_state.get('slots', {})
    intents = battle_state.get('intents', {})
    locked_skill_id = get_dodge_lock_skill_id(state, defender_actor_id)

    actor_slot_ids = [
        slot_id
        for slot_id, slot in slots.items()
        if slot.get('actor_id') == defender_actor_id
    ]
    if not actor_slot_ids:
        return None, None

    def _is_locked_skill_match(skill_id):
        if not locked_skill_id:
            return True
        return skill_id == locked_skill_id

    direct_candidates = []
    for slot_id in actor_slot_ids:
        intent = intents.get(slot_id, {})
        skill_id = intent.get('skill_id')
        if not intent.get('committed', False):
            continue
        if not _is_evade_skill(skill_id):
            continue
        if not _is_locked_skill_match(skill_id):
            continue
        target = intent.get('target', {})
        if target.get('type') == 'single_slot' and target.get('slot_id') == attacker_slot:
            direct_candidates.append(slot_id)
    picked = _choose_highest_initiative_slot(direct_candidates, slots)
    if picked:
        return picked, 'targeted_evade'

    evade_candidates = []
    for slot_id in actor_slot_ids:
        intent = intents.get(slot_id, {})
        skill_id = intent.get('skill_id')
        if not intent.get('committed', False):
            continue
        if not _is_evade_skill(skill_id):
            continue
        if not _is_locked_skill_match(skill_id):
            continue
        evade_candidates.append(slot_id)
    picked = _choose_highest_initiative_slot(evade_candidates, slots)
    if picked:
        return picked, 'evade_slot_reuse'

    resolved_slots = battle_state.get('resolve', {}).get('resolved_slots', [])
    reusable = [
        slot_id for slot_id in resolved_slots
        if slots.get(slot_id, {}).get('actor_id') == defender_actor_id
    ]
    picked = _choose_highest_initiative_slot(reusable, slots)
    if picked:
        return picked, 'resolved_slot_reuse'

    return None, None


def select_hard_followup_evade_slot(state, battle_state, defender_actor_id, attacker_slot):
    """
    強硬追撃向けの回避差し込み選定。
    優先順位:
      1) 強硬追撃元を target 指定している未解決回避
      2) 未解決の回避スロット
      3) 再回避ロック時のみ、解決済み回避の再利用
    """
    if not defender_actor_id or not attacker_slot:
        return None, None

    slots = battle_state.get('slots', {})
    intents = battle_state.get('intents', {})
    resolved_slots = battle_state.get('resolve', {}).get('resolved_slots', [])
    resolved_set = set(resolved_slots if isinstance(resolved_slots, list) else [])

    actor_slot_ids = [
        slot_id
        for slot_id, slot in slots.items()
        if isinstance(slot, dict) and slot.get('actor_id') == defender_actor_id
    ]
    if not actor_slot_ids:
        return None, None

    def _is_unresolved(slot_id):
        return str(slot_id) not in resolved_set

    def _is_committed_evade(slot_id):
        intent = intents.get(slot_id, {}) if isinstance(intents, dict) else {}
        skill_id = intent.get('skill_id')
        if not intent.get('committed', False):
            return False
        return _is_evade_skill(skill_id)

    # 1) 明示targetの未解決回避
    direct_targeted = []
    for slot_id in actor_slot_ids:
        if not _is_unresolved(slot_id):
            continue
        if not _is_committed_evade(slot_id):
            continue
        target = intents.get(slot_id, {}).get('target', {})
        if target.get('type') == 'single_slot' and target.get('slot_id') == attacker_slot:
            direct_targeted.append(slot_id)
    picked = _choose_highest_initiative_slot(direct_targeted, slots)
    if picked:
        return picked, 'targeted_evade'

    # 2) 未解決回避
    unresolved_evade = [
        slot_id for slot_id in actor_slot_ids
        if _is_unresolved(slot_id) and _is_committed_evade(slot_id)
    ]
    picked = _choose_highest_initiative_slot(unresolved_evade, slots)
    if picked:
        return picked, 'unresolved_evade'

    # 3) 再回避ロック時のみ解決済み再利用
    if is_dodge_lock_active(state, defender_actor_id):
        reusable = [
            slot_id for slot_id in actor_slot_ids
            if str(slot_id) in resolved_set
        ]
        picked = _choose_highest_initiative_slot(reusable, slots)
        if picked:
            return picked, 're_evasion_reuse'

    return None, None
