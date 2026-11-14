# events/socket_battle_only.py
import copy, json, random, time
from datetime import datetime, timezone
from flask import request
from extensions import socketio, user_sids
from manager.units.characters import build_character, skill_catalog
from manager.units.runtime import deployment_store, draft_reference_failures, record_map, visible_records
from manager.game_logic import process_battle_start
from manager.room_access import GM_ROLES
from manager.room_manager import (
    broadcast_log,
    broadcast_state_update,
    get_room_state,
    get_user_info_from_sid,
    save_specific_room_state,
    set_character_owner,
)
from manager.utils import apply_passive_effect_buffs
from events.battle_only.catalog_state import (
    _apply_start_draft_payload,
    _ally_entries_from_formation_record,
    _count_room_allies,
    _enemy_entries_from_formation_record,
    _ensure_bo_state,
    _estimate_battle_result,
    _finalize_active_record,
    _find_record,
    _get_records,
    _normalize_ally_entries as _catalog_normalize_ally_entries,
    _normalize_enemy_entries,
    _normalize_optional_id,
    _normalize_stage_avatar,
    _normalize_stage_field_effect_profile,
    _sort_named_ids,
    _sort_stage_ids,
    _validate_battle_only_entry,
)
from events.battle_only.catalog_access_context import catalog_request_context as _catalog_request_context
from manager.battle_only_runtime import (
    _bo_assign_auto_positions,
    _force_character_side,
    _reset_runtime_battle_state,
    _start_battle_only_round,
)
def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
def _now_ms(): return int(time.time() * 1000)
def _now_iso(): return datetime.now(timezone.utc).isoformat()
def _new_id(prefix): return f"{prefix}_{_now_ms()}_{random.randint(1000, 9999)}"
def _emit_error(error_code, message, event_name='bo_catalog_error', extra=None):
    payload = {
        "error": str(error_code or "unknown_error"),
        "message": str(message or "operation failed"),
    }
    if isinstance(extra, dict):
        payload.update(extra)
    socketio.emit(event_name, payload, to=request.sid)


def _is_gm(user_info):
    return str((user_info or {}).get('attribute', '')).strip().upper() == 'GM'


def _require_room_gm_context(data, event_name='bo_draft_error'):
    context = _catalog_request_context(data)
    if context.get('room') and context.get('room_role') in GM_ROLES:
        return True, context
    _emit_error('permission_denied', '対象ルームのowner・gm権限が必要です。', event_name=event_name)
    return False, context


def _require_room_participant(room, event_name='bo_draft_error'):
    target_room = str(room or '').strip()
    if not target_room:
        _emit_error('missing_room', 'room は必須です。', event_name=event_name)
        return False, get_user_info_from_sid(request.sid)
    user_info = get_user_info_from_sid(request.sid)
    room_from_sid = ''
    sid_entry = user_sids.get(request.sid) if isinstance(user_sids, dict) else None
    if isinstance(sid_entry, dict):
        room_from_sid = str(sid_entry.get('room', '')).strip()
    if room_from_sid and room_from_sid == target_room:
        return True, user_info
    user_id = str((user_info or {}).get('user_id', '')).strip()
    if user_id and _find_username_by_user_id(target_room, user_id):
        return True, user_info
    if _is_gm(user_info):
        return True, user_info
    _emit_error('permission_denied', 'このルームの参加者のみ実行できます。', event_name=event_name)
    return False, user_info


def _room_users(room):
    result = []
    for _, info in user_sids.items():
        if not isinstance(info, dict):
            continue
        if str(info.get('room', '')).strip() != str(room):
            continue
        result.append({
            "user_id": str(info.get('user_id', '')).strip() or None,
            "username": str(info.get('username', '')).strip() or '',
            "attribute": str(info.get('attribute', '')).strip() or '',
        })
    result.sort(key=lambda row: row.get('username', ''))
    return result


def _find_username_by_user_id(room, user_id):
    target_id = str(user_id or '').strip()
    if not target_id:
        return None
    for _, info in user_sids.items():
        if not isinstance(info, dict):
            continue
        if str(info.get('room', '')).strip() != str(room):
            continue
        if str(info.get('user_id', '')).strip() != target_id:
            continue
        name = str(info.get('username', '')).strip()
        if name:
            return name
    return None


def _normalize_ally_entries(entries, presets, validate_user_ids=False, room=None):
    return _catalog_normalize_ally_entries(
        entries, presets, validate_user_ids=validate_user_ids, room=room,
        user_lookup=_find_username_by_user_id,
    )

@socketio.on('request_bo_select_enemy_formation')
def handle_bo_select_enemy_formation(data):
    room = str((data or {}).get('room', '')).strip()
    if not room:
        _emit_error('missing_room', 'room は必須です。', event_name='bo_draft_error')
        return
    allowed, user_info = _require_room_gm_context(data)
    if not allowed:
        return
    formation_id = str((data or {}).get('formation_id', '')).strip()
    if not formation_id:
        _emit_error('invalid_request', 'formation_id は必須です。', event_name='bo_draft_error')
        return

    store = deployment_store()
    formations = record_map(store, "enemy_formation")
    record = formations.get(formation_id)
    if not isinstance(record, dict):
        _emit_error('not_found', '敵編成が見つかりません。', event_name='bo_draft_error', extra={"id": formation_id})
        return

    state = get_room_state(room)
    bo = _ensure_bo_state(state)
    bo['selected_stage_id'] = None
    bo['enemy_formation_id'] = formation_id
    bo['enemy_entries'] = _enemy_entries_from_formation_record(record)
    recommended = max(0, _safe_int(record.get('recommended_ally_count'), 0))
    bo['required_ally_count'] = recommended
    bo['status'] = 'draft'
    state['play_mode'] = 'battle_only'

    save_specific_room_state(room)
    broadcast_state_update(room)
    socketio.emit(
        'bo_enemy_formation_selected',
        {
            "formation_id": formation_id,
            "enemy_entries": copy.deepcopy(bo.get('enemy_entries', [])),
            "battle_only": copy.deepcopy(bo),
        },
        to=request.sid
    )


@socketio.on('request_bo_select_ally_formation')
def handle_bo_select_ally_formation(data):
    room = str((data or {}).get('room', '')).strip()
    if not room:
        _emit_error('missing_room', 'room は必須です。', event_name='bo_draft_error')
        return
    allowed, user_info = _require_room_gm_context(data)
    if not allowed:
        return
    formation_id = str((data or {}).get('formation_id', '')).strip()
    if not formation_id:
        _emit_error('invalid_request', 'formation_id は必須です。', event_name='bo_draft_error')
        return

    store = deployment_store()
    formations = record_map(store, "ally_formation")
    record = formations.get(formation_id)
    if not isinstance(record, dict):
        _emit_error('not_found', '味方編成が見つかりません。', event_name='bo_draft_error', extra={"id": formation_id})
        return

    state = get_room_state(room)
    bo = _ensure_bo_state(state)
    bo['selected_stage_id'] = None
    bo['ally_formation_id'] = formation_id
    bo['ally_entries'] = _ally_entries_from_formation_record(record)
    bo['required_ally_count'] = max(0, _safe_int(record.get('recommended_ally_count'), 0))
    bo['ally_mode'] = 'preset'
    bo['status'] = 'draft'
    state['play_mode'] = 'battle_only'

    save_specific_room_state(room)
    broadcast_state_update(room)
    socketio.emit(
        'bo_ally_formation_selected',
        {
            "formation_id": formation_id,
            "ally_entries": copy.deepcopy(bo.get('ally_entries', [])),
            "battle_only": copy.deepcopy(bo),
        },
        to=request.sid
    )


@socketio.on('request_bo_select_stage_preset')
def handle_bo_select_stage_preset(data):
    room = str((data or {}).get('room', '')).strip()
    if not room:
        _emit_error('missing_room', 'room は必須です。', event_name='bo_draft_error')
        return
    allowed, user_info = _require_room_participant(room, event_name='bo_draft_error')
    if not allowed:
        return
    context = _catalog_request_context(data)
    if context.get('room_role') not in GM_ROLES:
        _emit_error('permission_denied', 'ステージ配置にはルームowner・gm権限が必要です。', event_name='bo_draft_error')
        return
    stage_id = str((data or {}).get('stage_id', '')).strip()
    if not stage_id:
        _emit_error('invalid_request', 'stage_id は必須です。', event_name='bo_draft_error')
        return

    store = deployment_store()
    stages = record_map(store, "stage")
    enemy_formations = record_map(store, "enemy_formation")
    ally_formations = record_map(store, "ally_formation")
    stage = stages.get(stage_id)
    if not isinstance(stage, dict):
        _emit_error('not_found', 'ステージが見つかりません。', event_name='bo_draft_error', extra={"id": stage_id})
        return

    enemy_formation_id = str(stage.get('enemy_formation_id', '')).strip()
    enemy_rec = enemy_formations.get(enemy_formation_id)
    if not isinstance(enemy_rec, dict):
        _emit_error('invalid_stage', f'ステージが参照する敵編成が見つかりません: {enemy_formation_id}', event_name='bo_draft_error')
        return

    ally_formation_id = _normalize_optional_id(stage.get('ally_formation_id', ''))
    ally_rec = None
    if ally_formation_id:
        ally_rec = ally_formations.get(ally_formation_id)
        if not isinstance(ally_rec, dict):
            _emit_error('invalid_stage', f'ステージが参照する味方編成が見つかりません: {ally_formation_id}', event_name='bo_draft_error')
            return

    state = get_room_state(room)
    bo = _ensure_bo_state(state)
    bo['selected_stage_id'] = stage_id
    bo['enemy_formation_id'] = enemy_formation_id
    bo['enemy_entries'] = _enemy_entries_from_formation_record(enemy_rec)
    bo['ally_formation_id'] = ally_formation_id
    bo['ally_entries'] = _ally_entries_from_formation_record(ally_rec) if isinstance(ally_rec, dict) else []
    bo['required_ally_count'] = max(0, _safe_int(stage.get('required_ally_count'), 0))
    if bo['required_ally_count'] <= 0:
        bo['required_ally_count'] = max(0, _safe_int(enemy_rec.get('recommended_ally_count'), 0))
    bo['stage_field_effect_profile'] = _normalize_stage_field_effect_profile(stage.get('field_effect_profile'))
    stage_avatar_profile = _normalize_stage_avatar(stage.get('stage_avatar'))
    bo['stage_avatar_profile'] = stage_avatar_profile
    bo['stage_field_effect_enabled'] = bool(bo.get('stage_field_effect_enabled', True))
    bo['stage_avatar_enabled'] = bool(stage_avatar_profile.get('enabled', True))
    bo['ally_mode'] = 'preset'
    bo['status'] = 'draft'
    state['play_mode'] = 'battle_only'

    save_specific_room_state(room)
    broadcast_state_update(room)
    socketio.emit(
        'bo_stage_preset_selected',
        {
            "stage_id": stage_id,
            "battle_only": copy.deepcopy(bo),
            "stage_preset": copy.deepcopy(stage),
        },
        to=request.sid
    )


@socketio.on('request_bo_set_ally_mode')
def handle_bo_set_ally_mode(data):
    room = str((data or {}).get('room', '')).strip()
    if not room:
        _emit_error('missing_room', 'room は必須です。', event_name='bo_draft_error')
        return
    allowed, _ = _require_room_gm_context(data)
    if not allowed:
        return
    mode = str((data or {}).get('ally_mode', '')).strip().lower()
    if mode not in ('preset', 'room_existing'):
        _emit_error('invalid_payload', 'ally_mode が不正です。', event_name='bo_draft_error')
        return
    required_ally_count = max(0, _safe_int((data or {}).get('required_ally_count'), 0))

    state = get_room_state(room)
    bo = _ensure_bo_state(state)
    bo['ally_mode'] = mode
    bo['required_ally_count'] = required_ally_count
    bo['status'] = 'draft'
    state['play_mode'] = 'battle_only'

    save_specific_room_state(room)
    broadcast_state_update(room)
    socketio.emit('bo_ally_mode_updated', {"battle_only": copy.deepcopy(bo)}, to=request.sid)


@socketio.on('request_bo_set_stage_field_effect_enabled')
def handle_bo_set_stage_field_effect_enabled(data):
    room = str((data or {}).get('room', '')).strip()
    if not room:
        _emit_error('missing_room', 'room は必須です。', event_name='bo_draft_error')
        return
    allowed, _ = _require_room_gm_context(data)
    if not allowed:
        return

    enabled = bool((data or {}).get('enabled', True))
    state = get_room_state(room)
    bo = _ensure_bo_state(state)
    bo['stage_field_effect_enabled'] = enabled
    bo['status'] = 'draft'
    state['play_mode'] = 'battle_only'
    save_specific_room_state(room)
    broadcast_state_update(room)
    socketio.emit('bo_stage_field_effect_updated', {"battle_only": copy.deepcopy(bo)}, to=request.sid)


@socketio.on('request_bo_set_stage_avatar_enabled')
def handle_bo_set_stage_avatar_enabled(data):
    room = str((data or {}).get('room', '')).strip()
    if not room:
        _emit_error('missing_room', 'room は必須です。', event_name='bo_draft_error')
        return
    allowed, _ = _require_room_gm_context(data)
    if not allowed:
        return

    enabled = bool((data or {}).get('enabled', True))
    state = get_room_state(room)
    bo = _ensure_bo_state(state)
    bo['stage_avatar_enabled'] = enabled
    bo['status'] = 'draft'
    state['play_mode'] = 'battle_only'
    save_specific_room_state(room)
    broadcast_state_update(room)
    socketio.emit('bo_stage_avatar_updated', {"battle_only": copy.deepcopy(bo)}, to=request.sid)


@socketio.on('request_bo_set_control_mode')
def handle_bo_set_control_mode(data):
    room = str((data or {}).get('room', '')).strip()
    if not room:
        _emit_error('missing_room', 'room は必須です。', event_name='bo_draft_error')
        return
    allowed, _ = _require_room_gm_context(data)
    if not allowed:
        return

    mode = str((data or {}).get('intent_control_mode', '')).strip().lower()
    if mode not in ('all', 'starter_only'):
        _emit_error('invalid_payload', 'intent_control_mode が不正です。', event_name='bo_draft_error')
        return

    state = get_room_state(room)
    bo = _ensure_bo_state(state)
    options = bo.get('options') if isinstance(bo.get('options'), dict) else {}
    bo['options'] = options
    bo['options']['intent_control_mode'] = mode

    save_specific_room_state(room)
    broadcast_state_update(room)
    socketio.emit('bo_control_mode_updated', {"battle_only": copy.deepcopy(bo)}, to=request.sid)


@socketio.on('request_bo_validate_entry')
def handle_bo_validate_entry(data):
    room = str((data or {}).get('room', '')).strip()
    if not room:
        _emit_error('missing_room', 'room は必須です。', event_name='bo_draft_error')
        return
    allowed, _ = _require_room_gm_context(data)
    if not allowed:
        return

    state = get_room_state(room)
    bo = _ensure_bo_state(state)
    save_specific_room_state(room)
    store = deployment_store()
    presets = record_map(store, "character")
    failures = draft_reference_failures(store, bo)
    if failures:
        refs = ' / '.join(row['message'] for row in failures)
        _emit_error('unavailable_reference', f'利用できない参照があります: {refs}',
                    event_name='bo_draft_error', extra={"references": failures})
        return
    validation = _validate_battle_only_entry(state, bo, presets)
    payload = {
        **validation,
        "battle_only": copy.deepcopy(bo),
    }
    socketio.emit('bo_entry_validated', payload, to=request.sid)


@socketio.on('request_bo_draft_state')
def handle_bo_draft_state(data):
    room = str((data or {}).get('room', '')).strip()
    if not room:
        _emit_error('missing_room', 'room は必須です。', event_name='bo_draft_error')
        return

    state = get_room_state(room)
    bo = _ensure_bo_state(state)
    save_specific_room_state(room)
    users = _room_users(room)
    context = _catalog_request_context(data)
    store = deployment_store()
    visible = visible_records(record_map(store, "character"), is_author=context["is_author"], room_role=context["room_role"])
    visible_formations = visible_records(record_map(store, "enemy_formation"), is_author=context["is_author"], room_role=context["room_role"])
    visible_ally_formations = visible_records(record_map(store, "ally_formation"), is_author=context["is_author"], room_role=context["room_role"])
    visible_stage_presets = visible_records(record_map(store, "stage"), is_author=context["is_author"], room_role=context["room_role"])
    bo_payload = copy.deepcopy(bo)
    if context.get('room_role') not in GM_ROLES:
        bo_payload.pop('preset_bookmarks', None)
    payload = {
        "battle_only": bo_payload,
        "users": users,
        "presets": visible,
        "sorted_ids": _sort_named_ids(visible),
        "enemy_formations": visible_formations,
        "sorted_enemy_formation_ids": _sort_named_ids(visible_formations),
        "ally_formations": visible_ally_formations,
        "sorted_ally_formation_ids": _sort_named_ids(visible_ally_formations),
        "stage_presets": visible_stage_presets,
        "sorted_stage_preset_ids": _sort_stage_ids(visible_stage_presets),
        "records": copy.deepcopy(_get_records(bo)),
        "active_record_id": str(bo.get('active_record_id', '')).strip() or None,
        "can_manage": context.get('room_role') in GM_ROLES,
    }
    socketio.emit('bo_draft_state', payload, to=request.sid)


@socketio.on('request_bo_draft_update')
def handle_bo_draft_update(data):
    room = str((data or {}).get('room', '')).strip()
    if not room:
        _emit_error('missing_room', 'room は必須です。', event_name='bo_draft_error')
        return
    allowed, _ = _require_room_gm_context(data)
    if not allowed:
        return

    payload = (data or {}).get('payload') if isinstance((data or {}).get('payload'), dict) else {}
    state = get_room_state(room)
    bo = _ensure_bo_state(state)
    store = deployment_store()
    presets = record_map(store, "character")

    try:
        ally_entries = _normalize_ally_entries(payload.get('ally_entries'), presets, validate_user_ids=False, room=room)
        enemy_entries = _normalize_enemy_entries(payload.get('enemy_entries'), presets)
    except ValueError as ex:
        _emit_error('invalid_payload', str(ex), event_name='bo_draft_error')
        return

    ally_mode = str(payload.get('ally_mode', bo.get('ally_mode', 'preset'))).strip().lower() or 'preset'
    if ally_mode not in ('preset', 'room_existing'):
        _emit_error('invalid_payload', 'ally_mode が不正です。', event_name='bo_draft_error')
        return
    required_ally_count = max(0, _safe_int(payload.get('required_ally_count', bo.get('required_ally_count', 0)), 0))
    enemy_formation_id = _normalize_optional_id(payload.get('enemy_formation_id', bo.get('enemy_formation_id')))
    ally_formation_id = _normalize_optional_id(payload.get('ally_formation_id', bo.get('ally_formation_id')))
    selected_stage_id = _normalize_optional_id(payload.get('selected_stage_id', bo.get('selected_stage_id')))
    intent_control_mode = str(
        payload.get(
            'intent_control_mode',
            (bo.get('options', {}) if isinstance(bo.get('options'), dict) else {}).get('intent_control_mode', 'all')
        )
    ).strip().lower() or 'all'
    if intent_control_mode not in ('all', 'starter_only'):
        _emit_error('invalid_payload', 'intent_control_mode が不正です。', event_name='bo_draft_error')
        return

    bo['ally_mode'] = ally_mode
    bo['required_ally_count'] = required_ally_count
    bo['enemy_formation_id'] = enemy_formation_id
    bo['ally_formation_id'] = ally_formation_id
    bo['selected_stage_id'] = selected_stage_id
    if 'stage_field_effect_enabled' in payload:
        bo['stage_field_effect_enabled'] = bool(payload.get('stage_field_effect_enabled'))
    if 'stage_avatar_enabled' in payload:
        bo['stage_avatar_enabled'] = bool(payload.get('stage_avatar_enabled'))
    bo['ally_entries'] = ally_entries
    bo['enemy_entries'] = enemy_entries
    bo['status'] = 'draft'
    options = bo.get('options') if isinstance(bo.get('options'), dict) else {}
    bo['options'] = options
    bo['options']['intent_control_mode'] = intent_control_mode
    state['play_mode'] = 'battle_only'

    save_specific_room_state(room)
    broadcast_state_update(room)
    socketio.emit('bo_draft_updated', {"battle_only": copy.deepcopy(bo)}, to=request.sid)


@socketio.on('request_bo_start_battle')
def handle_bo_start_battle(data):
    room = str((data or {}).get('room', '')).strip()
    if not room:
        _emit_error('missing_room', 'room は必須です。', event_name='bo_draft_error')
        return
    allowed, user_info = _require_room_participant(room, event_name='bo_draft_error')
    if not allowed:
        return
    manager_allowed, _ = _require_room_gm_context(data)
    if not manager_allowed:
        return

    state = get_room_state(room)
    bo = _ensure_bo_state(state)
    store = deployment_store()
    presets = record_map(store, "character")
    # 開始要求に同梱された画面上の最新編成を、このイベント内で確定させる。
    draft_payload = (data or {}).get('draft_payload')
    if isinstance(draft_payload, dict):
        try:
            _apply_start_draft_payload(bo, draft_payload, presets, room)
        except ValueError as ex:
            _emit_error('invalid_payload', str(ex), event_name='bo_draft_error')
            return

    failures = draft_reference_failures(store, bo)
    if failures:
        refs = ' / '.join(row['message'] for row in failures)
        _emit_error('unavailable_reference', f'利用できない参照があります: {refs}',
                    event_name='bo_draft_error', extra={"references": failures})
        return

    ally_mode = str(bo.get('ally_mode', 'preset') or 'preset').strip().lower()
    if ally_mode not in ('preset', 'room_existing'):
        ally_mode = 'preset'
    required_ally_count = max(0, _safe_int(bo.get('required_ally_count'), 0))

    try:
        enemy_entries = _normalize_enemy_entries(bo.get('enemy_entries'), presets)
    except ValueError as ex:
        _emit_error('invalid_payload', str(ex), event_name='bo_draft_error')
        return
    if len(enemy_entries) == 0:
        _emit_error('missing_enemy', '敵編成が空です。', event_name='bo_draft_error')
        return

    ally_entries = []
    source_room_allies = []
    if ally_mode == 'preset':
        try:
            ally_entries = _normalize_ally_entries(bo.get('ally_entries'), presets, validate_user_ids=False, room=room)
        except ValueError as ex:
            _emit_error('invalid_payload', str(ex), event_name='bo_draft_error')
            return
        if len(ally_entries) == 0:
            _emit_error('missing_ally', '味方編成が空です。', event_name='bo_draft_error')
            return
    else:
        source_room_allies = [
            copy.deepcopy(c)
            for c in (state.get('characters') or [])
            if isinstance(c, dict) and str(c.get('type', '')).strip().lower() == 'ally'
        ]
        if required_ally_count <= 0:
            _emit_error('missing_required_ally_count', '現在ルーム利用時は必要味方人数の指定が必要です。', event_name='bo_draft_error')
            return
        if len(source_room_allies) != required_ally_count:
            _emit_error(
                'ally_count_mismatch',
                f'現在ルームの味方人数が不一致です。必要:{required_ally_count} / 現在:{len(source_room_allies)}',
                event_name='bo_draft_error'
            )
            return

    masters = skill_catalog()
    # 実行用コピーを作れることを先に検証し、途中までルーム状態を消さない。
    try:
        serial_probe = 1
        for row in ally_entries:
            build_character(presets[row['preset_id']], 'ally', serial_probe, masters=masters)
            serial_probe += 1
        for row in enemy_entries:
            for _ in range(max(0, _safe_int(row.get('count'), 0))):
                build_character(presets[row['preset_id']], 'enemy', serial_probe, pattern_id=row.get('pattern_id'), masters=masters)
                serial_probe += 1
    except (KeyError, ValueError) as ex:
        _emit_error('invalid_preset', f'実行用キャラクターを構築できません: {ex}', event_name='bo_draft_error')
        return

    _finalize_active_record(bo, forced_result='aborted', reason='restarted')

    _reset_runtime_battle_state(state)

    serial = 1
    built_ally_rows = []
    built_enemy_rows = []
    built_ally_chars = []
    built_enemy_chars = []

    if ally_mode == 'preset':
        for row in ally_entries:
            rec = presets.get(row.get('preset_id'))
            if not isinstance(rec, dict):
                _emit_error('not_found', f"味方プリセットが見つかりません: {row.get('preset_id')}", event_name='bo_draft_error')
                return
            try:
                ally_char = build_character(rec, 'ally', serial, masters=masters)
            except ValueError as ex:
                _emit_error('invalid_preset', f"{row.get('preset_id')}: {ex}", event_name='bo_draft_error')
                return
            serial += 1
            user_id = str(row.get('user_id', '')).strip()
            owner_name = _find_username_by_user_id(room, user_id)
            if not owner_name:
                owner_name = str(user_info.get('username', 'GM') or 'GM')
                if not user_id:
                    user_id = str(user_info.get('user_id', '') or '')
            ally_char['owner'] = owner_name
            ally_char['owner_id'] = user_id or None
            state['characters'].append(ally_char)
            built_ally_chars.append(ally_char)
            set_character_owner(room, ally_char['id'], owner_name)
            built_ally_rows.append({
                "source": "preset",
                "preset_id": str(rec.get('id', '')).strip(),
                "preset_name": str(rec.get('name', '')).strip() or str(rec.get('id', '')).strip(),
                "user_id": user_id or None,
                "username": owner_name,
            })
    else:
        for raw_char in source_room_allies:
            ally_char = copy.deepcopy(raw_char)
            char_id = str(ally_char.get('id', '')).strip()
            if not char_id:
                char_id = f"char_bo_{_now_ms()}_{random.randint(1000, 9999)}_{int(serial)}"
                ally_char['id'] = char_id
                serial += 1
            _force_character_side(ally_char, 'ally')
            owner_name = str(ally_char.get('owner', '')).strip() or str(user_info.get('username', 'GM') or 'GM')
            owner_id = str(ally_char.get('owner_id', '')).strip() or None
            ally_char['owner'] = owner_name
            ally_char['owner_id'] = owner_id
            state['characters'].append(ally_char)
            built_ally_chars.append(ally_char)
            set_character_owner(room, char_id, owner_name)
            built_ally_rows.append({
                "source": "room_existing",
                "char_id": char_id,
                "name": str(ally_char.get('name', '')).strip() or char_id,
                "user_id": owner_id,
                "username": owner_name,
                "x": _safe_int(ally_char.get('x'), -1),
                "y": _safe_int(ally_char.get('y'), -1),
            })

    for row in enemy_entries:
        rec = presets.get(row.get('preset_id'))
        if not isinstance(rec, dict):
            _emit_error('not_found', f"敵プリセットが見つかりません: {row.get('preset_id')}", event_name='bo_draft_error')
            return
        count = max(0, _safe_int(row.get('count'), 0))
        if count <= 0:
            continue
        for _ in range(count):
            try:
                enemy_char = build_character(rec, 'enemy', serial, pattern_id=row.get('pattern_id'), masters=masters)
            except ValueError as ex:
                _emit_error('invalid_preset', f"{row.get('preset_id')}: {ex}", event_name='bo_draft_error')
                return
            serial += 1
            state['characters'].append(enemy_char)
            built_enemy_chars.append(enemy_char)
        built_enemy_rows.append({
            "preset_id": str(rec.get('id', '')).strip(),
            "preset_name": str(rec.get('name', '')).strip() or str(rec.get('id', '')).strip(),
            "count": count,
            "pattern_id": row.get("pattern_id"),
        })

    anchor = (data or {}).get('anchor') if isinstance((data or {}).get('anchor'), dict) else None
    if ally_mode == 'preset':
        _bo_assign_auto_positions(built_ally_chars, built_enemy_chars, state, anchor=anchor)
    else:
        _bo_assign_auto_positions([], built_enemy_chars, state, anchor=anchor)

    for char in state.get('characters', []):
        apply_passive_effect_buffs(char)
        process_battle_start(room, char)

    bo['ally_entries'] = ally_entries
    bo['enemy_entries'] = enemy_entries
    bo['status'] = 'in_battle'
    bo['pending_auto_reset'] = False
    bo['pending_auto_reset_round'] = None
    bo['ally_mode'] = ally_mode
    bo['selected_stage_id'] = _normalize_optional_id(bo.get('selected_stage_id'))
    bo['required_ally_count'] = required_ally_count
    stage_profile = _normalize_stage_field_effect_profile(bo.get('stage_field_effect_profile'))
    stage_avatar_profile = _normalize_stage_avatar(bo.get('stage_avatar_profile'))
    stage_effect_enabled = bool(bo.get('stage_field_effect_enabled', True))
    stage_avatar_enabled = bool(bo.get('stage_avatar_enabled', True))
    state['stage_field_effect_profile'] = copy.deepcopy(stage_profile)
    state['stage_avatar_profile'] = copy.deepcopy(stage_avatar_profile)
    state['stage_avatar_enabled'] = stage_avatar_enabled
    state['field_effects'] = []
    if stage_effect_enabled:
        state['field_effects'] = [
            {
                "field_id": str(rule.get('rule_id') or f"stage_rule_{idx + 1}"),
                "source_type": "stage_preset",
                "source_id": str(bo.get('selected_stage_id') or ''),
                "rule": copy.deepcopy(rule),
            }
            for idx, rule in enumerate(stage_profile.get('rules', []))
            if isinstance(rule, dict)
        ]
    requested_control_mode = str((data or {}).get('intent_control_mode', '')).strip().lower()
    if requested_control_mode not in ('all', 'starter_only'):
        requested_control_mode = str((bo.get('options', {}) if isinstance(bo.get('options'), dict) else {}).get('intent_control_mode', 'all')).strip().lower()
    if requested_control_mode not in ('all', 'starter_only'):
        requested_control_mode = 'all'
    bo['options'] = {
        "force_pve": True,
        "show_enemy_target_arrows": True,
        "intent_control_mode": requested_control_mode,
    }
    bo['controller_user_id'] = str(user_info.get('user_id', '')).strip() or None
    bo['controller_username'] = str(user_info.get('username', '')).strip() or None
    state['play_mode'] = 'battle_only'

    record_id = _new_id('bor')
    record = {
        "id": record_id,
        "room_id": room,
        "battle_id": f"battle_{room}",
        "status": "in_battle",
        "result": None,
        "started_at": _now_iso(),
        "ended_at": None,
        "config": {
            "selected_stage_id": bo.get('selected_stage_id'),
            "stage_field_effect_enabled": stage_effect_enabled,
            "stage_field_effect_profile": copy.deepcopy(stage_profile),
            "stage_avatar_enabled": stage_avatar_enabled,
            "stage_avatar_profile": copy.deepcopy(stage_avatar_profile),
            "ally_mode": ally_mode,
            "ally_formation_id": bo.get('ally_formation_id'),
            "required_ally_count": required_ally_count,
            "enemy_formation_id": bo.get('enemy_formation_id'),
            "options": copy.deepcopy(bo.get('options', {})),
            "ally_entries": built_ally_rows,
            "enemy_entries": built_enemy_rows,
        },
        "ally_count": len([c for c in state.get('characters', []) if str(c.get('type', '')).strip().lower() == 'ally']),
        "enemy_count": len([c for c in state.get('characters', []) if str(c.get('type', '')).strip().lower() == 'enemy']),
    }
    records = _get_records(bo)
    records.append(record)
    bo['active_record_id'] = record_id

    broadcast_log(
            room,
            f"[BattleOnly] Stage field effects active: {len(state.get('field_effects', []))} rules (source=stage).",
            'info'
        )
    broadcast_log(room, "[BattleOnly] 戦闘専用編成で戦闘に突入しました。", 'info')
    try:
        _start_battle_only_round(room, user_info)
    except Exception as ex:
        _emit_error('round_start_failed', f'戦闘突入後のラウンド開始に失敗しました: {ex}', event_name='bo_draft_error')

    socketio.emit(
        'bo_battle_started',
        {
            "ally_count": record.get('ally_count'),
            "enemy_count": record.get('enemy_count'),
            "record_id": record_id,
            "battle_id": record.get('battle_id'),
        },
        to=request.sid
    )


@socketio.on('request_bo_record_state')
def handle_bo_record_state(data):
    room = str((data or {}).get('room', '')).strip()
    if not room:
        _emit_error('missing_room', 'room は必須です。', event_name='bo_draft_error')
        return

    state = get_room_state(room)
    bo = _ensure_bo_state(state)
    payload = {
        "records": copy.deepcopy(_get_records(bo)),
        "active_record_id": str(bo.get('active_record_id', '')).strip() or None,
        "status": str(bo.get('status', '')).strip() or 'lobby',
    }
    socketio.emit('bo_record_state', payload, to=request.sid)


@socketio.on('request_bo_record_mark_result')
def handle_bo_record_mark_result(data):
    room = str((data or {}).get('room', '')).strip()
    if not room:
        _emit_error('missing_room', 'room は必須です。', event_name='bo_draft_error')
        return
    allowed, _ = _require_room_gm_context(data)
    if not allowed:
        return

    state = get_room_state(room)
    bo = _ensure_bo_state(state)
    rec, resolved_id = _find_record(bo, record_id=(data or {}).get('record_id'))
    if not isinstance(rec, dict):
        _emit_error('not_found', '戦績が見つかりません。', event_name='bo_draft_error', extra={"id": resolved_id})
        return

    raw_result = str((data or {}).get('result', '')).strip().lower()
    allowed_results = {'ally_win', 'enemy_win', 'draw', 'aborted', 'unknown', 'auto'}
    if raw_result not in allowed_results:
        _emit_error('invalid_result', 'result が不正です。', event_name='bo_draft_error')
        return
    result = _estimate_battle_result(state) if raw_result == 'auto' else raw_result
    if result == 'in_progress':
        result = 'unknown'
    rec['status'] = 'finished'
    rec['result'] = result
    rec['ended_at'] = _now_iso()
    note = str((data or {}).get('note', '')).strip()
    if note:
        rec['note'] = note
    if str(bo.get('active_record_id', '')).strip() == str(rec.get('id', '')).strip():
        bo['active_record_id'] = None
        bo['status'] = 'draft'

    save_specific_room_state(room)
    broadcast_state_update(room)
    socketio.emit(
        'bo_record_updated',
        {
            "record_id": rec.get('id'),
            "record": copy.deepcopy(rec),
            "active_record_id": bo.get('active_record_id'),
        },
        to=request.sid
    )


@socketio.on("request_bo_record_export")
def handle_bo_record_export(data):
    context = _catalog_request_context(data)
    room = context.get("room")
    if not room or not context.get("room_role"):
        socketio.emit(
            "bo_draft_error",
            {"error": "permission_denied", "message": "対象ルームの参加者だけが出力できます。"},
            to=request.sid,
        )
        return
    state = get_room_state(room)
    bo = _ensure_bo_state(state)
    records = copy.deepcopy(_get_records(bo))
    payload = {
        "room": room,
        "play_mode": str(state.get("play_mode", "normal")),
        "exported_at": _now_iso(),
        "battle_only": {
            "status": bo.get("status"),
            "active_record_id": bo.get("active_record_id"),
            "selected_stage_id": bo.get("selected_stage_id"),
            "ally_formation_id": bo.get("ally_formation_id"),
            "enemy_formation_id": bo.get("enemy_formation_id"),
            "required_ally_count": bo.get("required_ally_count"),
            "ally_entries": copy.deepcopy(bo.get("ally_entries", [])),
            "enemy_entries": copy.deepcopy(bo.get("enemy_entries", [])),
        },
        "records": records,
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    socketio.emit(
        "bo_record_export",
        {
            "filename": f"battle_only_records_{room.replace(' ', '_')}_{int(time.time())}.json",
            "content": content,
            "record_count": len(records),
        },
        to=request.sid,
    )
