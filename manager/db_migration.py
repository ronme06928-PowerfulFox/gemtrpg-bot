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

            if inspector.has_table('rooms'):
                room_columns = [c['name'] for c in inspector.get_columns('rooms')]
                if 'gm_pin_hash' not in room_columns:
                    logging.info("Run Auto Migration: Adding 'gm_pin_hash' column to rooms")
                    try:
                        if is_postgres:
                            db.session.execute(text("ALTER TABLE rooms ADD COLUMN IF NOT EXISTS gm_pin_hash VARCHAR(255)"))
                        else:
                            db.session.execute(text("ALTER TABLE rooms ADD COLUMN gm_pin_hash VARCHAR(255)"))
                        db.session.commit()
                        logging.info("Auto Migration Completed: 'gm_pin_hash' column added.")
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
