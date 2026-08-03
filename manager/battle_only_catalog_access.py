"""戦闘専用プリセットversion 3の権限・参照・分類操作。

このモジュールはSocketやFlaskのrequestへ依存しない。要求者のuser_id、
アプリ管理者フラグ、対象ルームで解決済みのroleを入力として受け取り、
保存キャッシュに対する共通判定を返す。
"""

import copy

from manager.battle_only_presets import normalize_access_control, normalize_catalog_meta


RECORD_MAP_KEYS = {
    "character": "character_presets",
    "enemy_formation": "enemy_formations",
    "ally_formation": "ally_formations",
    "stage": "stage_presets",
    "collection": "catalog_collections",
}

ROOM_GM_ROLES = frozenset({"owner", "gm"})


def record_map(store, record_type, *, create=False):
    key = RECORD_MAP_KEYS.get(str(record_type or "").strip())
    if not key:
        return None
    rows = store.get(key) if isinstance(store, dict) else None
    if record_type == "character" and not isinstance(rows, dict) and isinstance(store, dict):
        rows = store.get("presets")
    if not isinstance(rows, dict):
        rows = {}
        if create and isinstance(store, dict):
            store[key] = rows
    elif create and record_type == "character" and isinstance(store, dict):
        store[key] = rows
    return rows


def get_record(store, record_type, record_id):
    rows = record_map(store, record_type)
    return rows.get(str(record_id or "").strip()) if isinstance(rows, dict) else None


def capabilities(record, *, user_id=None, is_app_admin=False, room_role=None):
    rec = record if isinstance(record, dict) else {}
    uid = str(user_id or "").strip()
    acl = normalize_access_control(
        rec.get("access_control"),
        legacy_visibility=rec.get("visibility", "public"),
    )
    owner = str(acl.get("owner_user_id") or "").strip()
    editors = set(acl.get("editor_user_ids") or [])
    viewers = set(acl.get("viewer_user_ids") or [])
    mode = acl.get("viewer_mode", "public")
    admin = bool(is_app_admin)
    is_owner = bool(uid and owner and uid == owner)
    is_editor = bool(uid and uid in editors)
    is_named_viewer = bool(uid and uid in viewers)
    gm_context = str(room_role or "").strip().lower() in ROOM_GM_ROLES

    can_view = bool(
        admin
        or is_owner
        or is_editor
        or is_named_viewer
        or (uid and mode == "public")
        or (uid and mode == "gm" and gm_context)
    )
    can_use = can_view
    can_edit = bool(admin or is_owner or is_editor)
    can_manage_acl = bool(admin or is_owner)
    can_delete = can_manage_acl
    can_deploy = bool(can_use and gm_context)
    return {
        "can_view": can_view,
        "can_use": can_use,
        "can_deploy": can_deploy,
        "can_edit": can_edit,
        "can_delete": can_delete,
        "can_manage_acl": can_manage_acl,
        "is_owner": is_owner,
        "is_editor": is_editor,
        "is_named_viewer": is_named_viewer,
        "is_orphaned": not bool(owner),
        "viewer_mode": mode,
    }


def sanitize_record_for_user(
    record,
    *,
    user_id=None,
    is_app_admin=False,
    room_role=None,
    owner_name=None,
):
    caps = capabilities(
        record,
        user_id=user_id,
        is_app_admin=is_app_admin,
        room_role=room_role,
    )
    if not caps["can_view"]:
        return None
    result = copy.deepcopy(record)
    acl = normalize_access_control(
        result.get("access_control"),
        legacy_visibility=result.get("visibility", "public"),
    )
    if not caps["can_manage_acl"]:
        result.pop("access_control", None)
    else:
        result["access_control"] = acl
    result["capabilities"] = caps
    result["owner_display_name"] = str(owner_name or result.get("created_by") or "").strip()
    result["shared_via"] = (
        "owner" if caps["is_owner"]
        else "editor" if caps["is_editor"]
        else "individual" if caps["is_named_viewer"]
        else acl["viewer_mode"]
    )
    return result


def filter_visible_records(
    rows,
    *,
    user_id=None,
    is_app_admin=False,
    room_role=None,
    owner_names=None,
):
    result = {}
    names = owner_names if isinstance(owner_names, dict) else {}
    for record_id, record in (rows if isinstance(rows, dict) else {}).items():
        if not isinstance(record, dict):
            continue
        owner_id = str(
            (record.get("access_control") or {}).get("owner_user_id") or ""
        ).strip()
        sanitized = sanitize_record_for_user(
            record,
            user_id=user_id,
            is_app_admin=is_app_admin,
            room_role=room_role,
            owner_name=names.get(owner_id),
        )
        if sanitized is not None:
            result[str(record_id)] = sanitized
    return result


def normalize_record_security(record, *, creator_user_id=None, existing=None, allow_acl=False):
    """保存直前のACLと分類を正規化する。

    既存レコードではpayloadにACLが無い古いUIからの保存でも現在ACLを維持する。
    新規レコードは作成者をownerにする。ACL変更を許可されない呼び出しでは既存ACLを
    必ず優先する。
    """
    rec = copy.deepcopy(record if isinstance(record, dict) else {})
    current = existing if isinstance(existing, dict) else {}
    current_acl = current.get("access_control") if isinstance(current.get("access_control"), dict) else None
    incoming_acl = rec.get("access_control") if isinstance(rec.get("access_control"), dict) else None
    if not allow_acl:
        acl_source = current_acl
    elif current_acl is not None and incoming_acl is None:
        acl_source = current_acl
    else:
        acl_source = incoming_acl
    if current:
        owner_default = (current_acl or {}).get("owner_user_id")
    else:
        owner_default = creator_user_id
    acl = normalize_access_control(
        acl_source,
        legacy_visibility=(current.get("visibility") if current else rec.get("visibility", "public")),
        owner_user_id=owner_default,
    )
    if not current and creator_user_id:
        acl["owner_user_id"] = str(creator_user_id).strip()
        acl = normalize_access_control(acl, legacy_visibility=acl["viewer_mode"])
    rec["access_control"] = acl
    rec["visibility"] = acl["viewer_mode"]
    if isinstance(current.get("catalog_meta"), dict) and "catalog_meta" not in rec:
        rec["catalog_meta"] = normalize_catalog_meta(current.get("catalog_meta"))
    else:
        rec["catalog_meta"] = normalize_catalog_meta(rec.get("catalog_meta"))
    return rec


def reference_blockers(store, record_type, record_id):
    target = str(record_id or "").strip()
    blockers = []
    if not target:
        return blockers
    if record_type == "character":
        for kind, key in (
            ("enemy_formation", "enemy_formations"),
            ("ally_formation", "ally_formations"),
        ):
            for parent_id, parent in (store.get(key) or {}).items():
                members = parent.get("members") if isinstance(parent, dict) else []
                if any(
                    isinstance(row, dict) and str(row.get("preset_id") or "").strip() == target
                    for row in (members if isinstance(members, list) else [])
                ):
                    blockers.append({
                        "type": kind,
                        "id": str(parent_id),
                        "name": str(parent.get("name") or parent_id),
                    })
    elif record_type in {"enemy_formation", "ally_formation"}:
        ref_key = "enemy_formation_id" if record_type == "enemy_formation" else "ally_formation_id"
        for parent_id, parent in (store.get("stage_presets") or {}).items():
            if isinstance(parent, dict) and str(parent.get(ref_key) or "").strip() == target:
                blockers.append({
                    "type": "stage",
                    "id": str(parent_id),
                    "name": str(parent.get("name") or parent_id),
                })
    return blockers


def _acl_audience(acl):
    normalized = normalize_access_control(acl)
    return {
        value for value in [normalized.get("owner_user_id"), *normalized.get("editor_user_ids", []), *normalized.get("viewer_user_ids", [])]
        if value
    }


def reference_scope_covers(parent, child):
    parent_acl = normalize_access_control(
        (parent or {}).get("access_control"),
        legacy_visibility=(parent or {}).get("visibility", "public"),
    )
    child_acl = normalize_access_control(
        (child or {}).get("access_control"),
        legacy_visibility=(child or {}).get("visibility", "public"),
    )
    parent_mode = parent_acl["viewer_mode"]
    child_mode = child_acl["viewer_mode"]
    if child_mode == "public":
        return True
    if parent_mode == "public":
        return False
    if parent_mode == "gm":
        return child_mode == "gm"
    if child_mode != "restricted":
        return False
    return _acl_audience(parent_acl).issubset(_acl_audience(child_acl))


def validate_parent_references(store, record_type, record):
    refs = []
    if record_type in {"enemy_formation", "ally_formation"}:
        refs = [
            ("character", row.get("preset_id"))
            for row in record.get("members", []) if isinstance(row, dict)
        ]
    elif record_type == "stage":
        refs = [
            ("enemy_formation", record.get("enemy_formation_id")),
            ("ally_formation", record.get("ally_formation_id")),
        ]
    for child_type, child_id in refs:
        if not child_id:
            continue
        child = get_record(store, child_type, child_id)
        if not isinstance(child, dict) or not reference_scope_covers(record, child):
            return False
    return True


def clear_collection_references(store, collection_id, *, section_id=None):
    collection = str(collection_id or "").strip()
    section = str(section_id or "").strip() or None
    changed = 0
    for record_type in ("character", "enemy_formation", "ally_formation", "stage"):
        for record in (record_map(store, record_type) or {}).values():
            if not isinstance(record, dict):
                continue
            meta = normalize_catalog_meta(record.get("catalog_meta"))
            if meta.get("collection_id") != collection:
                continue
            if section is not None:
                if meta.get("section_id") != section:
                    continue
                meta["section_id"] = None
            else:
                meta["collection_id"] = None
                meta["section_id"] = None
            record["catalog_meta"] = meta
            changed += 1
    return changed


def owned_asset_counts(store, user_id):
    uid = str(user_id or "").strip()
    result = {record_type: 0 for record_type in RECORD_MAP_KEYS}
    for record_type in result:
        for record in (record_map(store, record_type) or {}).values():
            owner = str((record.get("access_control") or {}).get("owner_user_id") or "").strip()
            if owner == uid:
                result[record_type] += 1
    result["total"] = sum(result.values())
    return result


def transfer_user_assets(store, old_user_id, new_user_id):
    old_uid = str(old_user_id or "").strip()
    new_uid = str(new_user_id or "").strip()
    counts = {record_type: 0 for record_type in RECORD_MAP_KEYS}
    acl_refs_removed = 0
    for record_type in counts:
        for record in (record_map(store, record_type) or {}).values():
            if not isinstance(record, dict):
                continue
            acl = normalize_access_control(
                record.get("access_control"),
                legacy_visibility=record.get("visibility", "public"),
            )
            if str(acl.get("owner_user_id") or "") == old_uid:
                acl["owner_user_id"] = new_uid
                if old_uid and old_uid != new_uid:
                    acl["editor_user_ids"] = [old_uid, *acl.get("editor_user_ids", [])]
                counts[record_type] += 1
            before = len(acl.get("editor_user_ids", [])) + len(acl.get("viewer_user_ids", []))
            acl["editor_user_ids"] = [uid for uid in acl.get("editor_user_ids", []) if uid != new_uid]
            acl["viewer_user_ids"] = [
                uid for uid in acl.get("viewer_user_ids", [])
                if uid not in {old_uid, new_uid}
            ]
            acl = normalize_access_control(acl, legacy_visibility=acl.get("viewer_mode", "public"))
            after = len(acl.get("editor_user_ids", [])) + len(acl.get("viewer_user_ids", []))
            acl_refs_removed += max(0, before - after)
            record["access_control"] = acl
            record["visibility"] = acl["viewer_mode"]
    counts["total"] = sum(counts.values())
    counts["acl_refs_removed"] = acl_refs_removed
    return counts


def scrub_user_from_acl(store, user_id):
    uid = str(user_id or "").strip()
    removed = 0
    for record_type in RECORD_MAP_KEYS:
        for record in (record_map(store, record_type) or {}).values():
            if not isinstance(record, dict):
                continue
            acl = normalize_access_control(
                record.get("access_control"),
                legacy_visibility=record.get("visibility", "public"),
            )
            before = len(acl["editor_user_ids"]) + len(acl["viewer_user_ids"])
            acl["editor_user_ids"] = [value for value in acl["editor_user_ids"] if value != uid]
            acl["viewer_user_ids"] = [value for value in acl["viewer_user_ids"] if value != uid]
            removed += before - len(acl["editor_user_ids"]) - len(acl["viewer_user_ids"])
            record["access_control"] = acl
    return removed


def validate_deploy_references(store, battle_only, *, user_id=None, is_app_admin=False, room_role=None):
    """戦闘投入で利用する全グローバル参照を現在権限で検査する。"""
    bo = battle_only if isinstance(battle_only, dict) else {}
    refs = []
    for record_type, key in (
        ("stage", "selected_stage_id"),
        ("enemy_formation", "enemy_formation_id"),
        ("ally_formation", "ally_formation_id"),
    ):
        record_id = str(bo.get(key) or "").strip()
        if record_id:
            refs.append((record_type, record_id))
    for key in ("ally_entries", "enemy_entries"):
        for row in bo.get(key) if isinstance(bo.get(key), list) else []:
            if isinstance(row, dict) and str(row.get("preset_id") or "").strip():
                refs.append(("character", str(row.get("preset_id")).strip()))
    for record_type, record_id in refs:
        record = get_record(store, record_type, record_id)
        caps = capabilities(
            record,
            user_id=user_id,
            is_app_admin=is_app_admin,
            room_role=room_role,
        ) if isinstance(record, dict) else {}
        if not caps.get("can_use"):
            return False
        if record_type in {"enemy_formation", "ally_formation", "stage"} and not validate_parent_references(store, record_type, record):
            return False
    return True


def touch_last_used_for_battle(store, battle_only, timestamp_ms):
    bo = battle_only if isinstance(battle_only, dict) else {}
    touched = 0
    refs = {
        ("stage", str(bo.get("selected_stage_id") or "").strip()),
        ("enemy_formation", str(bo.get("enemy_formation_id") or "").strip()),
        ("ally_formation", str(bo.get("ally_formation_id") or "").strip()),
    }
    for key in ("ally_entries", "enemy_entries"):
        for row in bo.get(key) if isinstance(bo.get(key), list) else []:
            if isinstance(row, dict):
                refs.add(("character", str(row.get("preset_id") or "").strip()))
    for record_type, record_id in refs:
        if not record_id:
            continue
        record = get_record(store, record_type, record_id)
        if not isinstance(record, dict):
            continue
        meta = normalize_catalog_meta(record.get("catalog_meta"))
        meta["last_used_at"] = max(0, int(timestamp_ms or 0))
        record["catalog_meta"] = meta
        touched += 1
    return touched
