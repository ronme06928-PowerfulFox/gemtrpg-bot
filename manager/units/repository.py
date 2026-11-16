"""Directly edited, revisioned game-wide unit resources."""
from datetime import datetime, timezone

from sqlalchemy import text

from extensions import db
from models import CatalogEntry, CatalogHistory
from manager.catalog.kinds import CatalogValidationError
from manager.catalog.repository import CatalogConflictError, _transaction, record_history
from manager.units.validation import IDS, inspect_payload, links, valid_id


def entry_json(row):
    return {"kind": row.kind, "entry_id": row.entry_id, "payload": row.payload,
            "visibility": row.visibility, "deprecated": row.deprecated, "revision": row.revision}


def entries(*, include_staff=True, include_deprecated=True):
    query = CatalogEntry.query.filter(CatalogEntry.kind.in_(IDS))
    if not include_staff:
        query = query.filter_by(visibility="public")
    if not include_deprecated:
        query = query.filter_by(deprecated=False)
    return {(row.kind, row.entry_id): entry_json(row)
            for row in query.order_by(CatalogEntry.kind, CatalogEntry.entry_id)}


def get(kind, entry_id):
    if kind not in IDS:
        raise CatalogValidationError({"kind": "未対応の種類です"})
    return CatalogEntry.query.filter_by(kind=kind, entry_id=entry_id).populate_existing().first()


def history(kind, entry_id):
    return CatalogHistory.query.filter_by(kind=kind, entry_id=entry_id).order_by(
        CatalogHistory.revision.desc()).all()


def next_id(kind, reserved=()):
    prefix, width = IDS[kind]
    used = [entry_id for (entry_id,) in db.session.query(CatalogHistory.entry_id).filter_by(kind=kind).distinct()]
    used.extend(reserved)
    numbers = [int(key.split("-")[1]) for key in used if valid_id(kind, key)]
    return f"{prefix}-{max(numbers, default=0) + 1:0{width}d}"


def check(kind, payload, visibility="public", *, entry_id=None, pattern_additions=None):
    if entry_id is not None and not isinstance(entry_id, str):
        return {"entry_id": "IDが不正です"}, {}
    current = entries()
    try:
        current.update(_formation_pattern_updates(kind, payload, pattern_additions, current))
    except CatalogValidationError as exc:
        return exc.errors, {}
    except CatalogConflictError as exc:
        return exc.errors, {}
    previous = current.get((kind, entry_id), {}).get("payload")
    errors, warnings, normalized = inspect_payload(kind, payload, visibility, current, previous=previous)
    if not errors and entry_id:
        errors = dependent_errors(kind, entry_id, normalized, current)
    return errors, warnings


def references(kind, entry_id, *, resources=None):
    resources = entries() if resources is None else resources
    return [{"kind": source_kind, "entry_id": source_id, "path": path,
             "display_name": source["payload"].get("name", source_id)}
            for (source_kind, source_id), source in resources.items()
            for target_kind, target_id, path in links(source_kind, source["payload"])
            if (target_kind, target_id) == (kind, entry_id)]


def lock_writes():
    # Reference checks and ID allocation cover multiple rows, including currently absent rows.
    if db.engine.dialect.name == "postgresql":
        db.session.execute(text("SELECT pg_advisory_xact_lock(61001)"))
    elif db.engine.dialect.name == "sqlite":
        db.session.execute(text("BEGIN IMMEDIATE"))


def expect_revision(row, base_revision):
    if row is None or type(base_revision) is not int or row.revision != base_revision:
        raise CatalogConflictError("版が変わりました。読み直してください", field="base_revision")


def write(kind, entry_id, payload, visibility, deprecated, action, actor_user_id=None, *, row=None):
    if row is None:
        latest = history(kind, entry_id)
        if latest:
            raise CatalogConflictError("このIDは削除済みです", field="entry_id")
        row = CatalogEntry(kind=kind, entry_id=entry_id, revision=0)
        db.session.add(row)
    row.payload, row.visibility, row.deprecated = payload, visibility, deprecated
    row.revision += 1
    row.updated_by, row.updated_at = actor_user_id, datetime.now(timezone.utc).replace(tzinfo=None)
    record_history(row, action, actor_user_id)
    return row


def _formation_pattern_updates(kind, payload, additions, resources):
    if additions is None:
        return {}
    if (kind != "formation" or not isinstance(payload, dict) or payload.get("type") != "enemy"
            or not isinstance(additions, dict) or not isinstance(payload.get("members"), list)):
        raise CatalogValidationError({"patterns": "パターンの複製には敵編成が必要です"})
    updates = {}
    for unit_id, addition in additions.items():
        key = ("unit", unit_id)
        original = resources.get(key)
        if original is None or not original["payload"].get("allow_enemy", True):
            raise CatalogValidationError({unit_id: "複製先の敵ユニットが見つかりません"})
        base = addition.get("base_revision") if isinstance(addition, dict) else None
        if type(base) is not int or base != original["revision"]:
            raise CatalogConflictError(f"{unit_id} の版が変わりました。読み直してください",
                                       field="base_revision")
        patterns = addition.get("patterns")
        selected = {member.get("pattern_id") for member in payload["members"]
                    if isinstance(member, dict) and member.get("unit_id") == unit_id
                    and isinstance(member.get("pattern_id"), str)}
        if not isinstance(patterns, list) or not patterns or any(
            not isinstance(pattern, dict) or not isinstance(pattern.get("id"), str)
            or pattern["id"] not in selected for pattern in patterns
        ):
            raise CatalogValidationError({unit_id: "複製したパターンを編成の枠で指定してください"})
        existing = original["payload"].get("patterns", [])
        draft = {**original["payload"], "patterns": [*existing, *patterns]}
        errors, _, normalized = inspect_payload("unit", draft, original["visibility"], resources,
                                                previous=original["payload"])
        if errors:
            raise CatalogValidationError({f"{unit_id}.{field}": message for field, message in errors.items()})
        updates[key] = {**original, "payload": normalized}
    return updates


def _validate(kind, key, payload, visibility, *, resources=None):
    resources = entries() if resources is None else resources
    previous = resources.get((kind, key), {}).get("payload")
    errors, warnings, normalized = inspect_payload(kind, payload, visibility, resources, previous=previous)
    if not errors and key:
        errors = dependent_errors(kind, key, normalized, resources)
    if errors:
        raise CatalogValidationError(errors)
    return normalized, warnings


def dependent_errors(kind, entry_id, payload, resources):
    """Keep saved formations and stages resolvable when their target changes."""
    if kind not in ("unit", "formation"):
        return {}
    errors = {}
    for ref in references(kind, entry_id, resources=resources):
        key = (ref["kind"], ref["entry_id"])
        source = resources[key]["payload"]
        if kind == "unit" and ref["kind"] == "formation":
            allowed = payload.get("allow_" + source["type"], True)
            patterns = {item["id"] for item in payload.get("patterns", [])}
            members = [member for member in source["members"] if member["unit_id"] == entry_id]
            valid = allowed and all(not member.get("pattern_id") or member["pattern_id"] in patterns
                                    for member in members)
        elif kind == "formation" and ref["kind"] == "stage":
            valid = payload.get("type") == ref["path"].split("_")[0]
        else:
            continue
        if not valid:
            errors[f"{ref['entry_id']}.{ref['path']}"] = "使用中の陣営またはパターンを変更できません"
    return errors


@_transaction
def save(kind, entry_id, payload, *, visibility="public", base_revision=None, actor_user_id=None,
         pattern_additions=None):
    lock_writes()
    row = get(kind, entry_id) if entry_id is not None else None
    if entry_id is not None:
        expect_revision(row, base_revision)
    elif base_revision is not None:
        raise CatalogValidationError({"base_revision": "新規作成では指定できません"})
    resources = entries() if pattern_additions is not None else None
    updates = _formation_pattern_updates(kind, payload, pattern_additions, resources)
    if resources is not None:
        resources.update(updates)
    payload, warnings = _validate(kind, entry_id, payload, visibility, resources=resources)
    for (_, unit_id), unit in updates.items():
        write("unit", unit_id, unit["payload"], unit["visibility"], unit["deprecated"],
              "publish", actor_user_id, row=get("unit", unit_id))
    key = entry_id or next_id(kind)
    row = write(kind, key, payload, visibility, row.deprecated if row else False,
                "publish", actor_user_id, row=row)
    db.session.commit()
    return row, warnings


@_transaction
def set_deprecated(kind, entry_id, deprecated, *, base_revision, actor_user_id=None):
    lock_writes()
    row = get(kind, entry_id)
    expect_revision(row, base_revision)
    if type(deprecated) is not bool:
        raise CatalogValidationError({"deprecated": "真偽値が必要です"})
    if row.deprecated != deprecated:
        write(kind, entry_id, row.payload, row.visibility, deprecated,
              "deprecate" if deprecated else "undeprecate", actor_user_id, row=row)
    db.session.commit()
    return row


@_transaction
def restore(kind, entry_id, revision, *, base_revision, actor_user_id=None):
    lock_writes()
    row = get(kind, entry_id)
    expect_revision(row, base_revision)
    if type(revision) is not int or revision < 1:
        raise CatalogValidationError({"revision": "1以上の整数が必要です"})
    snapshot = CatalogHistory.query.filter_by(kind=kind, entry_id=entry_id, revision=revision).first()
    if snapshot is None:
        raise CatalogValidationError({"revision": "指定の版がありません"})
    payload, warnings = _validate(kind, entry_id, snapshot.payload, snapshot.visibility)
    write(kind, entry_id, payload, snapshot.visibility, snapshot.deprecated,
          "restore", actor_user_id, row=row)
    db.session.commit()
    return row, warnings


@_transaction
def delete(kind, entry_id, *, base_revision):
    lock_writes()
    row = get(kind, entry_id)
    expect_revision(row, base_revision)
    in_use = references(kind, entry_id)
    if in_use:
        raise CatalogConflictError("参照されている資源は削除できません", field="references")
    db.session.delete(row)
    db.session.commit()
