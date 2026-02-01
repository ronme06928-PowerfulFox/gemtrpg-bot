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
            # image_registryテーブルが存在するか確認
            if not inspector.has_table('image_registry'):
                return

            columns = [c['name'] for c in inspector.get_columns('image_registry')]

            if 'visibility' not in columns:
                logging.info("Run Auto Migration: Adding 'visibility' column to image_registry")

                # PostgreSQLかどうか判定（念のため）
                is_postgres = 'postgres' in str(db.engine.url)

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
