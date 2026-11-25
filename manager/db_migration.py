import logging
from collections import Counter
from copy import deepcopy

from sqlalchemy import MetaData, Table, text, inspect, select
from extensions import db

def _migrate_skill_cost(inspector):
    from models import CatalogEntry, CatalogDraft, CatalogHistory

    old_key, new_key = "使用時効果", "コスト"
    migrated = 0
    tables = [model.__table__ for model in (CatalogEntry, CatalogDraft, CatalogHistory)
              if inspector.has_table(model.__tablename__)]
    for table in tables:
        rows = db.session.execute(
            select(table.c.id, table.c.payload).where(table.c.kind == "skill")
        ).all()
        for row_id, payload in rows:
            if not isinstance(payload, dict) or old_key not in payload:
                continue
            if new_key in payload:
                raise ValueError(f"{table.name} id={row_id}: {old_key} と {new_key} が共存しています")
            renamed = {new_key if key == old_key else key: value for key, value in payload.items()}
            db.session.execute(table.update().where(table.c.id == row_id).values(payload=renamed))
            migrated += 1
    if migrated:
        db.session.commit()
        logging.info("Auto Migration: renamed skill cost in %d rows", migrated)


def _remove_unit_initial_states(inspector):
    from models import CatalogEntry, CatalogHistory

    changed = 0
    for model in (CatalogEntry, CatalogHistory):
        table = model.__table__
        if not inspector.has_table(table.name):
            continue
        for row_id, payload in db.session.execute(
            select(table.c.id, table.c.payload).where(table.c.kind == "unit")
        ).all():
            if not isinstance(payload, dict) or "states" not in payload:
                continue
            updated = {key: value for key, value in payload.items() if key != "states"}
            db.session.execute(table.update().where(table.c.id == row_id).values(payload=updated))
            changed += 1
    if changed:
        db.session.commit()
        logging.info("Auto Migration: removed initial states from %d unit rows", changed)


_RETIRED_ROOM_MODE = "battle_only"


def normalize_room_play_mode(state):
    if state.get("play_mode") == _RETIRED_ROOM_MODE:
        state.setdefault("combat_phase", "ready")
    state["play_mode"] = "normal"
    state.pop(_RETIRED_ROOM_MODE, None)


def _migrate_room_play_modes():
    from models import Room

    for room in Room.query.yield_per(100):
        state = room.data
        if isinstance(state, dict) and (state.get("play_mode") != "normal" or _RETIRED_ROOM_MODE in state):
            normalized = state.copy()
            normalize_room_play_mode(normalized)
            room.data = normalized
    db.session.commit()


def _remap_room_presets(ids):
    from models import Room

    for room in Room.query.all():
        if not isinstance(room.data, dict):
            continue
        state = deepcopy(room.data)
        placement = state.get("room_preset_state")
        if isinstance(placement, dict) and placement.get("selected_stage_id"):
            placement["selected_stage_id"] = ids.get(("stage", placement["selected_stage_id"]))
        if state != room.data:
            room.data = state


def _migrate_unit_resources():
    from models import CatalogEntry, CatalogHistory
    from manager.cache_paths import SKILLS_CACHE_FILE, load_json_cache
    from manager.units.characters import read_character, skill_catalog
    from manager.units.repository import lock_writes, next_id, write

    lock_writes()
    connection = db.session.connection()
    inspector = inspect(connection)
    old_tables = {"preset_resources", "preset_resource_acl"}
    existing = set(inspector.get_table_names())
    for model in (CatalogEntry, CatalogHistory):
        table = model.__table__
        if table.name not in existing:
            if "preset_resources" in existing:
                table.create(connection)
        elif "visibility" not in {col["name"] for col in inspector.get_columns(table.name)}:
            db.session.execute(text(
                f"ALTER TABLE {table.name} ADD COLUMN visibility VARCHAR(8) DEFAULT 'public' NOT NULL"
            ))
    if not old_tables.intersection(existing):
        db.session.commit()
        return
    external = sorted(
        name for name in existing - old_tables for fk in inspector.get_foreign_keys(name)
        if fk["referred_table"] in old_tables
    )
    if external:
        raise RuntimeError(f"旧プリセット表を参照する外部キーがあります: {', '.join(external)}")

    counts = Counter()
    ids = {}
    if "preset_resources" in existing:
        old = Table("preset_resources", MetaData(), autoload_with=connection)
        rows = list(db.session.execute(select(old).order_by(old.c.id)).mappings())
        kinds = {"character": "unit", "enemy_formation": "formation", "ally_formation": "formation",
                 "stage": "stage", "collection": "unit_collection"}
        reserved = {kind: [] for kind in kinds.values()}
        for row in rows:
            resource_type = row["resource_type"]
            kind = kinds[resource_type]
            entry_id = next_id(kind, reserved[kind])
            reserved[kind].append(entry_id)
            ids[resource_type, row["stable_id"]] = entry_id

        masters = skill_catalog() or load_json_cache(SKILLS_CACHE_FILE)
        for row in rows:
            resource_type = row["resource_type"]
            entry_id = ids[resource_type, row["stable_id"]]
            payload = dict(row["payload"])
            payload["name"] = row["name"]
            if resource_type == "character":
                marks = payload.get("marks")
                payload, _ = read_character(payload, masters=masters)
                if isinstance(marks, list):
                    payload["marks"] = marks
            elif kinds[resource_type] == "formation":
                payload["type"] = resource_type.split("_")[0]
                # 消えた参照先を指すメンバーは移さない（起動を止めない）。
                payload["members"] = [
                    {"unit_id": ids["character", member.get("preset_id")],
                     "count": max(1, int(member.get("count") or 1)), "pattern_id": None}
                    for member in payload.get("members", [])
                    if isinstance(member, dict) and ("character", member.get("preset_id")) in ids
                ]
            elif resource_type == "stage":
                for side in ("enemy", "ally"):
                    field = f"{side}_formation_id"
                    if payload.get(field):
                        payload[field] = ids.get((f"{side}_formation", payload[field]))
            if resource_type != "collection" and row["collection_id"]:
                payload["collection_id"] = ids.get(("collection", row["collection_id"]))
            for field in ("owner_user_id", "access_control", "creator", "created_by", "updated_by"):
                payload.pop(field, None)
            kind = kinds[resource_type]
            write(kind, entry_id, payload, "public" if row["viewer_mode"] == "public" else "staff",
                  bool(row["archived"] or payload.pop("archived", False)), "import")
            counts[kind] += 1
        if "rooms" in existing:
            _remap_room_presets(ids)
        db.session.flush()
    for name in ("preset_resource_acl", "preset_resources"):
        if name in existing:
            db.session.execute(text(f"DROP TABLE {name}"))
    db.session.commit()
    logging.info("Auto Migration: moved preset resources %s, removed legacy tables", dict(counts))


def _migrate_unit_domains(inspector):
    from models import CatalogDraft, CatalogEntry, CatalogHistory
    from manager.catalog.kinds import KINDS
    from manager.units.validation import IDS, links

    if not inspector.has_table(CatalogEntry.__tablename__):
        return

    units = CatalogEntry.query.filter(CatalogEntry.kind.in_(IDS)).all()
    resources = {(row.kind, row.entry_id): row.payload for row in units}
    domains = {key: payload.get("domain", "session") for key, payload in resources.items()}
    neighbors = {key: set() for key in resources}
    for key, payload in resources.items():
        for target_kind, entry_id, _ in links(key[0], payload):
            target = (target_kind, entry_id)
            neighbors[key].add(target)
            if target in neighbors:
                neighbors[target].add(key)

    for key, payload in resources.items():
        if key[0] != "unit" or "hollow" not in (payload.get("marks") or []):
            continue
        if domains[key] == "hollow":
            continue
        incompatible = sorted(target[1] for target in neighbors[key] if domains.get(target) != "hollow")
        if incompatible:
            logging.warning("Auto Migration: %s kept in %s because of unit resource references: %s",
                            key[1], domains[key], ", ".join(incompatible))
        else:
            domains[key] = "hollow"

    master_marks = set()
    for model in (CatalogEntry, CatalogHistory, CatalogDraft):
        if not inspector.has_table(model.__tablename__):
            continue
        kinds = KINDS if model is CatalogDraft else set(IDS) | set(KINDS)
        for row in model.query.filter(model.kind.in_(kinds)):
            payload = dict(row.payload)
            if row.kind in IDS:
                key = (row.kind, row.entry_id)
                if model is CatalogEntry:
                    payload["domain"] = domains[key]
                else:
                    payload.setdefault("domain", domains.get(key, "session"))
            marks = payload.get("marks")
            if isinstance(marks, list) and "hollow" in marks:
                payload["marks"] = [mark for mark in marks if mark != "hollow"]
                if row.kind in KINDS:
                    master_marks.add((row.kind, row.target_id if model is CatalogDraft else row.entry_id))
            if payload != row.payload:
                row.payload = payload
    db.session.commit()
    for kind, entry_id in sorted(master_marks):
        logging.warning("Auto Migration: removed hollow mark from master data %s %s", kind, entry_id)


def run_auto_migration(app):
    """
    アプリケーション起動時に実行する簡易マイグレーション。
    不足しているカラムがあれば自動追加する。
    列追加の失敗は起動を中断する（fail-fast）。
    一意インデックスの失敗のみ非致命的（既存重複があっても起動継続）。
    """
    with app.app_context():
        try:
            inspector = inspect(db.engine)
            is_postgres = 'postgres' in str(db.engine.url)

            if inspector.has_table('catalog_drafts') and 'id_prefix' not in {c['name'] for c in inspector.get_columns('catalog_drafts')}:
                db.session.execute(text("ALTER TABLE catalog_drafts ADD COLUMN id_prefix VARCHAR(8)"))
                db.session.commit()

            if inspector.has_table('users'):
                user_columns = [c['name'] for c in inspector.get_columns('users')]
                if 'is_app_admin' not in user_columns:
                    logging.info("Run Auto Migration: Adding 'is_app_admin' column to users")
                    try:
                        if is_postgres:
                            db.session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_app_admin BOOLEAN DEFAULT FALSE NOT NULL"))
                        else:
                            db.session.execute(text("ALTER TABLE users ADD COLUMN is_app_admin BOOLEAN DEFAULT 0 NOT NULL"))
                        db.session.commit()
                        logging.info("Auto Migration Completed: 'is_app_admin' column added.")
                    except Exception as e:
                        db.session.rollback()
                        logging.error(f"Migration Query Failed: {e}")
                        raise

                user_column_specs = {
                    'is_catalog_author': 'BOOLEAN DEFAULT FALSE NOT NULL',
                    'recovery_code_hash': 'VARCHAR(255)',
                    'recovery_token_hash': 'VARCHAR(64)',
                    'recovery_code_issued_at': 'TIMESTAMP',
                    # --- Phase 1 拡張 ---
                    'login_name_normalized': 'VARCHAR(100)',
                    'password_hash': 'VARCHAR(255)',
                    'password_changed_at': 'TIMESTAMP',
                    'auth_version': 'INTEGER DEFAULT 1 NOT NULL',
                }
                for column_name, column_type in user_column_specs.items():
                    if column_name in user_columns:
                        continue
                    logging.info(f"Run Auto Migration: Adding '{column_name}' column to users")
                    try:
                        if is_postgres:
                            db.session.execute(text(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {column_name} {column_type}"))
                        else:
                            db.session.execute(text(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}"))
                        db.session.commit()
                        logging.info(f"Auto Migration Completed: '{column_name}' column added.")
                    except Exception as e:
                        db.session.rollback()
                        logging.error(f"Migration Query Failed: {e}")
                        raise

                # login_name_normalized の一意制約は unique index で担保する
                # （nullable のため複数 NULL は許容される / postgres・sqlite とも IF NOT EXISTS 可）。
                # 既存重複があると作成に失敗するため非致命的とし、backfill側でdedupする。
                try:
                    db.session.execute(text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_login_name_normalized "
                        "ON users (login_name_normalized)"
                    ))
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    logging.error(f"Migration Query Failed (login_name index): {e}")

            if inspector.has_table('rooms'):
                room_columns = [c['name'] for c in inspector.get_columns('rooms')]
                room_column_specs = {
                    'gm_pin_hash': 'VARCHAR(255)',
                    # --- Phase 1 拡張 ---
                    'description': 'TEXT',
                    'lobby_visibility': "VARCHAR(20) DEFAULT 'hidden'",
                    'recruitment_status': 'VARCHAR(20)',
                    'join_code_hash': 'VARCHAR(255)',
                    'join_code_rotated_at': 'TIMESTAMP',
                }
                for column_name, column_type in room_column_specs.items():
                    if column_name in room_columns:
                        continue
                    logging.info(f"Run Auto Migration: Adding '{column_name}' column to rooms")
                    try:
                        if is_postgres:
                            db.session.execute(text(f"ALTER TABLE rooms ADD COLUMN IF NOT EXISTS {column_name} {column_type}"))
                        else:
                            db.session.execute(text(f"ALTER TABLE rooms ADD COLUMN {column_name} {column_type}"))
                        db.session.commit()
                        logging.info(f"Auto Migration Completed: '{column_name}' column added.")
                    except Exception as e:
                        db.session.rollback()
                        logging.error(f"Migration Query Failed: {e}")
                        raise

            # room_members（本番Neonに既存・コード外だった会員名簿）を採用する。
            # 既存列(id/room_id/user_id/role/joined_at/granted_by_user_id)へ
            # manual 6.4 の updated_at / revoked_at を追加し、有効membershipの
            # 一意インデックスを張る。新規環境では create_all が全体を作る。
            if inspector.has_table('room_members'):
                rm_columns = [c['name'] for c in inspector.get_columns('room_members')]
                rm_column_specs = {
                    'updated_at': 'TIMESTAMP',
                    'revoked_at': 'TIMESTAMP',
                }
                for column_name, column_type in rm_column_specs.items():
                    if column_name in rm_columns:
                        continue
                    logging.info(f"Run Auto Migration: Adding '{column_name}' column to room_members")
                    try:
                        if is_postgres:
                            db.session.execute(text(f"ALTER TABLE room_members ADD COLUMN IF NOT EXISTS {column_name} {column_type}"))
                        else:
                            db.session.execute(text(f"ALTER TABLE room_members ADD COLUMN {column_name} {column_type}"))
                        db.session.commit()
                        logging.info(f"Auto Migration Completed: '{column_name}' column added.")
                    except Exception as e:
                        db.session.rollback()
                        logging.error(f"Migration Query Failed: {e}")
                        raise

                # 有効membership(revoked_at IS NULL)について (room_id, user_id) を一意に。
                # 既存重複があると作成に失敗するため非致命的とし、backfill側でdedupする。
                try:
                    db.session.execute(text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS uq_room_members_active "
                        "ON room_members (room_id, user_id) WHERE revoked_at IS NULL"
                    ))
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    logging.error(f"Migration Query Failed (room_members active index): {e}")

            _migrate_skill_cost(inspector)
            _migrate_unit_resources()
            if inspector.has_table("rooms"):
                _migrate_room_play_modes()
            _remove_unit_initial_states(inspect(db.session.connection()))
            _migrate_unit_domains(inspect(db.session.connection()))

            # image_registryテーブルが存在するか確認
            if not inspector.has_table('image_registry'):
                return

            columns = [c['name'] for c in inspector.get_columns('image_registry')]

            if 'visibility' not in columns:
                logging.info("Run Auto Migration: Adding 'visibility' column to image_registry")

                try:
                    if is_postgres:
                         db.session.execute(text("ALTER TABLE image_registry ADD COLUMN IF NOT EXISTS visibility VARCHAR(20) DEFAULT 'public'"))
                    else:
                         # SQLite
                         db.session.execute(text("ALTER TABLE image_registry ADD COLUMN visibility VARCHAR(20) DEFAULT 'public'"))

                    db.session.commit()
                    logging.info("Auto Migration Completed: 'visibility' column added.")
                except Exception as e:
                    db.session.rollback()
                    logging.error(f"Migration Query Failed: {e}")
                    raise
            else:
                logging.info("DB Schema Check: 'visibility' column exists.")

        except Exception as e:
            db.session.rollback()
            logging.critical(f"Auto Migration Failed — 起動を中止します: {e}")
            raise RuntimeError(f"DB migration failed, aborting startup: {e}") from e
