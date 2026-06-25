import logging
from sqlalchemy import text, inspect
from extensions import db

def run_auto_migration(app):
    """
    アプリケーション起動時に実行する簡易マイグレーション
    不足しているカラムがあれば自動追加する
    """
    with app.app_context():
        try:
            inspector = inspect(db.engine)
            is_postgres = 'postgres' in str(db.engine.url)

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

                user_column_specs = {
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

                # login_name_normalized の一意制約は unique index で担保する
                # （nullable のため複数 NULL は許容される / postgres・sqlite とも IF NOT EXISTS 可）。
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
            else:
                logging.info("DB Schema Check: 'visibility' column exists.")

        except Exception as e:
            logging.error(f"Auto Migration Failed: {e}")
