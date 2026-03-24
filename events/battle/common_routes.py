import copy
import json
import time

from flask import request
from flask_socketio import emit, rooms
from extensions import socketio, all_skill_data
from manager.logs import setup_logger
from manager.room_manager import (
    get_user_info_from_sid, get_room_state, broadcast_log, broadcast_state_update,
    is_authorized_for_character,
)
try:
    from manager.room_manager import emit_select_resolve_events
except Exception:
    # Test suites may monkeypatch manager.room_manager with partial stubs.
    # Keep routes importable in that environment.
    def emit_select_resolve_events(*args, **kwargs):
        return None
from manager.battle.core import proceed_next_turn, run_select_resolve_auto
from manager.battle.common_manager import (
    process_full_round_end, reset_battle_logic, force_end_match_logic,
    move_token_logic, open_match_modal_logic, close_match_modal_logic,
    sync_match_data_logic, process_round_start, process_wide_declarations,
    process_wide_modal_confirm, update_battle_background_logic,
    get_or_create_select_resolve_state, build_select_resolve_state_payload,
    process_select_resolve_round_start
)
from plugins.buffs.confusion import ConfusionBuff
from plugins.buffs.immobilize import ImmobilizeBuff


from manager.utils import apply_buff, get_status_value, set_status_value # For debug

logger = setup_logger(__name__)


def _log_battle_recv(event_name, data=None, phase=None):
    data = data or {}
    sid = getattr(request, 'sid', None)
    try:
        sid_rooms = list(rooms(sid)) if sid else []
    except Exception:
        sid_rooms = []
    target = data.get('target') or {}
    logger.debug(
        "[RECV] %s sid=%s sid_rooms=%s room=%s battle=%s slot=%s phase=%s skill=%s target_type=%s target_slot=%s",
        event_name,
        sid,
        sid_rooms,
        data.get('room_id'),
        data.get('battle_id'),
        data.get('slot_id'),
        phase,
        data.get('skill_id'),
        target.get('type'),
        target.get('slot_id')
    )


def _log_battle_emit(event_name, room_id, battle_id, payload):
    payload = payload or {}
    timeline_len = len(payload.get('timeline', []) or [])
    slots_len = len(payload.get('slots', {}) or {})
    intents_len = len(payload.get('intents', {}) or {})
    trace_len = len(payload.get('trace', []) or [])
    phase = payload.get('phase') or payload.get('to') or payload.get('from')
    logger.debug(
        "[EMIT] %s room=%s battle=%s phase=%s timeline=%d slots=%d intents=%d trace=%d",
        event_name, room_id, battle_id, phase, timeline_len, slots_len, intents_len, trace_len
    )


@socketio.on('request_next_turn')
def on_request_next_turn(data):
    room = data.get('room')
    if not room: return
    proceed_next_turn(room)

@socketio.on('request_new_round')
def on_request_new_round(data):
    room = data.get('room')
    if not room: return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    if attribute != 'GM':
        emit('new_log', {'message': 'ラウンド開始はGMのみ実行可能です。', 'type': 'error'})
        return

    process_round_start(room, username)

@socketio.on('request_declare_wide_skill_users')
def on_request_declare_wide_skill_users(data):
    room = data.get('room')
    if not room: return
    wide_user_ids = data.get('wideUserIds', [])

    # Needs process_wide_declarations in common_manager.py
    process_wide_declarations(room, wide_user_ids)

@socketio.on('request_wide_modal_confirm')
def on_request_wide_modal_confirm(data):
    room = data.get('room')
    if not room: return
    wide_ids = data.get('wideUserIds', [])

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    process_wide_modal_confirm(room, username, attribute, wide_ids)




@socketio.on('request_end_round')
def on_request_end_round(data):
    room = data.get('room')
    if not room: return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    if attribute != 'GM':
        print(f"[Security] Player {username} tried to end round. Denied.")
        return

    process_full_round_end(room, username)

@socketio.on('request_reset_battle')
def on_request_reset_battle(data):
    room = data.get('room')
    if not room: return
    mode = data.get('mode', 'full')
    options = data.get('options') # get dictionary or None
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    reset_battle_logic(room, mode, username, options)

@socketio.on('request_force_end_match')
def on_request_force_end_match(data):
    room = data.get('room')
    if not room: return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    if attribute != 'GM':
        return

    force_end_match_logic(room, username)

@socketio.on('request_move_token')
def on_request_move_token(data):
    room = data.get('room')
    char_id = data.get('charId')
    x = data.get('x')
    y = data.get('y')

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    move_token_logic(room, char_id, x, y, username, attribute)

@socketio.on('open_match_modal')
def on_open_match_modal(data):
    room = data.get('room')
    if not room: return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    open_match_modal_logic(room, data, username)

@socketio.on('close_match_modal')
def on_close_match_modal(data):
    room = data.get('room')
    if not room: return
    close_match_modal_logic(room)

@socketio.on('sync_match_data')
def on_sync_match_data(data):
    room = data.get('room')
    if not room: return
    side = data.get('side')
    match_data = data.get('data')
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")
    sync_match_data_logic(room, side, match_data, username, attribute)

@socketio.on('debug_apply_buff')
def on_debug_apply_buff(data):
    room = data.get('room')
    target_id = data.get('target_id')
    buff_id = data.get('buff_id')
    duration = int(data.get('duration', 2))
    delay = int(data.get('delay', 0))

    if not room or not target_id or not buff_id: return

    state = get_room_state(room)
    if not state: return

    char = next((c for c in state['characters'] if c['id'] == target_id), None)
    if not char: return

    buff_name = data.get('buff_name')
    if not buff_name:
        buff_name_map = {
            'Bu-02': '混乱',
            'Bu-03': '混乱(戦慄殺到)',
            'Bu-05': '再回避ロック',
            'Bu-06': '破裂威力減少無効'
        }
        buff_name = buff_name_map.get(buff_id, buff_id)

    apply_buff(char, buff_name, duration, delay, data={'buff_id': buff_id})
    broadcast_state_update(room)
    broadcast_log(room, f"[DEBUG] {char['name']} に {buff_name}({buff_id}) を付与しました。", 'system')

@socketio.on('request_update_battle_background')
def on_request_update_battle_background(data):
    room = data.get('room')
    image_url = data.get('imageUrl')
    scale = data.get('scale')
    offset_x = data.get('offsetX')
    offset_y = data.get('offsetY')

    if not room: return

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    update_battle_background_logic(room, image_url, scale, offset_x, offset_y, username, attribute)

# NOTE: PvE / PvP モード切り替え
@socketio.on('request_switch_battle_mode')
def on_request_switch_battle_mode(data):
    room = data.get('room')
    mode = data.get('mode') # 'pvp' or 'pve'

    if not room or not mode: return

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    if attribute != 'GM':
        return # GM only

    from manager.battle.common_manager import process_switch_battle_mode
    process_switch_battle_mode(room, mode, username)

# NOTE: AIスキル提案
@socketio.on('request_ai_suggest_skill')
def on_request_ai_suggest_skill(data):
    room = data.get('room')
    char_id = data.get('charId')

    if not room or not char_id: return

    # 誰でも要求可能（最終採用はGM判断）

    from manager.battle.common_manager import process_ai_suggest_skill
    suggested_skill_id = process_ai_suggest_skill(room, char_id)

    emit('ai_skill_suggested', {
        'charId': char_id,
        'skillId': suggested_skill_id
    })


def _default_intent_tags(existing=None):
    tags = dict(existing or {})
    tags.setdefault('instant', False)
    tags.setdefault('mass_type', None)
    tags.setdefault('no_redirect', False)
    return tags


def _default_target(target):
    if isinstance(target, dict):
        target_type = target.get('type', 'none')
        if target_type not in ['single_slot', 'mass_individual', 'mass_summation', 'none']:
            target_type = 'none'
        return {
            'type': target_type,
            'slot_id': target.get('slot_id')
        }
    return {'type': 'none', 'slot_id': None}


def _normalize_target_slot_id(value):
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text if text else None
    return str(value)


def _validate_and_normalize_target(target, state, allow_none=True):
    normalized = _default_target(target)
    target_type = normalized.get('type')
    slot_id = _normalize_target_slot_id(normalized.get('slot_id'))

    if target_type == 'none':
        if not allow_none:
            return None, 'target.type none is not allowed here'
        return {'type': 'none', 'slot_id': None}, None

    if target_type == 'single_slot':
        if not slot_id:
            return None, 'single_slot target requires slot_id'
        if slot_id not in (state.get('slots', {}) or {}):
            return None, 'target.slot_id is unknown'
        return {'type': 'single_slot', 'slot_id': slot_id}, None

    if target_type in ['mass_individual', 'mass_summation']:
        return {'type': target_type, 'slot_id': None}, None

    return None, 'invalid target.type'


def _extract_skill_tags(skill_id):
    if not skill_id:
        return []
    skill_data = all_skill_data.get(skill_id, {})
    tags = list(skill_data.get('tags', []))
    rule_data = _extract_skill_rule_data(skill_data)
    for t in rule_data.get('tags', []) if isinstance(rule_data, dict) else []:
        if t not in tags:
            tags.append(t)
    return tags


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
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue
    for raw in skill_data.values():
        if not isinstance(raw, str):
            continue
        text = raw.strip()
        if not text.startswith('{'):
            continue
        if (
            ('"effects"' not in text)
            and ('"cost"' not in text)
            and ('"tags"' not in text)
            and ('"target_scope"' not in text)
            and ('"target_team"' not in text)
            and ('"deals_damage"' not in text)
        ):
            continue
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    return {}


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
    ):
        return 'mass_individual'

    if '広域' in merged:
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

    merged_parts = []
    merged_parts.extend(_extract_skill_tags(skill_id))
    if isinstance(rule_data, dict):
        rule_tags = rule_data.get('tags', [])
        if isinstance(rule_tags, list):
            merged_parts.extend(rule_tags)

    for key in [
        'category',
        'distance',
        '分類',
        'カテゴリ',
        '距離',
        '射程',
        '範囲',
        'target_scope',
        'target',
        'target_type',
        'targeting',
        'mass_type',
    ]:
        if isinstance(skill_data.get(key), str):
            merged_parts.append(skill_data.get(key))
        if isinstance(rule_data, dict) and isinstance(rule_data.get(key), str):
            merged_parts.append(rule_data.get(key))

    merged = ' '.join(str(v or '').lower() for v in merged_parts)
    return _infer_mass_type_from_text(merged)


def _normalize_target_scope(raw_value, default='enemy'):
    text = str(raw_value or '').strip().lower()
    if text in ['', 'default', 'auto']:
        return str(default or 'enemy')
    if text in ['enemy', 'enemies', 'foe', 'opponent', 'opponents', '敵', '敵対']:
        return 'enemy'
    if text in ['ally', 'allies', 'friend', 'friends', '味方', '味方全体']:
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

    tags = []
    for raw_tag in _extract_skill_tags(skill_id):
        text = str(raw_tag or '').strip()
        if text:
            tags.append(text)
    normalized = {str(v).strip().lower() for v in tags}
    ally_tags = {'ally_target', 'target_ally', '味方対象', '味方指定'}
    any_tags = {'any_target', 'target_any', '任意対象', '対象自由'}
    enemy_tags = {'enemy_target', 'target_enemy', '敵対象'}
    if any(str(t).lower() in normalized for t in any_tags):
        return 'any'
    if any(str(t).lower() in normalized for t in ally_tags):
        return 'ally'
    if any(str(t).lower() in normalized for t in enemy_tags):
        return 'enemy'
    return 'enemy'


def _resolve_slot_team(state, slot_id):
    if not isinstance(state, dict) or not slot_id:
        return None
    slots = state.get('slots', {}) or {}
    slot = slots.get(slot_id, {}) if isinstance(slots, dict) else {}
    team = str(slot.get('team', '') or '').strip().lower()
    if team in ['ally', 'enemy']:
        return team

    actor_id = slot.get('actor_id')
    chars = state.get('characters', []) if isinstance(state.get('characters'), list) else []
    actor = next((c for c in chars if str(c.get('id')) == str(actor_id)), None)
    actor_team = str((actor or {}).get('type', '') or '').strip().lower()
    if actor_team in ['ally', 'enemy']:
        return actor_team
    return None


def _validate_single_target_scope(state, source_slot_id, target_slot_id, target_scope):
    scope = _normalize_target_scope(target_scope, default='enemy')
    if scope == 'any':
        return None
    source_team = _resolve_slot_team(state, source_slot_id)
    target_team = _resolve_slot_team(state, target_slot_id)
    if source_team not in ['ally', 'enemy'] or target_team not in ['ally', 'enemy']:
        return None
    if scope == 'enemy' and source_team == target_team:
        return 'target_scope=enemy のため味方スロットは指定できません'
    if scope == 'ally' and source_team != target_team:
        return 'target_scope=ally のため敵スロットは指定できません'
    return None


def _normalize_target_by_skill(skill_id, target, state=None, source_slot_id=None, allow_none=True):
    normalized = _default_target(target)
    inferred_mass = _infer_mass_type_from_skill(skill_id)
    if inferred_mass in ['mass_individual', 'mass_summation']:
        return {'type': inferred_mass, 'slot_id': None}, None

    if normalized.get('type') in ['mass_individual', 'mass_summation']:
        return None, 'this skill does not support mass target'
    if normalized.get('type') == 'none':
        if allow_none:
            return {'type': 'none', 'slot_id': None}, None
        return None, 'target.type none is not allowed here'
    if normalized.get('type') == 'single_slot':
        slot_id = _normalize_target_slot_id(normalized.get('slot_id'))
        if not slot_id:
            return None, 'single_slot target requires slot_id'
        if state and source_slot_id:
            target_scope = _infer_target_scope_from_skill(skill_id)
            scope_error = _validate_single_target_scope(state, source_slot_id, slot_id, target_scope)
            if scope_error:
                return None, scope_error
        return {'type': 'single_slot', 'slot_id': slot_id}, None
    return None, 'invalid target.type'


def _normalize_target_by_skill_compat(skill_id, target, state=None, source_slot_id=None, allow_none=True):
    """
    Backward-compat for tests/patches that monkeypatch _normalize_target_by_skill
    with older signatures.
    """
    try:
        return _normalize_target_by_skill(
            skill_id,
            target,
            state=state,
            source_slot_id=source_slot_id,
            allow_none=allow_none
        )
    except TypeError as e:
        msg = str(e)
        if 'unexpected keyword argument' in msg:
            try:
                return _normalize_target_by_skill(skill_id, target, allow_none=allow_none)
            except TypeError:
                return _normalize_target_by_skill(skill_id, target)
        raise


def _build_tags(skill_id, target):
    skill_tags = _extract_skill_tags(skill_id)
    target_type = (target or {}).get('type')
    target_scope = _infer_target_scope_from_skill(skill_id)
    inferred_mass = _infer_mass_type_from_skill(skill_id)
    if inferred_mass in ['mass_individual', 'mass_summation']:
        mass_type = inferred_mass
    elif target_type in ['mass_individual', 'mass_summation']:
        mass_type = target_type
    else:
        mass_type = None
    tags_text = ' '.join(str(t or '').lower() for t in skill_tags)
    return {
        'instant': (
            'instant' in skill_tags
            or '即時' in tags_text
            or '即時発動' in tags_text
        ),
        'mass_type': mass_type,
        'no_redirect': (
            'no_redirect' in skill_tags
            or '対象変更不可' in tags_text
            or target_scope == 'ally'
        )
    }

def _extract_skill_cost_entries(skill_data):
    if not isinstance(skill_data, dict):
        return []
    direct = skill_data.get('cost')
    if isinstance(direct, list):
        return direct

    rule_data = _extract_skill_rule_data(skill_data)
    if isinstance(rule_data, dict) and isinstance(rule_data.get('cost'), list):
        return rule_data.get('cost', [])
    return []


def _consume_mass_costs_on_resolve_start(room_id, state, required_slots):
    room_state = get_room_state(room_id) or {}
    chars = room_state.get('characters', []) if isinstance(room_state, dict) else []
    chars_by_id = {
        c.get('id'): c for c in chars
        if isinstance(c, dict) and c.get('id')
    }

    intents = state.get('intents', {}) if isinstance(state, dict) else {}
    slots = state.get('slots', {}) if isinstance(state, dict) else {}
    consumed_rows = []

    for slot_id in sorted(required_slots or []):
        intent = intents.get(slot_id, {})
        if not isinstance(intent, dict):
            continue

        tags = intent.get('tags', {}) or {}
        mass_type = tags.get('mass_type')
        if mass_type not in ['mass_individual', 'mass_summation', 'individual', 'summation']:
            continue
        if not intent.get('committed', False):
            continue
        if intent.get('cost_consumed_at_resolve_start', False):
            continue

        actor_id = (slots.get(slot_id) or {}).get('actor_id')
        actor = chars_by_id.get(actor_id)
        skill_id = intent.get('skill_id')
        skill_data = all_skill_data.get(skill_id, {}) if skill_id else {}
        spent = {'hp': 0, 'mp': 0, 'fp': 0}

        if isinstance(actor, dict):
            for entry in _extract_skill_cost_entries(skill_data):
                if not isinstance(entry, dict):
                    continue
                c_type = str(entry.get('type', '')).strip().upper()
                if not c_type:
                    continue
                try:
                    c_val = int(entry.get('value', 0))
                except (TypeError, ValueError):
                    c_val = 0
                if c_val <= 0:
                    continue

                curr = int(get_status_value(actor, c_type))
                new_val = max(0, curr - c_val)
                consumed = max(0, curr - new_val)
                if consumed <= 0:
                    continue

                if c_type == 'HP':
                    actor['hp'] = new_val
                    spent['hp'] += consumed
                elif c_type == 'MP':
                    actor['mp'] = new_val
                    spent['mp'] += consumed
                elif c_type == 'FP':
                    if 'fp' in actor:
                        actor['fp'] = new_val
                    set_status_value(actor, 'FP', new_val)
                    spent['fp'] += consumed
                else:
                    set_status_value(actor, c_type, new_val)

        intent['cost_consumed_at_resolve_start'] = True
        intents[slot_id] = intent
        if spent['hp'] or spent['mp'] or spent['fp']:
            consumed_rows.append({
                'slot_id': slot_id,
                'actor_id': actor_id,
                'skill_id': skill_id,
                'spent': spent
            })

    return consumed_rows


def _is_select_phase(state):
    return state.get('phase') == 'select'


def _authorize_intent_slot_control(room_id, battle_id, state, slot_id, event_name):
    slots = state.get('slots', {}) if isinstance(state, dict) else {}
    slot = slots.get(slot_id) if isinstance(slots, dict) else None
    if not isinstance(slot, dict):
        logger.warning(
            "[FLOW] %s_denied room=%s battle=%s slot=%s reason=unknown_slot",
            event_name, room_id, battle_id, slot_id
        )
        emit('battle_error', {'message': 'unknown slot_id', 'slot_id': slot_id}, to=request.sid)
        return False

    actor_id = slot.get('actor_id')
    if not actor_id:
        logger.warning(
            "[FLOW] %s_denied room=%s battle=%s slot=%s reason=slot_actor_missing",
            event_name, room_id, battle_id, slot_id
        )
        emit(
            'battle_error',
            {'message': 'slot actor is missing', 'slot_id': slot_id},
            to=request.sid
        )
        return False

    user_info = get_user_info_from_sid(request.sid) or {}
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")
    allowed = is_authorized_for_character(room_id, actor_id, username, attribute)
    if not allowed:
        logger.warning(
            "[FLOW] %s_denied room=%s battle=%s slot=%s actor=%s user=%s attribute=%s",
            event_name, room_id, battle_id, slot_id, actor_id, username, attribute
        )
        emit(
            'battle_error',
            {
                'message': f'{event_name} permission denied',
                'slot_id': slot_id,
                'actor_id': actor_id
            },
            to=request.sid
        )
        return False

    return True


def _is_actor_actionable(room_id, actor_id):
    room_state = get_room_state(room_id)
    if not room_state:
        return False
    actor = next((c for c in room_state.get('characters', []) if c.get('id') == actor_id), None)
    if not actor:
        return False
    if actor.get('hp', 0) <= 0:
        return False
    if actor.get('is_escaped', False):
        return False
    try:
        x_val = float(actor.get('x', -1))
    except (TypeError, ValueError):
        x_val = -1
    if x_val < 0:
        return False
    if ConfusionBuff.is_incapacitated(actor):
        return False
    can_act, _ = ImmobilizeBuff.can_act(actor, {})
    if not can_act:
        return False
    return True


def _canonical_team(raw_value):
    text = str(raw_value or '').strip().lower()
    if text in ['ally', 'player', 'friend', 'friends']:
        return 'ally'
    if text in ['enemy', 'foe', 'opponent', 'boss', 'npc']:
        return 'enemy'
    return None


def _is_actor_targetable(room_id, actor_id):
    room_state = get_room_state(room_id)
    if not room_state:
        return False
    actor = next((c for c in room_state.get('characters', []) if c.get('id') == actor_id), None)
    if not actor:
        return False
    if actor.get('hp', 0) <= 0:
        return False
    if actor.get('is_escaped', False):
        return False
    try:
        x_val = float(actor.get('x', -1))
    except (TypeError, ValueError):
        x_val = -1
    return x_val >= 0


def _is_valid_single_target_slot_for_pve_enemy(room_id, state, source_slot_id, target_slot_id):
    slots = state.get('slots', {}) or {}
    source_slot = slots.get(source_slot_id, {}) if isinstance(slots, dict) else {}
    target_slot = slots.get(target_slot_id, {}) if isinstance(slots, dict) else {}
    if not isinstance(source_slot, dict) or not isinstance(target_slot, dict):
        return False
    if bool(target_slot.get('disabled', False)):
        return False

    source_team = _canonical_team(source_slot.get('team'))
    target_team = _canonical_team(target_slot.get('team'))
    if source_team and target_team and source_team == target_team:
        return False
    if target_team and target_team != 'ally':
        return False

    target_actor_id = target_slot.get('actor_id')
    if not target_actor_id:
        return False
    if not _is_actor_targetable(room_id, target_actor_id):
        return False
    return True


def _pick_default_pve_enemy_target_slot(room_id, state, source_slot_id, preferred_slot_id=None):
    slots = state.get('slots', {}) or {}
    if not isinstance(slots, dict):
        return None

    if preferred_slot_id and _is_valid_single_target_slot_for_pve_enemy(
        room_id, state, source_slot_id, preferred_slot_id
    ):
        return preferred_slot_id

    candidates = []
    for slot_id, slot in slots.items():
        if not _is_valid_single_target_slot_for_pve_enemy(room_id, state, source_slot_id, slot_id):
            continue
        candidates.append((int(slot.get('initiative', 0) or 0), str(slot_id)))

    if not candidates:
        return None
    candidates.sort(key=lambda row: (-row[0], row[1]))
    return candidates[0][1]


def _is_pve_enemy_auto_target_slot(room_id, state, slot_id):
    room_state = get_room_state(room_id) or {}
    if room_state.get('battle_mode', 'pvp') != 'pve':
        return False

    slots = state.get('slots', {}) or {}
    slot = slots.get(slot_id, {}) if isinstance(slots, dict) else {}
    if not isinstance(slot, dict):
        return False

    slot_team = _canonical_team(slot.get('team'))
    if slot_team and slot_team != 'enemy':
        return False

    actor_id = slot.get('actor_id')
    if not actor_id:
        return False

    actor = next((c for c in room_state.get('characters', []) if c.get('id') == actor_id), None)
    if not actor:
        return False

    actor_team = _canonical_team(actor.get('type'))
    if actor_team and actor_team != 'enemy':
        return False

    flags = actor.get('flags', {}) if isinstance(actor.get('flags'), dict) else {}
    return bool(flags.get('auto_target_select', True))


def _apply_pve_enemy_intent_defaults(
    room_id,
    state,
    slot_id,
    intent,
    intent_before=None,
    requested_skill_id=None,
    requested_target=None
):
    """
    Keep PvE enemy slot target stable:
    - If client sends target none, restore previous/default ally target.
    - If user explicitly sets single_slot target, respect it.
    - If auto_skill_select is on and skill is empty, suggest from AI pool.
    """
    if not _is_pve_enemy_auto_target_slot(room_id, state, slot_id):
        return intent
    if not isinstance(intent, dict):
        return intent

    prev = intent_before if isinstance(intent_before, dict) else {}
    req_target = requested_target if isinstance(requested_target, dict) else {}
    explicit_target_slot = None
    if req_target.get('type') == 'single_slot':
        explicit_target_slot = _normalize_target_slot_id(req_target.get('slot_id'))

    target = intent.get('target', {}) if isinstance(intent.get('target'), dict) else {}
    curr_target_slot = _normalize_target_slot_id(target.get('slot_id')) if target.get('type') == 'single_slot' else None
    prev_target = (prev.get('target') or {}) if isinstance(prev.get('target'), dict) else {}
    prev_target_slot = _normalize_target_slot_id(prev_target.get('slot_id')) if prev_target.get('type') == 'single_slot' else None

    if explicit_target_slot:
        intent['target'] = {'type': 'single_slot', 'slot_id': explicit_target_slot}
    else:
        chosen_target = None
        if curr_target_slot and _is_valid_single_target_slot_for_pve_enemy(room_id, state, slot_id, curr_target_slot):
            chosen_target = curr_target_slot
        if not chosen_target and prev_target_slot and _is_valid_single_target_slot_for_pve_enemy(
            room_id, state, slot_id, prev_target_slot
        ):
            chosen_target = prev_target_slot
        if not chosen_target:
            chosen_target = _pick_default_pve_enemy_target_slot(
                room_id,
                state,
                slot_id,
                preferred_slot_id=prev_target_slot,
            )
        if chosen_target:
            intent['target'] = {'type': 'single_slot', 'slot_id': chosen_target}

    room_state = get_room_state(room_id) or {}
    slots = state.get('slots', {}) or {}
    actor_id = (slots.get(slot_id) or {}).get('actor_id') if isinstance(slots, dict) else None
    actor = next((c for c in room_state.get('characters', []) if c.get('id') == actor_id), None)
    flags = actor.get('flags', {}) if isinstance(actor, dict) and isinstance(actor.get('flags'), dict) else {}
    auto_skill_select = bool(
        flags.get('auto_skill_select', False)
        or flags.get('show_planned_skill', False)
    )
    explicit_skill = requested_skill_id not in [None, '']

    if auto_skill_select and not explicit_skill and not intent.get('skill_id'):
        from manager.battle.battle_ai import ai_suggest_skill
        suggested = ai_suggest_skill(actor)
        if suggested:
            intent['skill_id'] = suggested

    normalized_target, target_error = _normalize_target_by_skill_compat(
        intent.get('skill_id'),
        intent.get('target'),
        state=state,
        source_slot_id=slot_id,
        allow_none=True
    )
    if not target_error:
        intent['target'] = normalized_target
    intent['tags'] = _default_intent_tags(_build_tags(intent.get('skill_id'), intent.get('target')))
    return intent


def _required_slots(room_id, state):
    required = set()
    for slot_id, slot in state.get('slots', {}).items():
        if slot.get('disabled', False):
            continue
        actor_id = slot.get('actor_id')
        if not _is_actor_actionable(room_id, actor_id):
            continue

        intent = state.get('intents', {}).get(slot_id, {})
        is_committed_instant = bool(intent.get('committed') and intent.get('tags', {}).get('instant'))
        if is_committed_instant:
            continue
        required.add(slot_id)
    return required


def _count_committed_required(required_slots, state):
    intents = state.get('intents', {})
    committed = 0
    for slot_id in required_slots:
        if intents.get(slot_id, {}).get('committed', False):
            committed += 1
    return committed


def _commit_progress(room_id, state):
    required = _required_slots(room_id, state)
    committed_count = _count_committed_required(required, state)
    waiting_slots = sorted([
        slot_id for slot_id in required
        if not state.get('intents', {}).get(slot_id, {}).get('committed', False)
    ])
    return required, committed_count, waiting_slots


def _emit_battle_resolve_ready(room_id, battle_id, state, required_count, committed_count, waiting_slots):
    payload = {
        'room_id': room_id,
        'battle_id': battle_id,
        'round': state.get('round', 0),
        'phase': state.get('phase', 'select'),
        'ready': True,
        'required_count': required_count,
        'committed_count': committed_count,
        'waiting_slots': waiting_slots
    }
    logger.info(
        "[FLOW] resolve_ready room=%s battle=%s required=%d committed=%d waiting=%s",
        room_id, battle_id, required_count, committed_count, waiting_slots[:8]
    )
    _log_battle_emit('battle_resolve_ready', room_id, battle_id, payload)
    socketio.emit('battle_resolve_ready', payload, to=room_id)


def _resolve_room_for_battle_start(data):
    room_id = (data or {}).get('room_id') or (data or {}).get('room')
    if room_id:
        return room_id

    user_info = get_user_info_from_sid(request.sid) or {}
    sid_room = user_info.get('room')
    if sid_room:
        return sid_room

    try:
        sid_rooms = list(rooms(request.sid))
    except Exception:
        sid_rooms = []
    for rid in sid_rooms:
        if rid and rid != request.sid:
            return rid
    return None


def _resolve_battle_id_for_room(room_id, data):
    battle_id = (data or {}).get('battle_id') or (data or {}).get('battle')
    if battle_id:
        return battle_id

    room_state = get_room_state(room_id) or {}
    existing = (room_state.get('battle_state') or {}).get('battle_id')
    if existing:
        return existing
    return f"battle_{room_id}"


def _start_select_resolve_if_ready(room_id, battle_id, source_event):
    state = get_or_create_select_resolve_state(room_id, battle_id=battle_id)
    if not state:
        emit('battle_error', {'message': 'room state not found'}, to=request.sid)
        return

    phase = state.get('phase')
    if not _is_select_phase(state):
        emit('battle_error', {'message': f'{source_event} is only allowed in select phase', 'phase': phase}, to=request.sid)
        return

    required = _required_slots(room_id, state)
    committed_count = _count_committed_required(required, state)
    waiting_slots = sorted([
        slot_id for slot_id in required
        if not state.get('intents', {}).get(slot_id, {}).get('committed', False)
    ])

    logger.info(
        "[FLOW] %s_check room=%s battle=%s required=%d committed=%d waiting=%s",
        source_event, room_id, battle_id, len(required), committed_count, waiting_slots[:8]
    )

    if len(required) == 0:
        logger.warning(
            "[FLOW] %s_abort room=%s battle=%s reason=no_required_slots",
            source_event, room_id, battle_id
        )
        emit('battle_error', {
            'message': 'no required slots to resolve',
            'required_count': 0,
            'committed_count': committed_count
        }, to=request.sid)
        _emit_battle_state_updated(room_id, battle_id)
        return

    if committed_count != len(required):
        emit('battle_error', {
            'message': 'not all required slots are committed',
            'required_count': len(required),
            'committed_count': committed_count,
            'missing_count': max(0, len(required) - committed_count),
            'waiting_slots': waiting_slots
        }, to=request.sid)
        _emit_battle_state_updated(room_id, battle_id)
        return

    consumed_rows = _consume_mass_costs_on_resolve_start(room_id, state, required)
    for row in consumed_rows:
        logger.info(
            "[FLOW] resolve_start_cost room=%s battle=%s slot=%s actor=%s skill=%s spent=%s",
            room_id,
            battle_id,
            row.get('slot_id'),
            row.get('actor_id'),
            row.get('skill_id'),
            row.get('spent')
        )
    if consumed_rows:
        broadcast_state_update(room_id)

    # Freeze intents at the exact moment GM starts resolve.
    # Resolve must not read mutable select-phase intents directly.
    state['resolve_snapshot_intents'] = copy.deepcopy(state.get('intents', {}))
    state['resolve_snapshot_at'] = _server_ts_ms()

    state['resolve_ready'] = False
    state['resolve_ready_info'] = {}
    state['phase'] = 'resolve_mass'
    state.setdefault('resolve', {})
    state['resolve']['mass_queue'] = state['resolve'].get('mass_queue', [])
    state['resolve']['single_queue'] = state['resolve'].get('single_queue', [])
    state['resolve']['resolved_slots'] = state['resolve'].get('resolved_slots', [])
    state['resolve']['trace'] = state['resolve'].get('trace', [])

    payload = {
        'room_id': room_id,
        'battle_id': battle_id,
        'round': state.get('round', 0),
        'from': 'select',
        'to': 'resolve_mass'
    }
    logger.info("[FLOW] %s_start room=%s battle=%s", source_event, room_id, battle_id)
    _log_battle_emit('battle_phase_changed', room_id, battle_id, payload)
    socketio.emit('battle_phase_changed', payload, to=room_id)

    # Keep new battle_* state synchronized through the same room pathway.
    emit_select_resolve_events(room_id, include_round_started=False)
    run_select_resolve_auto(room_id, battle_id)


def _refresh_resolve_ready(room_id, state):
    required, committed_count, waiting_slots = _commit_progress(room_id, state)
    ready = committed_count == len(required)
    state['resolve_ready'] = ready
    state['resolve_ready_info'] = {
        'required_count': len(required),
        'committed_count': committed_count,
        'waiting_slots': waiting_slots
    }
    return ready, required, committed_count, waiting_slots


def _maybe_advance_phase_to_resolve_mass(room_id, battle_id, state):
    if not _is_select_phase(state):
        return
    was_ready = bool(state.get('resolve_ready', False))
    ready, required, committed_count, waiting_slots = _refresh_resolve_ready(room_id, state)
    logger.info(
        "[FLOW] commit_progress room=%s battle=%s required=%d committed=%d waiting=%s",
        room_id, battle_id, len(required), committed_count, waiting_slots[:8]
    )
    if len(required) == 0:
        state['resolve_ready'] = False
        state['resolve_ready_info'] = {
            'required_count': 0,
            'committed_count': committed_count,
            'waiting_slots': waiting_slots
        }
        return
    if not ready:
        return

    _emit_battle_state_updated(room_id, battle_id)
    if not was_ready:
        _emit_battle_resolve_ready(
            room_id,
            battle_id,
            state,
            required_count=len(required),
            committed_count=committed_count,
            waiting_slots=waiting_slots
        )


def _apply_intent_identity(intent, state, slot_id):
    slot = state.get('slots', {}).get(slot_id, {})
    intent['slot_id'] = slot_id
    intent['actor_id'] = slot.get('actor_id')
    return intent


def _ensure_battle_payload(data, require_slot=False):
    room_id = data.get('room_id')
    battle_id = data.get('battle_id')
    slot_id = data.get('slot_id')

    if not room_id or not battle_id:
        emit('battle_error', {'message': 'room_id and battle_id are required'}, to=request.sid)
        return None

    if require_slot and not slot_id:
        emit('battle_error', {'message': 'slot_id is required'}, to=request.sid)
        return None

    return room_id, battle_id, slot_id


def _emit_battle_state_updated(room_id, battle_id):
    payload = build_select_resolve_state_payload(room_id, battle_id=battle_id)
    if payload is None:
        emit('battle_error', {'message': 'failed to build battle_state_updated'}, to=request.sid)
        return
    state = get_or_create_select_resolve_state(room_id, battle_id=battle_id)
    if state:
        payload['resolve_ready'] = bool(state.get('resolve_ready', False))
        payload['resolve_ready_info'] = state.get('resolve_ready_info', {})
    _log_battle_emit('battle_state_updated', room_id, battle_id, payload)
    socketio.emit('battle_state_updated', payload, to=room_id)


def _server_ts():
    return int(time.time())


def _server_ts_ms():
    return int(time.time() * 1000)


def _next_intent_revision(state):
    current = int(state.get('intent_revision_seq', 0) or 0)
    nxt = current + 1
    state['intent_revision_seq'] = nxt
    return nxt


def _ensure_intent_for_slot(state, slot_id):
    intent = state.get('intents', {}).get(slot_id, {})
    intent = _apply_intent_identity(intent, state, slot_id)
    intent.setdefault('skill_id', None)
    intent.setdefault('target', {'type': 'none', 'slot_id': None})
    intent.setdefault('tags', _default_intent_tags())
    intent.setdefault('committed', False)
    intent.setdefault('committed_at', None)
    intent.setdefault('committed_by', None)
    intent.setdefault('intent_rev', 0)
    state['intents'][slot_id] = intent
    return intent


def _clear_redirect_state(state):
    if not isinstance(state, dict):
        return
    slots = state.get('slots', {})
    if isinstance(slots, dict):
        for slot in slots.values():
            if not isinstance(slot, dict):
                continue
            slot['locked_target'] = False
            slot.pop('locked_by_slot', None)
            slot.pop('locked_by_initiative', None)
            slot.pop('locked_by_intent_rev', None)
            slot.pop('locked_by_committed_at', None)
    state['redirects'] = []


def _append_redirect_record(state, record):
    state.setdefault('redirects', [])
    state['redirects'].append(record)
    trace = state.get('resolve', {}).get('trace', [])
    trace.append({
        'step': len(trace) + 1,
        'kind': record.get('kind', 'redirect'),
        'attacker_slot': record.get('by_slot'),
        'defender_slot': record.get('from_slot'),
        'target_actor_id': None,
        'rolls': {},
        'outcome': 'no_effect',
        'cost': {'mp': 0, 'hp': 0},
        'notes': None
    })
    state['resolve']['trace'] = trace


def _cancel_redirect_by_no_redirect(room_id, battle_id, state, slot_id, reset_target=False):
    slot = state.get('slots', {}).get(slot_id, {})
    if not slot:
        return

    intent = _ensure_intent_for_slot(state, slot_id)
    was_locked = bool(slot.get('locked_target', False))
    old_target_slot = intent.get('target', {}).get('slot_id')
    if not was_locked:
        return

    slot['locked_target'] = False
    if 'locked_by_slot' in slot:
        slot.pop('locked_by_slot', None)
    if 'locked_by_initiative' in slot:
        slot.pop('locked_by_initiative', None)
    if 'locked_by_intent_rev' in slot:
        slot.pop('locked_by_intent_rev', None)
    if 'locked_by_committed_at' in slot:
        slot.pop('locked_by_committed_at', None)
    if reset_target:
        intent['target'] = {'type': 'none', 'slot_id': None}

    cancel_record = {
        'ts': _server_ts(),
        'kind': 'redirect_cancelled_by_no_redirect',
        'by_slot': slot_id,
        'from_slot': slot_id,
        'old_target_slot': old_target_slot,
        'new_target_slot': None
    }
    _append_redirect_record(state, cancel_record)
    print(f"unlock target for {slot_id} due to no_redirect")


def _try_apply_redirect(room_id, battle_id, state, slot_a):
    slot_a_data = state.get('slots', {}).get(slot_a, {})
    intent_a = _ensure_intent_for_slot(state, slot_a)
    target = intent_a.get('target', {})

    if target.get('type') != 'single_slot':
        return
    slot_b = target.get('slot_id')
    if not slot_b or slot_b not in state.get('slots', {}):
        return
    if slot_b == slot_a:
        return

    intent_b = _ensure_intent_for_slot(state, slot_b)
    slot_b_data = state['slots'][slot_b]
    scope_a = _infer_target_scope_from_skill(intent_a.get('skill_id'))
    scope_b = _infer_target_scope_from_skill(intent_b.get('skill_id'))
    # 味方指定スキルは対象変更の仕組みに参加させない。
    if scope_a == 'ally' or scope_b == 'ally':
        return

    # If slot_b is currently aiming at a mass skill slot, keep that pairing stable.
    # This prevents higher-initiative third parties from stealing the clash target.
    slot_b_target = (intent_b.get('target') or {})
    slot_b_target_slot = slot_b_target.get('slot_id') if slot_b_target.get('type') == 'single_slot' else None
    if slot_b_target_slot:
        intent_targeted_by_b = _ensure_intent_for_slot(state, slot_b_target_slot)
        target_mass_type = ((intent_targeted_by_b.get('tags') or {}).get('mass_type'))
        if target_mass_type in ['mass_individual', 'mass_summation', 'individual', 'summation']:
            return

    init_a = int(slot_a_data.get('initiative', 0))
    init_b = int(slot_b_data.get('initiative', 0))
    if init_a <= init_b:
        return

    if intent_a.get('tags', {}).get('no_redirect', False):
        return
    if intent_b.get('tags', {}).get('no_redirect', False):
        return

    # Redirect contention rule:
    # among faster-than-B candidates, the most recently committed declaration wins.
    intent_rev_a = int(intent_a.get('intent_rev', 0) or 0)
    committed_at_a = int(intent_a.get('committed_at', 0) or 0)
    current_locked_by_rev = int(slot_b_data.get('locked_by_intent_rev', -999999))
    current_locked_by_ts = int(slot_b_data.get('locked_by_committed_at', -999999))
    if slot_b_data.get('locked_target', False):
        if intent_rev_a < current_locked_by_rev:
            return
        if intent_rev_a == current_locked_by_rev and committed_at_a < current_locked_by_ts:
            return

    old_target_slot = intent_b.get('target', {}).get('slot_id')
    intent_b['target'] = {'type': 'single_slot', 'slot_id': slot_a}
    slot_b_data['locked_target'] = True
    slot_b_data['locked_by_slot'] = slot_a
    slot_b_data['locked_by_initiative'] = init_a
    slot_b_data['locked_by_intent_rev'] = intent_rev_a
    slot_b_data['locked_by_committed_at'] = committed_at_a

    redirect_record = {
        'ts': _server_ts(),
        'kind': 'redirect',
        'by_slot': slot_a,
        'from_slot': slot_b,
        'old_target_slot': old_target_slot,
        'new_target_slot': slot_a
    }
    _append_redirect_record(state, redirect_record)
    print(
        f"redirect {slot_b} -> {slot_a} by {slot_a}"
        f"(init={init_a} > {init_b}, rev={intent_rev_a}, ts={committed_at_a})"
    )


def _recalculate_redirect_state(room_id, battle_id, state):
    if not isinstance(state, dict):
        return
    _clear_redirect_state(state)
    slots = state.get('slots', {}) or {}
    intents = state.get('intents', {}) or {}
    if not isinstance(slots, dict) or not isinstance(intents, dict):
        return

    def _redirect_sort_key(slot_id):
        intent = intents.get(slot_id, {}) if isinstance(intents, dict) else {}
        slot = slots.get(slot_id, {}) if isinstance(slots, dict) else {}
        # Lower values first so later declarations are processed later and can overwrite.
        intent_rev = int(intent.get('intent_rev', 0) or 0)
        committed_at = int(intent.get('committed_at', 0) or 0)
        initiative = int(slot.get('initiative', 0) or 0)
        return (intent_rev, committed_at, initiative, str(slot_id))

    ordered_slot_ids = sorted([sid for sid in slots.keys()], key=_redirect_sort_key)

    for slot_id in ordered_slot_ids:
        intent = _ensure_intent_for_slot(state, slot_id)
        if not intent.get('committed', False):
            continue
        target = intent.get('target', {}) or {}
        if target.get('type') != 'single_slot':
            continue
        if not intent.get('skill_id'):
            continue
        if intent.get('tags', {}).get('no_redirect', False):
            _cancel_redirect_by_no_redirect(room_id, battle_id, state, slot_id, reset_target=False)
            continue
        _try_apply_redirect(room_id, battle_id, state, slot_id)


@socketio.on('battle_round_request_start')
def on_battle_round_request_start(data):
    data = data or {}
    _log_battle_recv('battle_round_request_start', data)
    room_battle_slot = _ensure_battle_payload(data, require_slot=False)
    if room_battle_slot is None:
        return

    room_id, battle_id, _ = room_battle_slot
    print(f"[battle_round_request_start] room_id={room_id} battle_id={battle_id} slot_id=None")

    round_value = data.get('round')
    if not isinstance(round_value, int):
        emit('battle_error', {'message': 'round must be int'}, to=request.sid)
        return

    round_started_payload = process_select_resolve_round_start(
        room_id,
        battle_id=battle_id,
        round_value=round_value
    )
    if not round_started_payload:
        emit('battle_error', {'message': 'room state not found'}, to=request.sid)
        return

    _log_battle_emit('battle_round_started', room_id, battle_id, round_started_payload)
    socketio.emit('battle_round_started', round_started_payload, to=room_id)

    _emit_battle_state_updated(room_id, battle_id)


@socketio.on('battle_intent_preview')
def on_battle_intent_preview(data):
    data = data or {}
    _log_battle_recv('battle_intent_preview', data)
    room_battle_slot = _ensure_battle_payload(data, require_slot=True)
    if room_battle_slot is None:
        return

    room_id, battle_id, slot_id = room_battle_slot
    print(f"[battle_intent_preview] room_id={room_id} battle_id={battle_id} slot_id={slot_id}")

    state = get_or_create_select_resolve_state(room_id, battle_id=battle_id)
    if not state:
        emit('battle_error', {'message': 'room state not found'}, to=request.sid)
        return
    logger.info(
        "[FLOW] preview_state room=%s battle=%s phase=%s slots=%d intents=%d",
        room_id, battle_id, state.get('phase'), len(state.get('slots', {})), len(state.get('intents', {}))
    )
    if not _is_select_phase(state):
        emit('battle_error', {'message': 'battle_intent_preview is only allowed in select phase'}, to=request.sid)
        return

    if not _authorize_intent_slot_control(room_id, battle_id, state, slot_id, 'battle_intent_preview'):
        return

    skill_id = data.get('skill_id')
    target, target_error = _validate_and_normalize_target(
        data.get('target'),
        state,
        allow_none=True
    )
    if target_error:
        emit('battle_error', {'message': target_error}, to=request.sid)
        return
    target, target_error = _normalize_target_by_skill_compat(
        skill_id,
        target,
        state=state,
        source_slot_id=slot_id,
        allow_none=True
    )
    if target_error:
        emit('battle_error', {'message': target_error}, to=request.sid)
        return

    intent_before = copy.deepcopy(state['intents'].get(slot_id, {}))
    intent = state['intents'].get(slot_id, {})
    intent = _apply_intent_identity(intent, state, slot_id)
    intent['skill_id'] = skill_id
    intent['target'] = target
    intent['committed'] = False
    intent['committed_at'] = None
    intent['committed_by'] = None
    intent['tags'] = _default_intent_tags(_build_tags(intent['skill_id'], intent['target']))
    intent = _apply_pve_enemy_intent_defaults(
        room_id,
        state,
        slot_id,
        intent,
        intent_before=intent_before,
        requested_skill_id=skill_id,
        requested_target=target,
    )
    state['intents'][slot_id] = intent
    _recalculate_redirect_state(room_id, battle_id, state)
    logger.info(
        "[FLOW] preview_saved room=%s battle=%s slot=%s committed=%s skill=%s target=%s",
        room_id, battle_id, slot_id, intent.get('committed'), intent.get('skill_id'), intent.get('target')
    )

    _refresh_resolve_ready(room_id, state)
    _emit_battle_state_updated(room_id, battle_id)


@socketio.on('battle_intent_commit')
def on_battle_intent_commit(data):
    data = data or {}
    _log_battle_recv('battle_intent_commit', data)
    room_battle_slot = _ensure_battle_payload(data, require_slot=True)
    if room_battle_slot is None:
        return

    room_id, battle_id, slot_id = room_battle_slot
    print(f"[battle_intent_commit] room_id={room_id} battle_id={battle_id} slot_id={slot_id}")

    state = get_or_create_select_resolve_state(room_id, battle_id=battle_id)
    if not state:
        emit('battle_error', {'message': 'room state not found'}, to=request.sid)
        return
    logger.info(
        "[FLOW] commit_state room=%s battle=%s phase=%s slots=%d intents=%d",
        room_id, battle_id, state.get('phase'), len(state.get('slots', {})), len(state.get('intents', {}))
    )
    if not _is_select_phase(state):
        emit('battle_error', {'message': 'battle_intent_commit is only allowed in select phase'}, to=request.sid)
        return

    if not _authorize_intent_slot_control(room_id, battle_id, state, slot_id, 'battle_intent_commit'):
        return

    skill_id = data.get('skill_id')
    target, target_error = _validate_and_normalize_target(
        data.get('target'),
        state,
        allow_none=False
    )
    if target_error:
        emit('battle_error', {'message': target_error}, to=request.sid)
        return
    if not skill_id:
        emit('battle_error', {'message': 'commit requires skill_id'}, to=request.sid)
        return
    target, target_error = _normalize_target_by_skill_compat(
        skill_id,
        target,
        state=state,
        source_slot_id=slot_id,
        allow_none=False
    )
    if target_error:
        emit('battle_error', {'message': target_error}, to=request.sid)
        return

    intent = state['intents'].get(slot_id, {})
    intent = _apply_intent_identity(intent, state, slot_id)
    intent['skill_id'] = skill_id
    intent['target'] = target
    intent['committed'] = True
    intent['committed_at'] = _server_ts_ms()
    intent['committed_by'] = (get_user_info_from_sid(request.sid) or {}).get('username') or request.sid
    intent['intent_rev'] = _next_intent_revision(state)
    intent['tags'] = _default_intent_tags(_build_tags(intent['skill_id'], intent['target']))
    state['intents'][slot_id] = intent
    _recalculate_redirect_state(room_id, battle_id, state)
    logger.info(
        "[FLOW] commit_saved room=%s battle=%s slot=%s committed=%s skill=%s target=%s",
        room_id, battle_id, slot_id, intent.get('committed'), intent.get('skill_id'), intent.get('target')
    )

    _emit_battle_state_updated(room_id, battle_id)
    _maybe_advance_phase_to_resolve_mass(room_id, battle_id, state)


@socketio.on('battle_resolve_confirm')
def on_battle_resolve_confirm(data):
    data = data or {}
    _log_battle_recv('battle_resolve_confirm', data)
    room_battle_slot = _ensure_battle_payload(data, require_slot=False)
    if room_battle_slot is None:
        return

    room_id, battle_id, _ = room_battle_slot
    state = get_or_create_select_resolve_state(room_id, battle_id=battle_id)
    if not state:
        emit('battle_error', {'message': 'room state not found'}, to=request.sid)
        return
    if not _is_select_phase(state):
        emit('battle_error', {'message': 'battle_resolve_confirm is only allowed in select phase'}, to=request.sid)
        return

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")
    if attribute != 'GM':
        logger.info("[FLOW] resolve_confirm_denied room=%s battle=%s user=%s attribute=%s", room_id, battle_id, username, attribute)
        emit('battle_error', {'message': 'battle_resolve_confirm is GM only'}, to=request.sid)
        return

    ready, required, committed_count, waiting_slots = _refresh_resolve_ready(room_id, state)
    logger.info(
        "[FLOW] resolve_confirm_attempt room=%s battle=%s user=%s required=%d committed=%d waiting=%s",
        room_id, battle_id, username, len(required), committed_count, waiting_slots[:8]
    )
    if not ready:
        emit('battle_error', {'message': 'not all required slots are committed'}, to=request.sid)
        _emit_battle_state_updated(room_id, battle_id)
        return

    logger.info("[FLOW] resolve_confirm room=%s battle=%s by=%s", room_id, battle_id, username)
    _start_select_resolve_if_ready(room_id, battle_id, source_event='battle_resolve_confirm')


@socketio.on('battle_resolve_start')
def on_battle_resolve_start(data):
    data = data or {}
    _log_battle_recv('battle_resolve_start', data)

    room_id = _resolve_room_for_battle_start(data)
    if not room_id:
        emit('battle_error', {'message': 'room is required'}, to=request.sid)
        return
    battle_id = _resolve_battle_id_for_room(room_id, data)

    logger.info(
        "[FLOW] resolve_start_request sid=%s room=%s battle=%s",
        request.sid, room_id, battle_id
    )
    _start_select_resolve_if_ready(room_id, battle_id, source_event='battle_resolve_start')


@socketio.on('battle_resolve_flow_advance_request')
def on_battle_resolve_flow_advance_request(data):
    data = data or {}
    room_id = data.get('room_id') or data.get('room') or data.get('room_name')
    if not room_id:
        emit('battle_error', {'message': 'room is required'}, to=request.sid)
        return

    user_info = get_user_info_from_sid(request.sid) or {}
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")
    if attribute != 'GM':
        logger.info(
            "[FLOW] resolve_flow_advance_denied room=%s user=%s attr=%s",
            room_id, username, attribute
        )
        emit('battle_error', {'message': 'battle_resolve_flow_advance_request is GM only'}, to=request.sid)
        return

    payload = {
        'room_id': room_id,
        'battle_id': data.get('battle_id'),
        'round': data.get('round'),
        'expected_step_index': data.get('expected_step_index'),
        'requested_by': username,
        'server_ts': int(time.time())
    }
    logger.info(
        "[FLOW] resolve_flow_advance room=%s battle=%s round=%s step=%s by=%s",
        payload.get('room_id'),
        payload.get('battle_id'),
        payload.get('round'),
        payload.get('expected_step_index'),
        username
    )
    socketio.emit('battle_resolve_flow_advance', payload, to=room_id)


@socketio.on('battle_intent_uncommit')
def on_battle_intent_uncommit(data):
    data = data or {}
    room_battle_slot = _ensure_battle_payload(data, require_slot=True)
    if room_battle_slot is None:
        return

    room_id, battle_id, slot_id = room_battle_slot
    print(f"[battle_intent_uncommit] room_id={room_id} battle_id={battle_id} slot_id={slot_id}")

    state = get_or_create_select_resolve_state(room_id, battle_id=battle_id)
    if not state:
        emit('battle_error', {'message': 'room state not found'}, to=request.sid)
        return
    if not _is_select_phase(state):
        emit('battle_error', {'message': 'battle_intent_uncommit is only allowed in select phase'}, to=request.sid)
        return

    if not _authorize_intent_slot_control(room_id, battle_id, state, slot_id, 'battle_intent_uncommit'):
        return

    intent_before = copy.deepcopy(state['intents'].get(slot_id, {}))
    intent = state['intents'].get(slot_id, {})
    intent = _apply_intent_identity(intent, state, slot_id)
    intent['committed'] = False
    intent['committed_at'] = None
    intent['committed_by'] = None
    intent['tags'] = _default_intent_tags(intent.get('tags'))
    if 'target' not in intent:
        intent['target'] = {'type': 'none', 'slot_id': None}
    intent = _apply_pve_enemy_intent_defaults(
        room_id,
        state,
        slot_id,
        intent,
        intent_before=intent_before,
        requested_skill_id=None,
        requested_target=intent.get('target'),
    )
    state['intents'][slot_id] = intent
    _recalculate_redirect_state(room_id, battle_id, state)

    _refresh_resolve_ready(room_id, state)
    _emit_battle_state_updated(room_id, battle_id)


@socketio.on('battle_intent_change_skill')
def on_battle_intent_change_skill(data):
    data = data or {}
    room_battle_slot = _ensure_battle_payload(data, require_slot=True)
    if room_battle_slot is None:
        return

    room_id, battle_id, slot_id = room_battle_slot
    print(f"[battle_intent_change_skill] room_id={room_id} battle_id={battle_id} slot_id={slot_id}")

    state = get_or_create_select_resolve_state(room_id, battle_id=battle_id)
    if not state:
        emit('battle_error', {'message': 'room state not found'}, to=request.sid)
        return
    if not _is_select_phase(state):
        emit('battle_error', {'message': 'battle_intent_change_skill is only allowed in select phase'}, to=request.sid)
        return

    if slot_id not in state.get('slots', {}):
        print(f"[battle_intent_change_skill] unknown slot_id={slot_id} in battle_id={battle_id}")

    intent_before = copy.deepcopy(state['intents'].get(slot_id, {}))
    intent = state['intents'].get(slot_id, {})
    intent = _apply_intent_identity(intent, state, slot_id)
    intent['skill_id'] = data.get('skill_id')
    if 'target' not in intent:
        intent['target'] = {'type': 'none', 'slot_id': None}
    normalized_target, target_error = _normalize_target_by_skill_compat(
        intent['skill_id'],
        intent.get('target'),
        state=state,
        source_slot_id=slot_id,
        allow_none=True
    )
    if target_error:
        emit('battle_error', {'message': target_error}, to=request.sid)
        return
    intent['target'] = normalized_target
    intent['tags'] = _default_intent_tags(_build_tags(intent['skill_id'], intent['target']))
    intent['committed'] = False
    intent['committed_at'] = None
    intent['committed_by'] = None
    intent = _apply_pve_enemy_intent_defaults(
        room_id,
        state,
        slot_id,
        intent,
        intent_before=intent_before,
        requested_skill_id=data.get('skill_id'),
        requested_target=intent.get('target'),
    )
    state['intents'][slot_id] = intent
    _recalculate_redirect_state(room_id, battle_id, state)

    _refresh_resolve_ready(room_id, state)
    _emit_battle_state_updated(room_id, battle_id)


@socketio.on('battle_intent_change_target')
def on_battle_intent_change_target(data):
    data = data or {}
    room_battle_slot = _ensure_battle_payload(data, require_slot=True)
    if room_battle_slot is None:
        return

    room_id, battle_id, slot_id = room_battle_slot
    print(f"[battle_intent_change_target] room_id={room_id} battle_id={battle_id} slot_id={slot_id}")

    state = get_or_create_select_resolve_state(room_id, battle_id=battle_id)
    if not state:
        emit('battle_error', {'message': 'room state not found'}, to=request.sid)
        return
    if not _is_select_phase(state):
        emit('battle_error', {'message': 'battle_intent_change_target is only allowed in select phase'}, to=request.sid)
        return

    if slot_id not in state.get('slots', {}):
        print(f"[battle_intent_change_target] unknown slot_id={slot_id} in battle_id={battle_id}")

    target, target_error = _validate_and_normalize_target(
        data.get('target'),
        state,
        allow_none=True
    )
    if target_error:
        emit('battle_error', {'message': target_error}, to=request.sid)
        return

    intent_before = copy.deepcopy(state['intents'].get(slot_id, {}))
    intent = state['intents'].get(slot_id, {})
    intent = _apply_intent_identity(intent, state, slot_id)
    normalized_target, target_error = _normalize_target_by_skill_compat(
        intent.get('skill_id'),
        target,
        state=state,
        source_slot_id=slot_id,
        allow_none=True
    )
    if target_error:
        emit('battle_error', {'message': target_error}, to=request.sid)
        return
    intent['target'] = normalized_target
    intent['tags'] = _default_intent_tags(_build_tags(intent.get('skill_id'), intent['target']))
    intent['committed'] = False
    intent['committed_at'] = None
    intent['committed_by'] = None
    intent = _apply_pve_enemy_intent_defaults(
        room_id,
        state,
        slot_id,
        intent,
        intent_before=intent_before,
        requested_skill_id=intent.get('skill_id'),
        requested_target=target,
    )
    state['intents'][slot_id] = intent
    _recalculate_redirect_state(room_id, battle_id, state)

    _refresh_resolve_ready(room_id, state)
    _emit_battle_state_updated(room_id, battle_id)



