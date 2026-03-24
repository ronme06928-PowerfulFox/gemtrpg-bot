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
from manager.battle.battle_ai import ai_select_targets, ai_suggest_skill, list_usable_skill_ids
from manager.dice_roller import roll_dice
from manager.logs import setup_logger
from manager.summons.service import apply_summon_change, process_summon_round_end
from manager.granted_skills.service import process_granted_skill_round_end, apply_grant_skill_change

logger = setup_logger(__name__)


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

    for key in ['rule_data', 'rule_json', 'rule', '迚ｹ險伜・逅・']:
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
        or '蠎・沺-蜷育ｮ・' in merged
        or '蜷育ｮ・' in merged
    ):
        return 'mass_summation'
    if (
        'mass_individual' in merged
        or 'individual' in merged
        or '蠎・沺-蛟句挨' in merged
        or '蛟句挨' in merged
        or '蠎・沺' in merged
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
        'category', 'attribute', 'distance', 'target_scope', 'target', 'target_type', 'targeting', 'mass_type',
        '蛻・｡・', '霍晞屬', '遽・峇', '繧ｫ繝・ざ繝ｪ',
    ]:
        if isinstance(skill_data.get(key), str):
            merged_parts.append(skill_data.get(key))
        if isinstance(rule_data, dict) and isinstance(rule_data.get(key), str):
            merged_parts.append(rule_data.get(key))

    return _infer_mass_type_from_text(' '.join(str(v or '') for v in merged_parts))


def _normalize_target_scope(raw_value, default='enemy'):
    text = str(raw_value or '').strip().lower()
    if text in ['', 'default', 'auto']:
        return str(default or 'enemy')
    if text in ['enemy', 'enemies', 'foe', 'opponent', 'opponents', '謨ｵ', '謨ｵ蟇ｾ']:
        return 'enemy'
    if text in ['ally', 'allies', 'friend', 'friends', '蜻ｳ譁ｹ', '蜻ｳ譁ｹ蜈ｨ菴・']:
        return 'ally'
    if text in ['同陣営', '同陣営対象', '同陣営指定']:
        return 'ally'
    if text in ['any', 'all', 'both', '蜈ｨ菴・', 'all_targets']:
        return 'any'
    return str(default or 'enemy')


def _infer_target_scope_from_skill(skill_id):
    if not skill_id:
        return 'enemy'
    skill_data = all_skill_data.get(skill_id, {})
    if not isinstance(skill_data, dict):
        return 'enemy'
    rule_data = _extract_skill_rule_data(skill_data)
    candidates = [
        skill_data.get('target_scope'),
        skill_data.get('targetScope'),
        skill_data.get('target_team'),
        skill_data.get('targetTeam'),
        rule_data.get('target_scope') if isinstance(rule_data, dict) else None,
        rule_data.get('targetScope') if isinstance(rule_data, dict) else None,
        rule_data.get('target_team') if isinstance(rule_data, dict) else None,
        rule_data.get('targetTeam') if isinstance(rule_data, dict) else None,
    ]
    for raw in candidates:
        if raw not in [None, '']:
            return _normalize_target_scope(raw, default='enemy')

    normalized_tags = set(_extract_skill_tags(skill_id))
    if any(tag in normalized_tags for tag in ['any_target', 'target_any', '莉ｻ諢丞ｯｾ雎｡', '蟇ｾ雎｡閾ｪ逕ｱ']):
        return 'any'
    if any(tag in normalized_tags for tag in ['ally_target', 'target_ally', '蜻ｳ譁ｹ蟇ｾ雎｡', '蜻ｳ譁ｹ謖・ｮ・']):
        return 'ally'
    if any(tag in normalized_tags for tag in ['同陣営対象', '同陣営指定']):
        return 'ally'
    if any(tag in normalized_tags for tag in ['enemy_target', 'target_enemy', '謨ｵ蟇ｾ雎｡']):
        return 'enemy'
    return 'enemy'


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
        'instant': ('instant' in tags or '蜊ｳ譎・' in tags_text or '蜊ｳ譎ら匱蜍・' in tags_text),
        'mass_type': mass_type,
        'no_redirect': ('no_redirect' in tags or '蟇ｾ雎｡螟画峩荳榊庄' in tags_text),
    })


def _resolve_skill_display_name(skill_id):
    if not skill_id:
        return None
    skill_data = all_skill_data.get(skill_id, {})
    if not isinstance(skill_data, dict):
        return str(skill_id)
    return (
        skill_data.get('name')
        or skill_data.get('繝・ヵ繧ｩ繝ｫ繝亥錐遘ｰ')
        or skill_data.get('skill_name')
        or str(skill_id)
    )


def _is_random_usable_skill_token(skill_id):
    raw = str(skill_id or '').strip()
    if not raw:
        return False
    if raw == BEHAVIOR_RANDOM_USABLE_SKILL_TOKEN:
        return True
    return raw.lower() in BEHAVIOR_RANDOM_USABLE_SKILL_ALIASES


def _resolve_behavior_chart_skill_id(actor, planned_skill_id):
    raw = str(planned_skill_id or '').strip()
    if not raw:
        return None
    if _is_random_usable_skill_token(raw):
        usable_ids = list_usable_skill_ids(actor, allow_instant=False)
        if not usable_ids:
            return None
        return random.choice(usable_ids)
    if raw in all_skill_data:
        return raw
    return None


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
            lines.append(f"{from_label} -> {target_label} / 使用スキル: [{skill_id}] {skill_name}")
        else:
            lines.append(f"{from_label} -> {target_label}")

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

    actionable_slots_by_team = {'ally': [], 'enemy': []}
    ally_target_slots = []
    enemy_slots = []
    for slot_id, slot in slots.items():
        if not _slot_is_actionable(slot):
            continue
        team = _slot_team(slot)
        if team in actionable_slots_by_team:
            actionable_slots_by_team[team].append(str(slot_id))
        if team == 'ally':
            ally_target_slots.append(str(slot_id))
        elif team == 'enemy':
            actor = char_by_id.get(slot.get('actor_id'), {})
            flags = actor.get('flags', {}) if isinstance(actor.get('flags'), dict) else {}
            if flags.get('auto_target_select', True):
                enemy_slots.append(str(slot_id))

    if not enemy_slots:
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

    def _sort_target_slots(slot_ids, fastest=True):
        ids = []
        for sid in slot_ids or []:
            slot = slots.get(sid, {}) if isinstance(slots, dict) else {}
            if _slot_is_actionable(slot):
                ids.append(str(sid))
        ids.sort(
            key=lambda sid: (
                int((slots.get(sid, {}) or {}).get('initiative', 0) or 0),
                int((slots.get(sid, {}) or {}).get('index_in_actor', 0) or 0),
                str(sid),
            ),
            reverse=bool(fastest),
        )
        return ids

    def _pick_target_slot_by_policy(policy, attacker_slot_id, attacker_team):
        policy_text = str(policy or BEHAVIOR_TARGET_POLICY_DEFAULT).strip().lower() or BEHAVIOR_TARGET_POLICY_DEFAULT
        if attacker_team == 'ally':
            enemy_team = 'enemy'
        elif attacker_team == 'enemy':
            enemy_team = 'ally'
        else:
            enemy_team = None

        enemy_candidates = list(actionable_slots_by_team.get(enemy_team, [])) if enemy_team else []
        ally_candidates = list(actionable_slots_by_team.get(attacker_team, [])) if attacker_team else []
        ally_non_self = [sid for sid in ally_candidates if sid != attacker_slot_id]

        if policy_text == 'target_self':
            if attacker_slot_id in ally_candidates:
                return attacker_slot_id
            return None
        if policy_text == 'target_enemy_fastest':
            sorted_ids = _sort_target_slots(enemy_candidates, fastest=True)
            return sorted_ids[0] if sorted_ids else None
        if policy_text == 'target_enemy_slowest':
            sorted_ids = _sort_target_slots(enemy_candidates, fastest=False)
            return sorted_ids[0] if sorted_ids else None
        if policy_text == 'target_ally_fastest':
            sorted_ids = _sort_target_slots(ally_non_self or ally_candidates, fastest=True)
            return sorted_ids[0] if sorted_ids else None
        if policy_text == 'target_ally_slowest':
            sorted_ids = _sort_target_slots(ally_non_self or ally_candidates, fastest=False)
            return sorted_ids[0] if sorted_ids else None
        if policy_text == 'target_ally_random':
            pool = [sid for sid in (ally_non_self or ally_candidates) if sid]
            return random.choice(pool) if pool else None

        # default: target_enemy_random
        pool = [sid for sid in enemy_candidates if sid]
        if pool:
            return random.choice(pool)
        fallback = [sid for sid in ally_candidates if sid and sid != attacker_slot_id]
        if fallback:
            return random.choice(fallback)
        return attacker_slot_id if attacker_slot_id in ally_candidates else None

    def _is_target_scope_allowed(attacker_team, target_team, target_scope):
        scope = _normalize_target_scope(target_scope, default='enemy')
        if scope == 'any':
            return True
        if scope == 'ally':
            return attacker_team == target_team
        return attacker_team != target_team

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
        planned_action_plans = [{
            'skill_id': None,
            'target_policy': BEHAVIOR_TARGET_POLICY_DEFAULT,
        } for _ in actor_slot_ids]
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
            planned_action_plans = choose_action_plans_for_slot_count(
                picked.get('plans', []),
                len(actor_slot_ids),
            )

        committed_skill_ids = []
        for idx, enemy_slot_id in enumerate(actor_slot_ids):
            slot = slots.get(enemy_slot_id, {}) if isinstance(slots, dict) else {}
            attacker_team = _slot_team(slot)
            planned = planned_action_plans[idx] if idx < len(planned_action_plans) else {}
            suggested_skill_id = _resolve_behavior_chart_skill_id(actor, (planned or {}).get('skill_id'))
            if (not suggested_skill_id) and auto_skill_select:
                suggested_skill_id = ai_suggest_skill(actor)

            target_policy = str((planned or {}).get('target_policy') or BEHAVIOR_TARGET_POLICY_DEFAULT).strip().lower()
            target_scope = _infer_target_scope_from_skill(suggested_skill_id)
            target_slot_id = _pick_target_slot_by_policy(target_policy, enemy_slot_id, attacker_team)
            target_slot = slots.get(target_slot_id, {}) if isinstance(slots, dict) else {}
            target_team = _slot_team(target_slot) if target_slot_id else None
            if (not target_slot_id) or (target_team and not _is_target_scope_allowed(attacker_team, target_team, target_scope)):
                fallback_pool = []
                for sid in actionable_slots_by_team.get('ally', []) + actionable_slots_by_team.get('enemy', []):
                    if sid == enemy_slot_id:
                        continue
                    slot_obj = slots.get(sid, {}) if isinstance(slots, dict) else {}
                    slot_team = _slot_team(slot_obj)
                    if not slot_team:
                        continue
                    if _is_target_scope_allowed(attacker_team, slot_team, target_scope):
                        fallback_pool.append(sid)
                if fallback_pool:
                    target_slot_id = random.choice(fallback_pool)
                    target_slot = slots.get(target_slot_id, {}) if isinstance(slots, dict) else {}
                else:
                    target_slot_id = None
                    target_slot = {}
            target_actor_id = target_slot.get('actor_id')

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
                target_label = '蜻ｳ譁ｹ蜈ｨ菴・'
            else:
                target_label = _format_slot_actor_label(target_slot, char_by_id.get(target_actor_id, {})) if target_slot_id else '蟇ｾ雎｡縺ｪ縺・'
            preview_rows.append({
                'from_label': from_label,
                'target_label': target_label,
                'skill_id': suggested_skill_id,
            })

        if use_behavior_chart:
            runtime_entry['last_skill_ids'] = committed_skill_ids
            runtime_entry['last_round'] = round_value
            runtime_entry = advance_step_pointer(
                behavior_profile,
                runtime_entry,
                step_transition=picked.get('step_transition') if isinstance(picked, dict) else None,
            )
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
        emit('new_log', {"message": "Round end has already been processed.", "type": "error"})
        return

    broadcast_log(room, f"--- {username} が Round {state.get('round', 0)} の終了処理を実行しました ---", 'info')
    characters_to_process = state.get('characters', [])

    # 蜈ｨ蜩｡陦悟虚貂医∩縺九メ繧ｧ繝・け
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
        return

    # 1. END_ROUND Effects
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
                apply_buff(c, name, value["lasting"], value["delay"], data=value.get("data"))
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

        # 1c. Bleed (round-end bleed processing, shared with bleed overflow logic)
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
                broadcast_log(room, f"[出血遷延] {char.get('name', '???')} consumed 1 stack (remaining {remaining})", "state-change")

        # 1d. Thorns
        thorns_value = get_status_value(char, "荊棘")
        if thorns_value > 0:
            _update_char_stat(room, char, "荊棘", thorns_value - 1, username="[荊棘減少]")

        # 2. Buff Timers
        if "special_buffs" in char:
            active_buffs = []
            buffs_to_remove = []

            for buff in char['special_buffs']:
                buff_name = buff.get("name")
                delay = buff.get("delay", 0)
                lasting = buff.get("lasting", 0)

                # Bu-08: round-based timer handling.
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
                        broadcast_log(room, f"[{buff_name}]が[{char['name']}]から消失した。", "state-change")
                        buffs_to_remove.append(buff_name)
                        if buff_name in ("混乱", "混乱(戦慄殺到)"):
                            _update_char_stat(room, char, 'MP', int(char.get('maxMp', 0)), username="[混乱解除]")
                            broadcast_log(room, f"{char['name']} は意識を取り戻した (MP全回復)", 'state-change')
                elif buff.get('is_permanent', False):
                    active_buffs.append(buff)

            char['special_buffs'] = active_buffs
            apply_origin_bonus_buffs(char)

        # Reset limits
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
            'states': True, # 出血遲・
            'bad_states': True, # 迥ｶ諷狗焚蟶ｸ (鮗ｻ逞ｺ縺ｪ縺ｩ)
            'buffs': True,
            'timeline': True # Force timeline reset for status mode too based on user request
        }

    log_msg = f"\n--- {username} が戦闘をリセットしました (Mode: {mode}) ---\n"
    # log_msg += f"Opt: {json.dumps(reset_options, ensure_ascii=False)}"
    broadcast_log(room, log_msg, 'round')

    # 笘・霑ｽ蜉: 遏｢蜊ｰ縺ｯ蟶ｸ縺ｫ繝ｪ繧ｻ繝・ヨ
    state['ai_target_arrows'] = []

    if mode == 'full':
        state['characters'] = []
        state['timeline'] = []
        state['round'] = 0
        state['is_round_ended'] = False
        state['turn_char_id'] = None
        state['turn_entry_id'] = None
    elif mode == 'status':
        # 繝ｩ繧ｦ繝ｳ繝画焚縺ｯ繝ｪ繧ｻ繝・ヨ縺励↑縺・ｦ∵悍繧ゅ≠繧九°繧ゅ＠繧後↑縺・′縲∽ｸ譌ｦ繝・ヵ繧ｩ繝ｫ繝医・0縺ｫ謌ｻ縺・        # (Status only reset usually implies starting over but keeping chars)
        state['round'] = 0
        state['is_round_ended'] = False
        state['ai_target_arrows'] = [] # Reset AI arrows

        # Status reset always clears timeline.
        state['timeline'] = []

        removed_summon_count = _remove_summoned_characters(state)
        if removed_summon_count > 0:
            broadcast_log(room, f"[Reset] Removed {removed_summon_count} summoned characters.", "info")

        for char in state.get('characters', []):
            initial = char.get('initial_state', {})

            # 笘・菫ｮ豁｣: 譛ｪ驟咲ｽｮ(x<0)縺九▽逕溷ｭ・hp>0)縺ｮ蝣ｴ蜷医・繝ｪ繧ｻ繝・ヨ蟇ｾ雎｡螟・
            # (謌ｦ髣倅ｸ崎・繧ｭ繝｣繝ｩ縺ｯ譛ｪ驟咲ｽｮ縺ｧ繧ゅΜ繧ｻ繝・ヨ縺励※蠕ｩ蟶ｰ縺輔○繧・
            is_unplaced = char.get('x', -1) < 0
            is_dead = char.get('hp', 0) <= 0

            if is_unplaced and not is_dead:
                # 繝ｪ繧ｻ繝・ヨ縺励↑縺・
                continue

            # --- HP ---
            if reset_options.get('hp'):
                max_hp = int(initial.get('maxHp', char.get('maxHp', 0)))
                # 蛻晄悄蛟､縺後≠繧後・縺昴ｌ縲√↑縺代ｌ縺ｰ迴ｾ蝨ｨ縺ｮMax
                char['maxHp'] = max_hp
                char['hp'] = max_hp

            # --- MP ---
            if reset_options.get('mp'):
                max_mp = int(initial.get('maxMp', char.get('maxMp', 0)))
                char['maxMp'] = max_mp
                char['mp'] = max_mp

                # --- FP & Stackable States (出血, 亀裂 etc) ---
            if reset_options.get('fp') or reset_options.get('states'):
                # 縺薙ｌ繧峨・ 'states' 驟榊・縺ｫ蜈･縺｣縺ｦ縺・ｋ
                # FP縺ｯ迢ｬ遶九＠縺ｦ邂｡逅・＆繧後ｋ縺薙→繧ょ､壹＞縺後√％縺薙〒縺ｯ states 繝ｪ繧ｹ繝亥・縺ｮ繧ゅ・縺ｧ蛻､譁ｭ

                # 縺ｾ縺壽里蟄倥・ states 繧堤ｶｭ謖√＠縺､縺､縲∝ｯｾ雎｡縺ｮ繧ゅ・縺縺代Μ繧ｻ繝・ヨ
                # 縺溘□縺励∵ｧ矩荳・states 縺ｯ繝ｪ繧ｹ繝医↑縺ｮ縺ｧ縲∝・驛ｨ菴懊ｊ逶ｴ縺励◆縺ｻ縺・′螳牙・

                new_states = []
                # 繝・ヵ繧ｩ繝ｫ繝医・繧ｹ繝・・繧ｿ繧ｹ螳夂ｾｩ
                default_states = {
                    "FP": 0,
                    "出血": 0,
                    "亀裂": 0,
                    "破裂": 0,
                    "戦慄": 0,
                    "荊棘": 0,
                }

                # 譌｢蟄倥・迥ｶ諷九ｒ蜿門ｾ・
                current_states = {s['name']: s['value'] for s in char.get('states', [])}

                for s_name, def_val in default_states.items():
                    # FP
                    if s_name == 'FP':
                        if reset_options.get('fp'):
                            # 蛻晄悄FP縺ｯ 0 縺ｧ縺ｯ縺ｪ縺・process_battle_start 縺ｧ蜈･繧九°繧ゅ＠繧後↑縺・′縲・
                            # 繝吶・繧ｹ縺ｨ縺励※縺ｯ 0 (縺ｾ縺溘・ maxFp?)
                            # 螳溯｣・〒縺ｯ FP = maxFp (蛻晄悄蛟､) 縺ｨ縺励※縺・ｋ邂・園縺瑚ｦ句ｽ薙◆繧・
                            # 縺薙％縺ｧ縺ｯ 0 縺ｫ縺励※縺九ｉ process_battle_start 縺ｫ莉ｻ縺帙ｋ縺九［axFp縺ｫ縺吶ｋ縺・
                            # 譌｢蟄倥Ο繧ｸ繝・け: char['FP'] = char.get('maxFp', 0)
                            char['FP'] = char.get('maxFp', 0)
                            new_states.append({"name": "FP", "value": 0}) # 陦ｨ遉ｺ逕ｨ?
                        else:
                            # 邯ｭ謖・
                            val = current_states.get(s_name, def_val)
                            new_states.append({"name": s_name, "value": val})

                    # 莉悶・闢・ｩ榊､
                    else:
                        if reset_options.get('states'):
                            new_states.append({"name": s_name, "value": 0})
                        else:
                            val = current_states.get(s_name, def_val)
                            new_states.append({"name": s_name, "value": val})

                char['states'] = new_states

            # --- Status Effects (鮗ｻ逞ｺ, 豈・etc - char['迥ｶ諷狗焚蟶ｸ'] list) ---
            if reset_options.get('bad_states'):
                char['迥ｶ諷狗焚蟶ｸ'] = []

            # --- Buffs ---
            if reset_options.get('buffs'):
                # 蛻晄悄繝舌ヵ・医ヱ繝・す繝也罰譚･繧・く繝｣繝ｩ菴懈・譎ゅヰ繝包ｼ峨・ initial_state 縺ｫ縺ゅｋ
                # initial_state 縺ｮ special_buffs 繧貞ｾｩ蜈・
                raw_initial_buffs = initial.get('special_buffs', [])
                char['special_buffs'] = [dict(b) for b in raw_initial_buffs]

            # --- Common Reset (Always) ---
            # 縺薙ｌ繧峨・縲梧姶髣倡憾諷九阪↑縺ｮ縺ｧ繝ｪ繧ｻ繝・ヨ蠢・・
            if 'round_item_usage' in char: char['round_item_usage'] = {}
            if 'used_immediate_skills_this_round' in char: char['used_immediate_skills_this_round'] = []
            if 'used_gem_protect_this_battle' in char: char['used_gem_protect_this_battle'] = False
            if 'used_skills_this_round' in char: char['used_skills_this_round'] = []

            char['hasActed'] = False
            char['speedRoll'] = 0
            char['isWideUser'] = False

            # 笘・霑ｽ蜉: 謌ｦ髣倬幕蟋区凾蜉ｹ譫懊・蜀埼←逕ｨ (FP繝ｪ繧ｻ繝・ヨ縺ｪ縺ｩ縺梧怏蜉ｹ縺ｪ蝣ｴ蜷医・縺ｿ)
            # 繝ｪ繧ｻ繝・ヨ繧ｪ繝励す繝ｧ繝ｳ縺ｫ縺九°繧上ｉ縺壹∵姶髣倬幕蟋区凾蜃ｦ逅・・襍ｰ繧峨○繧九∋縺阪°・・
            # 萓九∴縺ｰ縲熊P繝ｪ繧ｻ繝・ヨ縲阪ｒ驕ｸ繧薙□蝣ｴ蜷医・縺ｿ縲∝・譛檳P莉倅ｸ弱↑縺ｩ縺ｮ蜃ｦ逅・ｒ蜀榊ｺｦ驕ｩ逕ｨ縺励◆縺・・
            # 縺励°縺・process_battle_start 縺ｯ蜑ｯ菴懃畑縺後≠繧九°繧ゅ＠繧後↑縺・・
            # 縺薙％縺ｧ縺ｯ繧ｷ繝ｳ繝励Ν縺ｫ縲√粂P/MP/FP縺ｮ縺・★繧後°縺後Μ繧ｻ繝・ヨ縺輔ｌ縺溷ｴ蜷医阪・蜀埼←逕ｨ縺吶ｋ縲√→縺吶ｋ
            if reset_options.get('hp') or reset_options.get('mp') or reset_options.get('fp'):
                 try:
                     process_battle_start(room, char)
                 except Exception as e:
                     logger.error(f"process_battle_start in reset failed: {e}")

            # 笘・霑ｽ蜉: 蜃ｺ霄ｫ蝗ｽ繝懊・繝翫せ繝舌ヵ繧貞・驕ｩ逕ｨ (繝舌ヵ繝ｪ繧ｻ繝・ヨ譎ゅ・縺ｿ)
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
        emit('new_log', {"message": "There is no active match to force-end.", "type": "error"})
        return

    # 繝ｪ繧ｻ繝・ヨ蜃ｦ逅・
    state['active_match'] = None
    state['pending_wide_ids'] = []  # 蠎・沺繝槭ャ繝√・莠育ｴ・ｂ繧ｯ繝ｪ繧｢

    save_specific_room_state(room)
    broadcast_state_update(room)

    # 繝｢繝ｼ繝繝ｫ髢峨§繧九う繝吶Φ繝医ｒ騾∽ｿ｡ (蠎・沺逕ｨ縺ｨDuel逕ｨ)
    _safe_emit('match_modal_closed', {}, to=room)
    _safe_emit('force_close_wide_modal', {}, to=room) # 蠢・ｦ√〒縺ゅｌ縺ｰ繧ｯ繝ｩ繧､繧｢繝ｳ繝亥・縺ｧ蜿励￠繧・

    broadcast_log(room, f"[Force End] GM {username} force-ended the current match.", "match-end")

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
                         if (buff.get('name') in ['謖醍匱荳ｭ', '謖醍匱'] or buff.get('buff_id') in ['Bu-Provoke', 'Bu-01']) and buff.get('delay', 0) == 0:
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

    # 笘・讓ｩ髯舌メ繧ｧ繝・け: GM 縺ｾ縺溘・ 縺昴・繧ｭ繝｣繝ｩ繧ｯ繧ｿ繝ｼ縺ｮ謇譛芽・・縺ｿ險ｱ蜿ｯ
    target_char_id = None
    if side == 'attacker':
        target_char_id = active_match.get('attacker_id')
    elif side == 'defender':
        target_char_id = active_match.get('defender_id')

    # 謇譛芽・｢ｺ隱・
    allowed = False
    if attribute == 'GM':
        allowed = True
    elif target_char_id:
        owners = state.get('character_owners', {})
        if owners.get(target_char_id) == username:
            allowed = True

    if not allowed:
        # 讓ｩ髯舌′縺ｪ縺・ｴ蜷医・辟｡隕厄ｼ医Ο繧ｰ縺ｫ蜃ｺ縺励※繧り憶縺・′縲・ｻ郢√↑蜷梧悄縺ｪ縺ｮ縺ｧ繧ｵ繧､繝ｬ繝ｳ繝医↓辟｡隕悶☆繧九°縲√ョ繝舌ャ繧ｰ繝ｭ繧ｰ縺ｮ縺ｿ・・
        logger.warning(f"Unauthorized sync attempt by {username} for side {side} (CharID: {target_char_id})")
        return

    if side == 'attacker':
        state['active_match']['attacker_data'] = data
    elif side == 'defender':
        state['active_match']['defender_data'] = data

    save_specific_room_state(room)
    _safe_emit('match_data_updated', {'side': side, 'data': data}, to=room)

def process_round_start(room, username):
    logger.debug(f"process_round_start called for room: {room} by {username}")
    state = get_room_state(room)
    if not state:
        logger.debug(f"Room state not found for {room}")
        return
    clear_newly_applied_flags(state)
    clear_round_limited_flags(state)

    # Check previous round end flag
    if state.get('round', 0) > 0 and not state.get('is_round_ended', False):
        emit('new_log', {'message': '前ラウンドの終了処理が未完了です。先にラウンド終了を実行してください。', 'type': 'error'}, room=room)
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
            speed_val = int(get_status_value(char, "速度"))
        except Exception:
            speed_val = 0
        if speed_val <= 0:
            try:
                speed_val = int(get_status_value(char, '速度'))
            except Exception:
                speed_val = 0

        # 笘・蜉騾溘・貂幃溘↓繧医ｋ速度陬懈ｭ｣
        from plugins.buffs.speed_mod import SpeedModBuff
        speed_modifier = SpeedModBuff.get_speed_modifier(char)

        initiative = (speed_val // 6) + speed_modifier

        if speed_modifier != 0:
            mod_text = f"+{speed_modifier}" if speed_modifier > 0 else str(speed_modifier)
            broadcast_log(room, f"{char['name']} の速度補正: {mod_text} (基礎速度に加算)", 'info')

        # 速度繝ｭ繝ｼ繝ｫ蠕後↓蜉騾溘・貂幃溘ｒ繧ｯ繝ｪ繧｢
        SpeedModBuff.clear_speed_modifiers(char)

        # 陦悟虚蝗樊焚繧貞叙蠕・(繝・ヵ繧ｩ繝ｫ繝・)
        try:
             action_count = int(get_status_value(char, "行動回数"))
        except Exception:
             action_count = 0
        if action_count <= 0:
            try:
                action_count = int(get_status_value(char, '陦悟虚蝗樊焚'))
            except Exception:
                action_count = 1
        action_count = max(1, action_count)

        logger.debug(f"[SPEED ROLL] {char['name']}: speed={speed_val} (init={initiative}), count={action_count}")

        for i in range(action_count):
            roll = random.randint(1, 6)
            total_speed = initiative + roll

            # 笘・霑ｽ蜉: 速度値縺ｮ荳矩剞縺ｯ1
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

            # 繝ｦ繝ｼ繧ｶ繝ｼ隕∵悍: 1d6(X)+Y 縺ｮ蠖｢蠑上〒蜀・ｨｳ陦ｨ遉ｺ
            breakdown = f"1d6({roll}){sign}{stat} = {total}"

            log_msg += f"{idx+1}. {char['name']} ({breakdown})<br>"

    broadcast_log(room, log_msg, 'info')

    # 笘・霑ｽ蜉: 繝ｩ繝・ぅ繧ｦ繝 (ID: 3) 繝ｩ繧ｦ繝ｳ繝蛾幕蟋区凾荳諡ｬ蜃ｦ逅・
    # 蜈ｨ蜩｡縺ｮFP繧・1縺吶ｋ
    latium_targets = []
    for char in state.get('characters', []):
        if char.get('hp', 0) <= 0: continue
        if get_effective_origin_id(char) == 3:
            current_fp = get_status_value(char, 'FP')
            _update_char_stat(room, char, 'FP', current_fp + 1, username="[ラティウム恩恵]")
            latium_targets.append(char['name'])

    if latium_targets:
        broadcast_log(room, f"[Round Bonus] FP +1 applied to: {', '.join(latium_targets)}", "info")


    # 笘・霑ｽ蜉: PvE繝｢繝ｼ繝峨↑繧峨ち繝ｼ繧ｲ繝・ヨ謚ｽ驕ｸ -> 蠎・沺莠育ｴ・｢ｺ螳壼ｾ後↓荳譛ｬ蛹・
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
        _safe_emit('open_wide_declaration_modal', {}, to=room)

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
        broadcast_log(room, f"広域宣言を適用: {', '.join(names)}", 'info')
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
        broadcast_log(room, "No pending wide match entries.", "info")

    save_specific_room_state(room)
    broadcast_state_update(room)

    # 迥ｶ諷倶ｿ晏ｭ伜ｾ後↓蟆代＠蠕・ｩ溘＠縺ｦ縺九ｉ繧ｿ繝ｼ繝ｳ騾ｲ陦鯉ｼ亥ｿｵ縺ｮ縺溘ａ・・
    # proceed_next_turn(room)

    # 笘・ｿｮ豁｣: Latium (ID: 3) 縺ｪ縺ｩ縺ｮ繧ｿ繝ｼ繝ｳ髢句ｧ区凾蜉ｹ譫懊ｒ遒ｺ螳溘↓縺吶ｋ縺溘ａ
    # proceed_next_turn 繧貞他縺ｳ蜃ｺ縺励√◎縺ｮ邨先棡繧堤｢ｺ隱阪☆繧・
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
        _safe_emit('close_wide_declaration_modal', {}, to=room)

        broadcast_log(room, "GM requested wide declaration processing.", "info")
        return

    # 2. Normal Player Confirm
    if user_id not in state['wide_modal_confirms']:
        state['wide_modal_confirms'].append(user_id)
        broadcast_log(room, f"{user_id} confirmed wide declaration.", "info")

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
        _safe_emit('close_wide_declaration_modal', {}, to=room)
    else:
        # Wait
        logger.info(f"Player {user_id} confirmed. Waiting... ({len(confirmed_users)}/{len(non_gm_users)})")
        save_specific_room_state(room)



def update_battle_background_logic(room, image_url, scale, offset_x, offset_y, username, attribute):
    """
    謌ｦ髣倡判髱｢縺ｮ閭梧勹逕ｻ蜒上ｒ譖ｴ譁ｰ縺吶ｋ繝ｭ繧ｸ繝・け
    """
    if attribute != 'GM':
        emit('new_log', {'message': '背景設定はGMのみ変更できます。', 'type': 'error'})
        return

    state = get_room_state(room)
    if not state: return

    # 繝・・繧ｿ讒矩縺ｮ蛻晄悄蛹・
    if 'battle_map_data' not in state:
        state['battle_map_data'] = {}

    # 蛟､縺ｮ譖ｴ譁ｰ
    state['battle_map_data']['background_image'] = image_url
    if scale is not None:
        state['battle_map_data']['background_scale'] = scale
    if offset_x is not None:
        state['battle_map_data']['background_offset_x'] = offset_x
    if offset_y is not None:
        state['battle_map_data']['background_offset_y'] = offset_y

    broadcast_state_update(room)
    broadcast_log(room, "Battle map background updated.", "system")

# 笘・霑ｽ蜉: PvE繝｢繝ｼ繝牙・譖ｿ繝ｭ繧ｸ繝・け
def process_switch_battle_mode(room, mode, username):
    state = get_room_state(room)
    if not state: return

    old_mode = state.get('battle_mode', 'pvp')
    if old_mode == mode:
        return

    state['battle_mode'] = mode
    broadcast_log(room, f"戦闘モードを変更しました: {old_mode.upper()} -> {mode.upper()}", 'system')

    # PvE縺ｫ縺ｪ縺｣縺溘ｉ繧ｿ繝ｼ繧ｲ繝・ヨ蜀肴歓驕ｸ -> 繝ｦ繝ｼ繧ｶ繝ｼ隕∵悍縺ｫ繧医ｊ蟒・ｭ｢ (繝ｩ繧ｦ繝ｳ繝蛾幕蟋区凾縺ｮ縺ｿ)
    # if mode == 'pve':
    #     from manager.battle.battle_ai import ai_select_targets
    #     ai_select_targets(state)
    #     broadcast_log(room, "AI縺後ち繝ｼ繧ｲ繝・ヨ繧帝∈螳壹＠縺ｾ縺励◆縲・, 'info', secret=True)

    save_specific_room_state(room)
    broadcast_state_update(room)

# 笘・霑ｽ蜉: AI繧ｹ繧ｭ繝ｫ謠先｡・PI (Socket邨檎罰縺ｧ蜻ｼ縺ｰ繧後ｋ諠ｳ螳壹□縺後〉outes縺ｧ螳溯｣・＠縺ｦ繧ゅ＞縺・ゅ％縺薙〒縺ｯ繝ｭ繧ｸ繝・け縺ｮ縺ｿ)
def process_ai_suggest_skill(room, char_id):
    # 縺薙ｌ縺ｯ謌ｻ繧雁､繧定ｿ斐☆繧ｿ繧､繝励↑縺ｮ縺ｧ縲ヾocket縺ｮ繧ｳ繝ｼ繝ｫ繝舌ャ繧ｯ縺ｧ霑斐☆縺ｮ縺御ｸ闊ｬ逧・
    # common_manager縺ｫ縺翫￥蠢・ｦ∵ｧ縺ｯ阮・＞縺九ｂ縺励ｌ縺ｪ縺・′縲∽ｸ蠢・
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

    try:
        phase_sig = battle_state.get('phase')
        slots_sig = len(battle_state.get('slots', {}))
        intents_sig = len(battle_state.get('intents', {}))
        sig = (phase_sig, slots_sig, intents_sig)
        now = time.time()
        last_sig = getattr(ensure_battle_state_vNext, '_last_ensure_sig', None)
        last_ts = float(getattr(ensure_battle_state_vNext, '_last_ensure_ts', 0.0) or 0.0)
        if sig != last_sig or (now - last_ts) >= 5.0:
            logger.debug(
                "[battle_state.ensure] phase=%s slots=%s intents=%s",
                phase_sig,
                slots_sig,
                intents_sig
            )
            setattr(ensure_battle_state_vNext, '_last_ensure_sig', sig)
            setattr(ensure_battle_state_vNext, '_last_ensure_ts', now)
    except Exception:
        logger.debug("[battle_state.ensure] phase=%s", battle_state.get('phase'))
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
    clear_round_limited_flags(state)

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
            action_count = int(get_status_value(char, "行動回数"))
        except Exception:
            action_count = 0
        if action_count <= 0:
            try:
                action_count = int(get_status_value(char, '陦悟虚蝗樊焚'))
            except Exception:
                action_count = 1
        action_count = max(1, action_count)

        char['totalSpeed'] = None

        try:
            speed_val = int(get_status_value(char, "速度"))
        except Exception:
            speed_val = 0
        if speed_val <= 0:
            try:
                speed_val = int(get_status_value(char, '速度'))
            except Exception:
                speed_val = 0
        speed_modifier = SpeedModBuff.get_speed_modifier(char)
        base_initiative = (speed_val // 6) + speed_modifier

        if speed_modifier != 0:
            mod_text = f"+{speed_modifier}" if speed_modifier > 0 else str(speed_modifier)
            broadcast_log(room, f"{char.get('name', actor_id)} の速度補正: {mod_text} (基礎速度に加算)", 'info')

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
    category = str(
        skill_data.get('分類')
        or skill_data.get('蛻・｡・')
        or skill_data.get('attribute')
        or ''
    )
    if category in ['回避', '蝗樣∩']:
        return True
    for tag in skill_data.get('tags', []) or []:
        if isinstance(tag, str) and ('回避' in tag or '蝗樣∩' in tag):
            return True
    if '回避' in str(skill_data.get('name') or ''):
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
        slot_data = slots.get(slot_id, {}) if isinstance(slots, dict) else {}
        if isinstance(slot_data, dict) and slot_data.get('cancelled_without_use'):
            continue
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
        slot_data = slots.get(slot_id, {}) if isinstance(slots, dict) else {}
        if isinstance(slot_data, dict) and slot_data.get('cancelled_without_use'):
            continue
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
        and not slots.get(slot_id, {}).get('cancelled_without_use')
    ]
    picked = _choose_highest_initiative_slot(reusable, slots)
    if picked:
        return picked, 'resolved_slot_reuse'

    return None, None


def select_hard_followup_evade_slot(state, battle_state, defender_actor_id, attacker_slot):
    """
    蠑ｷ遑ｬ霑ｽ謦・髄縺代・蝗樣∩蟾ｮ縺苓ｾｼ縺ｿ驕ｸ螳壹・    蜆ｪ蜈磯・ｽ・
      1) 蠑ｷ遑ｬ霑ｽ謦・・繧・target 謖・ｮ壹＠縺ｦ縺・ｋ譛ｪ隗｣豎ｺ蝗樣∩
      2) 譛ｪ隗｣豎ｺ縺ｮ蝗樣∩繧ｹ繝ｭ繝・ヨ
      3) 再回避ロック譎ゅ・縺ｿ縲∬ｧ｣豎ｺ貂医∩蝗樣∩縺ｮ蜀榊茜逕ｨ
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
        slot_data = slots.get(slot_id, {}) if isinstance(slots, dict) else {}
        if isinstance(slot_data, dict) and slot_data.get('cancelled_without_use'):
            return False
        intent = intents.get(slot_id, {}) if isinstance(intents, dict) else {}
        skill_id = intent.get('skill_id')
        if not intent.get('committed', False):
            return False
        return _is_evade_skill(skill_id)

    # 1) 譏守､ｺtarget縺ｮ譛ｪ隗｣豎ｺ蝗樣∩
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

    # 2) 譛ｪ隗｣豎ｺ蝗樣∩
    unresolved_evade = [
        slot_id for slot_id in actor_slot_ids
        if _is_unresolved(slot_id) and _is_committed_evade(slot_id)
    ]
    picked = _choose_highest_initiative_slot(unresolved_evade, slots)
    if picked:
        return picked, 'unresolved_evade'

    # 3) 再回避ロック譎ゅ・縺ｿ隗｣豎ｺ貂医∩蜀榊茜逕ｨ
    if is_dodge_lock_active(state, defender_actor_id):
        reusable = [
            slot_id for slot_id in actor_slot_ids
            if str(slot_id) in resolved_set and not slots.get(slot_id, {}).get('cancelled_without_use')
        ]
        picked = _choose_highest_initiative_slot(reusable, slots)
        if picked:
            return picked, 're_evasion_reuse'

    return None, None




