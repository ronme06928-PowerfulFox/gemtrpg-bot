"""カタログ管理HTTP API。認証・権限・入出力のみを担当する。"""
from functools import wraps

from flask import Blueprint, abort, g, jsonify, request

from extensions import db, socketio
from models import User, CatalogEntry, CatalogDraft, CatalogHistory
from manager.catalog import repository
from manager.catalog.kinds import KINDS, CatalogValidationError
from manager.catalog.references import find_references
from manager.utils import session_required


catalog_bp = Blueprint("catalog", __name__)


def _endpoint(permission="read"):
    def decorate(function):
        @wraps(function)
        @session_required
        def guarded(*args, **kwargs):
            user = g.authenticated_user
            author = user.is_app_admin or user.is_catalog_author
            if permission == "admin" and not user.is_app_admin:
                return jsonify(error="アプリ管理者権限が必要です"), 403
            if permission in ("author", "owner") and not author:
                return jsonify(error="制作者権限が必要です"), 403
            kind = kwargs.get("kind")
            if kind is not None and kind not in KINDS:
                abort(404)
            if "draft_id" in kwargs:
                draft = db.session.get(CatalogDraft, kwargs["draft_id"])
                if draft is None or draft.kind not in KINDS:
                    abort(404)
                if permission == "owner" and not user.is_app_admin and draft.created_by != user.id:
                    return jsonify(error="作成者かアプリ管理者だけが操作できます"), 403
            if "entry_id" in kwargs:
                if CatalogEntry.query.filter_by(kind=kind, entry_id=kwargs["entry_id"]).first() is None:
                    abort(404)
            try:
                return function(*args, **kwargs)
            except (CatalogValidationError, repository.CatalogConflictError) as exc:
                return jsonify(error=str(exc), errors=exc.errors), (409 if isinstance(exc, repository.CatalogConflictError) else 422)
        return guarded
    return decorate


def _body():
    if not request.get_data():
        return {}
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise CatalogValidationError({"body": "JSONオブジェクトが必要です"})
    return data


def _name(user_id):
    user = db.session.get(User, user_id) if user_id else None
    return user.name if user else None


def _time(value):
    return value.isoformat() + "Z" if value else None


def _entry_json(row):
    return {"id": row.id, "kind": row.kind, "entry_id": row.entry_id,
            "payload": row.payload, "revision": row.revision, "deprecated": row.deprecated,
            "updated_by": row.updated_by, "updated_by_name": _name(row.updated_by),
            "updated_at": _time(row.updated_at)}


def _draft_json(row):
    return {"id": row.id, "kind": row.kind, "target_id": row.target_id,
            "payload": row.payload, "status": row.status, "base_revision": row.base_revision,
            "created_by": row.created_by, "created_by_name": _name(row.created_by),
            "reject_reason": row.reject_reason, "created_at": _time(row.created_at),
            "updated_at": _time(row.updated_at), "submitted_at": _time(row.submitted_at)}


def _published(row, *, notify=True):
    result = _entry_json(row)
    if notify:
        socketio.emit("catalog_updated", {"kind": row.kind, "entry_id": row.entry_id, "revision": row.revision})
    return jsonify(result)


@catalog_bp.get("/api/catalog/<kind>")
@_endpoint()
def list_catalog(kind):
    result = {"kind": kind, "entries": [_entry_json(row) for row in
              CatalogEntry.query.filter_by(kind=kind).order_by(CatalogEntry.entry_id).all()]}
    if g.authenticated_user.is_app_admin or g.authenticated_user.is_catalog_author:
        result["drafts"] = [_draft_json(row) for row in
                            CatalogDraft.query.filter_by(kind=kind).order_by(CatalogDraft.id).all()]
    return jsonify(result)


@catalog_bp.get("/api/catalog/<kind>/<entry_id>/history")
@_endpoint()
def history(kind, entry_id):
    rows = CatalogHistory.query.filter_by(kind=kind, entry_id=entry_id).order_by(CatalogHistory.revision.desc()).all()
    return jsonify(history=[{"id": row.id, "kind": row.kind, "entry_id": row.entry_id,
        "revision": row.revision, "payload": row.payload, "deprecated": row.deprecated,
        "action": row.action, "actor_user_id": row.actor_user_id,
        "actor_user_name": _name(row.actor_user_id), "draft_id": row.draft_id,
        "created_at": _time(row.created_at)} for row in rows])


@catalog_bp.get("/api/catalog/<kind>/<entry_id>/references")
@_endpoint()
def references(kind, entry_id):
    return jsonify(references=find_references(kind, entry_id))


@catalog_bp.get("/api/catalog/<kind>/next_id")
@_endpoint("admin")
def next_id(kind):
    return jsonify(entry_id=repository.next_entry_id(kind))


@catalog_bp.post("/api/catalog/<kind>/drafts")
@_endpoint("author")
def create_draft(kind):
    data = _body()
    target_id = data.get("target_id")
    if "target_id" in data and (not isinstance(target_id, str) or not target_id):
        raise CatalogValidationError({"target_id": "公開IDの文字列が必要です"})
    if target_id and CatalogEntry.query.filter_by(kind=kind, entry_id=target_id).first() is None:
        abort(404)
    return jsonify(_draft_json(repository.create_draft(kind, g.authenticated_user.id, target_id=target_id)))


@catalog_bp.put("/api/catalog/drafts/<int:draft_id>")
@_endpoint("owner")
def update_draft(draft_id):
    data = _body()
    return jsonify(_draft_json(repository.update_draft(draft_id, data.get("payload"))))


@catalog_bp.post("/api/catalog/drafts/<int:draft_id>/submit")
@_endpoint("owner")
def submit_draft(draft_id):
    return jsonify(_draft_json(repository.submit_draft(draft_id)))


@catalog_bp.delete("/api/catalog/drafts/<int:draft_id>")
@_endpoint("owner")
def withdraw_draft(draft_id):
    repository.withdraw_draft(draft_id)
    return jsonify(id=draft_id, withdrawn=True)


@catalog_bp.post("/api/catalog/drafts/<int:draft_id>/approve")
@_endpoint("admin")
def approve_draft(draft_id):
    return _published(repository.approve_draft(draft_id, g.authenticated_user.id, entry_id=_body().get("entry_id")))


@catalog_bp.post("/api/catalog/drafts/<int:draft_id>/reject")
@_endpoint("admin")
def reject_draft(draft_id):
    return jsonify(_draft_json(repository.reject_draft(draft_id, _body().get("reason"))))


@catalog_bp.post("/api/catalog/<kind>/<entry_id>/deprecate")
@_endpoint("admin")
def deprecate(kind, entry_id):
    before = CatalogEntry.query.filter_by(kind=kind, entry_id=entry_id).one().revision
    row = repository.set_deprecated(kind, entry_id, _body().get("deprecated"), g.authenticated_user.id)
    return _published(row, notify=row.revision != before)


@catalog_bp.post("/api/catalog/<kind>/<entry_id>/restore")
@_endpoint("admin")
def restore(kind, entry_id):
    revision = _body().get("revision")
    if type(revision) is not int or revision < 1:
        raise CatalogValidationError({"revision": "1以上の整数が必要です"})
    return _published(repository.restore_revision(kind, entry_id, revision, g.authenticated_user.id))
