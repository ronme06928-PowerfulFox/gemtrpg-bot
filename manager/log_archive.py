"""Room log archival helpers."""
from datetime import datetime, timezone
import json

from extensions import db
from manager.logs import setup_logger
from models import Room, RoomLogArchive

logger = setup_logger(__name__)


def _as_int_or_none(value):
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_log_payload(log):
    return dict(log) if isinstance(log, dict) else {"message": str(log or "")}


def archive_room_logs(room_name, logs):
    """Persist old logs before in-memory trimming.

    Returns True when there is nothing to archive or archival succeeds. Returns
    False when the room no longer exists or DB persistence fails.
    """
    rows = [_normalize_log_payload(log) for log in (logs or [])]
    if not rows:
        return True

    room = Room.query.filter_by(name=room_name).first()
    if room is None:
        logger.warning("[LogArchive] room not found; skip archive room=%s count=%d", room_name, len(rows))
        return False

    try:
        for row in rows:
            db.session.add(RoomLogArchive(
                room_id=room.id,
                room_name=room.name,
                log_id=_as_int_or_none(row.get("log_id")),
                timestamp_ms=_as_int_or_none(row.get("timestamp")),
                log_type=str(row.get("type") or "")[:50] or None,
                user_name=str(row.get("user") or "")[:100] or None,
                secret=bool(row.get("secret", False)),
                message=str(row.get("message") or ""),
                payload=row,
            ))
        db.session.commit()
        return True
    except Exception as exc:
        db.session.rollback()
        logger.error("[LogArchive] archive failed room=%s count=%d error=%s", room_name, len(rows), exc)
        return False


def get_archived_room_logs(room_name):
    room = Room.query.filter_by(name=room_name).first()
    if room is None:
        return []
    rows = (
        RoomLogArchive.query
        .filter(RoomLogArchive.room_id == room.id)
        .order_by(
            RoomLogArchive.timestamp_ms.asc().nullsfirst(),
            RoomLogArchive.log_id.asc().nullsfirst(),
            RoomLogArchive.id.asc(),
        )
        .all()
    )
    return [row.to_log_dict() for row in rows]


def _log_sort_key(log):
    if not isinstance(log, dict):
        return (0, 0)
    timestamp = _as_int_or_none(log.get("timestamp")) or 0
    log_id = _as_int_or_none(log.get("log_id")) or 0
    return (timestamp, log_id)


def combine_room_logs(room_name, active_logs):
    archived = get_archived_room_logs(room_name)
    combined = archived + [_normalize_log_payload(log) for log in (active_logs or [])]
    return sorted(combined, key=_log_sort_key)


def _format_timestamp(timestamp_ms):
    ts = _as_int_or_none(timestamp_ms)
    if ts is None:
        return ""
    try:
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return str(timestamp_ms)


def format_logs_text(logs):
    lines = []
    for log in logs or []:
        if not isinstance(log, dict):
            lines.append(str(log))
            continue
        parts = []
        timestamp = _format_timestamp(log.get("timestamp"))
        if timestamp:
            parts.append(timestamp)
        log_type = str(log.get("type") or "").strip()
        if log_type:
            parts.append(f"[{log_type}]")
        if log.get("secret"):
            parts.append("[secret]")
        user = str(log.get("user") or "").strip()
        if user:
            parts.append(f"{user}:")
        parts.append(str(log.get("message") or ""))
        lines.append(" ".join(parts).strip())
    return "\n".join(lines) + ("\n" if lines else "")


def build_room_log_export(room_name, active_logs, export_format="json"):
    logs = combine_room_logs(room_name, active_logs)
    safe_room = "".join(
        ch if (ch.isascii() and (ch.isalnum() or ch in ("-", "_"))) else "_"
        for ch in str(room_name or "room")
    ).strip("_") or "room"
    exported_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if str(export_format).lower() == "text":
        return {
            "filename": f"{safe_room}_logs.txt",
            "content_type": "text/plain; charset=utf-8",
            "content": format_logs_text(logs),
            "count": len(logs),
        }
    payload = {
        "schema": "gem_dicebot_room_logs.v1",
        "room_name": room_name,
        "exported_at": exported_at,
        "count": len(logs),
        "logs": logs,
    }
    return {
        "filename": f"{safe_room}_logs.json",
        "content_type": "application/json; charset=utf-8",
        "content": json.dumps(payload, ensure_ascii=False, indent=2),
        "count": len(logs),
    }
