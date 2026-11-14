"""Directly edited, revisioned game-wide unit resources."""
from datetime import datetime, timezone

from sqlalchemy import text

from extensions import active_room_states, db
from models import CatalogEntry, CatalogHistory, Room
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


def check(kind, payload, visibility="public", *, entry_id=None):
    if entry_id is not None and not isinstance(entry_id, str):
        return {"entry_id": "IDが不正です"}, {}
    current = entries()
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


def room_references(kind, entry_id):
    fields = {
        "formation": ("enemy_formation_id", "ally_formation_id"),
        "stage": ("selected_stage_id",),
    }
    result = []
    for room in Room.query.all():
        state = active_room_states.get(room.name, room.data)
        draft = state.get("battle_only") if isinstance(state, dict) else None
        if not isinstance(draft, dict):
            continue
        paths = [field for field in fields.get(kind, ()) if draft.get(field) == entry_id]
        if kind == "unit":
            paths += [f"{field}[{index}].preset_id"
                      for field in ("ally_entries", "enemy_entries")
                      for index, item in enumerate(draft.get(field) or [])
                      if isinstance(item, dict) and item.get("preset_id") == entry_id]
        result.extend({"kind": "room", "entry_id": room.name, "path": f"battle_only.{path}"}
                      for path in paths)
    return result


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


def _validate(kind, key, payload, visibility):
    resources = entries()
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
def save(kind, entry_id, payload, *, visibility="public", base_revision=None, actor_user_id=None):
    lock_writes()
    row = get(kind, entry_id) if entry_id is not None else None
    if entry_id is not None:
        expect_revision(row, base_revision)
    elif base_revision is not None:
        raise CatalogValidationError({"base_revision": "新規作成では指定できません"})
    payload, warnings = _validate(kind, entry_id, payload, visibility)
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
    in_use = references(kind, entry_id) or room_references(kind, entry_id)
    if in_use:
        raise CatalogConflictError("参照されている資源は削除できません", field="references")
    db.session.delete(row)
    db.session.commit()
