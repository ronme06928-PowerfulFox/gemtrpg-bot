"""Shared writes to a held character's growth and passage points."""

from sqlalchemy import text

from extensions import db
from models import OwnedCharacter


def locked_characters(ids, *, user_id=None):
    # SQLite cannot lock selected rows; take the write lock before reading.
    if db.engine.dialect.name == "sqlite":
        connection = db.session.connection()
        if not connection.connection.driver_connection.in_transaction:
            connection.execute(text("BEGIN IMMEDIATE"))
    query = OwnedCharacter.query.filter(OwnedCharacter.id.in_(ids), OwnedCharacter.deleted_at.is_(None))
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    return {row.id: row for row in query.order_by(OwnedCharacter.id).with_for_update().populate_existing()}


def add_passage_points(data, gain):
    params = data.get("params")
    if not isinstance(params, list):
        params = data["params"] = []
    points = next((row for row in params if isinstance(row, dict) and row.get("label") == "通過点"), None)
    if points is None:
        points = {"label": "通過点", "value": "0"}
        params.append(points)
    try:
        current = int(points.get("value"))
    except (TypeError, ValueError, OverflowError):
        current = 0
    points["value"] = str(current + gain)
