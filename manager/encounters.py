"""敵のスキルの公開と、接続中のユーザーの出会いを扱う。"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from threading import Lock

from flask import current_app, has_app_context
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from extensions import active_room_states, db, socketio, user_sids
from manager.logs import setup_logger
from models import CatalogEncounter, User

logger = setup_logger(__name__)
_candidate_buffs = ContextVar("candidate_encounter_buffs", default=None)
_KINDS = {"unit", "passive", "skill", "buff"}


class _EncounterBatch:
    def __init__(self, app):
        self.app = app
        self.lock = Lock()
        self.pending = {}
        self.running = False

    def add(self, keys, timestamp, room):
        with self.lock:
            for key in keys:
                self.pending.setdefault(key, (timestamp, room))
            if self.running:
                return
            self.running = True
        try:
            socketio.start_background_task(self.run)
        except Exception:
            with self.lock:
                self.running = False
            logger.exception("出会いの記録を開始できませんでした")

    def write(self, batch):
        with self.app.app_context():
            insert = postgres_insert if db.engine.dialect.name == "postgresql" else sqlite_insert
            user_ids = {key[0] for key in batch}
            existing_users = set(db.session.scalars(select(User.id).where(User.id.in_(user_ids))))
            rows = [dict(user_id=user, kind=kind, entry_id=entry_id, first_seen_at=at, room_name=room)
                    for (user, kind, entry_id), (at, room) in batch.items() if user in existing_users]
            for start in range(0, len(rows), 100):
                statement = insert(CatalogEncounter).values(rows[start:start + 100])
                db.session.execute(statement.on_conflict_do_nothing(index_elements=["user_id", "kind", "entry_id"]))
            db.session.commit()

    def run(self):
        failures = 0
        while True:
            socketio.sleep(0.1 if failures == 0 else failures)
            with self.lock:
                if not self.pending:
                    self.running = False
                    return
                batch = self.pending.copy()
            try:
                if socketio.async_mode == "eventlet":
                    from eventlet import tpool
                    tpool.execute(self.write, batch)
                else:
                    self.write(batch)
            except Exception:
                logger.exception("出会いの記録を保存できませんでした")
                failures += 1
                if failures >= 3:
                    with self.lock:
                        self.running = False
                    return
            else:
                with self.lock:
                    for key in batch:
                        del self.pending[key]
                failures = 0


def record(room, entries):
    if not room or not has_app_context():
        return
    users = {row["user_id"] for row in user_sids.copy().values()
             if row.get("room") == room and row.get("user_id")}
    if not users:
        return
    items = {(kind, entry_id) for kind, entry_id in entries
             if kind in _KINDS and isinstance(entry_id, str) and 0 < len(entry_id) <= 64}
    if items:
        app = current_app._get_current_object()
        batch = app.extensions.get("catalog_encounters")
        if batch is None:
            batch = app.extensions.setdefault("catalog_encounters", _EncounterBatch(app))
        batch.add(((user, kind, entry_id) for user in users for kind, entry_id in items), datetime.now(timezone.utc), room)


def hide_enemy_skills(char):
    if char.get("type") == "enemy":
        from manager.battle.skill_access import _normalize_skill_ids
        char["hidden_skills"] = _normalize_skill_ids(char)


def buff_entry_id(buff):
    data = buff.get("data")
    return buff.get("buff_id") or (data.get("buff_id") if isinstance(data, dict) else None)


def record_arrivals(room, characters, buff_ids=()):
    if not room:
        return
    entries = [("buff", buff_id) for buff_id in buff_ids]
    for char in characters:
        if char.get("type") == "enemy":
            entries.append(("unit", char.get("source_unit_id")))
            passives = char.get("SPassive")
            if isinstance(passives, list):
                entries.extend(("passive", key) for key in passives if isinstance(key, str) and key.startswith("Pa-"))
        entries.extend(("buff", buff_entry_id(row)) for row in char.get("special_buffs") or [] if isinstance(row, dict))
    record(room, entries)


def reveal_enemy_skill(room, char, skill_id):
    if not char or char.get("type") != "enemy" or not skill_id:
        return False
    record(room, [("skill", skill_id)])
    hidden = char.get("hidden_skills") or []
    if skill_id not in hidden:
        return False
    char["hidden_skills"] = [key for key in hidden if key != skill_id]
    return True


@contextmanager
def capture_candidate_buffs(characters):
    buff_ids = set()
    token = _candidate_buffs.set((characters, buff_ids))
    try:
        yield buff_ids
    finally:
        _candidate_buffs.reset(token)


def record_buff(char, buff_id):
    if not isinstance(buff_id, str) or not buff_id:
        return
    candidate = _candidate_buffs.get()
    if candidate is not None:
        characters, buff_ids = candidate
        if any(target is char for target in characters):
            buff_ids.add(buff_id)
        return
    if not has_app_context():
        return
    # 解決表示・効果試算は同じ ID のコピーを使う。盤面の実体に付いたものだけを記録する。
    for room, state in active_room_states.copy().items():
        if any(target is char for target in state.get("characters", [])):
            record(room, [("buff", buff_id)])
            return
