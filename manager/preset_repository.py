"""DB-backed persistence for globally reusable battle preset assets.

The public socket layer still exchanges the version 3 store shape.  This
repository translates that compatibility shape to resource-level database
rows so normal edits no longer rewrite a Git-managed JSON snapshot.
"""

from __future__ import annotations

import copy
import json
import threading
from datetime import datetime

from flask import has_app_context

from extensions import db
from models import PresetResource, PresetResourceAcl, User


RESOURCE_MAP_KEYS = {
    "character": "character_presets",
    "enemy_formation": "enemy_formations",
    "ally_formation": "ally_formations",
    "stage": "stage_presets",
    "collection": "catalog_collections",
}
MAP_KEY_RESOURCE_TYPES = {value: key for key, value in RESOURCE_MAP_KEYS.items()}

_WRITE_LOCK = threading.RLock()
_TRANSIENT_KEYS = {
    "access_control",
    "capabilities",
    "catalog_meta",
    "created_at",
    "id",
    "owner_display_name",
    "revision",
    "shared_via",
    "updated_at",
    "visibility",
}


def _require_app_context():
    if not has_app_context():
        raise RuntimeError("preset DB access requires a Flask application context")


def _datetime_to_ms(value):
    if not isinstance(value, datetime):
        return 0
    return int(value.timestamp() * 1000)


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _record_payload(record):
    payload = copy.deepcopy(record if isinstance(record, dict) else {})
    for key in _TRANSIENT_KEYS:
        payload.pop(key, None)
    return payload


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _business_fingerprint(record):
    rec = record if isinstance(record, dict) else {}
    acl = rec.get("access_control") if isinstance(rec.get("access_control"), dict) else {}
    meta = rec.get("catalog_meta") if isinstance(rec.get("catalog_meta"), dict) else {}
    return _canonical({
        "payload": _record_payload(rec),
        "name": str(rec.get("name") or ""),
        "owner_user_id": str(acl.get("owner_user_id") or ""),
        "editor_user_ids": sorted(str(value) for value in acl.get("editor_user_ids", []) if value),
        "viewer_mode": str(acl.get("viewer_mode") or rec.get("visibility") or "restricted"),
        "viewer_user_ids": sorted(str(value) for value in acl.get("viewer_user_ids", []) if value),
        "collection_id": str(meta.get("collection_id") or ""),
        "section_id": str(meta.get("section_id") or ""),
        "labels": list(meta.get("labels") or []),
        "sort_order": _safe_int(meta.get("sort_order"), 2147483647),
        "archived": bool(meta.get("archived", False)),
    })


def _row_to_record(row, acl_rows):
    record = copy.deepcopy(row.payload if isinstance(row.payload, dict) else {})
    editors = []
    viewers = []
    for acl in acl_rows:
        if acl.role == "editor":
            editors.append(str(acl.user_id))
        elif acl.role == "viewer":
            viewers.append(str(acl.user_id))
    record.update({
        "id": str(row.stable_id),
        "name": str(row.name or row.stable_id),
        "visibility": str(row.viewer_mode or "restricted"),
        "access_control": {
            "owner_user_id": str(row.owner_user_id) if row.owner_user_id else None,
            "editor_user_ids": sorted(set(editors)),
            "viewer_mode": str(row.viewer_mode or "restricted"),
            "viewer_user_ids": sorted(set(viewers)),
        },
        "revision": max(1, _safe_int(row.revision, 1)),
        "created_at": _datetime_to_ms(row.created_at),
        "updated_at": _datetime_to_ms(row.updated_at),
    })
    if row.resource_type != "collection":
        record["catalog_meta"] = {
            "collection_id": str(row.collection_id) if row.collection_id else None,
            "section_id": str(row.section_id) if row.section_id else None,
            "sort_order": _safe_int(row.sort_order, 2147483647),
            "labels": list(row.labels) if isinstance(row.labels, list) else [],
            "archived": bool(row.archived),
            "last_used_at": max(0, _safe_int(row.last_used_at, 0)),
        }
    return record


def load_store_from_db():
    _require_app_context()
    rows = PresetResource.query.order_by(PresetResource.id.asc()).all()
    acl_by_resource = {}
    if rows:
        ids = [row.id for row in rows]
        for acl in PresetResourceAcl.query.filter(PresetResourceAcl.resource_id.in_(ids)).all():
            acl_by_resource.setdefault(acl.resource_id, []).append(acl)
    store = {
        "version": 3,
        "character_presets": {},
        "enemy_formations": {},
        "ally_formations": {},
        "stage_presets": {},
        "catalog_collections": {},
        "updated_at": 0,
    }
    latest = 0
    for row in rows:
        map_key = RESOURCE_MAP_KEYS.get(row.resource_type)
        if not map_key:
            continue
        record = _row_to_record(row, acl_by_resource.get(row.id, []))
        store[map_key][record["id"]] = record
        latest = max(latest, record.get("updated_at", 0))
    store["updated_at"] = latest
    return store


def _existing_record(row, acl_by_resource):
    return _row_to_record(row, acl_by_resource.get(row.id, []))


def _validate_user_references(records):
    requested = set()
    for record in records:
        acl = record.get("access_control") if isinstance(record.get("access_control"), dict) else {}
        requested.update(
            str(value).strip()
            for value in [
                acl.get("owner_user_id"),
                *(acl.get("editor_user_ids") or []),
                *(acl.get("viewer_user_ids") or []),
            ]
            if str(value or "").strip()
        )
    if not requested:
        return
    found = {str(row.id) for row in User.query.filter(User.id.in_(requested)).all()}
    missing = sorted(requested - found)
    if missing:
        raise ValueError(f"存在しないユーザーIDが権限に含まれています: {', '.join(missing)}")


def _replace_acl(row, record):
    for existing_acl in PresetResourceAcl.query.filter_by(resource_id=row.id).all():
        db.session.delete(existing_acl)
    db.session.flush()
    acl = record.get("access_control") if isinstance(record.get("access_control"), dict) else {}
    owner = str(acl.get("owner_user_id") or "").strip()
    editor_ids = []
    for value in acl.get("editor_user_ids") or []:
        user_id = str(value or "").strip()
        if user_id and user_id != owner and user_id not in editor_ids:
            editor_ids.append(user_id)
    viewer_ids = []
    for value in acl.get("viewer_user_ids") or []:
        user_id = str(value or "").strip()
        if user_id and user_id != owner and user_id not in editor_ids and user_id not in viewer_ids:
            viewer_ids.append(user_id)
    for user_id in editor_ids:
        db.session.add(PresetResourceAcl(resource_id=row.id, user_id=user_id, role="editor"))
    for user_id in viewer_ids:
        db.session.add(PresetResourceAcl(resource_id=row.id, user_id=user_id, role="viewer"))


def _apply_record(row, resource_type, stable_id, record, existing_record=None):
    rec = record if isinstance(record, dict) else {}
    acl = rec.get("access_control") if isinstance(rec.get("access_control"), dict) else {}
    meta = rec.get("catalog_meta") if isinstance(rec.get("catalog_meta"), dict) else {}
    now = datetime.utcnow()
    changed = existing_record is None or _business_fingerprint(existing_record) != _business_fingerprint(rec)
    incoming_last_used = max(0, _safe_int(meta.get("last_used_at"), 0))
    if existing_record is not None and not changed:
        if resource_type != "collection" and _safe_int(row.last_used_at, 0) != incoming_last_used:
            row.last_used_at = incoming_last_used
        return
    if existing_record is None:
        row.resource_type = resource_type
        row.stable_id = stable_id
        row.created_at = now
        row.revision = max(1, _safe_int(rec.get("revision"), 1))
    elif changed:
        row.revision = max(1, _safe_int(row.revision, 1)) + 1
    row.name = str(rec.get("name") or stable_id).strip() or stable_id
    row.owner_user_id = str(acl.get("owner_user_id") or "").strip() or None
    mode = str(acl.get("viewer_mode") or rec.get("visibility") or "restricted").strip().lower()
    row.viewer_mode = mode if mode in {"public", "gm", "restricted"} else "restricted"
    row.payload = _record_payload(rec)
    if resource_type == "collection":
        row.collection_id = None
        row.section_id = None
        row.labels = []
        row.sort_order = _safe_int(rec.get("sort_order"), 2147483647)
        row.archived = bool(rec.get("archived", False))
        row.last_used_at = 0
    else:
        row.collection_id = str(meta.get("collection_id") or "").strip() or None
        row.section_id = str(meta.get("section_id") or "").strip() or None
        row.labels = [str(value).strip() for value in meta.get("labels", []) if str(value).strip()]
        row.sort_order = _safe_int(meta.get("sort_order"), 2147483647)
        row.archived = bool(meta.get("archived", False))
        row.last_used_at = incoming_last_used
    if changed:
        row.updated_at = now
    _replace_acl(row, rec)


def persist_store_to_db(store, *, replace=False, commit=True):
    _require_app_context()
    src = store if isinstance(store, dict) else {}
    incoming = {}
    all_records = []
    for resource_type, map_key in RESOURCE_MAP_KEYS.items():
        rows = src.get(map_key) if isinstance(src.get(map_key), dict) else {}
        for stable_id, record in rows.items():
            if not isinstance(record, dict):
                continue
            key = (resource_type, str(record.get("id") or stable_id).strip())
            if not key[1]:
                continue
            incoming[key] = record
            all_records.append(record)
    _validate_user_references(all_records)

    existing_rows = PresetResource.query.all()
    existing = {(row.resource_type, row.stable_id): row for row in existing_rows}
    acl_by_resource = {}
    if existing_rows:
        for acl in PresetResourceAcl.query.filter(
            PresetResourceAcl.resource_id.in_([row.id for row in existing_rows])
        ).all():
            acl_by_resource.setdefault(acl.resource_id, []).append(acl)

    if replace:
        for key, row in existing.items():
            if key not in incoming:
                for acl in PresetResourceAcl.query.filter_by(resource_id=row.id).all():
                    db.session.delete(acl)
                db.session.delete(row)

    for (resource_type, stable_id), record in incoming.items():
        row = existing.get((resource_type, stable_id))
        old_record = _existing_record(row, acl_by_resource) if row else None
        if row is None:
            row = PresetResource(resource_type=resource_type, stable_id=stable_id, name=stable_id)
            db.session.add(row)
            db.session.flush()
        _apply_record(row, resource_type, stable_id, record, old_record)

    try:
        if commit:
            db.session.commit()
        else:
            db.session.flush()
    except Exception:
        db.session.rollback()
        raise


def mutate_store_in_db(mutator, normalize_store, *, commit=True):
    _require_app_context()
    with _WRITE_LOCK:
        working = load_store_from_db()
        mutator(working)
        normalized = normalize_store(working)
        persist_store_to_db(normalized, replace=True, commit=commit)
        return load_store_from_db()


def replace_store_in_db(store, normalize_store, *, commit=True):
    _require_app_context()
    with _WRITE_LOCK:
        normalized = normalize_store(store)
        persist_store_to_db(normalized, replace=True, commit=commit)
        return load_store_from_db()
