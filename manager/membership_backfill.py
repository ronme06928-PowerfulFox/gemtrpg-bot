"""Phase 1: 既存データから room_members(RoomMember) を backfill する。

- owner membership は `Room.owner_id` から作る。
- player membership は room state 内のキャラクター `owner_id`（UUID）から作る。
  正本はキャラ単位の `owner_id`。`character_owners` 辞書は補助参照に留める。
- backfill は冪等：有効membershipが既にあればスキップする（本番 room_members に
  既存行があるため、二重作成しない）。
- dry_run_report は一切書き込まず、owner不在ルーム・重複表示名・所有者不明キャラ
  などの移行前集計を返す。
"""
from collections import Counter
from datetime import datetime

from extensions import db, active_room_states
from models import User, Room, RoomMember


def _iter_room_states():
    """(Room, state dict) を列挙する。メモリ上の状態を優先し、無ければDBのdata。"""
    for room in Room.query.all():
        state = active_room_states.get(room.name)
        if not state:
            state = room.data or {}
        yield room, (state or {})


def _character_owner_ids(state):
    """room state から、キャラ所有者の UUID 候補を重複なく返す。"""
    owners = []
    for char in (state.get("characters") or []):
        if isinstance(char, dict):
            oid = char.get("owner_id")
            if oid:
                owners.append(oid)
    # 補助参照: character_owners 辞書（値が UUID のもの）も拾う
    for oid in (state.get("character_owners") or {}).values():
        if oid:
            owners.append(oid)
    # 重複除去（順序維持）
    seen = set()
    result = []
    for oid in owners:
        if oid not in seen:
            seen.add(oid)
            result.append(oid)
    return result


def _active_member_exists(room_id, user_id):
    return (
        RoomMember.query
        .filter_by(room_id=room_id, user_id=user_id, revoked_at=None)
        .first()
        is not None
    )


def dry_run_report():
    """書き込みせず、移行前の集計レポートを返す。"""
    user_ids = {u.id for u in User.query.all()}

    report = {
        "rooms_total": 0,
        "rooms_without_owner": [],          # room name
        "owners_missing_user": [],          # {"room": name, "owner_id": id}
        "duplicate_display_names": [],       # {"name": name, "count": n}
        "characters_unknown_owner": [],      # {"room": name, "owner_id": id}
        "would_create_owner": 0,
        "would_create_player": 0,
        "existing_active_memberships": RoomMember.query.filter_by(revoked_at=None).count(),
    }

    # 重複表示名
    name_counts = Counter(u.name for u in User.query.all())
    report["duplicate_display_names"] = [
        {"name": name, "count": cnt} for name, cnt in name_counts.items() if cnt > 1
    ]

    for room, state in _iter_room_states():
        report["rooms_total"] += 1

        if not room.owner_id:
            report["rooms_without_owner"].append(room.name)
        elif room.owner_id not in user_ids:
            report["owners_missing_user"].append({"room": room.name, "owner_id": room.owner_id})
        elif not _active_member_exists(room.id, room.owner_id):
            report["would_create_owner"] += 1

        for oid in _character_owner_ids(state):
            if oid == room.owner_id:
                continue
            if oid not in user_ids:
                report["characters_unknown_owner"].append({"room": room.name, "owner_id": oid})
                continue
            if not _active_member_exists(room.id, oid):
                report["would_create_player"] += 1

    return report


def backfill_memberships(commit=True):
    """owner / player の有効membershipを冪等に作成する。作成数を返す。"""
    user_ids = {u.id for u in User.query.all()}
    created_owner = 0
    created_player = 0
    skipped_existing = 0
    now = datetime.utcnow()

    for room, state in _iter_room_states():
        # owner membership
        if room.owner_id and room.owner_id in user_ids:
            if _active_member_exists(room.id, room.owner_id):
                skipped_existing += 1
            else:
                db.session.add(RoomMember(
                    room_id=room.id, user_id=room.owner_id, role="owner", joined_at=now,
                ))
                created_owner += 1

        # player memberships（キャラ所有者）
        for oid in _character_owner_ids(state):
            if oid == room.owner_id or oid not in user_ids:
                continue
            if _active_member_exists(room.id, oid):
                skipped_existing += 1
            else:
                db.session.add(RoomMember(
                    room_id=room.id, user_id=oid, role="player", joined_at=now,
                ))
                created_player += 1

    if commit:
        db.session.commit()

    return {
        "created_owner": created_owner,
        "created_player": created_player,
        "skipped_existing": skipped_existing,
    }
