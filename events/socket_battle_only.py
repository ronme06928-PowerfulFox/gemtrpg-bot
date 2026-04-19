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


def _normalize_visibility(raw):
    text = str(raw or '').strip().lower()
    if text in ('gm', 'private'):
        return 'gm'
    return 'public'


def _normalize_preset_record(payload, user_info, existing=None):
    src = payload if isinstance(payload, dict) else {}
    current = existing if isinstance(existing, dict) else {}
    now_ms = _now_ms()

    rec_id = str(src.get('id', '')).strip() or str(current.get('id', '')).strip() or _new_id('bop')
    name = str(src.get('name', '')).strip() or str(current.get('name', '')).strip()
    visibility = _normalize_visibility(src.get('visibility', current.get('visibility', 'public')))
    allow_ally = bool(src.get('allow_ally', current.get('allow_ally', True)))
    allow_enemy = bool(src.get('allow_enemy', current.get('allow_enemy', True)))
    if not allow_ally and not allow_enemy:
        allow_ally = True

    character_json = src.get('character_json', current.get('character_json'))
    if isinstance(character_json, str):
        character_json = json.loads(character_json)
    if not isinstance(character_json, dict):
        raise ValueError('character_json が不正です。')

    # 保存時は無変換で保持する（要求仕様）。
    character_json_raw = copy.deepcopy(character_json)

    try:
        created_at = int(current.get('created_at', now_ms) or now_ms)
    except Exception:
        created_at = now_ms

    creator = str(current.get('created_by', '')).strip() or str((user_info or {}).get('username', '')).strip() or 'GM'
    updater = str((user_info or {}).get('username', '')).strip() or creator

    return {
        "id": rec_id,
        "name": name,
        "visibility": visibility,
        "allow_ally": allow_ally,
        "allow_enemy": allow_enemy,
        "character_json": character_json_raw,
        "created_at": created_at,
        "updated_at": now_ms,
        "created_by": creator,
        "updated_by": updater,
    }


def _sort_preset_ids(presets):
    if not isinstance(presets, dict):
        return []
    return sorted(
        list(presets.keys()),
        key=lambda x: (
            str((presets.get(x, {}) or {}).get('name', '')).lower(),
            str(x),
        ),
    )


def _filter_visible_presets(all_presets, user_info):
    source = all_presets if isinstance(all_presets, dict) else {}
    can_manage = _is_gm(user_info)
    if can_manage:
        return copy.deepcopy(source)

    result = {}
    for rec_id, rec in source.items():
        if not isinstance(rec, dict):
            continue
        if _normalize_visibility(rec.get('visibility', 'public')) != 'public':
            continue
        result[str(rec_id)] = copy.deepcopy(rec)
    return result


def _store_character_presets(store, create=False):
    src = store if isinstance(store, dict) else {}
    presets = src.get('character_presets')
    if not isinstance(presets, dict):
        legacy = src.get('presets')
        if isinstance(legacy, dict):
            presets = legacy
        elif create:
            presets = {}
        else:
            presets = {}
        if create:
            src['character_presets'] = presets
    return presets if isinstance(presets, dict) else {}


def _store_enemy_formations(store, create=False):
    src = store if isinstance(store, dict) else {}
    formations = src.get('enemy_formations')
    if not isinstance(formations, dict):
        formations = {} if create else {}
        if create:
            src['enemy_formations'] = formations
    return formations if isinstance(formations, dict) else {}


def _store_ally_formations(store, create=False):
    src = store if isinstance(store, dict) else {}
    formations = src.get('ally_formations')
    if not isinstance(formations, dict):
        formations = {} if create else {}
        if create:
            src['ally_formations'] = formations
    return formations if isinstance(formations, dict) else {}


def _store_stage_presets(store, create=False):
    src = store if isinstance(store, dict) else {}
    stages = src.get('stage_presets')
    if not isinstance(stages, dict):
        stages = {} if create else {}
        if create:
            src['stage_presets'] = stages
    return stages if isinstance(stages, dict) else {}


def _sort_named_ids(rows):
    if not isinstance(rows, dict):
        return []
    return sorted(
        list(rows.keys()),
        key=lambda x: (
            str((rows.get(x, {}) or {}).get('name', '')).lower(),
            str(x),
        ),
    )


def _filter_visible_rows_by_visibility(all_rows, user_info):
    source = all_rows if isinstance(all_rows, dict) else {}
    if _is_gm(user_info):
        return copy.deepcopy(source)
    result = {}
    for rec_id, rec in source.items():
        if not isinstance(rec, dict):
            continue
        if _normalize_visibility(rec.get('visibility', 'public')) != 'public':
            continue
        result[str(rec_id)] = copy.deepcopy(rec)
    return result


def _normalize_enemy_formation_record(payload, user_info, presets, existing=None):
    src = payload if isinstance(payload, dict) else {}
    current = existing if isinstance(existing, dict) else {}
    now_ms = _now_ms()

    rec_id = str(src.get('id', '')).strip() or str(current.get('id', '')).strip() or _new_id('bof')
    name = str(src.get('name', '')).strip() or str(current.get('name', '')).strip()
    visibility = _normalize_visibility(src.get('visibility', current.get('visibility', 'public')))
    recommended_ally_count = max(0, _safe_int(src.get('recommended_ally_count', current.get('recommended_ally_count', 0)), 0))
    members_src = src.get('members', current.get('members', []))
    members_src = members_src if isinstance(members_src, list) else []

    members = []
    for row in members_src:
        if not isinstance(row, dict):
            continue
        preset_id = str(row.get('preset_id', '')).strip()
        count = max(0, _safe_int(row.get('count'), 0))
        if not preset_id or count <= 0:
            continue
        preset = presets.get(preset_id)
        if not isinstance(preset, dict):
            raise ValueError(f'敵編成のプリセットが見つかりません: {preset_id}')
        if not bool(preset.get('allow_enemy', True)):
            raise ValueError(f'敵として使えないプリセットです: {preset_id}')
        behavior_override = row.get('behavior_profile_override')
        if not isinstance(behavior_override, dict):
            behavior_override = {}
        members.append({
            "preset_id": preset_id,
            "count": count,
            "behavior_profile_override": copy.deepcopy(behavior_override),
        })

    if not members:
        raise ValueError('敵編成メンバーが空です。')

    try:
        created_at = int(current.get('created_at', now_ms) or now_ms)
    except Exception:
        created_at = now_ms

    creator = str(current.get('created_by', '')).strip() or str((user_info or {}).get('username', '')).strip() or 'GM'
    updater = str((user_info or {}).get('username', '')).strip() or creator

    return {
        "id": rec_id,
        "name": name,
        "visibility": visibility,
        "recommended_ally_count": recommended_ally_count,
        "members": members,
        "created_at": created_at,
        "updated_at": now_ms,
        "created_by": creator,
        "updated_by": updater,
    }


def _normalize_ally_formation_record(payload, user_info, presets, existing=None):
    src = payload if isinstance(payload, dict) else {}
    current = existing if isinstance(existing, dict) else {}
    now_ms = _now_ms()

    rec_id = str(src.get('id', '')).strip() or str(current.get('id', '')).strip() or _new_id('baf')
    name = str(src.get('name', '')).strip() or str(current.get('name', '')).strip()
    visibility = _normalize_visibility(src.get('visibility', current.get('visibility', 'public')))
    recommended_ally_count = max(0, _safe_int(src.get('recommended_ally_count', current.get('recommended_ally_count', 0)), 0))
    members_src = src.get('members', current.get('members', []))
    members_src = members_src if isinstance(members_src, list) else []

    members = []
    for row in members_src:
        if not isinstance(row, dict):
            continue
        preset_id = str(row.get('preset_id', '')).strip()
        if not preset_id:
            continue
        preset = presets.get(preset_id)
        if not isinstance(preset, dict):
            raise ValueError(f'味方編成のプリセットが見つかりません: {preset_id}')
        if not bool(preset.get('allow_ally', True)):
            raise ValueError(f'味方として使えないプリセットです: {preset_id}')
        slot_label = str(row.get('slot_label', '')).strip()
        user_id = str(row.get('user_id', '')).strip() or None
        members.append({
            "preset_id": preset_id,
            "slot_label": slot_label,
            "user_id": user_id,
        })

    if not members:
        raise ValueError('味方編成メンバーが空です。')

    try:
        created_at = int(current.get('created_at', now_ms) or now_ms)
    except Exception:
        created_at = now_ms

    creator = str(current.get('created_by', '')).strip() or str((user_info or {}).get('username', '')).strip() or 'GM'
    updater = str((user_info or {}).get('username', '')).strip() or creator

    return {
        "id": rec_id,
        "name": name,
        "visibility": visibility,
        "recommended_ally_count": recommended_ally_count,
        "members": members,
        "created_at": created_at,
        "updated_at": now_ms,
        "created_by": creator,
        "updated_by": updater,
    }


def _normalize_stage_preset_record(payload, user_info, enemy_formations, ally_formations, existing=None):
    src = payload if isinstance(payload, dict) else {}
    current = existing if isinstance(existing, dict) else {}
    now_ms = _now_ms()

    rec_id = str(src.get('id', '')).strip() or str(current.get('id', '')).strip() or _new_id('bos')
    name = str(src.get('name', '')).strip() or str(current.get('name', '')).strip()
    visibility = _normalize_visibility(src.get('visibility', current.get('visibility', 'public')))

    enemy_formation_id = str(src.get('enemy_formation_id', current.get('enemy_formation_id', ''))).strip()
    if not enemy_formation_id:
        raise ValueError('enemy_formation_id は必須です。')
    enemy_form = enemy_formations.get(enemy_formation_id)
    if not isinstance(enemy_form, dict):
        raise ValueError(f'敵編成が見つかりません: {enemy_formation_id}')

    ally_formation_id = str(src.get('ally_formation_id', current.get('ally_formation_id', ''))).strip() or None
    if ally_formation_id:
        ally_form = ally_formations.get(ally_formation_id)
        if not isinstance(ally_form, dict):
            raise ValueError(f'味方編成が見つかりません: {ally_formation_id}')

    required_ally_count = max(0, _safe_int(src.get('required_ally_count', current.get('required_ally_count', 0)), 0))
    concept = str(src.get('concept', current.get('concept', ''))).strip()
    description = str(src.get('description', current.get('description', ''))).strip()
    raw_tags = src.get('tags', current.get('tags', []))
    tags = [str(x).strip() for x in raw_tags] if isinstance(raw_tags, list) else []
    tags = [x for x in tags if x]
    sort_key = max(0, _safe_int(src.get('sort_key', current.get('sort_key', 0)), 0))

    if required_ally_count <= 0:
        # 既定は敵編成推奨値、次に味方編成推奨値、最後に0
        required_ally_count = max(
            0,
            _safe_int(enemy_form.get('recommended_ally_count'), 0),
            _safe_int((ally_formations.get(ally_formation_id) or {}).get('recommended_ally_count'), 0) if ally_formation_id else 0,
        )

    try:
        created_at = int(current.get('created_at', now_ms) or now_ms)
    except Exception:
        created_at = now_ms

    creator = str(current.get('created_by', '')).strip() or str((user_info or {}).get('username', '')).strip() or 'GM'
    updater = str((user_info or {}).get('username', '')).strip() or creator

    return {
        "id": rec_id,
        "name": name,
        "visibility": visibility,
        "enemy_formation_id": enemy_formation_id,
        "ally_formation_id": ally_formation_id,
        "required_ally_count": required_ally_count,
        "concept": concept,
        "description": description,
        "tags": tags,
        "sort_key": sort_key,
        "created_at": created_at,
        "updated_at": now_ms,
        "created_by": creator,
        "updated_by": updater,
    }


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


def _ensure_bo_state(state):
    if not isinstance(state, dict):
        return {}
    bo = state.get('battle_only')
    if not isinstance(bo, dict):
        bo = {}
        state['battle_only'] = bo
    defaults = {
        "status": "lobby",
        "selected_stage_id": None,
        "ally_mode": "preset",
        "ally_formation_id": None,
        "required_ally_count": 0,
        "enemy_formation_id": None,
        "controller_user_id": None,
        "controller_username": None,
        "ally_entries": [],
        "enemy_entries": [],
        "records": [],
        "active_record_id": None,
        "options": {
            "force_pve": True,
            "show_enemy_target_arrows": True,
            "intent_control_mode": "all",
        },
    }
    for key, value in defaults.items():
        if key not in bo:
            bo[key] = copy.deepcopy(value)
    if not isinstance(bo.get('ally_entries'), list):
        bo['ally_entries'] = []
    if not isinstance(bo.get('enemy_entries'), list):
        bo['enemy_entries'] = []
    if not isinstance(bo.get('records'), list):
        bo['records'] = []
    if not isinstance(bo.get('options'), dict):
        bo['options'] = {
            "force_pve": True,
            "show_enemy_target_arrows": True,
            "intent_control_mode": "all",
        }
    bo['options']['force_pve'] = bool(bo['options'].get('force_pve', True))
    bo['options']['show_enemy_target_arrows'] = bool(bo['options'].get('show_enemy_target_arrows', True))
    control_mode = str(bo['options'].get('intent_control_mode', 'all') or 'all').strip().lower()
    if control_mode not in ('all', 'starter_only'):
        control_mode = 'all'
    bo['options']['intent_control_mode'] = control_mode
    controller_user_id = str(bo.get('controller_user_id', '')).strip()
    bo['controller_user_id'] = controller_user_id or None
    controller_username = str(bo.get('controller_username', '')).strip()
    bo['controller_username'] = controller_username or None
    bo['ally_mode'] = str(bo.get('ally_mode', 'preset') or 'preset').strip().lower()
    if bo['ally_mode'] not in ('preset', 'room_existing'):
        bo['ally_mode'] = 'preset'
    bo['required_ally_count'] = max(0, _safe_int(bo.get('required_ally_count'), 0))
    selected_stage_id = str(bo.get('selected_stage_id', '')).strip()
    bo['selected_stage_id'] = selected_stage_id or None
    ally_formation_id = str(bo.get('ally_formation_id', '')).strip()
    bo['ally_formation_id'] = ally_formation_id or None
    enemy_formation_id = str(bo.get('enemy_formation_id', '')).strip()
    bo['enemy_formation_id'] = enemy_formation_id or None
    bo['status'] = str(bo.get('status', 'lobby') or 'lobby').strip().lower() or 'lobby'
    if bo['status'] not in ('lobby', 'draft', 'in_battle'):
        bo['status'] = 'lobby'
    return bo


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


def _extract_char_data_from_raw(raw_character_json):
    if not isinstance(raw_character_json, dict):
        return None
    kind = str(raw_character_json.get('kind', '')).strip().lower()
    if kind == 'character' and isinstance(raw_character_json.get('data'), dict):
        return copy.deepcopy(raw_character_json.get('data'))
    if isinstance(raw_character_json.get('data'), dict):
        return copy.deepcopy(raw_character_json.get('data'))
    return copy.deepcopy(raw_character_json)


def _status_rows_from_data(data):
    rows = data.get('status')
    if not isinstance(rows, list):
        return []
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get('label', row.get('name', ''))).strip()
        if not label:
            continue
        value = _safe_int(row.get('value'), 0)
        max_value = _safe_int(row.get('max', value), value)
        normalized.append({"label": label, "value": value, "max": max_value})
    return normalized


def _states_from_status_rows(status_rows, fallback_states):
    states = []
    for row in status_rows:
        label = str(row.get('label', '')).strip()
        if not label or label in ('HP', 'MP'):
            continue
        states.append({
            "name": label,
            "value": _safe_int(row.get('value'), 0),
            "max": _safe_int(row.get('max'), _safe_int(row.get('value'), 0)),
        })

    if not states and isinstance(fallback_states, list):
        for row in fallback_states:
            if not isinstance(row, dict):
                continue
            name = str(row.get('name', '')).strip()
            if not name:
                continue
            states.append({
                "name": name,
                "value": _safe_int(row.get('value'), 0),
                "max": _safe_int(row.get('max'), _safe_int(row.get('value'), 0)),
            })

    required_names = ['FP', '出血', '破裂', '亀裂', '戦慄', '荊棘']
    for name in required_names:
        if any(str(s.get('name', '')).strip() == name for s in states):
            continue
        states.append({"name": name, "value": 0, "max": 0})
    return states


def _build_runtime_character_from_preset(rec, char_type, serial_no):
    if not isinstance(rec, dict):
        raise ValueError('preset が不正です。')
    raw = rec.get('character_json')
    data = _extract_char_data_from_raw(raw)
    if not isinstance(data, dict):
        raise ValueError('character_json.data が見つかりません。')

    char = copy.deepcopy(data)
    char['id'] = f"char_bo_{_now_ms()}_{random.randint(1000, 9999)}_{int(serial_no)}"
    side = str(char_type or 'enemy').strip().lower()
    if side not in ('ally', 'enemy'):
        side = 'enemy'
    char['type'] = side
    # 陣営参照に使われる互換キーも type と揃えて明示上書きする。
    char['team'] = side
    char['side'] = side
    char['faction'] = side
    char['is_ally'] = (side == 'ally')
    char['is_enemy'] = (side == 'enemy')
    char['color'] = '#007bff' if side == 'ally' else '#dc3545'

    base_name = str(char.get('name', '')).strip() or str(rec.get('name', '')).strip() or ('味方' if side == 'ally' else '敵')
    char['name'] = base_name
    char['baseName'] = base_name

    status_rows = _status_rows_from_data(data)
    char['status'] = copy.deepcopy(status_rows)
    char['initial_status'] = copy.deepcopy(status_rows)

    hp_row = next((r for r in status_rows if str(r.get('label', '')).strip() == 'HP'), None)
    mp_row = next((r for r in status_rows if str(r.get('label', '')).strip() == 'MP'), None)
    hp = _safe_int((hp_row or {}).get('value'), _safe_int(char.get('hp'), 0))
    max_hp = _safe_int((hp_row or {}).get('max'), _safe_int(char.get('maxHp'), hp))
    mp = _safe_int((mp_row or {}).get('value'), _safe_int(char.get('mp'), 0))
    max_mp = _safe_int((mp_row or {}).get('max'), _safe_int(char.get('maxMp'), mp))
    if max_hp <= 0:
        max_hp = max(0, hp)
    if max_mp <= 0:
        max_mp = max(0, mp)

    char['hp'] = min(max_hp, max(0, hp))
    char['maxHp'] = max_hp
    char['mp'] = min(max_mp, max(0, mp))
    char['maxMp'] = max_mp

    if not isinstance(char.get('params'), list):
        char['params'] = []
    if not isinstance(char.get('inventory'), dict):
        char['inventory'] = {}
    if not isinstance(char.get('special_buffs'), list):
        char['special_buffs'] = []
    if not isinstance(char.get('hidden_skills'), list):
        char['hidden_skills'] = []
    if not isinstance(char.get('SPassive'), list):
        char['SPassive'] = []
    if not isinstance(char.get('radiance_skills'), list):
        char['radiance_skills'] = []

    fallback_states = char.get('states')
    char['states'] = _states_from_status_rows(status_rows, fallback_states if isinstance(fallback_states, list) else [])

    flags = char.get('flags')
    if not isinstance(flags, dict):
        flags = {}
        char['flags'] = flags
    flags['immediate_action_used'] = False

    char['x'] = -1
    char['y'] = -1
    char['hasActed'] = False
    char['speedRoll'] = 0
    char['used_skills_this_round'] = []
    char['active_round'] = 0

    initial_params = {}
    for p in char.get('params', []):
        if not isinstance(p, dict):
            continue
        label = str(p.get('label', '')).strip()
        if not label:
            continue
        value = p.get('value')
        try:
            initial_params[label] = int(value)
        except Exception:
            initial_params[label] = value
    char['initial_data'] = initial_params
    char['initial_state'] = {
        "inventory": copy.deepcopy(char.get('inventory', {})),
        "special_buffs": [copy.deepcopy(b) for b in char.get('special_buffs', []) if isinstance(b, dict)],
        "maxHp": int(char.get('maxHp', 0)),
        "maxMp": int(char.get('maxMp', 0)),
    }
    return char


def _normalize_behavior_profile_safe(raw_profile):
    if not isinstance(raw_profile, dict):
        return {}
    try:
        from manager.battle.enemy_behavior import normalize_behavior_profile
        return normalize_behavior_profile(raw_profile)
    except Exception:
        return copy.deepcopy(raw_profile)


def _apply_enemy_behavior_override(char, behavior_profile_override):
    if not isinstance(char, dict):
        return
    if not isinstance(behavior_profile_override, dict) or not behavior_profile_override:
        return
    flags = char.get('flags')
    if not isinstance(flags, dict):
        flags = {}
        char['flags'] = flags
    normalized = _normalize_behavior_profile_safe(behavior_profile_override)
    # 敵編成で上書きが指定された場合は、生成敵で必ず行動チャートが機能するよう有効化する。
    # （UI側で enabled チェックが外れたまま保存されたケースを吸収）
    if isinstance(normalized, dict):
        loops = normalized.get('loops')
        if isinstance(loops, dict) and loops:
            normalized['enabled'] = True
    flags['behavior_profile'] = normalized


def _force_character_side(char, side):
    if not isinstance(char, dict):
        return
    normalized_side = str(side or 'enemy').strip().lower()
    if normalized_side not in ('ally', 'enemy'):
        normalized_side = 'enemy'
    char['type'] = normalized_side
    char['team'] = normalized_side
    char['side'] = normalized_side
    char['faction'] = normalized_side
    char['is_ally'] = (normalized_side == 'ally')
    char['is_enemy'] = (normalized_side == 'enemy')
    char['color'] = '#007bff' if normalized_side == 'ally' else '#dc3545'


def _bo_get_map_size(state):
    map_data = state.get('map_data') if isinstance(state, dict) else {}
    width = _safe_int((map_data or {}).get('width'), 20)
    height = _safe_int((map_data or {}).get('height'), 15)
    width = max(6, width)
    height = max(6, height)
    return width, height


def _bo_clamp_anchor(value, minimum, maximum, fallback):
    if maximum < minimum:
        return minimum
    try:
        num = float(value)
    except (TypeError, ValueError):
        num = float(fallback)
    if num < minimum:
        num = float(minimum)
    if num > maximum:
        num = float(maximum)
    return num


def _bo_side_range(width, side, center_x=None):
    fallback_center = max(2, min(width - 3, width // 2))
    center = int(round(_bo_clamp_anchor(center_x, 2, width - 3, fallback_center)))
    if side == 'left':
        return 1, max(1, center - 1)
    return min(width - 2, center + 1), width - 2


def _bo_sorted_axis(values, anchor):
    rows = list(values)
    if not rows:
        return []
    return sorted(rows, key=lambda v: (abs(v - anchor), v))


def _bo_generate_positions(count, width, height, side, gap, center_x=None, center_y=None):
    if count <= 0:
        return []

    x_min, x_max = _bo_side_range(width, side, center_x=center_x)
    if x_max < x_min:
        x_max = x_min

    y_min = 1
    y_max = max(1, height - 2)

    step = max(1, gap)
    cols = list(range(x_min, x_max + 1, step))
    rows = list(range(y_min, y_max + 1, step))
    fallback_x = max(x_min, min(x_max, (x_min + x_max) / 2))
    fallback_y = max(y_min, min(y_max, (y_min + y_max) / 2))
    center_x_num = _bo_clamp_anchor(center_x, x_min, x_max, fallback_x)
    center_y_num = _bo_clamp_anchor(center_y, y_min, y_max, fallback_y)

    cols = _bo_sorted_axis(cols, center_x_num)
    rows = _bo_sorted_axis(rows, center_y_num)

    positions = []
    for col in cols:
        for row in rows:
            positions.append((col, row))
            if len(positions) >= count:
                return positions
    return positions


def _bo_assign_auto_positions(allies, enemies, state, anchor=None):
    ally_rows = allies if isinstance(allies, list) else []
    enemy_rows = enemies if isinstance(enemies, list) else []
    width, height = _bo_get_map_size(state)
    anchor_data = anchor if isinstance(anchor, dict) else {}
    center_x = _bo_clamp_anchor(anchor_data.get('x'), 1, width - 2, width / 2)
    center_y = _bo_clamp_anchor(anchor_data.get('y'), 1, height - 2, height / 2)

    # まずは十分な間隔（2マス）を試し、入り切らない場合のみ段階的に詰める。
    def pick_positions(count, side):
        # まず広めに配置を試し、収まらない場合のみ段階的に詰める。
        for gap in (3, 2, 1):
            rows = _bo_generate_positions(count, width, height, side, gap, center_x=center_x, center_y=center_y)
            if len(rows) >= count:
                return rows[:count]
        # 理論上はここに来ないが、保険として最後は連続配置。
        return _bo_generate_positions(count, width, height, side, 1, center_x=center_x, center_y=center_y)[:count]

    ally_pos = pick_positions(len(ally_rows), 'left')
    enemy_pos = pick_positions(len(enemy_rows), 'right')

    for idx, char in enumerate(ally_rows):
        if idx < len(ally_pos) and isinstance(char, dict):
            char['x'], char['y'] = ally_pos[idx]
    for idx, char in enumerate(enemy_rows):
        if idx < len(enemy_pos) and isinstance(char, dict):
            char['x'], char['y'] = enemy_pos[idx]


def _normalize_ally_entries(entries, presets, validate_user_ids=False, room=None):
    rows = entries if isinstance(entries, list) else []
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        preset_id = str(row.get('preset_id', '')).strip()
        if not preset_id:
            continue
        rec = presets.get(preset_id)
        if not isinstance(rec, dict):
            raise ValueError(f'味方プリセットが見つかりません: {preset_id}')
        if not bool(rec.get('allow_ally', True)):
            raise ValueError(f'味方専用でないプリセットです: {preset_id}')
        user_id = str(row.get('user_id', '')).strip() or None
        if validate_user_ids and user_id and room:
            if not _find_username_by_user_id(room, user_id):
                raise ValueError(f'割当ユーザーが見つかりません: {user_id}')
        normalized.append({
            "preset_id": preset_id,
            "user_id": user_id,
        })
    return normalized


def _normalize_enemy_entries(entries, presets):
    rows = entries if isinstance(entries, list) else []
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        preset_id = str(row.get('preset_id', '')).strip()
        count = max(0, _safe_int(row.get('count'), 0))
        if not preset_id or count <= 0:
            continue
        rec = presets.get(preset_id)
        if not isinstance(rec, dict):
            raise ValueError(f'敵プリセットが見つかりません: {preset_id}')
        if not bool(rec.get('allow_enemy', True)):
            raise ValueError(f'敵専用でないプリセットです: {preset_id}')
        behavior_profile_override = row.get('behavior_profile_override')
        if not isinstance(behavior_profile_override, dict):
            behavior_profile_override = {}
        normalized.append({
            "preset_id": preset_id,
            "count": count,
            "behavior_profile_override": copy.deepcopy(behavior_profile_override),
        })
    return normalized


def _get_records(bo):
    if not isinstance(bo, dict):
        return []
    records = bo.get('records')
    if not isinstance(records, list):
        records = []
        bo['records'] = records
    return records


def _find_record(bo, record_id=None):
    if not isinstance(bo, dict):
        return None, None
    records = _get_records(bo)
    target = str(record_id or '').strip() or str(bo.get('active_record_id', '')).strip()
    if not target:
        return None, None
    for rec in records:
        if not isinstance(rec, dict):
            continue
        if str(rec.get('id', '')).strip() == target:
            return rec, target
    return None, target


def _estimate_battle_result(state):
    allies_alive = False
    enemies_alive = False
    for char in state.get('characters', []):
        if not isinstance(char, dict):
            continue
        ctype = str(char.get('type', '')).strip().lower()
        hp = _safe_int(char.get('hp'), 0)
        if ctype == 'ally' and hp > 0:
            allies_alive = True
        elif ctype == 'enemy' and hp > 0:
            enemies_alive = True
    if allies_alive and not enemies_alive:
        return 'ally_win'
    if enemies_alive and not allies_alive:
        return 'enemy_win'
    if not allies_alive and not enemies_alive:
        return 'draw'
    return 'in_progress'


def _finalize_active_record(bo, forced_result='aborted', reason=None):
    rec, _ = _find_record(bo)
    if not isinstance(rec, dict):
        return None
    if str(rec.get('status', '')).strip().lower() != 'in_battle':
        bo['active_record_id'] = None
        return None
    rec['status'] = 'finished'
    rec['result'] = str(forced_result or 'aborted').strip().lower() or 'aborted'
    rec['ended_at'] = _now_iso()
    if reason:
        rec['end_reason'] = str(reason)
    bo['active_record_id'] = None
    bo['status'] = 'draft'
    return rec


def _count_room_allies(state):
    if not isinstance(state, dict):
        return 0
    return len([
        c for c in (state.get('characters') or [])
        if isinstance(c, dict) and str(c.get('type', '')).strip().lower() == 'ally'
    ])


def _validate_battle_only_entry(state, bo, presets):
    result = {
        "ready": False,
        "issues": [],
        "ally_mode": str((bo or {}).get('ally_mode', 'preset') or 'preset').strip().lower(),
        "required_ally_count": max(0, _safe_int((bo or {}).get('required_ally_count'), 0)),
        "room_ally_count": _count_room_allies(state),
        "ally_entry_count": 0,
        "enemy_entry_count": 0,
    }
    issues = result["issues"]
    ally_mode = result["ally_mode"]
    if ally_mode not in ('preset', 'room_existing'):
        ally_mode = 'preset'
        result["ally_mode"] = ally_mode

    try:
        enemy_entries = _normalize_enemy_entries((bo or {}).get('enemy_entries'), presets)
    except ValueError as ex:
        enemy_entries = []
        issues.append(str(ex))
    result["enemy_entry_count"] = sum(max(0, _safe_int((r or {}).get('count'), 0)) for r in enemy_entries)
    if result["enemy_entry_count"] <= 0:
        issues.append('敵編成が空です。')

    if ally_mode == 'preset':
        try:
            ally_entries = _normalize_ally_entries((bo or {}).get('ally_entries'), presets, validate_user_ids=False, room=None)
        except ValueError as ex:
            ally_entries = []
            issues.append(str(ex))
        result["ally_entry_count"] = len(ally_entries)
        if result["ally_entry_count"] <= 0:
            issues.append('味方編成が空です。')
    else:
        required = result["required_ally_count"]
        room_allies = result["room_ally_count"]
        result["ally_entry_count"] = room_allies
        if required <= 0:
            issues.append('現在ルーム利用時は必要味方人数の指定が必要です。')
        if required > 0 and room_allies != required:
            issues.append(f'現在ルーム味方人数が不一致です（必要:{required} / 現在:{room_allies}）。')

    result["ready"] = len(issues) == 0
    return result


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


def _enemy_entries_from_formation_record(record):
    src = record if isinstance(record, dict) else {}
    members = src.get('members')
    members = members if isinstance(members, list) else []
    out = []
    for row in members:
        if not isinstance(row, dict):
            continue
        preset_id = str(row.get('preset_id', '')).strip()
        count = max(0, _safe_int(row.get('count'), 0))
        if not preset_id or count <= 0:
            continue
        behavior_profile_override = row.get('behavior_profile_override')
        if not isinstance(behavior_profile_override, dict):
            behavior_profile_override = {}
        out.append({
            "preset_id": preset_id,
            "count": count,
            "behavior_profile_override": copy.deepcopy(behavior_profile_override),
        })
    return out


def _ally_entries_from_formation_record(record):
    src = record if isinstance(record, dict) else {}
    members = src.get('members')
    members = members if isinstance(members, list) else []
    out = []
    for row in members:
        if not isinstance(row, dict):
            continue
        preset_id = str(row.get('preset_id', '')).strip()
        if not preset_id:
            continue
        user_id = str(row.get('user_id', '')).strip() or None
        out.append({
            "preset_id": preset_id,
            "user_id": user_id,
        })
    return out


def _sort_stage_ids(rows):
    if not isinstance(rows, dict):
        return []

    def _key(stage_id):
        rec = rows.get(stage_id, {}) if isinstance(rows.get(stage_id), dict) else {}
        sort_key = max(0, _safe_int(rec.get('sort_key'), 0))
        name = str(rec.get('name', '')).strip().lower()
        return (sort_key, name, str(stage_id))

    return sorted(list(rows.keys()), key=_key)


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

    ally_formation_id = str(stage.get('ally_formation_id', '')).strip() or None
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
    bo['ally_mode'] = ally_mode
    bo['selected_stage_id'] = str(bo.get('selected_stage_id', '')).strip() or None
    bo['required_ally_count'] = required_ally_count
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
