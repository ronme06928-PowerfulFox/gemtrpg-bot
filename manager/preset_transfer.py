"""Portable collection packages for moving preset assets between environments."""

from __future__ import annotations

import copy
import json
import re
import uuid
from datetime import datetime, timezone

from manager.battle_only_catalog_access import (
    capabilities,
    get_record,
    record_map,
    validate_parent_references,
)
from manager.battle_only_presets import _normalize_store, normalize_access_control


PACKAGE_SCHEMA = "gem_dicebot_preset_package.v1"
MAX_PACKAGE_BYTES = 5 * 1024 * 1024
MAX_PACKAGE_RESOURCES = 1000
RESOURCE_TYPES = ("collection", "character", "enemy_formation", "ally_formation", "stage")
TYPE_PREFIXES = {
    "collection": "boc",
    "character": "bop",
    "enemy_formation": "bof",
    "ally_formation": "baf",
    "stage": "bos",
}
_SAFE_ID = re.compile(r"^[^\x00-\x1f]{1,128}$")


class PresetPackageError(ValueError):
    def __init__(self, code, message, *, details=None):
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)
        self.details = details if isinstance(details, (dict, list)) else None


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _resource_key(resource_type, stable_id):
    return f"{resource_type}:{stable_id}"


def _new_id(resource_type):
    return f"{TYPE_PREFIXES.get(resource_type, 'bor')}_{uuid.uuid4().hex[:12]}"


def _sanitize_record(record, resource_type, *, root_collection_id=None):
    exported = copy.deepcopy(record if isinstance(record, dict) else {})
    for key in (
        "access_control",
        "capabilities",
        "created_at",
        "created_by",
        "owner_display_name",
        "revision",
        "shared_via",
        "updated_at",
        "updated_by",
        "visibility",
    ):
        exported.pop(key, None)
    if resource_type != "collection":
        meta = exported.get("catalog_meta") if isinstance(exported.get("catalog_meta"), dict) else {}
        meta = copy.deepcopy(meta)
        meta["last_used_at"] = 0
        if root_collection_id and meta.get("collection_id") != root_collection_id:
            meta["collection_id"] = None
            meta["section_id"] = None
        exported["catalog_meta"] = meta
    if resource_type == "ally_formation":
        for member in exported.get("members") if isinstance(exported.get("members"), list) else []:
            if isinstance(member, dict):
                member.pop("user_id", None)
    return exported


def _dependency_keys(store, collection_id):
    keys = {("collection", collection_id)}
    for resource_type in RESOURCE_TYPES:
        if resource_type == "collection":
            continue
        for record_id, record in (record_map(store, resource_type) or {}).items():
            meta = record.get("catalog_meta") if isinstance(record, dict) else {}
            if isinstance(meta, dict) and str(meta.get("collection_id") or "") == collection_id:
                keys.add((resource_type, str(record_id)))

    changed = True
    while changed:
        changed = False
        for resource_type, record_id in list(keys):
            record = get_record(store, resource_type, record_id)
            refs = []
            if resource_type in {"enemy_formation", "ally_formation"} and isinstance(record, dict):
                refs = [
                    ("character", str(row.get("preset_id") or "").strip())
                    for row in record.get("members", []) if isinstance(row, dict)
                ]
            elif resource_type == "stage" and isinstance(record, dict):
                refs = [
                    ("enemy_formation", str(record.get("enemy_formation_id") or "").strip()),
                    ("ally_formation", str(record.get("ally_formation_id") or "").strip()),
                ]
            for ref in refs:
                if ref[1] and ref not in keys:
                    keys.add(ref)
                    changed = True
    return keys


def build_collection_package(store, collection_id, *, can_view):
    collection_id = str(collection_id or "").strip()
    collection = get_record(store, "collection", collection_id)
    if not isinstance(collection, dict) or not can_view("collection", collection):
        raise PresetPackageError("not_found", "出力できるコレクションが見つかりません。")
    resources = []
    for resource_type, stable_id in sorted(
        _dependency_keys(store, collection_id),
        key=lambda item: (RESOURCE_TYPES.index(item[0]), item[1]),
    ):
        record = get_record(store, resource_type, stable_id)
        if not isinstance(record, dict):
            raise PresetPackageError(
                "missing_reference",
                f"参照先が見つかりません: {_resource_key(resource_type, stable_id)}",
            )
        if not can_view(resource_type, record):
            raise PresetPackageError(
                "permission_denied",
                f"参照素材を出力する権限がありません: {record.get('name') or stable_id}",
            )
        resources.append({
            "resource_type": resource_type,
            "stable_id": stable_id,
            "source_revision": max(1, int(record.get("revision", 1) or 1)),
            "record": _sanitize_record(record, resource_type, root_collection_id=collection_id),
        })
    return {
        "schema": PACKAGE_SCHEMA,
        "schema_version": 1,
        "package_id": f"collection:{collection_id}",
        "name": str(collection.get("name") or collection_id),
        "root_collection_id": collection_id,
        "exported_at": _now_iso(),
        "resources": resources,
    }


def package_json(package):
    return json.dumps(package, ensure_ascii=False, indent=2)


def parse_package(raw):
    if isinstance(raw, str):
        if len(raw.encode("utf-8")) > MAX_PACKAGE_BYTES:
            raise PresetPackageError("package_too_large", "移送JSONは5MB以下にしてください。")
        try:
            package = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PresetPackageError("invalid_json", f"JSONを読み取れません: {exc.msg}") from exc
    elif isinstance(raw, dict):
        package = copy.deepcopy(raw)
        try:
            encoded_size = len(json.dumps(package, ensure_ascii=False).encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise PresetPackageError("invalid_json", "移送JSONに変換できない値が含まれています。") from exc
        if encoded_size > MAX_PACKAGE_BYTES:
            raise PresetPackageError("package_too_large", "移送JSONは5MB以下にしてください。")
    else:
        raise PresetPackageError("invalid_json", "移送JSONの形式が正しくありません。")
    if package.get("schema") != PACKAGE_SCHEMA or int(package.get("schema_version", 0) or 0) != 1:
        raise PresetPackageError("unsupported_schema", "対応していない移送JSON形式です。")
    resources = package.get("resources")
    if not isinstance(resources, list) or not resources:
        raise PresetPackageError("empty_package", "移送対象の素材がありません。")
    if len(resources) > MAX_PACKAGE_RESOURCES:
        raise PresetPackageError("too_many_resources", "1回に取り込める素材は1000件までです。")
    seen = set()
    normalized_resources = []
    for item in resources:
        if not isinstance(item, dict):
            raise PresetPackageError("invalid_resource", "素材レコードの形式が正しくありません。")
        resource_type = str(item.get("resource_type") or "").strip()
        stable_id = str(item.get("stable_id") or "").strip()
        if resource_type not in RESOURCE_TYPES or not _SAFE_ID.fullmatch(stable_id):
            raise PresetPackageError("invalid_resource", f"素材種別または安定IDが不正です: {resource_type}:{stable_id}")
        key = (resource_type, stable_id)
        if key in seen:
            raise PresetPackageError("duplicate_resource", f"同じ素材が重複しています: {_resource_key(*key)}")
        seen.add(key)
        if not isinstance(item.get("record"), dict):
            raise PresetPackageError("invalid_resource", f"素材本文がありません: {_resource_key(*key)}")
        try:
            source_revision = max(1, int(item.get("source_revision", 1) or 1))
        except (TypeError, ValueError) as exc:
            raise PresetPackageError(
                "invalid_resource",
                f"改訂番号が不正です: {_resource_key(*key)}",
            ) from exc
        normalized_resources.append({
            "resource_type": resource_type,
            "stable_id": stable_id,
            "source_revision": source_revision,
            "record": copy.deepcopy(item["record"]),
        })
    result = copy.deepcopy(package)
    result["resources"] = normalized_resources
    result["root_collection_id"] = str(package.get("root_collection_id") or "").strip() or None
    return result


def _incoming_store(package):
    raw = {
        "version": 3,
        "character_presets": {},
        "enemy_formations": {},
        "ally_formations": {},
        "stage_presets": {},
        "catalog_collections": {},
    }
    for item in package["resources"]:
        rows = record_map(raw, item["resource_type"], create=True)
        record = copy.deepcopy(item["record"])
        record["id"] = item["stable_id"]
        rows[item["stable_id"]] = record
    return _normalize_store(raw)


def _reference_errors(candidate, incoming_keys, *, can_use_existing):
    errors = []
    for resource_type, stable_id in incoming_keys:
        record = get_record(candidate, resource_type, stable_id)
        refs = []
        if resource_type in {"enemy_formation", "ally_formation"} and isinstance(record, dict):
            refs = [
                ("character", str(row.get("preset_id") or "").strip())
                for row in record.get("members", []) if isinstance(row, dict)
            ]
        elif resource_type == "stage" and isinstance(record, dict):
            refs = [
                ("enemy_formation", str(record.get("enemy_formation_id") or "").strip()),
                ("ally_formation", str(record.get("ally_formation_id") or "").strip()),
            ]
        for ref_type, ref_id in refs:
            if not ref_id:
                continue
            child = get_record(candidate, ref_type, ref_id)
            if not isinstance(child, dict):
                errors.append({
                    "code": "missing_reference",
                    "resource": _resource_key(resource_type, stable_id),
                    "reference": _resource_key(ref_type, ref_id),
                })
            elif (ref_type, ref_id) not in incoming_keys and not can_use_existing(ref_type, child):
                errors.append({
                    "code": "reference_permission_denied",
                    "resource": _resource_key(resource_type, stable_id),
                    "reference": _resource_key(ref_type, ref_id),
                })
    return errors


def preview_package(package_raw, store, *, can_update, can_use_existing):
    package = parse_package(package_raw)
    incoming = _incoming_store(package)
    incoming_keys = {
        (item["resource_type"], item["stable_id"])
        for item in package["resources"]
    }
    candidate = copy.deepcopy(store)
    for resource_type, stable_id in incoming_keys:
        record_map(candidate, resource_type, create=True)[stable_id] = copy.deepcopy(
            get_record(incoming, resource_type, stable_id)
        )
    errors = _reference_errors(candidate, incoming_keys, can_use_existing=can_use_existing)
    items = []
    counts = {"new": 0, "conflict": 0}
    for item in package["resources"]:
        resource_type = item["resource_type"]
        stable_id = item["stable_id"]
        existing = get_record(store, resource_type, stable_id)
        status = "conflict" if isinstance(existing, dict) else "new"
        counts[status] += 1
        allowed = ["create"] if status == "new" else ["copy", "skip"]
        if status == "conflict" and can_update(resource_type, existing):
            allowed.insert(0, "update")
        items.append({
            "key": _resource_key(resource_type, stable_id),
            "resource_type": resource_type,
            "stable_id": stable_id,
            "name": str(item["record"].get("name") or stable_id),
            "status": status,
            "existing_revision": max(1, int(existing.get("revision", 1) or 1)) if status == "conflict" else None,
            "allowed_actions": allowed,
            "default_action": "create" if status == "new" else "skip",
        })
    return {
        "schema": PACKAGE_SCHEMA,
        "package_id": str(package.get("package_id") or ""),
        "name": str(package.get("name") or package.get("package_id") or "移送パッケージ"),
        "root_collection_id": package.get("root_collection_id"),
        "counts": counts,
        "items": items,
        "errors": errors,
        "can_import": not errors,
    }


def _remap_record(record, resource_type, id_map):
    rec = copy.deepcopy(record)
    if resource_type in {"enemy_formation", "ally_formation"}:
        for member in rec.get("members") if isinstance(rec.get("members"), list) else []:
            if isinstance(member, dict):
                old = str(member.get("preset_id") or "").strip()
                member["preset_id"] = id_map.get(("character", old), old)
    elif resource_type == "stage":
        for ref_type, field in (
            ("enemy_formation", "enemy_formation_id"),
            ("ally_formation", "ally_formation_id"),
        ):
            old = str(rec.get(field) or "").strip()
            rec[field] = id_map.get((ref_type, old), old) if old else None
    if resource_type != "collection":
        meta = rec.get("catalog_meta") if isinstance(rec.get("catalog_meta"), dict) else {}
        old_collection = str(meta.get("collection_id") or "").strip()
        meta["collection_id"] = id_map.get(("collection", old_collection), old_collection) if old_collection else None
        meta["last_used_at"] = 0
        rec["catalog_meta"] = meta
    return rec


def apply_package(
    package_raw,
    store,
    *,
    owner_user_id,
    actions,
    expected_revisions=None,
    can_update,
    can_use_existing,
    owner_name="",
):
    package = parse_package(package_raw)
    preview = preview_package(
        package,
        store,
        can_update=can_update,
        can_use_existing=can_use_existing,
    )
    if preview["errors"]:
        raise PresetPackageError("invalid_references", "参照関係を解決できません。", details=preview["errors"])
    action_map = actions if isinstance(actions, dict) else {}
    revision_map = expected_revisions if isinstance(expected_revisions, dict) else {}
    item_by_key = {item["key"]: item for item in preview["items"]}
    id_map = {}
    resolved_actions = {}
    for item in package["resources"]:
        key = _resource_key(item["resource_type"], item["stable_id"])
        preview_item = item_by_key[key]
        action = str(action_map.get(key) or preview_item["default_action"]).strip()
        if action not in preview_item["allowed_actions"]:
            raise PresetPackageError("invalid_action", f"選択できない処理です: {key}={action}")
        resolved_actions[key] = action
        if action == "copy":
            id_map[(item["resource_type"], item["stable_id"])] = _new_id(item["resource_type"])
        else:
            id_map[(item["resource_type"], item["stable_id"])] = item["stable_id"]

    incoming = _incoming_store(package)
    root_source_id = package.get("root_collection_id")
    root_target_id = id_map.get(("collection", root_source_id), root_source_id) if root_source_id else None
    root_existing = get_record(store, "collection", root_target_id) if root_target_id else None
    root_acl = None
    root_action = resolved_actions.get(_resource_key("collection", root_source_id)) if root_source_id else None
    if root_action == "update" and isinstance(root_existing, dict):
        root_acl = normalize_access_control(
            root_existing.get("access_control"),
            legacy_visibility=root_existing.get("visibility", "restricted"),
        )

    result = {"created": [], "updated": [], "copied": [], "skipped": []}
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    for item in package["resources"]:
        resource_type = item["resource_type"]
        source_id = item["stable_id"]
        key = _resource_key(resource_type, source_id)
        action = resolved_actions[key]
        if action == "skip":
            result["skipped"].append(key)
            continue
        target_id = id_map[(resource_type, source_id)]
        rows = record_map(store, resource_type, create=True)
        existing = rows.get(target_id)
        record = _remap_record(get_record(incoming, resource_type, source_id), resource_type, id_map)
        record["id"] = target_id
        record["created_at"] = existing.get("created_at", now_ms) if isinstance(existing, dict) else now_ms
        record["updated_at"] = now_ms
        if action == "update":
            if not isinstance(existing, dict) or not can_update(resource_type, existing):
                raise PresetPackageError("conflict", f"更新権限または更新対象が失われました: {key}")
            expected_revision = revision_map.get(key)
            if expected_revision is not None:
                try:
                    revision_matches = int(expected_revision) == int(existing.get("revision", 0))
                except (TypeError, ValueError):
                    revision_matches = False
                if not revision_matches:
                    raise PresetPackageError(
                        "conflict",
                        f"確認後に別の利用者が更新しました: {key}",
                    )
            record["access_control"] = copy.deepcopy(existing.get("access_control"))
            record["visibility"] = existing.get("visibility", "restricted")
            record["catalog_meta"] = record.get("catalog_meta") or existing.get("catalog_meta")
            result["updated"].append(_resource_key(resource_type, target_id))
        else:
            inherited_acl = None
            meta = record.get("catalog_meta") if isinstance(record.get("catalog_meta"), dict) else {}
            if root_acl and str(meta.get("collection_id") or "") == str(root_target_id or ""):
                inherited_acl = copy.deepcopy(root_acl)
            record["access_control"] = inherited_acl or {
                "owner_user_id": owner_user_id,
                "editor_user_ids": [],
                "viewer_mode": "restricted",
                "viewer_user_ids": [],
            }
            record["visibility"] = record["access_control"]["viewer_mode"]
            record["created_by"] = str(owner_name or "")
            result["copied" if action == "copy" else "created"].append(
                _resource_key(resource_type, target_id)
            )
        record["updated_by"] = str(owner_name or record.get("updated_by") or "")
        rows[target_id] = record

    for resource_type in ("enemy_formation", "ally_formation", "stage"):
        target_ids = []
        for (kind, source_id), target_id in id_map.items():
            if kind == resource_type and resolved_actions.get(_resource_key(kind, source_id)) != "skip":
                target_ids.append(target_id)
        for record_id in target_ids:
            record = get_record(store, resource_type, record_id)
            if not validate_parent_references(store, resource_type, record):
                raise PresetPackageError(
                    "visibility_mismatch",
                    f"公開範囲または参照関係が一致しません: {_resource_key(resource_type, record_id)}",
                )
    result["id_map"] = {
        _resource_key(resource_type, source_id): target_id
        for (resource_type, source_id), target_id in id_map.items()
    }
    return result


def legacy_store_package(legacy_store):
    """旧キャッシュを管理者が必要時だけ回収するための移送形式へ変換する。"""
    store = _normalize_store(legacy_store)
    resources = []
    for resource_type in RESOURCE_TYPES:
        for stable_id, record in sorted((record_map(store, resource_type) or {}).items()):
            resources.append({
                "resource_type": resource_type,
                "stable_id": str(stable_id),
                "source_revision": max(1, int(record.get("revision", 1) or 1)),
                "record": _sanitize_record(record, resource_type),
            })
    if not resources:
        raise PresetPackageError("empty_package", "旧キャッシュに移送対象がありません。")
    return {
        "schema": PACKAGE_SCHEMA,
        "schema_version": 1,
        "package_id": f"legacy:{uuid.uuid4().hex}",
        "name": "旧プリセットキャッシュ",
        "root_collection_id": None,
        "exported_at": _now_iso(),
        "resources": resources,
    }
