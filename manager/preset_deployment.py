"""プリセットを通常ルームまたは戦闘専用下書きへ安全に反映する共通処理。"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from manager.battle_only_catalog_access import (
    capabilities,
    filter_visible_records,
    get_record,
    record_map,
    validate_parent_references,
)
from manager.battle_only_presets import normalize_catalog_meta
from manager.buff_catalog import get_buff_effect
from manager.game_logic import (
    apply_buff,
    get_status_value,
    process_skill_effects,
    set_status_value,
)
from manager.granted_skills.service import apply_grant_skill_change
from manager.room_preset_apply import (
    apply_stage_background_to_state,
    assign_runtime_character_number,
    build_runtime_character_from_preset,
    normalize_stage_avatar,
    normalize_stage_field_effect_profile,
)
from manager.summons.service import apply_summon_change
from manager.utils import apply_passive_effect_buffs


MAX_DEPLOYED_CHARACTERS = 100
RECORD_TYPES = ("character", "enemy_formation", "ally_formation", "stage")
SIDES = ("ally", "enemy")


class PresetDeploymentError(ValueError):
    def __init__(self, code, message, *, refresh_required=False):
        super().__init__(message)
        self.code = str(code or "deployment_error")
        self.message = str(message or "")
        self.refresh_required = bool(refresh_required)


@dataclass
class DeploymentBuild:
    state: dict
    summary: dict
    logs: list[str]


def _safe_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _record_sort_key(record):
    rec = record if isinstance(record, dict) else {}
    meta = normalize_catalog_meta(rec.get("catalog_meta"))
    return (
        meta.get("sort_order", 2147483647),
        str(rec.get("name") or rec.get("id") or "").lower(),
        str(rec.get("id") or ""),
    )


def _collection_sort_key(record):
    rec = record if isinstance(record, dict) else {}
    return (
        _safe_int(rec.get("sort_order"), 2147483647),
        str(rec.get("name") or rec.get("id") or "").lower(),
        str(rec.get("id") or ""),
    )


def _catalog_record(record_type, record):
    rec = record if isinstance(record, dict) else {}
    meta = normalize_catalog_meta(rec.get("catalog_meta"))
    result = {
        "id": str(rec.get("id") or ""),
        "record_type": record_type,
        "name": str(rec.get("name") or rec.get("id") or ""),
        "description": str(rec.get("description") or ""),
        "catalog_meta": meta,
        "capabilities": copy.deepcopy(rec.get("capabilities") or {}),
        "shared_via": str(rec.get("shared_via") or rec.get("visibility") or "public"),
    }
    if record_type == "character":
        result.update({
            "allow_ally": bool(rec.get("allow_ally", True)),
            "allow_enemy": bool(rec.get("allow_enemy", True)),
            "tag_ids": [str(value) for value in rec.get("tag_ids", []) if str(value).strip()],
        })
    elif record_type in {"enemy_formation", "ally_formation"}:
        members = rec.get("members") if isinstance(rec.get("members"), list) else []
        result.update({
            "member_count": sum(
                max(1, _safe_int(row.get("count"), 1))
                for row in members if isinstance(row, dict) and str(row.get("preset_id") or "").strip()
            ),
            "member_kinds": len([
                row for row in members
                if isinstance(row, dict) and str(row.get("preset_id") or "").strip()
            ]),
        })
    elif record_type == "stage":
        field_profile = rec.get("field_effect_profile")
        if isinstance(field_profile, str):
            try:
                field_profile = normalize_stage_field_effect_profile(field_profile)
            except Exception:
                field_profile = {}
        field_rules = field_profile.get("rules") if isinstance(field_profile, dict) else []
        result.update({
            "enemy_formation_id": str(rec.get("enemy_formation_id") or "") or None,
            "ally_formation_id": str(rec.get("ally_formation_id") or "") or None,
            "required_ally_count": max(0, _safe_int(rec.get("required_ally_count"), 0)),
            "has_background": bool(_stage_background(rec)),
            "field_effect_count": len(field_rules) if isinstance(field_rules, list) else 0,
            "has_stage_avatar": bool(rec.get("stage_avatar")),
            "tags": [str(value) for value in rec.get("tags", []) if str(value).strip()],
        })
    return result


def build_deployment_catalog(
    store,
    *,
    user_id=None,
    is_app_admin=False,
    room_role=None,
    owner_names=None,
    bookmarks=None,
    users=None,
):
    visible = {}
    for record_type in RECORD_TYPES:
        rows = filter_visible_records(
            record_map(store, record_type) or {},
            user_id=user_id,
            is_app_admin=is_app_admin,
            room_role=room_role,
            owner_names=owner_names,
        )
        visible[record_type] = {
            record_id: _catalog_record(record_type, record)
            for record_id, record in rows.items()
            if isinstance(record, dict) and (record.get("capabilities") or {}).get("can_use")
        }

    collections = filter_visible_records(
        record_map(store, "collection") or {},
        user_id=user_id,
        is_app_admin=is_app_admin,
        room_role=room_role,
        owner_names=owner_names,
    )
    collection_counts = {}
    section_counts = {}
    for rows in visible.values():
        for record in rows.values():
            meta = record.get("catalog_meta") or {}
            collection_id = str(meta.get("collection_id") or "")
            section_id = str(meta.get("section_id") or "")
            if collection_id:
                collection_counts[collection_id] = collection_counts.get(collection_id, 0) + 1
                if section_id:
                    key = f"{collection_id}:{section_id}"
                    section_counts[key] = section_counts.get(key, 0) + 1

    sorted_ids = {
        record_type: sorted(rows, key=lambda record_id: _record_sort_key(rows[record_id]))
        for record_type, rows in visible.items()
    }
    return {
        "records": visible,
        "sorted_ids": sorted_ids,
        "catalog_collections": collections,
        "sorted_collection_ids": sorted(collections, key=lambda rid: _collection_sort_key(collections[rid])),
        "collection_counts": collection_counts,
        "section_counts": section_counts,
        "bookmarks": copy.deepcopy(bookmarks if isinstance(bookmarks, list) else []),
        "users": copy.deepcopy(users if isinstance(users, list) else []),
        "can_deploy": str(room_role or "").lower() in {"owner", "gm"},
        "max_deployed_characters": MAX_DEPLOYED_CHARACTERS,
    }


def normalize_deployment_request(raw):
    src = raw if isinstance(raw, dict) else {}
    target_mode = str(src.get("target_mode") or "normal").strip().lower()
    if target_mode not in {"normal", "battle_only"}:
        raise PresetDeploymentError("invalid_target_mode", "配置先が不正です。")

    stage_src = src.get("stage") if isinstance(src.get("stage"), dict) else None
    stage = None
    if stage_src:
        record_id = str(stage_src.get("record_id") or stage_src.get("id") or "").strip()
        if not record_id:
            raise PresetDeploymentError("invalid_stage", "ステージIDが必要です。")
        apply_src = stage_src.get("apply") if isinstance(stage_src.get("apply"), dict) else {}
        stage = {
            "record_id": record_id,
            "apply": {
                "enemy_formation": bool(apply_src.get("enemy_formation", True)),
                "ally_formation": bool(apply_src.get("ally_formation", True)),
                "background": bool(apply_src.get("background", True)),
                "field_effects": bool(apply_src.get("field_effects", True)),
                "stage_avatar": bool(apply_src.get("stage_avatar", True)),
            },
        }

    formations_src = src.get("formations") if isinstance(src.get("formations"), dict) else {}
    formations = {"ally": None, "enemy": None}
    for side in SIDES:
        row = formations_src.get(side)
        if not isinstance(row, dict):
            continue
        record_id = str(row.get("record_id") or row.get("id") or "").strip()
        if not record_id:
            continue
        mode = str(row.get("mode") or ("append" if side == "ally" else "replace")).strip().lower()
        if mode not in {"append", "replace"}:
            raise PresetDeploymentError("invalid_mode", "編成の適用方法が不正です。")
        formations[side] = {
            "record_id": record_id,
            "mode": mode,
            "source": str(row.get("source") or "manual"),
        }

    character_rows = src.get("characters") if isinstance(src.get("characters"), list) else []
    characters = []
    combined = {}
    for row in character_rows:
        if not isinstance(row, dict):
            continue
        record_id = str(row.get("record_id") or row.get("id") or "").strip()
        side = str(row.get("side") or "enemy").strip().lower()
        count = _safe_int(row.get("count"), 0)
        if not record_id:
            raise PresetDeploymentError("invalid_character", "キャラクターIDが必要です。")
        if side not in SIDES:
            raise PresetDeploymentError("invalid_side", "配置する陣営が不正です。")
        if count <= 0:
            raise PresetDeploymentError("invalid_count", "追加数は1以上で指定してください。")
        user_id = str(row.get("user_id") or "").strip() or None
        key = (record_id, side, user_id)
        combined[key] = combined.get(key, 0) + count
    for (record_id, side, user_id), count in combined.items():
        characters.append({
            "record_id": record_id,
            "side": side,
            "count": count,
            "user_id": user_id,
        })

    if not stage and not any(formations.values()) and not characters:
        raise PresetDeploymentError("empty_deployment", "配置するプリセットを選んでください。")
    return {
        "target_mode": target_mode,
        "stage": stage,
        "formations": formations,
        "characters": characters,
    }


def _require_deployable(store, record_type, record_id, access):
    record = get_record(store, record_type, record_id)
    if not isinstance(record, dict):
        raise PresetDeploymentError("not_found", "プリセットが見つかりません。", refresh_required=True)
    caps = capabilities(record, **access)
    if not caps.get("can_deploy"):
        raise PresetDeploymentError("permission_denied", "このプリセットを配置する権限がありません。", refresh_required=True)
    if record_type in {"enemy_formation", "ally_formation", "stage"}:
        if not validate_parent_references(store, record_type, record):
            raise PresetDeploymentError("invalid_reference", "参照先を利用できないプリセットです。", refresh_required=True)
    return record


def resolve_deployment_request(store, request_data, *, user_id=None, is_app_admin=False, room_role=None):
    request_data = normalize_deployment_request(request_data)
    access = {
        "user_id": user_id,
        "is_app_admin": is_app_admin,
        "room_role": room_role,
    }
    if str(room_role or "").lower() not in {"owner", "gm"}:
        raise PresetDeploymentError("permission_denied", "配置にはルームowner・gm権限が必要です。")

    resolved = copy.deepcopy(request_data)
    stage = None
    if resolved.get("stage"):
        stage = _require_deployable(store, "stage", resolved["stage"]["record_id"], access)
        resolved["stage"]["record"] = copy.deepcopy(stage)

    for side, record_type in (("ally", "ally_formation"), ("enemy", "enemy_formation")):
        formation = resolved["formations"].get(side)
        if formation is None and stage and resolved["stage"]["apply"].get(f"{side}_formation"):
            stage_ref = str(stage.get(f"{side}_formation_id") or "").strip()
            if stage_ref:
                formation = {
                    "record_id": stage_ref,
                    "mode": "append" if side == "ally" and resolved["target_mode"] == "normal" else "replace",
                    "source": "stage",
                }
                resolved["formations"][side] = formation
        if formation:
            formation["record"] = copy.deepcopy(
                _require_deployable(store, record_type, formation["record_id"], access)
            )

    for row in resolved["characters"]:
        record = _require_deployable(store, "character", row["record_id"], access)
        allow_key = "allow_ally" if row["side"] == "ally" else "allow_enemy"
        if not bool(record.get(allow_key, True)):
            raise PresetDeploymentError("side_not_allowed", "このキャラクターは指定陣営へ配置できません。")
        row["record"] = copy.deepcopy(record)

    total = 0
    for formation in resolved["formations"].values():
        if not formation:
            continue
        members = formation["record"].get("members")
        for member in members if isinstance(members, list) else []:
            if isinstance(member, dict) and str(member.get("preset_id") or "").strip():
                total += max(1, _safe_int(member.get("count"), 1))
    total += sum(row["count"] for row in resolved["characters"])
    resolved["new_character_count"] = total
    if total > MAX_DEPLOYED_CHARACTERS:
        raise PresetDeploymentError(
            "deployment_limit_exceeded",
            f"一度に配置できるのは{MAX_DEPLOYED_CHARACTERS}体までです（現在{total}体）。",
        )
    return resolved


def _char_side(char):
    if not isinstance(char, dict):
        return ""
    for key in ("type", "team", "side", "faction"):
        side = str(char.get(key) or "").strip().lower()
        if side in SIDES:
            return side
    return "ally" if char.get("is_ally") else "enemy" if char.get("is_enemy") else ""


def _cleanup_removed_refs(state, removed_ids):
    removed_ids = {str(value) for value in removed_ids if str(value)}
    if not removed_ids:
        return
    owners = state.get("character_owners")
    if isinstance(owners, dict):
        for char_id in removed_ids:
            owners.pop(char_id, None)
    timeline = state.get("timeline")
    if isinstance(timeline, list):
        state["timeline"] = [
            row for row in timeline
            if not (
                (isinstance(row, dict) and (
                    str(row.get("char_id") or "") in removed_ids
                    or str(row.get("id") or "") in removed_ids
                ))
                or (not isinstance(row, dict) and str(row) in removed_ids)
            )
        ]
    battle_state = state.get("battle_state")
    if isinstance(battle_state, dict):
        removed_slots = set()
        slots = battle_state.get("slots")
        if isinstance(slots, dict):
            for slot_id, slot in list(slots.items()):
                actor_id = str((slot or {}).get("actor_id", (slot or {}).get("actor_char_id", ""))) if isinstance(slot, dict) else ""
                if actor_id in removed_ids:
                    removed_slots.add(str(slot_id))
                    slots.pop(slot_id, None)
        elif isinstance(slots, list):
            kept = []
            for slot in slots:
                actor_id = str((slot or {}).get("actor_id", (slot or {}).get("actor_char_id", ""))) if isinstance(slot, dict) else ""
                if actor_id in removed_ids:
                    removed_slots.add(str((slot or {}).get("slot_id", (slot or {}).get("id", ""))))
                else:
                    kept.append(slot)
            battle_state["slots"] = kept
        for key in ("timeline", "tiebreak"):
            if isinstance(battle_state.get(key), list):
                battle_state[key] = [value for value in battle_state[key] if str(value) not in removed_slots]
        if isinstance(battle_state.get("intents"), dict):
            for slot_id in removed_slots:
                battle_state["intents"].pop(slot_id, None)
    state["ai_target_arrows"] = []


def _remove_side(state, side):
    chars = state.get("characters") if isinstance(state.get("characters"), list) else []
    removed = [str(char.get("id") or "") for char in chars if _char_side(char) == side]
    state["characters"] = [char for char in chars if _char_side(char) != side]
    _cleanup_removed_refs(state, removed)
    return [value for value in removed if value]


def _stage_background(stage):
    if not isinstance(stage, dict):
        return {}
    for key in ("background", "background_profile", "battle_background", "battle_map_data"):
        value = stage.get(key)
        if isinstance(value, dict) and value:
            return copy.deepcopy(value)
        if isinstance(value, str) and value.strip():
            return {"background_image": value.strip()}
    for key in ("background_image", "backgroundImage", "background_url", "backgroundUrl", "image_url", "image"):
        value = str(stage.get(key) or "").strip()
        if value:
            return {"background_image": value}
    return {}


def _stage_field_rows(profile, stage_id):
    rules = profile.get("rules") if isinstance(profile, dict) else []
    return [
        {
            "field_id": str(rule.get("rule_id") or f"stage_rule_{idx + 1}"),
            "source_type": "stage_preset",
            "source_id": str(stage_id or ""),
            "rule": copy.deepcopy(rule),
        }
        for idx, rule in enumerate(rules if isinstance(rules, list) else [])
        if isinstance(rule, dict)
    ]


def _owner_for(user_id, active_users, gm_user):
    users = active_users if isinstance(active_users, dict) else {}
    uid = str(user_id or "").strip()
    if uid and uid in users:
        return str(users[uid] or "GM"), uid
    gm = gm_user if isinstance(gm_user, dict) else {}
    return str(gm.get("username") or "GM"), str(gm.get("user_id") or "").strip() or None


def _formation_rows(formation, side):
    members = formation.get("members") if isinstance(formation, dict) else []
    rows = []
    for member in members if isinstance(members, list) else []:
        if not isinstance(member, dict):
            continue
        preset_id = str(member.get("preset_id") or "").strip()
        if not preset_id:
            continue
        rows.append({
            "preset_id": preset_id,
            "count": max(1, _safe_int(member.get("count"), 1)),
            "user_id": str(member.get("user_id") or "").strip() or None,
            "behavior_profile_override": copy.deepcopy(member.get("behavior_profile_override") or {}),
            "side": side,
        })
    return rows


def _assign_positions(state, new_chars):
    chars = [char for char in new_chars if isinstance(char, dict)]
    if not chars:
        return
    map_data = state.get("map_data") if isinstance(state.get("map_data"), dict) else {}
    width = max(6, _safe_int(map_data.get("width"), 20))
    height = max(6, _safe_int(map_data.get("height"), 15))
    occupied = {
        (_safe_int(char.get("x"), -1), _safe_int(char.get("y"), -1))
        for char in state.get("characters", []) if isinstance(char, dict)
        if char not in chars and _safe_int(char.get("x"), -1) >= 0 and _safe_int(char.get("y"), -1) >= 0
    }
    for side in SIDES:
        side_chars = [char for char in chars if _char_side(char) == side]
        xs = range(1, max(2, width // 2)) if side == "ally" else range(width - 2, max(width // 2, 1), -1)
        candidates = [(x, y) for x in xs for y in range(1, height - 1)]
        for char in side_chars:
            pos = next((value for value in candidates if value not in occupied), (-1, -1))
            char["x"], char["y"] = pos
            if pos != (-1, -1):
                occupied.add(pos)


def _set_status_clamped(char, name, value):
    numeric = max(0, _safe_int(value, 0))
    if str(name) == "HP" and _safe_int(char.get("maxHp"), 0) > 0:
        numeric = min(numeric, _safe_int(char.get("maxHp"), numeric))
    if str(name) == "MP" and _safe_int(char.get("maxMp"), 0) > 0:
        numeric = min(numeric, _safe_int(char.get("maxMp"), numeric))
    set_status_value(char, name, numeric)


def _initialize_battle_start(candidate, initial_chars):
    logs = []
    queue = list(initial_chars)
    processed = 0
    while queue:
        char = queue.pop(0)
        processed += 1
        if processed > 512:
            raise PresetDeploymentError("initialization_loop", "戦闘開始時効果の連鎖が上限を超えました。")
        for buff in char.get("special_buffs", []) if isinstance(char.get("special_buffs"), list) else []:
            if not isinstance(buff, dict):
                continue
            buff_name = str(buff.get("name") or "")
            effect_data = get_buff_effect(buff_name) or (buff.get("data") if isinstance(buff.get("data"), dict) else None)
            start_effects = effect_data.get("battle_start_effect") if isinstance(effect_data, dict) else []
            if not isinstance(start_effects, list) or not start_effects:
                continue
            effects = copy.deepcopy(start_effects)
            for effect in effects:
                if isinstance(effect, dict):
                    effect["timing"] = "BATTLE_START"
                    effect.setdefault("target", "self")
            _, snippets, changes = process_skill_effects(
                effects,
                "BATTLE_START",
                char,
                None,
                None,
                context={"characters": candidate.get("characters", []), "state": candidate},
            )
            if snippets:
                logs.append(f"[{char.get('name', '')} battle_start] " + " ".join(snippets))
            for target, change_type, name, value in changes:
                if change_type == "APPLY_STATE":
                    _set_status_clamped(target, name, get_status_value(target, name) + _safe_int(value, 0))
                elif change_type == "APPLY_BUFF" and isinstance(value, dict):
                    apply_buff(
                        target,
                        name,
                        value.get("lasting", 0),
                        value.get("delay", 0),
                        data=copy.deepcopy(value.get("data")),
                        count=value.get("count"),
                    )
                    logs.append(f"[{name}] applied to {target.get('name', '')}")
                elif change_type == "SUMMON_CHARACTER" and isinstance(value, dict):
                    result = apply_summon_change(None, candidate, target, value, run_battle_start=False)
                    if result.get("ok") and isinstance(result.get("char"), dict):
                        queue.append(result["char"])
                        logs.append(str(result.get("message") or "Summon applied"))
                elif change_type == "GRANT_SKILL" and isinstance(value, dict):
                    payload = copy.deepcopy(value)
                    payload.setdefault("skill_id", name)
                    result = apply_grant_skill_change(None, candidate, char, target, payload)
                    if result.get("ok"):
                        logs.append(str(result.get("message") or "Skill grant applied"))
    return logs


def _build_normal_candidate(state, resolved, store, *, gm_user=None, active_users=None):
    candidate = copy.deepcopy(state if isinstance(state, dict) else {})
    candidate.setdefault("characters", [])
    candidate.setdefault("character_owners", {})
    summary = {
        "target_mode": "normal",
        "added": {"ally": 0, "enemy": 0},
        "removed": {"ally": 0, "enemy": 0},
        "changes": [],
        "new_character_count": resolved.get("new_character_count", 0),
        "max_deployed_characters": MAX_DEPLOYED_CHARACTERS,
        "warnings": [],
        "issues": [],
        "can_apply": True,
        "ready": True,
    }
    stage_row = resolved.get("stage")
    if stage_row:
        stage = stage_row["record"]
        apply_options = stage_row["apply"]
        if apply_options.get("background") and apply_stage_background_to_state(candidate, _stage_background(stage)):
            summary["changes"].append("背景")
        if apply_options.get("field_effects"):
            profile = normalize_stage_field_effect_profile(stage.get("field_effect_profile"))
            candidate["stage_field_effect_profile"] = copy.deepcopy(profile)
            candidate["field_effects"] = _stage_field_rows(profile, stage_row["record_id"])
            summary["changes"].append(f"フィールド効果 {len(candidate['field_effects'])}件")
        if apply_options.get("stage_avatar"):
            avatar = normalize_stage_avatar(stage.get("stage_avatar"))
            candidate["stage_avatar_profile"] = avatar
            candidate["stage_avatar_enabled"] = bool(avatar.get("enabled", True))
            summary["changes"].append("ステージアバター")
        candidate["room_preset_state"] = {
            "selected_stage_id": stage_row["record_id"],
            "last_apply": copy.deepcopy(apply_options),
        }

    new_chars = []
    serial = len(candidate.get("characters", [])) + 1
    gm_name, gm_id = _owner_for(None, active_users, gm_user)
    for side in SIDES:
        formation = resolved["formations"].get(side)
        if not formation:
            continue
        if formation["mode"] == "replace":
            removed = _remove_side(candidate, side)
            summary["removed"][side] += len(removed)
        for row in _formation_rows(formation["record"], side):
            rec = get_record(store, "character", row["preset_id"])
            if not isinstance(rec, dict):
                raise PresetDeploymentError("invalid_reference", "編成内のキャラクターが見つかりません。", refresh_required=True)
            owner_name, owner_id = _owner_for(row.get("user_id"), active_users, gm_user) if side == "ally" else (gm_name, gm_id)
            for _ in range(row["count"]):
                char = build_runtime_character_from_preset(
                    rec,
                    serial,
                    side=side,
                    owner_name=owner_name,
                    owner_id=owner_id,
                )
                serial += 1
                if row.get("behavior_profile_override") and side == "enemy":
                    flags = char.setdefault("flags", {})
                    flags["behavior_profile"] = copy.deepcopy(row["behavior_profile_override"])
                apply_passive_effect_buffs(char)
                assign_runtime_character_number(char, candidate["characters"])
                candidate["characters"].append(char)
                candidate["character_owners"][char["id"]] = owner_name
                new_chars.append(char)
                summary["added"][side] += 1

    for row in resolved["characters"]:
        side = row["side"]
        owner_name, owner_id = _owner_for(row.get("user_id"), active_users, gm_user) if side == "ally" else (gm_name, gm_id)
        for _ in range(row["count"]):
            char = build_runtime_character_from_preset(
                row["record"],
                serial,
                side=side,
                owner_name=owner_name,
                owner_id=owner_id,
            )
            serial += 1
            apply_passive_effect_buffs(char)
            assign_runtime_character_number(char, candidate["characters"])
            candidate["characters"].append(char)
            candidate["character_owners"][char["id"]] = owner_name
            new_chars.append(char)
            summary["added"][side] += 1

    _assign_positions(candidate, new_chars)
    logs = _initialize_battle_start(candidate, new_chars)
    candidate["play_mode"] = "normal"
    if resolved["formations"].get("enemy"):
        candidate["battle_mode"] = "pve"
    return DeploymentBuild(candidate, summary, logs)


def _battle_only_defaults(bo):
    result = bo if isinstance(bo, dict) else {}
    result.setdefault("status", "draft")
    result.setdefault("ally_mode", "preset")
    result.setdefault("ally_entries", [])
    result.setdefault("enemy_entries", [])
    result.setdefault("required_ally_count", 0)
    result.setdefault("selected_stage_id", None)
    result.setdefault("ally_formation_id", None)
    result.setdefault("enemy_formation_id", None)
    result.setdefault("stage_field_effect_enabled", True)
    result.setdefault("stage_avatar_enabled", True)
    return result


def _validate_battle_only_candidate(candidate, store, active_users):
    bo = candidate.get("battle_only") if isinstance(candidate.get("battle_only"), dict) else {}
    users = active_users if isinstance(active_users, dict) else {}
    issues = []
    ally_entries = bo.get("ally_entries") if isinstance(bo.get("ally_entries"), list) else []
    enemy_entries = bo.get("enemy_entries") if isinstance(bo.get("enemy_entries"), list) else []
    ally_count = 0
    enemy_count = 0
    for row in ally_entries:
        if not isinstance(row, dict):
            issues.append("味方編成に不正な項目があります。")
            continue
        preset_id = str(row.get("preset_id") or "").strip()
        record = get_record(store, "character", preset_id)
        if not isinstance(record, dict) or not bool(record.get("allow_ally", True)):
            issues.append(f"味方キャラクターを利用できません: {preset_id or 'ID未指定'}")
            continue
        ally_count += 1
        user_id = str(row.get("user_id") or "").strip()
        if not user_id or user_id not in users:
            issues.append(f"{record.get('name') or preset_id}の担当ユーザーがルームにいません。")
    for row in enemy_entries:
        if not isinstance(row, dict):
            issues.append("敵編成に不正な項目があります。")
            continue
        preset_id = str(row.get("preset_id") or "").strip()
        record = get_record(store, "character", preset_id)
        count = max(0, _safe_int(row.get("count"), 0))
        if not isinstance(record, dict) or not bool(record.get("allow_enemy", True)):
            issues.append(f"敵キャラクターを利用できません: {preset_id or 'ID未指定'}")
            continue
        if count <= 0:
            issues.append(f"{record.get('name') or preset_id}の配置数が不正です。")
            continue
        enemy_count += count
    if ally_count <= 0:
        issues.append("味方編成が空です。")
    if enemy_count <= 0:
        issues.append("敵編成が空です。")
    required = max(0, _safe_int(bo.get("required_ally_count"), 0))
    if required > 0 and ally_count != required:
        issues.append(f"味方人数が不一致です（必要:{required} / 現在:{ally_count}）。")
    return {
        "ready": not issues,
        "issues": list(dict.fromkeys(issues)),
        "warnings": [],
        "ally_entry_count": ally_count,
        "enemy_entry_count": enemy_count,
        "required_ally_count": required,
    }


def _build_battle_only_candidate(state, resolved, store, *, gm_user=None, active_users=None):
    candidate = copy.deepcopy(state if isinstance(state, dict) else {})
    bo = _battle_only_defaults(candidate.get("battle_only"))
    candidate["battle_only"] = bo
    summary = {
        "target_mode": "battle_only",
        "added": {"ally": 0, "enemy": 0},
        "removed": {"ally": 0, "enemy": 0},
        "changes": [],
        "new_character_count": resolved.get("new_character_count", 0),
        "max_deployed_characters": MAX_DEPLOYED_CHARACTERS,
        "warnings": [],
        "issues": [],
        "can_apply": True,
        "ready": True,
    }
    stage_row = resolved.get("stage")
    if stage_row:
        stage = stage_row["record"]
        bo["selected_stage_id"] = stage_row["record_id"]
        bo["required_ally_count"] = max(0, _safe_int(stage.get("required_ally_count"), 0))
        if bo["required_ally_count"] <= 0 and resolved["formations"].get("enemy"):
            bo["required_ally_count"] = max(
                0,
                _safe_int(resolved["formations"]["enemy"]["record"].get("recommended_ally_count"), 0),
            )
        if stage_row["apply"].get("background"):
            bo["stage_background_profile"] = _stage_background(stage)
            apply_stage_background_to_state(candidate, bo["stage_background_profile"])
            summary["changes"].append("背景")
        if stage_row["apply"].get("field_effects"):
            bo["stage_field_effect_profile"] = normalize_stage_field_effect_profile(stage.get("field_effect_profile"))
            bo["stage_field_effect_enabled"] = True
        if stage_row["apply"].get("stage_avatar"):
            avatar = normalize_stage_avatar(stage.get("stage_avatar"))
            bo["stage_avatar_profile"] = avatar
            bo["stage_avatar_enabled"] = bool(avatar.get("enabled", True))
        summary["changes"].append("ステージ")

    gm_name, gm_id = _owner_for(None, active_users, gm_user)
    for side in SIDES:
        key = f"{side}_entries"
        formation_key = f"{side}_formation_id"
        formation = resolved["formations"].get(side)
        if not formation:
            continue
        existing = bo.get(key) if isinstance(bo.get(key), list) else []
        if formation["mode"] == "replace":
            summary["removed"][side] += (
                sum(max(1, _safe_int(row.get("count"), 1)) for row in existing if isinstance(row, dict))
                if side == "enemy" else len(existing)
            )
            existing = []
        rows = _formation_rows(formation["record"], side)
        if side == "ally":
            expanded = []
            for row in rows:
                owner_name, owner_id = _owner_for(row.get("user_id"), active_users, gm_user)
                _ = owner_name
                expanded.extend({"preset_id": row["preset_id"], "user_id": owner_id or gm_id} for _ in range(row["count"]))
            bo[key] = [*existing, *expanded]
            summary["added"][side] += len(expanded)
        else:
            normalized = [
                {
                    "preset_id": row["preset_id"],
                    "count": row["count"],
                    "behavior_profile_override": copy.deepcopy(row.get("behavior_profile_override") or {}),
                }
                for row in rows
            ]
            bo[key] = [*existing, *normalized]
            summary["added"][side] += sum(row["count"] for row in normalized)
        bo[formation_key] = formation["record_id"]

    for row in resolved["characters"]:
        side = row["side"]
        key = f"{side}_entries"
        existing = bo.get(key) if isinstance(bo.get(key), list) else []
        if side == "ally":
            _, owner_id = _owner_for(row.get("user_id"), active_users, gm_user)
            existing.extend({"preset_id": row["record_id"], "user_id": owner_id or gm_id} for _ in range(row["count"]))
        else:
            existing.append({"preset_id": row["record_id"], "count": row["count"], "behavior_profile_override": {}})
        bo[key] = existing
        summary["added"][side] += row["count"]

    bo["ally_mode"] = "preset"
    bo["status"] = "draft"
    candidate["play_mode"] = "battle_only"
    summary.update(_validate_battle_only_candidate(candidate, store, active_users))
    return DeploymentBuild(candidate, summary, [])


def build_deployment_candidate(
    state,
    resolved,
    store,
    *,
    gm_user=None,
    active_users=None,
):
    if resolved.get("target_mode") == "battle_only":
        return _build_battle_only_candidate(
            state,
            resolved,
            store,
            gm_user=gm_user,
            active_users=active_users,
        )
    return _build_normal_candidate(
        state,
        resolved,
        store,
        gm_user=gm_user,
        active_users=active_users,
    )


def preview_deployment(state, request_data, store, **context):
    resolved = resolve_deployment_request(
        store,
        request_data,
        user_id=context.get("user_id"),
        is_app_admin=context.get("is_app_admin", False),
        room_role=context.get("room_role"),
    )
    build = build_deployment_candidate(
        state,
        resolved,
        store,
        gm_user=context.get("gm_user"),
        active_users=context.get("active_users"),
    )
    return copy.deepcopy(build.summary)


def apply_deployment(state, request_data, store, **context):
    resolved = resolve_deployment_request(
        store,
        request_data,
        user_id=context.get("user_id"),
        is_app_admin=context.get("is_app_admin", False),
        room_role=context.get("room_role"),
    )
    build = build_deployment_candidate(
        state,
        resolved,
        store,
        gm_user=context.get("gm_user"),
        active_users=context.get("active_users"),
    )
    state.clear()
    state.update(build.state)
    return copy.deepcopy(build.summary), list(build.logs)
