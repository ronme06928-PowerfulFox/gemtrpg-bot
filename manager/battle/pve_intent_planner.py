import json
import time
import random

from extensions import all_skill_data
from manager.logs import setup_logger
import manager.room_manager as room_manager
from manager.battle.battle_ai import list_usable_skill_ids, ai_suggest_skill
from manager.battle.enemy_behavior import (
    normalize_behavior_profile,
    initialize_behavior_runtime_entry,
    evaluate_transitions,
    pick_step_actions,
    advance_step_pointer,
    choose_action_plans_for_slot_count,
    BEHAVIOR_TARGET_POLICY_DEFAULT,
)


logger = setup_logger(__name__)
broadcast_log = getattr(room_manager, "broadcast_log", lambda *_args, **_kwargs: None)

BEHAVIOR_RANDOM_USABLE_SKILL_TOKEN = "__RANDOM_USABLE__"
BEHAVIOR_RANDOM_USABLE_SKILL_ALIASES = {
    "__random_usable__",
    "random_usable",
    "__random_skill__",
    "random_skill",
    "__random__",
    "random",
}

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
        'category', 'attribute', 'distance', 'target_scope', 'target', 'target_type', 'targeting', 'mass_type',
        '分類', '距離', 'カテゴリ',
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
    if text in ['enemy', 'enemies', 'foe', 'opponent', 'opponents', '敵', '敵対']:
        return 'enemy'
    if text in ['ally', 'allies', 'friend', 'friends', '味方', '味方全体']:
        return 'ally'
    if text in ['同陣営', '同陣営対象', '同陣営指定']:
        return 'ally'
    if text in ['any', 'all', 'both', '全体', 'all_targets']:
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
    if any(tag in normalized_tags for tag in ['any_target', 'target_any', '任意対象', '対象自由']):
        return 'any'
    if any(tag in normalized_tags for tag in ['ally_target', 'target_ally', '味方対象', '味方指定']):
        return 'ally'
    if any(tag in normalized_tags for tag in ['同陣営対象', '同陣営指定']):
        return 'ally'
    if any(tag in normalized_tags for tag in ['enemy_target', 'target_enemy', '敵対象']):
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
                target_label = '味方全体'
            else:
                target_label = _format_slot_actor_label(target_slot, char_by_id.get(target_actor_id, {})) if target_slot_id else '対象なし'
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

