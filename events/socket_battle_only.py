# events/socket_battle_only.py
import copy
import json
import random
import time
from datetime import datetime, timezone

from flask import request

from extensions import socketio, user_sids
from manager.battle_only_presets import load_store as load_bo_preset_store
from manager.battle_only_presets import mutate_store as mutate_bo_preset_store
from manager.game_logic import process_battle_start
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
    _ally_entries_from_formation_record,
    _count_room_allies,
    _enemy_entries_from_formation_record,
    _ensure_bo_state,
    _estimate_battle_result,
    _filter_visible_presets,
    _filter_visible_rows_by_visibility,
    _finalize_active_record,
    _find_record,
    _get_records,
    _normalize_ally_formation_record,
    _normalize_ally_entries as _catalog_normalize_ally_entries,
    _normalize_enemy_formation_record,
    _normalize_enemy_entries,
    _normalize_optional_id,
    _normalize_preset_record,
    _normalize_stage_avatar,
    _normalize_stage_field_effect_profile,
    _normalize_stage_preset_record,
    _normalize_visibility,
    _sort_named_ids,
    _sort_preset_ids,
    _sort_stage_ids,
    _store_ally_formations,
    _store_character_presets,
    _store_enemy_formations,
    _store_stage_presets,
    _validate_battle_only_entry,
)
from events.battle_only.runtime_builders import (
    _apply_enemy_behavior_override,
    _bo_assign_auto_positions,
    _build_runtime_character_from_preset,
    _force_character_side,
)


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _now_ms():
    return int(time.time() * 1000)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix):
    return f"{prefix}_{_now_ms()}_{random.randint(1000, 9999)}"


def _start_battle_only_round(room, user_info):
    from manager.battle.common_manager import process_round_start
    starter = str((user_info or {}).get('username', '')).strip() or '戦闘専用モード'
    process_round_start(room, starter)


def _emit_error(error_code, message, event_name='bo_catalog_error', extra=None):
    payload = {
        "error": str(error_code or "unknown_error"),
        "message": str(message or "operation failed"),
    }
    if isinstance(extra, dict):
        payload.update(extra)
    socketio.emit(event_name, payload, to=request.sid)


def _require_gm(event_name='bo_catalog_error'):
    user_info = get_user_info_from_sid(request.sid)
    username = user_info.get("username", "System")
    attribute = user_info.get("attribute", "Player")
    if attribute == 'GM':
        return True, user_info
    print(f"⚠️ Security: Player {username} tried to access battle-only manage API. Denied.")
    _emit_error('permission_denied', '戦闘専用プリセットの保存・編集はGMのみ可能です。', event_name=event_name)
    return False, user_info


def _is_gm(user_info):
    return str((user_info or {}).get('attribute', '')).strip().upper() == 'GM'


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

@socketio.on('request_bo_catalog_list')
def handle_bo_catalog_list(_data):
    user_info = get_user_info_from_sid(request.sid)
    store = load_bo_preset_store()
    all_presets = _store_character_presets(store, create=False)
    all_formations = _store_enemy_formations(store, create=False)
    all_ally_formations = _store_ally_formations(store, create=False)
    all_stage_presets = _store_stage_presets(store, create=False)
    visible = _filter_visible_presets(all_presets, user_info)
    visible_formations = _filter_visible_rows_by_visibility(all_formations, user_info)
    visible_ally_formations = _filter_visible_rows_by_visibility(all_ally_formations, user_info)
    visible_stage_presets = _filter_visible_rows_by_visibility(all_stage_presets, user_info)
    payload = {
        "presets": visible,
        "sorted_ids": _sort_preset_ids(visible),
        "enemy_formations": visible_formations,
        "sorted_enemy_formation_ids": _sort_named_ids(visible_formations),
        "ally_formations": visible_ally_formations,
        "sorted_ally_formation_ids": _sort_named_ids(visible_ally_formations),
        "stage_presets": visible_stage_presets,
        "sorted_stage_preset_ids": _sort_stage_ids(visible_stage_presets),
        "can_manage": _is_gm(user_info),
    }
    socketio.emit('receive_bo_catalog_list', payload, to=request.sid)


@socketio.on('request_bo_preset_save')
def handle_bo_preset_save(data):
    allowed, user_info = _require_gm(event_name='bo_preset_error')
    if not allowed:
        return

    src = data if isinstance(data, dict) else {}
    payload = src.get('payload') if isinstance(src.get('payload'), dict) else src
    overwrite = bool(src.get('overwrite', False))

    try:
        incoming_id = str((payload or {}).get('id', '')).strip()
        existing_holder = {}

        def _mutator(store):
            presets = _store_character_presets(store, create=True)
            current = presets.get(incoming_id) if incoming_id else None
            normalized = _normalize_preset_record(payload, user_info, existing=current)
            rec_id = normalized['id']
            if rec_id in presets and not overwrite and not incoming_id:
                raise RuntimeError('duplicate_id')
            if not str(normalized.get('name', '')).strip():
                raise RuntimeError('name_required')
            presets[rec_id] = normalized
            existing_holder['record'] = normalized

        mutate_bo_preset_store(_mutator)
        saved = existing_holder.get('record') or {}
        socketio.emit('bo_preset_saved', {"id": saved.get('id'), "record": copy.deepcopy(saved)}, to=request.sid)
    except RuntimeError as ex:
        code = str(ex)
        if code == 'duplicate_id':
            _emit_error('duplicate', '同じIDのプリセットが既に存在します。', event_name='bo_preset_error')
        elif code == 'name_required':
            _emit_error('invalid_payload', 'プリセット名は必須です。', event_name='bo_preset_error')
        else:
            _emit_error('save_failed', 'プリセットの保存に失敗しました。', event_name='bo_preset_error')
    except Exception as ex:
        _emit_error('invalid_payload', f'保存データが不正です: {ex}', event_name='bo_preset_error')


@socketio.on('request_bo_preset_delete')
def handle_bo_preset_delete(data):
    allowed, _ = _require_gm(event_name='bo_preset_error')
    if not allowed:
        return
    rec_id = str((data or {}).get('id', '')).strip()
    if not rec_id:
        _emit_error('invalid_request', 'id は必須です。', event_name='bo_preset_error')
        return

    try:
        deleted = {"ok": False}

        def _mutator(store):
            presets = _store_character_presets(store, create=True)
            if rec_id not in presets:
                raise RuntimeError('not_found')
            del presets[rec_id]
            deleted['ok'] = True

        mutate_bo_preset_store(_mutator)
        socketio.emit('bo_preset_deleted', {"id": rec_id}, to=request.sid)
    except RuntimeError as ex:
        if str(ex) == 'not_found':
            _emit_error('not_found', 'プリセットが見つかりません。', event_name='bo_preset_error', extra={"id": rec_id})
        else:
            _emit_error('delete_failed', 'プリセット削除に失敗しました。', event_name='bo_preset_error')
    except Exception:
        _emit_error('delete_failed', 'プリセット削除に失敗しました。', event_name='bo_preset_error')


@socketio.on('request_bo_enemy_formation_list')
def handle_bo_enemy_formation_list(_data):
    user_info = get_user_info_from_sid(request.sid)
    store = load_bo_preset_store()
    formations = _store_enemy_formations(store, create=False)
    visible = _filter_visible_rows_by_visibility(formations, user_info)
    socketio.emit(
        'bo_enemy_formation_list',
        {
            "enemy_formations": visible,
            "sorted_enemy_formation_ids": _sort_named_ids(visible),
            "can_manage": _is_gm(user_info),
        },
        to=request.sid
    )


@socketio.on('request_bo_enemy_formation_save')
def handle_bo_enemy_formation_save(data):
    allowed, user_info = _require_gm(event_name='bo_enemy_formation_error')
    if not allowed:
        return
    src = data if isinstance(data, dict) else {}
    payload = src.get('payload') if isinstance(src.get('payload'), dict) else src
    overwrite = bool(src.get('overwrite', False))

    try:
        incoming_id = str((payload or {}).get('id', '')).strip()
        existing_holder = {}

        def _mutator(store):
            presets = _store_character_presets(store, create=False)
            formations = _store_enemy_formations(store, create=True)
            current = formations.get(incoming_id) if incoming_id else None
            normalized = _normalize_enemy_formation_record(payload, user_info, presets, existing=current)
            rec_id = normalized['id']
            if rec_id in formations and not overwrite and not incoming_id:
                raise RuntimeError('duplicate_id')
            if not str(normalized.get('name', '')).strip():
                raise RuntimeError('name_required')
            formations[rec_id] = normalized
            existing_holder['record'] = normalized

        mutate_bo_preset_store(_mutator)
        saved = existing_holder.get('record') or {}
        socketio.emit('bo_enemy_formation_saved', {"id": saved.get('id'), "record": copy.deepcopy(saved)}, to=request.sid)
    except RuntimeError as ex:
        code = str(ex)
        if code == 'duplicate_id':
            _emit_error('duplicate', '同じIDの敵編成が既に存在します。', event_name='bo_enemy_formation_error')
        elif code == 'name_required':
            _emit_error('invalid_payload', '敵編成名は必須です。', event_name='bo_enemy_formation_error')
        else:
            _emit_error('save_failed', '敵編成の保存に失敗しました。', event_name='bo_enemy_formation_error')
    except ValueError as ex:
        _emit_error('invalid_payload', str(ex), event_name='bo_enemy_formation_error')
    except Exception as ex:
        _emit_error('invalid_payload', f'保存データが不正です: {ex}', event_name='bo_enemy_formation_error')


@socketio.on('request_bo_enemy_formation_delete')
def handle_bo_enemy_formation_delete(data):
    allowed, _ = _require_gm(event_name='bo_enemy_formation_error')
    if not allowed:
        return
    rec_id = str((data or {}).get('id', '')).strip()
    if not rec_id:
        _emit_error('invalid_request', 'id は必須です。', event_name='bo_enemy_formation_error')
        return
    try:
        def _mutator(store):
            formations = _store_enemy_formations(store, create=True)
            if rec_id not in formations:
                raise RuntimeError('not_found')
            del formations[rec_id]

        mutate_bo_preset_store(_mutator)
        socketio.emit('bo_enemy_formation_deleted', {"id": rec_id}, to=request.sid)
    except RuntimeError as ex:
        if str(ex) == 'not_found':
            _emit_error('not_found', '敵編成が見つかりません。', event_name='bo_enemy_formation_error', extra={"id": rec_id})
        else:
            _emit_error('delete_failed', '敵編成の削除に失敗しました。', event_name='bo_enemy_formation_error')
    except Exception:
        _emit_error('delete_failed', '敵編成の削除に失敗しました。', event_name='bo_enemy_formation_error')


@socketio.on('request_bo_select_enemy_formation')
def handle_bo_select_enemy_formation(data):
    room = str((data or {}).get('room', '')).strip()
    if not room:
        _emit_error('missing_room', 'room は必須です。', event_name='bo_draft_error')
        return
    allowed, user_info = _require_room_participant(room, event_name='bo_draft_error')
    if not allowed:
        return
    formation_id = str((data or {}).get('formation_id', '')).strip()
    if not formation_id:
        _emit_error('invalid_request', 'formation_id は必須です。', event_name='bo_draft_error')
        return

    store = load_bo_preset_store()
    formations = _store_enemy_formations(store, create=False)
    visible_formations = _filter_visible_rows_by_visibility(formations, user_info)
    record = visible_formations.get(formation_id)
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


@socketio.on('request_bo_ally_formation_list')
def handle_bo_ally_formation_list(_data):
    user_info = get_user_info_from_sid(request.sid)
    store = load_bo_preset_store()
    formations = _store_ally_formations(store, create=False)
    visible = _filter_visible_rows_by_visibility(formations, user_info)
    socketio.emit(
        'bo_ally_formation_list',
        {
            "ally_formations": visible,
            "sorted_ally_formation_ids": _sort_named_ids(visible),
            "can_manage": _is_gm(user_info),
        },
        to=request.sid
    )


@socketio.on('request_bo_ally_formation_save')
def handle_bo_ally_formation_save(data):
    allowed, user_info = _require_gm(event_name='bo_ally_formation_error')
    if not allowed:
        return
    src = data if isinstance(data, dict) else {}
    payload = src.get('payload') if isinstance(src.get('payload'), dict) else src
    overwrite = bool(src.get('overwrite', False))

    try:
        incoming_id = str((payload or {}).get('id', '')).strip()
        existing_holder = {}

        def _mutator(store):
            presets = _store_character_presets(store, create=False)
            formations = _store_ally_formations(store, create=True)
            current = formations.get(incoming_id) if incoming_id else None
            normalized = _normalize_ally_formation_record(payload, user_info, presets, existing=current)
            rec_id = normalized['id']
            if rec_id in formations and not overwrite and not incoming_id:
                raise RuntimeError('duplicate_id')
            if not str(normalized.get('name', '')).strip():
                raise RuntimeError('name_required')
            formations[rec_id] = normalized
            existing_holder['record'] = normalized

        mutate_bo_preset_store(_mutator)
        saved = existing_holder.get('record') or {}
        socketio.emit('bo_ally_formation_saved', {"id": saved.get('id'), "record": copy.deepcopy(saved)}, to=request.sid)
    except RuntimeError as ex:
        code = str(ex)
        if code == 'duplicate_id':
            _emit_error('duplicate', '同じIDの味方編成が既に存在します。', event_name='bo_ally_formation_error')
        elif code == 'name_required':
            _emit_error('invalid_payload', '味方編成名は必須です。', event_name='bo_ally_formation_error')
        else:
            _emit_error('save_failed', '味方編成の保存に失敗しました。', event_name='bo_ally_formation_error')
    except ValueError as ex:
        _emit_error('invalid_payload', str(ex), event_name='bo_ally_formation_error')
    except Exception as ex:
        _emit_error('invalid_payload', f'保存データが不正です: {ex}', event_name='bo_ally_formation_error')


@socketio.on('request_bo_ally_formation_delete')
def handle_bo_ally_formation_delete(data):
    allowed, _ = _require_gm(event_name='bo_ally_formation_error')
    if not allowed:
        return
    rec_id = str((data or {}).get('id', '')).strip()
    if not rec_id:
        _emit_error('invalid_request', 'id は必須です。', event_name='bo_ally_formation_error')
        return
    try:
        def _mutator(store):
            formations = _store_ally_formations(store, create=True)
            if rec_id not in formations:
                raise RuntimeError('not_found')
            del formations[rec_id]

        mutate_bo_preset_store(_mutator)
        socketio.emit('bo_ally_formation_deleted', {"id": rec_id}, to=request.sid)
    except RuntimeError as ex:
        if str(ex) == 'not_found':
            _emit_error('not_found', '味方編成が見つかりません。', event_name='bo_ally_formation_error', extra={"id": rec_id})
        else:
            _emit_error('delete_failed', '味方編成の削除に失敗しました。', event_name='bo_ally_formation_error')
    except Exception:
        _emit_error('delete_failed', '味方編成の削除に失敗しました。', event_name='bo_ally_formation_error')


@socketio.on('request_bo_select_ally_formation')
def handle_bo_select_ally_formation(data):
    room = str((data or {}).get('room', '')).strip()
    if not room:
        _emit_error('missing_room', 'room は必須です。', event_name='bo_draft_error')
        return
    allowed, user_info = _require_room_participant(room, event_name='bo_draft_error')
    if not allowed:
        return
    formation_id = str((data or {}).get('formation_id', '')).strip()
    if not formation_id:
        _emit_error('invalid_request', 'formation_id は必須です。', event_name='bo_draft_error')
        return

    store = load_bo_preset_store()
    formations = _store_ally_formations(store, create=False)
    visible_formations = _filter_visible_rows_by_visibility(formations, user_info)
    record = visible_formations.get(formation_id)
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


@socketio.on('request_bo_stage_preset_list')
def handle_bo_stage_preset_list(_data):
    user_info = get_user_info_from_sid(request.sid)
    store = load_bo_preset_store()
    stages = _store_stage_presets(store, create=False)
    visible = _filter_visible_rows_by_visibility(stages, user_info)
    socketio.emit(
        'bo_stage_preset_list',
        {
            "stage_presets": visible,
            "sorted_stage_preset_ids": _sort_stage_ids(visible),
            "can_manage": _is_gm(user_info),
        },
        to=request.sid
    )


@socketio.on('request_bo_stage_preset_save')
def handle_bo_stage_preset_save(data):
    allowed, user_info = _require_gm(event_name='bo_stage_preset_error')
    if not allowed:
        return
    src = data if isinstance(data, dict) else {}
    payload = src.get('payload') if isinstance(src.get('payload'), dict) else src
    overwrite = bool(src.get('overwrite', False))

    try:
        incoming_id = str((payload or {}).get('id', '')).strip()
        existing_holder = {}

        def _mutator(store):
            enemy_formations = _store_enemy_formations(store, create=False)
            ally_formations = _store_ally_formations(store, create=False)
            stages = _store_stage_presets(store, create=True)
            current = stages.get(incoming_id) if incoming_id else None
            normalized = _normalize_stage_preset_record(
                payload,
                user_info,
                enemy_formations=enemy_formations,
                ally_formations=ally_formations,
                existing=current,
            )
            rec_id = normalized['id']
            if rec_id in stages and not overwrite and not incoming_id:
                raise RuntimeError('duplicate_id')
            if not str(normalized.get('name', '')).strip():
                raise RuntimeError('name_required')
            stages[rec_id] = normalized
            existing_holder['record'] = normalized

        mutate_bo_preset_store(_mutator)
        saved = existing_holder.get('record') or {}
        socketio.emit('bo_stage_preset_saved', {"id": saved.get('id'), "record": copy.deepcopy(saved)}, to=request.sid)
    except RuntimeError as ex:
        code = str(ex)
        if code == 'duplicate_id':
            _emit_error('duplicate', '同じIDのステージが既に存在します。', event_name='bo_stage_preset_error')
        elif code == 'name_required':
            _emit_error('invalid_payload', 'ステージ名は必須です。', event_name='bo_stage_preset_error')
        else:
            _emit_error('save_failed', 'ステージの保存に失敗しました。', event_name='bo_stage_preset_error')
    except ValueError as ex:
        _emit_error('invalid_payload', str(ex), event_name='bo_stage_preset_error')
    except Exception as ex:
        _emit_error('invalid_payload', f'保存データが不正です: {ex}', event_name='bo_stage_preset_error')


@socketio.on('request_bo_stage_preset_delete')
def handle_bo_stage_preset_delete(data):
    allowed, _ = _require_gm(event_name='bo_stage_preset_error')
    if not allowed:
        return
    rec_id = str((data or {}).get('id', '')).strip()
    if not rec_id:
        _emit_error('invalid_request', 'id は必須です。', event_name='bo_stage_preset_error')
        return
    try:
        def _mutator(store):
            stages = _store_stage_presets(store, create=True)
            if rec_id not in stages:
                raise RuntimeError('not_found')
            del stages[rec_id]

        mutate_bo_preset_store(_mutator)
        socketio.emit('bo_stage_preset_deleted', {"id": rec_id}, to=request.sid)
    except RuntimeError as ex:
        if str(ex) == 'not_found':
            _emit_error('not_found', 'ステージが見つかりません。', event_name='bo_stage_preset_error', extra={"id": rec_id})
        else:
            _emit_error('delete_failed', 'ステージの削除に失敗しました。', event_name='bo_stage_preset_error')
    except Exception:
        _emit_error('delete_failed', 'ステージの削除に失敗しました。', event_name='bo_stage_preset_error')


@socketio.on('request_bo_select_stage_preset')
def handle_bo_select_stage_preset(data):
    room = str((data or {}).get('room', '')).strip()
    if not room:
        _emit_error('missing_room', 'room は必須です。', event_name='bo_draft_error')
        return
    allowed, user_info = _require_room_participant(room, event_name='bo_draft_error')
    if not allowed:
        return
    stage_id = str((data or {}).get('stage_id', '')).strip()
    if not stage_id:
        _emit_error('invalid_request', 'stage_id は必須です。', event_name='bo_draft_error')
        return

    store = load_bo_preset_store()
    stages = _store_stage_presets(store, create=False)
    enemy_formations = _store_enemy_formations(store, create=False)
    ally_formations = _store_ally_formations(store, create=False)
    visible_stages = _filter_visible_rows_by_visibility(stages, user_info)
    stage = visible_stages.get(stage_id)
    if not isinstance(stage, dict):
        _emit_error('not_found', 'ステージが見つかりません。', event_name='bo_draft_error', extra={"id": stage_id})
        return

    enemy_formation_id = str(stage.get('enemy_formation_id', '')).strip()
    enemy_rec = enemy_formations.get(enemy_formation_id)
    if not isinstance(enemy_rec, dict):
        _emit_error('invalid_stage', f'ステージが参照する敵編成が見つかりません: {enemy_formation_id}', event_name='bo_draft_error')
        return
    if _normalize_visibility(enemy_rec.get('visibility', 'public')) != 'public' and not _is_gm(user_info):
        _emit_error('permission_denied', 'このステージの敵編成にはアクセスできません。', event_name='bo_draft_error')
        return

    ally_formation_id = _normalize_optional_id(stage.get('ally_formation_id', ''))
    ally_rec = None
    if ally_formation_id:
        ally_rec = ally_formations.get(ally_formation_id)
        if not isinstance(ally_rec, dict):
            _emit_error('invalid_stage', f'ステージが参照する味方編成が見つかりません: {ally_formation_id}', event_name='bo_draft_error')
            return
        if _normalize_visibility(ally_rec.get('visibility', 'public')) != 'public' and not _is_gm(user_info):
            _emit_error('permission_denied', 'このステージの味方編成にはアクセスできません。', event_name='bo_draft_error')
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
    allowed, _ = _require_room_participant(room, event_name='bo_draft_error')
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
    allowed, _ = _require_gm(event_name='bo_draft_error')
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
    allowed, _ = _require_gm(event_name='bo_draft_error')
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
    allowed, _ = _require_gm(event_name='bo_draft_error')
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
    allowed, _ = _require_room_participant(room, event_name='bo_draft_error')
    if not allowed:
        return

    state = get_room_state(room)
    bo = _ensure_bo_state(state)
    store = load_bo_preset_store()
    presets = _store_character_presets(store, create=False)
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
    users = _room_users(room)
    user_info = get_user_info_from_sid(request.sid)
    store = load_bo_preset_store()
    all_presets = _store_character_presets(store, create=False)
    all_formations = _store_enemy_formations(store, create=False)
    all_ally_formations = _store_ally_formations(store, create=False)
    all_stage_presets = _store_stage_presets(store, create=False)
    visible = _filter_visible_presets(all_presets, user_info)
    visible_formations = _filter_visible_rows_by_visibility(all_formations, user_info)
    visible_ally_formations = _filter_visible_rows_by_visibility(all_ally_formations, user_info)
    visible_stage_presets = _filter_visible_rows_by_visibility(all_stage_presets, user_info)
    payload = {
        "battle_only": copy.deepcopy(bo),
        "users": users,
        "presets": visible,
        "sorted_ids": _sort_preset_ids(visible),
        "enemy_formations": visible_formations,
        "sorted_enemy_formation_ids": _sort_named_ids(visible_formations),
        "ally_formations": visible_ally_formations,
        "sorted_ally_formation_ids": _sort_named_ids(visible_ally_formations),
        "stage_presets": visible_stage_presets,
        "sorted_stage_preset_ids": _sort_stage_ids(visible_stage_presets),
        "records": copy.deepcopy(_get_records(bo)),
        "active_record_id": str(bo.get('active_record_id', '')).strip() or None,
        "can_manage": _is_gm(user_info),
    }
    socketio.emit('bo_draft_state', payload, to=request.sid)


@socketio.on('request_bo_draft_update')
def handle_bo_draft_update(data):
    room = str((data or {}).get('room', '')).strip()
    if not room:
        _emit_error('missing_room', 'room は必須です。', event_name='bo_draft_error')
        return
    allowed, _ = _require_gm(event_name='bo_draft_error')
    if not allowed:
        return

    payload = (data or {}).get('payload') if isinstance((data or {}).get('payload'), dict) else {}
    state = get_room_state(room)
    bo = _ensure_bo_state(state)
    store = load_bo_preset_store()
    presets = _store_character_presets(store, create=False)

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
    enemy_formation_id = str(payload.get('enemy_formation_id', bo.get('enemy_formation_id', '') or '')).strip() or None
    ally_formation_id = str(payload.get('ally_formation_id', bo.get('ally_formation_id', '') or '')).strip() or None
    selected_stage_id = str(payload.get('selected_stage_id', bo.get('selected_stage_id', '') or '')).strip() or None
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

    state = get_room_state(room)
    bo = _ensure_bo_state(state)
    store = load_bo_preset_store()
    presets = _store_character_presets(store, create=False)

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

    _finalize_active_record(bo, forced_result='aborted', reason='restarted')

    state['characters'] = []
    state['timeline'] = []
    state['round'] = 0
    state['character_owners'] = {}
    state['battle_mode'] = 'pve'
    state['ai_target_arrows'] = []

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
                ally_char = _build_runtime_character_from_preset(rec, 'ally', serial)
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
            _force_character_side(ally_char, 'ally')
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
        behavior_override = row.get('behavior_profile_override')
        if not isinstance(behavior_override, dict):
            behavior_override = {}
        for _ in range(count):
            try:
                enemy_char = _build_runtime_character_from_preset(rec, 'enemy', serial)
            except ValueError as ex:
                _emit_error('invalid_preset', f"{row.get('preset_id')}: {ex}", event_name='bo_draft_error')
                return
            serial += 1
            _apply_enemy_behavior_override(enemy_char, behavior_override)
            _force_character_side(enemy_char, 'enemy')
            state['characters'].append(enemy_char)
            built_enemy_chars.append(enemy_char)
        built_enemy_rows.append({
            "preset_id": str(rec.get('id', '')).strip(),
            "preset_name": str(rec.get('name', '')).strip() or str(rec.get('id', '')).strip(),
            "count": count,
            "has_behavior_profile_override": bool(behavior_override),
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
    bo['selected_stage_id'] = str(bo.get('selected_stage_id', '')).strip() or None
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

    save_specific_room_state(room)
    broadcast_state_update(room)
    if stage_effect_enabled:
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
    allowed, _ = _require_gm(event_name='bo_draft_error')
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


def _emit_bo_store_export(event_name, filename_prefix, rows, sorted_ids):
    content = json.dumps(
        {
            "version": 1,
            "exported_at": _now_iso(),
            "count": len(rows) if isinstance(rows, dict) else 0,
            "sorted_ids": sorted_ids if isinstance(sorted_ids, list) else [],
            "items": rows if isinstance(rows, dict) else {},
        },
        ensure_ascii=False,
        indent=2,
    )
    filename = f"{filename_prefix}_{int(time.time())}.json"
    socketio.emit(event_name, {"filename": filename, "content": content}, to=request.sid)


@socketio.on('request_bo_export_enemy_formations_json')
def handle_bo_export_enemy_formations_json(_data):
    user_info = get_user_info_from_sid(request.sid)
    store = load_bo_preset_store()
    rows = _filter_visible_rows_by_visibility(_store_enemy_formations(store, create=False), user_info)
    _emit_bo_store_export('bo_export_enemy_formations_json', 'bo_enemy_formations', rows, _sort_named_ids(rows))


@socketio.on('request_bo_export_ally_formations_json')
def handle_bo_export_ally_formations_json(_data):
    user_info = get_user_info_from_sid(request.sid)
    store = load_bo_preset_store()
    rows = _filter_visible_rows_by_visibility(_store_ally_formations(store, create=False), user_info)
    _emit_bo_store_export('bo_export_ally_formations_json', 'bo_ally_formations', rows, _sort_named_ids(rows))


@socketio.on('request_bo_export_stage_presets_json')
def handle_bo_export_stage_presets_json(_data):
    user_info = get_user_info_from_sid(request.sid)
    store = load_bo_preset_store()
    rows = _filter_visible_rows_by_visibility(_store_stage_presets(store, create=False), user_info)
    _emit_bo_store_export('bo_export_stage_presets_json', 'bo_stage_presets', rows, _sort_stage_ids(rows))


@socketio.on('request_bo_record_export')
def handle_bo_record_export(data):
    room = str((data or {}).get('room', '')).strip()
    if not room:
        _emit_error('missing_room', 'room は必須です。', event_name='bo_draft_error')
        return
    allowed, _ = _require_room_participant(room, event_name='bo_draft_error')
    if not allowed:
        return

    state = get_room_state(room)
    bo = _ensure_bo_state(state)
    records = copy.deepcopy(_get_records(bo))
    payload = {
        "room": str(room),
        "play_mode": str(state.get('play_mode', 'normal')),
        "exported_at": _now_iso(),
        "battle_only": {
            "status": bo.get('status'),
            "active_record_id": bo.get('active_record_id'),
            "selected_stage_id": bo.get('selected_stage_id'),
            "ally_formation_id": bo.get('ally_formation_id'),
            "enemy_formation_id": bo.get('enemy_formation_id'),
            "required_ally_count": bo.get('required_ally_count'),
            "ally_entries": copy.deepcopy(bo.get('ally_entries', [])),
            "enemy_entries": copy.deepcopy(bo.get('enemy_entries', [])),
        },
        "records": records,
    }
    filename_room = str(room).strip().replace(' ', '_')
    filename = f"battle_only_records_{filename_room}_{int(time.time())}.json"
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    socketio.emit(
        'bo_record_export',
        {
            "filename": filename,
            "content": content,
            "record_count": len(records),
        },
        to=request.sid
    )
