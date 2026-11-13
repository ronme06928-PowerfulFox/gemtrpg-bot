"""カタログ管理HTTP API。認証・権限・入出力のみを担当する。"""
from functools import wraps

from sqlalchemy import func

from flask import Blueprint, abort, g, jsonify, request

from extensions import db, socketio
from models import User, CatalogEntry, CatalogDraft, CatalogHistory, CatalogEffectRequest
from manager.catalog import effect_requests, repository
from manager.catalog.kinds import KINDS, CatalogValidationError, inspect_payload
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
            "payload": row.payload, "id_prefix": row.id_prefix,
            "problems": inspect_payload(row.kind, row.payload, entry_id=row.target_id, stage="submit"),
            "status": row.status, "base_revision": row.base_revision,
            "created_by": row.created_by, "created_by_name": _name(row.created_by),
            "reject_reason": row.reject_reason, "created_at": _time(row.created_at),
            "updated_at": _time(row.updated_at), "submitted_at": _time(row.submitted_at)}


def _published(row, *, notify=True):
    result = _entry_json(row)
    if notify:
        socketio.emit("catalog_updated", {"kind": row.kind, "entry_id": row.entry_id, "revision": row.revision})
    return jsonify(result)


@catalog_bp.get("/api/catalog/overview")
@_endpoint()
def overview():
    user = g.authenticated_user
    author = user.is_app_admin or user.is_catalog_author
    statuses = ("published", "deprecated", "draft", "pending", "rejected") if author else ("published", "deprecated")
    counts = {kind: dict.fromkeys(statuses, 0) for kind in KINDS}
    for kind, deprecated, count in db.session.query(
            CatalogEntry.kind, CatalogEntry.deprecated, func.count(CatalogEntry.id)
    ).group_by(CatalogEntry.kind, CatalogEntry.deprecated):
        if kind in counts:
            counts[kind]["deprecated" if deprecated else "published"] = count
    if author:
        for kind, status, count in db.session.query(
                CatalogDraft.kind, CatalogDraft.status, func.count(CatalogDraft.id)
        ).group_by(CatalogDraft.kind, CatalogDraft.status):
            if kind in counts and status in ("draft", "pending", "rejected"):
                counts[kind][status] = count
    result = {"counts": counts}
    if author:
        result["open_requests"] = effect_requests.count_open()
    if user.is_app_admin:
        pending = CatalogDraft.query.filter(CatalogDraft.kind.in_(KINDS), CatalogDraft.status == "pending")
        result["pending"] = [_draft_json(row) for row in pending.order_by(CatalogDraft.submitted_at, CatalogDraft.id)]
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
    return jsonify(entry_id=repository.next_entry_id(kind, prefix=request.args.get("prefix")))


@catalog_bp.post("/api/catalog/<kind>/drafts")
@_endpoint("author")
def create_draft(kind):
    data = _body()
    target_id = data.get("target_id")
    if "target_id" in data and (not isinstance(target_id, str) or not target_id):
        raise CatalogValidationError({"target_id": "公開IDの文字列が必要です"})
    if target_id and CatalogEntry.query.filter_by(kind=kind, entry_id=target_id).first() is None:
        abort(404)
    return jsonify(_draft_json(repository.create_draft(kind, g.authenticated_user.id, target_id=target_id, id_prefix=data.get("id_prefix"))))


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


@catalog_bp.get("/api/catalog/skill/text_references")
@_endpoint()
def skill_text_references():
    from manager.summons.loader import load_summon_templates
    return jsonify(summon_refs=[{"id": key, "name": row.get("name", key),
        "summon_duration_mode": row.get("summon_duration_mode", "permanent"),
        "summon_duration": row.get("summon_duration", 0),
        **({"tag_ids": row["tag_ids"]} if "tag_ids" in row else {})}
        for key, row in sorted(load_summon_templates().items())])


@catalog_bp.post("/api/catalog/skill/power_preview")
@_endpoint()
def skill_power_preview():
    from manager.catalog.power import preview_skill_power

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error="JSONオブジェクトが必要です。"), 400
    try:
        return jsonify(preview_skill_power(body.get("payload"), body.get("params", {})))
    except ValueError as error:
        return jsonify(error=str(error)), 400


def _effect_request_json(row):
    return {"id": row.id, "title": row.title, "want": row.want, "example": row.example,
            "near_type": row.near_type, "draft_id": row.draft_id, "draft_kind": row.draft_kind,
            "draft_target_id": row.draft_target_id, "draft_name": row.draft_name,
            "status": row.status, "memo": row.memo, "created_by": row.created_by,
            "created_by_name": _name(row.created_by), "created_at": _time(row.created_at),
            "updated_at": _time(row.updated_at)}


@catalog_bp.route("/api/catalog/effect_requests", methods=["GET", "POST"])
@_endpoint("author")
def list_or_create_effect_request():
    if request.method == "POST":
        return jsonify(_effect_request_json(effect_requests.create(_body(), g.authenticated_user.id))), 201
    rows = CatalogEffectRequest.query.order_by(CatalogEffectRequest.created_at.desc(), CatalogEffectRequest.id.desc())
    return jsonify(requests=[_effect_request_json(row) for row in rows])


def _locked_effect_request(request_id):
    row = CatalogEffectRequest.query.filter_by(id=request_id).with_for_update().first()
    if row is None:
        abort(404)
    return row


@catalog_bp.patch("/api/catalog/effect_requests/<int:request_id>")
@_endpoint("author")
def update_effect_request(request_id):
    try:
        row = effect_requests.update(_locked_effect_request(request_id), _body(), g.authenticated_user.id)
    except PermissionError:
        return jsonify(error="出した本人だけが操作できます。"), 403
    return jsonify(_effect_request_json(row))


@catalog_bp.delete("/api/catalog/effect_requests/<int:request_id>")
@_endpoint("author")
def withdraw_effect_request(request_id):
    try:
        effect_requests.withdraw(_locked_effect_request(request_id), g.authenticated_user.id)
    except PermissionError:
        return jsonify(error="出した本人だけが操作できます。"), 403
    return jsonify(id=request_id, withdrawn=True)


@catalog_bp.post("/api/catalog/effect_requests/<int:request_id>/review")
@_endpoint("admin")
def review_effect_request(request_id):
    return jsonify(_effect_request_json(effect_requests.review(_locked_effect_request(request_id), _body())))
