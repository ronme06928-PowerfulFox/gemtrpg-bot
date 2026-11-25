"""HTTP endpoints for game-wide unit resources."""
from functools import wraps

from flask import Blueprint, abort, g, jsonify, request

from manager.room_access import GM_ROLES, resolve_room_role
from manager.catalog.kinds import MARK_LABELS
from manager.units import repository, transfer
from manager.units.characters import read_character
from manager.units.validation import DOMAINS, IDS, master_links
from manager.utils import session_required
from manager.battle.hidden_passives import redact_hidden_passives
from manager.practice_rooms import is_practice

units_bp = Blueprint("units", __name__, url_prefix="/api/units")


def endpoint(*, author_only=False):
    def decorate(function):
        @wraps(function)
        @session_required
        def guarded(*args, **kwargs):
            user = g.authenticated_user
            author = user.is_catalog_author or user.is_app_admin
            if author_only and not author:
                return jsonify(error="制作者権限が必要です"), 403
            room = request.args.get("room", "").strip()
            g.units_staff = author or bool(room and not is_practice(room) and resolve_room_role(user.id, room) in GM_ROLES)
            if kwargs.get("kind") is not None and kwargs["kind"] not in IDS:
                abort(404)
            try:
                return function(*args, **kwargs)
            except repository.CatalogValidationError as exc:
                return jsonify(errors=exc.errors), 422
            except repository.CatalogConflictError as exc:
                return jsonify(errors=exc.errors), 409
        return guarded
    return decorate


def _body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise repository.CatalogValidationError({"body": "JSONオブジェクトが必要です"})
    return body


def _visible(kind, entry_id):
    row = repository.get(kind, entry_id)
    if row is None or (row.visibility == "staff" and not g.units_staff):
        abort(404)
    return row


@units_bp.get("")
@units_bp.get("/<kind>")
@endpoint()
def list_entries(kind=None):
    domain = request.args.get("domain")
    if domain is not None and domain not in DOMAINS:
        raise repository.CatalogValidationError({"domain": "session または hollow を指定してください"})
    rows = repository.entries(include_staff=g.units_staff,
                              include_deprecated=request.args.get("include_deprecated") == "1",
                              domain=domain)
    return jsonify(entries=[row if g.units_staff else redact_hidden_passives(row)
                            for (row_kind, _), row in rows.items() if kind is None or kind == row_kind],
                   marks=MARK_LABELS)


@units_bp.get("/<kind>/<entry_id>")
@endpoint()
def get_entry(kind, entry_id):
    entry = repository.entry_json(_visible(kind, entry_id))
    return jsonify(entry if g.units_staff else redact_hidden_passives(entry))


@units_bp.get("/<kind>/<entry_id>/history")
@endpoint()
def list_history(kind, entry_id):
    _visible(kind, entry_id)
    snapshots = repository.history(kind, entry_id)
    return jsonify(history=[{
        **(repository.entry_json(row) if g.units_staff else redact_hidden_passives(repository.entry_json(row))),
        "action": row.action,
        "actor_user_id": row.actor_user_id, "created_at": row.created_at.isoformat() + "Z",
    } for row in snapshots if g.units_staff or row.visibility == "public"])


@units_bp.get("/<kind>/<entry_id>/references")
@endpoint()
def list_references(kind, entry_id):
    row = _visible(kind, entry_id)
    result = {"references": repository.references(
        kind, entry_id, resources=repository.entries(include_staff=g.units_staff))}
    if kind == "unit":
        result["master_references"] = [
            {"kind": target, "entry_id": key, "path": path}
            for target, key, path in master_links(row.payload)
            if g.units_staff or not path.startswith("hidden_passives[")]
    return jsonify(result)


@units_bp.post("/<kind>/check")
@endpoint(author_only=True)
def check(kind):
    data = _body()
    errors, warnings = repository.check(kind, data.get("payload"), data.get("visibility", "public"),
                                         entry_id=data.get("entry_id"), pattern_additions=data.get("pattern_additions"))
    return jsonify(errors=errors, warnings=warnings)


@units_bp.post("/<kind>")
@units_bp.put("/<kind>/<entry_id>")
@endpoint(author_only=True)
def save(kind, entry_id=None):
    data = _body()
    row, warnings = repository.save(
        kind, entry_id, data.get("payload"), visibility=data.get("visibility", "public"),
        base_revision=data.get("base_revision"), actor_user_id=g.authenticated_user.id,
        pattern_additions=data.get("pattern_additions"))
    return jsonify(entry=repository.entry_json(row), warnings=warnings), (201 if entry_id is None else 200)


@units_bp.post("/unit/<entry_id>/duplicate-to-hollow")
@endpoint(author_only=True)
def duplicate_to_hollow(entry_id):
    result = repository.duplicate_to_hollow(entry_id, actor_user_id=g.authenticated_user.id)
    if result is None:
        abort(404)
    row, warnings = result
    return jsonify(entry=repository.entry_json(row), warnings=warnings), 201


@units_bp.post("/<kind>/<entry_id>/deprecation")
@endpoint(author_only=True)
def set_deprecated(kind, entry_id):
    data = _body()
    row = repository.set_deprecated(kind, entry_id, data.get("deprecated"),
                                    base_revision=data.get("base_revision"), actor_user_id=g.authenticated_user.id)
    return jsonify(entry=repository.entry_json(row))


@units_bp.post("/<kind>/<entry_id>/restore")
@endpoint(author_only=True)
def restore(kind, entry_id):
    data = _body()
    row, warnings = repository.restore(kind, entry_id, data.get("revision"),
                                       base_revision=data.get("base_revision"), actor_user_id=g.authenticated_user.id)
    return jsonify(entry=repository.entry_json(row), warnings=warnings)


@units_bp.delete("/<kind>/<entry_id>")
@endpoint(author_only=True)
def delete(kind, entry_id):
    repository.delete(kind, entry_id, base_revision=_body().get("base_revision"))
    return "", 204


@units_bp.post("/import-character")
@endpoint(author_only=True)
def import_character():
    try:
        payload, discarded = read_character(_body().get("character"))
    except ValueError as exc:
        raise repository.CatalogValidationError({"character": str(exc)}) from exc
    errors, warnings = repository.check("unit", payload)
    return jsonify(payload=payload, discarded=discarded, errors=errors, warnings=warnings)


@units_bp.get("/export")
@endpoint(author_only=True)
def export():
    return jsonify(transfer.export_package(
        request.args.get("collection_id"), include_deprecated=request.args.get("include_deprecated", "1") == "1"))


@units_bp.post("/import/preview")
@endpoint(author_only=True)
def preview():
    return jsonify(entries=transfer.preview(_body().get("package")))


@units_bp.post("/import/confirm")
@endpoint(author_only=True)
def confirm():
    data = _body()
    rows, report = transfer.confirm(data.get("package"), data.get("base_revisions"), g.authenticated_user.id)
    return jsonify(entries=rows, report=report)
