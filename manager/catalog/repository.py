"""カタログの保存。権限判定とHTTP/Socket通知は呼び出し側が担う。"""
from copy import deepcopy
from datetime import datetime
from functools import wraps
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from extensions import db
from models import CatalogEntry, CatalogDraft, CatalogHistory, CatalogEffectRequest
from manager.cache_paths import load_json_cache
from .kinds import (get_kind, validate_entry_id, validate_payload, to_memory_entry,
                    validate_public_payload, replace_draft_id, CatalogValidationError)


class CatalogConflictError(ValueError):
    """公開版・下書き状態・正式IDが食い違っている。"""

    def __init__(self, message, *, field="conflict"):
        self.errors = {field: message}
        super().__init__(message)


def _transaction(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (IntegrityError, StaleDataError) as exc:
            db.session.rollback()
            raise CatalogConflictError("同時に更新されたか、IDが重複しています") from exc
        except Exception:
            db.session.rollback()
            raise
    return wrapped


def _entry(kind, entry_id):
    get_kind(kind)
    entry = CatalogEntry.query.filter_by(kind=kind, entry_id=entry_id).with_for_update().first()
    if entry is None:
        raise CatalogValidationError({"entry_id": "公開データがありません"})
    return entry


def _draft(draft_id):
    draft = CatalogDraft.query.filter_by(id=draft_id).with_for_update().first()
    if draft is None:
        raise CatalogValidationError({"draft_id": "下書きがありません"})
    return draft


def _validate(kind, payload, entry_id, *, allow_drafts=True):
    if not allow_drafts:
        return validate_public_payload(kind, payload, entry_id=entry_id)
    return validate_payload(kind, payload, entry_id=entry_id)


def _history(entry, action, actor_user_id=None, draft_id=None):
    db.session.add(CatalogHistory(kind=entry.kind, entry_id=entry.entry_id,
        revision=entry.revision, payload=deepcopy(entry.payload), deprecated=entry.deprecated,
        action=action, actor_user_id=actor_user_id, draft_id=draft_id))


def load_kind_into_memory(kind):
    import extensions
    memory = getattr(extensions, get_kind(kind)["memory_name"])
    entries = {row.entry_id: to_memory_entry(kind, row)
               for row in CatalogEntry.query.filter_by(kind=kind).order_by(CatalogEntry.entry_id).all()}
    memory.clear()
    memory.update(entries)
    if kind == "skill":
        from manager.battle.system_skills import ensure_system_skills_registered
        ensure_system_skills_registered()
    return memory


def stage_pulled_catalogs(catalogs):
    """取得済みの公開版をステージする。commit/rollbackはファイル反映側が行う。
    変わった行だけ版を進め、履歴は取り込み（import）として残す。"""
    from sqlalchemy import func

    for kind, records in catalogs.items():
        get_kind(kind)
        if kind == "skill":
            records = {key: row for key, row in records.items() if not key.startswith("SYS-")}
        existing = {row.entry_id: row for row in CatalogEntry.query.filter_by(kind=kind).all()}
        revisions = dict(db.session.query(CatalogHistory.entry_id, func.max(CatalogHistory.revision))
                         .filter_by(kind=kind).group_by(CatalogHistory.entry_id).all())
        for entry_id, entry in existing.items():
            if entry_id not in records:
                db.session.delete(entry)
        for entry_id, record in records.items():
            entry = existing.get(entry_id)
            payload = _cache_payload(kind, record)
            deprecated = record.get("deprecated", False)
            if entry is not None and entry.payload == payload and entry.deprecated == deprecated:
                continue
            revision = max(revisions.get(entry_id, 0), entry.revision if entry else 0) + 1
            if entry is None:
                entry = CatalogEntry(kind=kind, entry_id=entry_id)
                db.session.add(entry)
            entry.payload, entry.revision, entry.deprecated = payload, revision, deprecated
            entry.updated_by, entry.updated_at = None, datetime.utcnow()
            _history(entry, "import")
    db.session.flush()


def _cache_payload(kind, record):
    definition = get_kind(kind)
    if "from_cache" in definition:
        return definition["from_cache"](record)
    return {**deepcopy(definition["defaults"]),
            **{key: deepcopy(value) for key, value in record.items() if key in definition["fields"]}}


@_transaction
def seed_kind_if_empty(kind):
    definition = get_kind(kind)
    if CatalogEntry.query.filter_by(kind=kind).first() is not None:
        return 0
    cache = load_json_cache(definition["cache_file"])
    if not isinstance(cache, dict) or not cache:
        raise CatalogValidationError({"cache": "初回取り込み用のキャッシュがありません"})
    if kind == "skill":
        cache = {key: row for key, row in cache.items() if not key.startswith("SYS-")}
    for entry_id, old_payload in cache.items():
        validate_entry_id(kind, entry_id)
        payload = _cache_payload(kind, old_payload)
        payload = validate_payload(kind, payload, entry_id=entry_id, published_ids=set(cache))
        entry = CatalogEntry(kind=kind, entry_id=entry_id, payload=payload, revision=1,
                             deprecated=old_payload.get("deprecated") is True)
        db.session.add(entry)
        _history(entry, "import")
    db.session.commit()
    return len(cache)


@_transaction
def create_draft(kind, created_by, *, target_id=None, id_prefix=None):
    definition = get_kind(kind)
    if kind == "skill":
        id_prefix = target_id.split("-", 1)[0] if target_id else id_prefix
        _validate_prefix(kind, id_prefix)
    if target_id is not None:
        entry = _entry(kind, target_id)
        existing = CatalogDraft.query.filter_by(kind=kind, target_id=target_id).first()
        if existing is not None:
            return existing
        payload, base_revision = deepcopy(entry.payload), entry.revision
    else:
        target_id = "X-" + uuid.uuid4().hex[:8]
        payload, base_revision = {}, None
    draft = CatalogDraft(kind=kind, target_id=target_id, payload=payload,
                         base_revision=base_revision, created_by=created_by, id_prefix=id_prefix)
    db.session.add(draft)
    db.session.commit()
    return draft


@_transaction
def update_draft(draft_id, payload):
    draft = _draft(draft_id)
    if draft.status == "pending":
        raise CatalogConflictError("承認待ちの下書きは変更できません", field="status")
    # 不完全なフォームも保存できる。項目とリンクの検査は申請時に行う。
    if not isinstance(payload, dict):
        raise CatalogValidationError({"payload": "オブジェクトが必要です"})
    draft.payload = deepcopy(payload)
    draft.status, draft.reject_reason, draft.submitted_at = "draft", None, None
    draft.updated_at = datetime.utcnow()
    db.session.commit()
    return draft


@_transaction
def submit_draft(draft_id):
    draft = _draft(draft_id)
    if draft.status == "pending":
        raise CatalogConflictError("すでに承認待ちです", field="status")
    draft.payload = _validate(draft.kind, draft.payload, draft.target_id)
    draft.status = "pending"
    draft.updated_at = draft.submitted_at = datetime.utcnow()
    db.session.commit()
    return draft


@_transaction
def withdraw_draft(draft_id):
    db.session.delete(_draft(draft_id))
    db.session.commit()


@_transaction
def reject_draft(draft_id, reason):
    draft = _draft(draft_id)
    if draft.status != "pending":
        raise CatalogConflictError("承認待ちではありません", field="status")
    if not isinstance(reason, str) or not reason.strip():
        raise CatalogValidationError({"reason": "却下の理由が必要です"})
    draft.status, draft.reject_reason = "rejected", reason
    draft.updated_at = datetime.utcnow()
    db.session.commit()
    return draft


@_transaction
def approve_draft(draft_id, actor_user_id, *, entry_id=None):
    draft = _draft(draft_id)
    if draft.status != "pending":
        raise CatalogConflictError("承認待ちではありません", field="status")
    kind = draft.kind
    if draft.base_revision is None:
        validate_entry_id(kind, entry_id)
        if kind == "skill" and entry_id.split("-", 1)[0] != draft.id_prefix:
            raise CatalogValidationError({"entry_id": "下書きのカテゴリと正式IDの頭が違います"})
        if CatalogEntry.query.filter_by(kind=kind, entry_id=entry_id).first():
            raise CatalogConflictError("正式IDが重複しています", field="entry_id")
        candidate = replace_draft_id(draft.payload, draft.target_id, entry_id) if kind == "skill" else draft.payload
        payload = _validate(kind, candidate, entry_id, allow_drafts=False)
        entry = CatalogEntry(kind=kind, entry_id=entry_id, payload=payload,
                             revision=1, deprecated=False)
        db.session.add(entry)
        CatalogEffectRequest.query.filter_by(draft_id=draft.id).update({
            CatalogEffectRequest.draft_target_id: entry_id,
        })
        for other in CatalogDraft.query.with_for_update().all():
            if other.id == draft.id:
                continue
            replaced = replace_draft_id(other.payload, draft.target_id, entry_id)
            if replaced != other.payload:
                other.payload = replaced
                other.updated_at = datetime.utcnow()
    else:
        entry = _entry(kind, draft.target_id)
        if entry.revision != draft.base_revision:
            raise CatalogConflictError("下書きの元の版と公開中の版が違います", field="base_revision")
        entry.payload = _validate(kind, draft.payload, entry.entry_id, allow_drafts=False)
        entry.revision += 1
    entry.updated_by, entry.updated_at = actor_user_id, datetime.utcnow()
    _history(entry, "publish", actor_user_id, draft.id)
    db.session.delete(draft)
    db.session.commit()
    load_kind_into_memory(kind)
    return entry


@_transaction
def set_deprecated(kind, entry_id, deprecated, actor_user_id):
    if type(deprecated) is not bool:
        raise CatalogValidationError({"deprecated": "真偽値が必要です"})
    entry = _entry(kind, entry_id)
    if entry.deprecated == deprecated:
        return entry
    entry.deprecated = deprecated
    entry.revision += 1
    entry.updated_by, entry.updated_at = actor_user_id, datetime.utcnow()
    _history(entry, "deprecate" if deprecated else "undeprecate", actor_user_id)
    db.session.commit()
    load_kind_into_memory(kind)
    return entry


@_transaction
def restore_revision(kind, entry_id, revision, actor_user_id):
    entry = _entry(kind, entry_id)
    history = CatalogHistory.query.filter_by(kind=kind, entry_id=entry_id, revision=revision).first()
    if history is None:
        raise CatalogValidationError({"revision": "指定の版がありません"})
    entry.payload = _validate(kind, history.payload, entry_id, allow_drafts=False)
    entry.deprecated = history.deprecated
    entry.revision += 1
    entry.updated_by, entry.updated_at = actor_user_id, datetime.utcnow()
    _history(entry, "restore", actor_user_id)
    db.session.commit()
    load_kind_into_memory(kind)
    return entry



def _validate_prefix(kind, prefix):
    if not isinstance(prefix, str) or prefix not in get_kind(kind).get("id_prefixes", ()):
        raise CatalogValidationError({"id_prefix": "カテゴリの接頭辞を指定してください"})


def next_entry_id(kind, *, prefix=None):
    """廃止分も含めた公開IDから採番候補を作る（予約はしない）。"""
    import re
    definition = get_kind(kind)
    if kind == "skill":
        _validate_prefix(kind, prefix)
        id_prefix = prefix + "-"
    else:
        id_prefix = definition["id_prefix"]
    ids = [row.entry_id for row in CatalogEntry.query.filter_by(kind=kind).all()]
    numbers = [int(value[len(id_prefix):]) for value in ids
               if value.startswith(id_prefix) and re.fullmatch(definition["id_pattern"], value)]
    return id_prefix + f"{max(numbers, default=-1) + 1:02d}"
