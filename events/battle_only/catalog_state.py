# events/battle_only/catalog_state.py
import copy
import json
import random
import time

from manager.json_rule_v2 import JsonRuleV2Error, normalize_skill_constraints_rows


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _now_ms():
    return int(time.time() * 1000)


def _new_id(prefix):
    return f"{prefix}_{_now_ms()}_{random.randint(1000, 9999)}"


def _is_gm(user_info):
    return str((user_info or {}).get('attribute', '')).strip().upper() == 'GM'


def _normalize_visibility(raw):
    text = str(raw or '').strip().lower()
    if text in ('gm', 'private'):
        return 'gm'
    return 'public'

def _normalize_optional_id(raw):
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.lower() in ('none', 'null'):
        return None
    return text

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

    ally_formation_id = _normalize_optional_id(src.get('ally_formation_id', current.get('ally_formation_id', '')))
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
    field_effect_profile = _normalize_stage_field_effect_profile(
        src.get('field_effect_profile', current.get('field_effect_profile'))
    )
    stage_avatar = _normalize_stage_avatar(src.get('stage_avatar', current.get('stage_avatar')))

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
        "field_effect_profile": field_effect_profile,
        "stage_avatar": stage_avatar,
        "created_at": created_at,
        "updated_at": now_ms,
        "created_by": creator,
        "updated_by": updater,
    }

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
        "stage_field_effect_profile": {},
        "stage_avatar_profile": {},
        "stage_field_effect_enabled": True,
        "stage_avatar_enabled": True,
        "controller_user_id": None,
        "controller_username": None,
        "ally_entries": [],
        "enemy_entries": [],
        "records": [],
        "active_record_id": None,
        "pending_auto_reset": False,
        "pending_auto_reset_round": None,
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
    bo['stage_field_effect_profile'] = _normalize_stage_field_effect_profile(bo.get('stage_field_effect_profile'))
    bo['stage_avatar_profile'] = _normalize_stage_avatar(bo.get('stage_avatar_profile'))
    bo['stage_field_effect_enabled'] = bool(bo.get('stage_field_effect_enabled', True))
    bo['stage_avatar_enabled'] = bool(bo.get('stage_avatar_enabled', True))
    bo['selected_stage_id'] = _normalize_optional_id(bo.get('selected_stage_id', ''))
    bo['ally_formation_id'] = _normalize_optional_id(bo.get('ally_formation_id', ''))
    bo['enemy_formation_id'] = _normalize_optional_id(bo.get('enemy_formation_id', ''))
    bo['status'] = str(bo.get('status', 'lobby') or 'lobby').strip().lower() or 'lobby'
    if bo['status'] not in ('lobby', 'draft', 'in_battle'):
        bo['status'] = 'lobby'
    return bo

def _normalize_stage_field_effect_profile(raw):
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            raw = json.loads(text)
        except Exception as ex:
            raise ValueError(f'field_effect_profile が不正なJSONです: {ex}')
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError('field_effect_profile は object で指定してください。')

    version = max(1, _safe_int(raw.get('version', 1), 1))
    rules_src = raw.get('rules')
    if rules_src is None:
        rules_src = []
    if not isinstance(rules_src, list):
        raise ValueError('field_effect_profile.rules は配列で指定してください。')

    rules = []
    for idx, row in enumerate(rules_src):
        if not isinstance(row, dict):
            raise ValueError(f'field_effect_profile.rules[{idx}] は object で指定してください。')
        rule_type = str(row.get('type', '')).strip()
        if not rule_type:
            raise ValueError(f'field_effect_profile.rules[{idx}].type は必須です。')
        rule = {
            "type": rule_type,
            "scope": str(row.get('scope', 'ALL') or 'ALL').strip().upper(),
            "priority": _safe_int(row.get('priority', 0), 0),
        }
        if 'value' in row:
            rule['value'] = row.get('value')
        if 'condition' in row and isinstance(row.get('condition'), dict):
            rule['condition'] = copy.deepcopy(row.get('condition'))
        if 'state_name' in row:
            rule['state_name'] = str(row.get('state_name') or '').strip()
        if 'display_name' in row:
            display_name = str(row.get('display_name') or '').strip()
            if display_name:
                rule['display_name'] = display_name
        if 'name' in row:
            name = str(row.get('name') or '').strip()
            if name:
                rule['name'] = name
        if 'description' in row:
            description = str(row.get('description') or '').strip()
            if description:
                rule['description'] = description
        if 'flavor_text' in row:
            flavor_text = str(row.get('flavor_text') or '').strip()
            if flavor_text:
                rule['flavor_text'] = flavor_text
        if 'flavor' in row:
            flavor = str(row.get('flavor') or '').strip()
            if flavor:
                rule['flavor'] = flavor
        if 'trigger_state_name' in row:
            trigger_state_name = str(row.get('trigger_state_name') or '').strip()
            if trigger_state_name:
                rule['trigger_state_name'] = trigger_state_name
        if 'rule_id' in row:
            rid = str(row.get('rule_id') or '').strip()
            if rid:
                rule['rule_id'] = rid
        constraints = row.get('skill_constraints', None)
        if constraints is not None:
            try:
                rule['skill_constraints'] = normalize_skill_constraints_rows(
                    constraints,
                    source_path=f"field_effect_profile.rules[{idx}].skill_constraints",
                )
            except JsonRuleV2Error as ex:
                raise ValueError(str(ex)) from ex
        rules.append(rule)

    return {"version": version, "rules": rules}

def _normalize_stage_avatar(raw):
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            raw = json.loads(text)
        except Exception as ex:
            raise ValueError(f'stage_avatar が不正なJSONです: {ex}')
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError('stage_avatar は object で指定してください。')
    return {
        "enabled": bool(raw.get('enabled', True)),
        "name": str(raw.get('name', '')).strip(),
        "description": str(raw.get('description', '')).strip(),
        "icon": str(raw.get('icon', '')).strip(),
    }

def _normalize_ally_entries(entries, presets, validate_user_ids=False, room=None, user_lookup=None):
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
            if not callable(user_lookup) or not user_lookup(room, user_id):
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
