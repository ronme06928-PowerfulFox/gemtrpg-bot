import copy
import json
import time

from flask import request
from flask_socketio import emit, rooms
from extensions import socketio, all_skill_data
from manager.logs import setup_logger
from manager.room_access import is_sid_in_room
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
from manager.battle.skill_access import evaluate_skill_access
from manager.battle.skill_rules import _extract_rule_data_from_skill as _extract_rule_data_from_skill_v2
from manager.battle.system_skills import ensure_system_skills_registered
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
from events.battle import intent_targets as _intent_targets
from events.battle import phase_flow as _phase_flow
from events.battle import pve_intents as _pve_intents
from events.battle.intent_targets import (
    _default_intent_tags,
    _validate_and_normalize_target,
)

from manager.utils import apply_buff, get_status_value, set_status_value # For debug
logger = setup_logger(__name__)
ensure_system_skills_registered()

def _require_in_room(room):
    if not is_sid_in_room(request.sid, room):
        emit('error', {'message': 'Not in this room'}, to=request.sid)
        return False
    return True


def _is_battle_only_mode(room):
    state = get_room_state(room)
    if not isinstance(state, dict):
        return False
    play_mode = str(state.get('play_mode') or 'normal').strip().lower()
    return play_mode == 'battle_only'


def _get_battle_only_intent_control_policy(room):
    state = get_room_state(room)
    if not isinstance(state, dict):
        return ("all", "", "")
    bo = state.get('battle_only') if isinstance(state.get('battle_only'), dict) else {}
    options = bo.get('options') if isinstance(bo.get('options'), dict) else {}
    mode = str(options.get('intent_control_mode') or 'all').strip().lower()
    if mode not in ('all', 'starter_only'):
        mode = 'all'
    controller_user_id = str(bo.get('controller_user_id') or '').strip()
    controller_username = str(bo.get('controller_username') or '').strip()
    return (mode, controller_user_id, controller_username)


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
    if not _require_in_room(room): return
    proceed_next_turn(room)

@socketio.on('request_new_round')
def on_request_new_round(data):
    room = data.get('room')
    if not room: return
    if not _require_in_room(room): return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    if attribute != 'GM':
        emit('new_log', {'message': 'ラウンド開始はGMのみ可能です。', 'type': 'error'})
        return

    process_round_start(room, username)

@socketio.on('request_declare_wide_skill_users')
def on_request_declare_wide_skill_users(data):
    room = data.get('room')
    if not room: return
    if not _require_in_room(room): return
    wide_user_ids = data.get('wideUserIds', [])

    # Needs process_wide_declarations in common_manager.py
    process_wide_declarations(room, wide_user_ids)

@socketio.on('request_wide_modal_confirm')
def on_request_wide_modal_confirm(data):
    room = data.get('room')
    if not room: return
    if not _require_in_room(room): return
    wide_ids = data.get('wideUserIds', [])

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    process_wide_modal_confirm(room, username, attribute, wide_ids)




@socketio.on('request_end_round')
def on_request_end_round(data):
    room = data.get('room')
    if not room: return
    if not _require_in_room(room): return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")
    is_battle_only = _is_battle_only_mode(room)

    if attribute != 'GM' and not is_battle_only:
        print(f"[Security] Player {username} tried to end round. Denied.")
        return

    before_state = get_room_state(room)
    before_round = int((before_state or {}).get('round', 0) or 0)
    end_result = process_full_round_end(room, username)
    if not is_battle_only:
        return

    state = get_room_state(room)
    if not isinstance(state, dict):
        return
    ended = bool(state.get('is_round_ended', False)) if end_result is None else bool(end_result)
    if not ended:
        return
    if int(state.get('round', 0) or 0) != before_round:
        return
    if not state.get('is_round_ended', False):
        return
    bo = state.get('battle_only') if isinstance(state.get('battle_only'), dict) else {}
    if bool(bo.get('pending_auto_reset', False)):
        bo['pending_auto_reset'] = False
        bo['pending_auto_reset_round'] = None
        try:
            reset_battle_logic(room, 'full', '戦闘専用モード(自動リセット)')
            broadcast_log(room, "[BattleOnly] 解決表示完了後にフィールドを自動リセットしました。", 'info')
        except Exception:
            logger.exception("[BattleOnly] auto reset after resolve completion failed room=%s", room)
        return

    bo_status = str(bo.get('status', '') or '').strip().lower()
    if bo_status and bo_status != 'in_battle':
        return

    process_round_start(room, "戦闘専用モード")

@socketio.on('request_reset_battle')
def on_request_reset_battle(data):
    room = data.get('room')
    if not room: return
    if not _require_in_room(room): return
    mode = data.get('mode', 'full')
    options = data.get('options') # get dictionary or None
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")
    is_battle_only = _is_battle_only_mode(room)

    if attribute != 'GM' and not is_battle_only:
        print(f"[Security] Player {username} tried to reset battle. Denied.")
        return

    reset_battle_logic(room, mode, username, options)

@socketio.on('request_force_end_match')
def on_request_force_end_match(data):
    room = data.get('room')
    if not room: return
    if not _require_in_room(room): return
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

    if not room: return
    if not _require_in_room(room): return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    move_token_logic(room, char_id, x, y, username, attribute)

@socketio.on('open_match_modal')
def on_open_match_modal(data):
    room = data.get('room')
    if not room: return
    if not _require_in_room(room): return
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    open_match_modal_logic(room, data, username)

@socketio.on('close_match_modal')
def on_close_match_modal(data):
    room = data.get('room')
    if not room: return
    if not _require_in_room(room): return
    close_match_modal_logic(room)

@socketio.on('sync_match_data')
def on_sync_match_data(data):
    room = data.get('room')
    if not room: return
    if not _require_in_room(room): return
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
    if not _require_in_room(room): return
    user_info = get_user_info_from_sid(request.sid)
    if str(user_info.get("attribute", "Player") or "Player").strip().upper() != 'GM':
        emit('error', {'message': 'GM権限が必要です。'})
        return

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
    if not _require_in_room(room): return

    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")

    update_battle_background_logic(room, image_url, scale, offset_x, offset_y, username, attribute)

# NOTE: PvE/PvP モード切り替え
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
def on_request_ai_suggest_skill(data):
    room = data.get('room')
    char_id = data.get('charId')

    if not room or not char_id: return

    # 誰でも要求可能。最終的な採用判断はGM側で行う。
    from manager.battle.common_manager import process_ai_suggest_skill
    suggested_skill_id = process_ai_suggest_skill(room, char_id)

    emit('ai_skill_suggested', {
        'charId': char_id,
        'skillId': suggested_skill_id
    })



def _sync_intent_target_context():
    _intent_targets.all_skill_data = all_skill_data
    _intent_targets._extract_rule_data_from_skill_v2 = _extract_rule_data_from_skill_v2


def _extract_skill_rule_data(skill_data):
    _sync_intent_target_context()
    return _intent_targets._extract_skill_rule_data(skill_data)


def _extract_skill_tags(skill_id):
    _sync_intent_target_context()
    return _intent_targets._extract_skill_tags(skill_id)


def _infer_mass_type_from_skill(skill_id):
    _sync_intent_target_context()
    return _intent_targets._infer_mass_type_from_skill(skill_id)


def _infer_target_scope_from_skill(skill_id):
    _sync_intent_target_context()
    return _intent_targets._infer_target_scope_from_skill(skill_id)


def _normalize_target_by_skill(skill_id, target, state=None, source_slot_id=None, allow_none=True):
    _sync_intent_target_context()
    return _intent_targets._normalize_target_by_skill(
        skill_id,
        target,
        state=state,
        source_slot_id=source_slot_id,
        allow_none=allow_none,
    )


def _normalize_target_by_skill_compat(skill_id, target, state=None, source_slot_id=None, allow_none=True):
    try:
        return _normalize_target_by_skill(
            skill_id,
            target,
            state=state,
            source_slot_id=source_slot_id,
            allow_none=allow_none,
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
    _sync_intent_target_context()
    return _intent_targets._build_tags(skill_id, target)


def _resolve_actor_for_slot(state, slot_id, room_id=None):
    return _intent_targets._resolve_actor_for_slot(
        state, slot_id, room_id=room_id, get_room_state_fn=get_room_state
    )

def _extract_skill_cost_entries(skill_data):
    _sync_intent_target_context()
    return _intent_targets._extract_skill_cost_entries(skill_data)

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

    # battle_only は操作モードで宣言権限を切り替える:
    # - all: 参加者全員が宣言操作可能
    # - starter_only: 戦闘開始者またはGMのみ操作可能
    if _is_battle_only_mode(room_id):
        if str(attribute or '').strip().upper() == 'GM':
            return True
        mode, controller_user_id, controller_username = _get_battle_only_intent_control_policy(room_id)
        if mode == 'starter_only':
            req_user_id = str(user_info.get('user_id') or '').strip()
            allowed_starter = False
            if controller_user_id and req_user_id and controller_user_id == req_user_id:
                allowed_starter = True
            elif (not controller_user_id) and controller_username and str(username or '').strip() == controller_username:
                allowed_starter = True
            if not allowed_starter:
                logger.warning(
                    "[FLOW] %s_denied room=%s battle=%s slot=%s reason=starter_only user=%s",
                    event_name, room_id, battle_id, slot_id, username
                )
                emit(
                    'battle_error',
                    {
                        'message': 'starter_only permission denied',
                        'slot_id': slot_id,
                        'actor_id': actor_id
                    },
                    to=request.sid
                )
                return False
        return True

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
    return _pve_intents._is_actor_actionable(
        room_id,
        actor_id,
        get_room_state_fn=get_room_state,
        confusion_buff_cls=ConfusionBuff,
        immobilize_buff_cls=ImmobilizeBuff,
    )


def _canonical_team(raw_value):
    return _pve_intents._canonical_team(raw_value)


def _is_actor_targetable(room_id, actor_id):
    return _pve_intents._is_actor_targetable(room_id, actor_id, get_room_state_fn=get_room_state)


def _is_valid_single_target_slot_for_pve_enemy(room_id, state, source_slot_id, target_slot_id):
    return _pve_intents._is_valid_single_target_slot_for_pve_enemy(
        room_id,
        state,
        source_slot_id,
        target_slot_id,
        get_room_state_fn=get_room_state,
    )


def _pick_default_pve_enemy_target_slot(room_id, state, source_slot_id, preferred_slot_id=None):
    return _pve_intents._pick_default_pve_enemy_target_slot(
        room_id,
        state,
        source_slot_id,
        preferred_slot_id=preferred_slot_id,
        get_room_state_fn=get_room_state,
    )


def _is_pve_enemy_auto_target_slot(room_id, state, slot_id):
    return _pve_intents._is_pve_enemy_auto_target_slot(
        room_id,
        state,
        slot_id,
        get_room_state_fn=get_room_state,
    )


def _apply_pve_enemy_intent_defaults(
    room_id,
    state,
    slot_id,
    intent,
    intent_before=None,
    requested_skill_id=None,
    requested_target=None
):
    def _ai_suggest_skill(actor):
        from manager.battle.battle_ai import ai_suggest_skill
        return ai_suggest_skill(actor)

    return _pve_intents._apply_pve_enemy_intent_defaults(
        room_id,
        state,
        slot_id,
        intent,
        intent_before=intent_before,
        requested_skill_id=requested_skill_id,
        requested_target=requested_target,
        get_room_state_fn=get_room_state,
        normalize_target_by_skill_compat_fn=_normalize_target_by_skill_compat,
        default_intent_tags_fn=_default_intent_tags,
        build_tags_fn=_build_tags,
        ai_suggest_skill_fn=_ai_suggest_skill,
    )


def _required_slots(room_id, state):
    return _pve_intents._required_slots(
        room_id,
        state,
        get_room_state_fn=get_room_state,
        is_actor_actionable_fn=_is_actor_actionable,
    )


def _count_committed_required(required_slots, state):
    return _phase_flow._count_committed_required(required_slots, state)


def _commit_progress(room_id, state):
    return _phase_flow._commit_progress(room_id, state, required_slots_fn=_required_slots)


def _emit_battle_resolve_ready(room_id, battle_id, state, required_count, committed_count, waiting_slots):
    return _phase_flow._emit_battle_resolve_ready(
        room_id,
        battle_id,
        state,
        required_count,
        committed_count,
        waiting_slots,
        ctx=_phase_flow_context(),
    )


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


def _phase_flow_context():
    return {
        'broadcast_state_update': broadcast_state_update,
        'consume_mass_costs_on_resolve_start': _consume_mass_costs_on_resolve_start,
        'emit': emit,
        'emit_battle_state_updated': _emit_battle_state_updated,
        'emit_select_resolve_events': emit_select_resolve_events,
        'get_or_create_select_resolve_state': get_or_create_select_resolve_state,
        'is_select_phase': _is_select_phase,
        'log_battle_emit': _log_battle_emit,
        'logger': logger,
        'refresh_resolve_ready': _refresh_resolve_ready,
        'request_sid': request.sid,
        'required_slots': _required_slots,
        'run_select_resolve_auto': run_select_resolve_auto,
        'server_ts_ms': _server_ts_ms,
        'socketio': socketio,
    }


def _start_select_resolve_if_ready(room_id, battle_id, source_event):
    return _phase_flow._start_select_resolve_if_ready(
        room_id,
        battle_id,
        source_event,
        ctx=_phase_flow_context(),
    )


def _refresh_resolve_ready(room_id, state):
    return _phase_flow._refresh_resolve_ready(
        room_id,
        state,
        required_slots_fn=_required_slots,
    )


def _maybe_advance_phase_to_resolve_mass(room_id, battle_id, state):
    return _phase_flow._maybe_advance_phase_to_resolve_mass(
        room_id,
        battle_id,
        state,
        ctx=_phase_flow_context(),
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

    if not is_sid_in_room(request.sid, room_id):
        emit('battle_error', {'message': 'Not in this room'}, to=request.sid)
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
    # Ally-target skills are excluded from redirect in this route.
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

    room_state = get_room_state(room_id)
    if not isinstance(room_state, dict):
        emit('battle_error', {'message': 'room state not found'}, to=request.sid)
        return
    current_round = int(room_state.get('round', 0) or 0)
    # Stale/advanced client requests must not mutate server round state.
    if round_value != current_round:
        logger.warning(
            "[FLOW] battle_round_request_start_denied room=%s battle=%s requested_round=%s current_round=%s",
            room_id, battle_id, round_value, current_round
        )
        emit(
            'battle_error',
            {
                'message': 'stale or invalid round request',
                'requested_round': round_value,
                'current_round': current_round,
            },
            to=request.sid
        )
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
        allow_none=True
    )
    if target_error:
        emit('battle_error', {'message': target_error}, to=request.sid)
        return
    if not skill_id:
        emit('battle_error', {'message': 'commit requires skill_id'}, to=request.sid)
        return
    actor = _resolve_actor_for_slot(state, slot_id, room_id=room_id)
    access_eval = evaluate_skill_access(
        actor,
        skill_id,
        room_state=None,
        battle_state=state,
        slot_id=slot_id,
        allow_instant=False,
    )
    if not access_eval.get("usable", False):
        reasons = access_eval.get("blocked_reasons", [])
        message = str((reasons[0] if reasons else "このスキルは現在使用できません") or "このスキルは現在使用できません")
        emit('battle_error', {'message': message}, to=request.sid)
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
    intent['effective_cost'] = list(access_eval.get('effective_cost', []) or [])
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
    if not is_sid_in_room(request.sid, room_id):
        emit('battle_error', {'message': 'Not in this room'}, to=request.sid)
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
    if not is_sid_in_room(request.sid, room_id):
        emit('battle_error', {'message': 'Not in this room'}, to=request.sid)
        return

    user_info = get_user_info_from_sid(request.sid) or {}
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")
    is_battle_only = _is_battle_only_mode(room_id)
    if attribute != 'GM' and not is_battle_only:
        logger.info(
            "[FLOW] resolve_flow_advance_denied room=%s user=%s attr=%s battle_only=%s",
            room_id, username, attribute, is_battle_only
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
    next_skill_id = data.get('skill_id')
    actor = _resolve_actor_for_slot(state, slot_id, room_id=room_id)
    if next_skill_id:
        access_eval = evaluate_skill_access(
            actor,
            next_skill_id,
            room_state=None,
            battle_state=state,
            slot_id=slot_id,
            allow_instant=False,
        )
        if not access_eval.get("usable", False):
            reasons = access_eval.get("blocked_reasons", [])
            message = str((reasons[0] if reasons else "このスキルは現在使用できません") or "このスキルは現在使用できません")
            emit('battle_error', {'message': message}, to=request.sid)
            return
        intent['effective_cost'] = list(access_eval.get('effective_cost', []) or [])
    else:
        intent.pop('effective_cost', None)
    intent['skill_id'] = next_skill_id
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

