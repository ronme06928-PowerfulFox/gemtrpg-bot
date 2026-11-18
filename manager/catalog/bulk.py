"""分類と印だけを、通常の下書き・申請・承認を通してまとめて変更する。"""
from copy import deepcopy

from sqlalchemy import update

from extensions import db, socketio
from models import CatalogDraft, CatalogEntry
from . import repository
from .kinds import CatalogValidationError, MARK_KINDS, MARK_LABELS, get_kind


def _changes(kind, changes):
    definition = get_kind(kind)
    if not isinstance(changes, dict) or not changes or changes.keys() - {"category", "marks_add", "marks_remove"}:
        raise CatalogValidationError({"changes": "分類と印の変更を指定してください"})
    if "category" in changes:
        value = changes["category"]
        choices = definition.get("categories", ())
        if kind not in ("buff", "glossary") or not isinstance(value, str) or (
                value not in choices and not (kind == "buff" and value == "")):
            raise CatalogValidationError({"category": "未定義の分類です"})
    for field in ("marks_add", "marks_remove"):
        if field not in changes:
            continue
        values = changes[field]
        if (kind not in MARK_KINDS or not isinstance(values, list)
                or any(not isinstance(value, str) or value not in MARK_LABELS for value in values)
                or len(values) != len(set(values))):
            raise CatalogValidationError({field: "印の値を確認してください"})
    if set(changes.get("marks_add", [])) & set(changes.get("marks_remove", [])):
        raise CatalogValidationError({"marks": "同じ印の追加と削除は同時に指定できません"})
    return changes


def _apply_one(kind, selected, changes, actor):
    key, revision = selected["entry_id"], selected["base_revision"]
    row = CatalogEntry.query.filter_by(kind=kind, entry_id=key).with_for_update().first()
    if row is None:
        raise repository.CatalogConflictError("公開版がありません")
    if row.revision != revision:
        raise repository.CatalogConflictError("版が変わりました。読み直してください")
    # SQLiteでも書き込みを予約し、選択時の版に対する変更に限定する。
    reserved = db.session.execute(update(CatalogEntry).where(
        CatalogEntry.kind == kind, CatalogEntry.entry_id == key, CatalogEntry.revision == revision
    ).values(updated_at=CatalogEntry.updated_at))
    if reserved.rowcount != 1:
        raise repository.CatalogConflictError("ほかの人が更新しました")
    draft = CatalogDraft.query.filter_by(kind=kind, target_id=key).first()
    if draft is not None:
        raise repository.CatalogConflictError("承認待ちの下書きがあります" if draft.status == "pending"
                                             else "既存の下書きがあります")
    payload = deepcopy(row.payload)
    if "category" in changes:
        payload["category"] = changes["category"]
    if "marks_add" in changes or "marks_remove" in changes:
        marks = payload.get("marks", [])
        if not isinstance(marks, list):
            raise CatalogValidationError({"marks": "公開版の印が配列ではありません"})
        payload["marks"] = [mark for mark in marks if mark not in changes.get("marks_remove", [])]
        payload["marks"].extend(mark for mark in changes.get("marks_add", []) if mark not in payload["marks"])
    if payload == row.payload:
        raise repository.CatalogConflictError("変更はありません")
    draft = repository.create_draft(kind, actor.id, target_id=key)
    repository.update_draft(draft.id, payload)
    repository.submit_draft(draft.id)
    if actor.is_app_admin:
        published = repository.approve_draft(draft.id, actor.id)
        return {"entry_id": key, "status": "published", "revision": published.revision}
    return {"entry_id": key, "status": "pending"}


def apply_bulk(kind, body, actor):
    changes = _changes(kind, body.get("changes"))
    entries = body.get("entries")
    if (not isinstance(entries, list) or not entries
            or any(not isinstance(row, dict) or not isinstance(row.get("entry_id"), str)
                   or type(row.get("base_revision")) is not int or row["base_revision"] < 1 for row in entries)
            or len({row["entry_id"] for row in entries}) != len(entries)):
        raise CatalogValidationError({"entries": "重複のないIDと選択時の版が必要です"})
    results = []
    for selected in entries:
        try:
            with db.session.begin_nested(), repository.staged_writes():
                result = _apply_one(kind, selected, changes, actor)
            db.session.commit()
        except (CatalogValidationError, repository.CatalogConflictError) as error:
            db.session.rollback()
            reason = " / ".join(str(value) for value in error.errors.values())
            results.append({"entry_id": selected["entry_id"], "status": "skipped", "reason": reason})
            continue
        results.append(result)
    # 読み直しは全員の画面で起きるので、何件変えても1回だけ知らせる。
    if any(row["status"] == "published" for row in results):
        repository.load_kind_into_memory(kind)
        socketio.emit("catalog_updated", {"kind": kind})
    skipped = sum(row["status"] == "skipped" for row in results)
    return {"results": results, "changed": len(results) - skipped, "skipped": skipped}
