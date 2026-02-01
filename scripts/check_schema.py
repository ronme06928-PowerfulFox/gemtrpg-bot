import sys
import os
import sqlite3

# Extract DB path from app.py or assume default
# Usually instance/gem_trpg.sqlite or similar
# Let's try to find the db file first or use app context.

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from extensions import db
from app import app
from sqlalchemy import text

def check_schema():
    with app.app_context():
        print("Checking Database Schema...")
        db_uri = app.config['SQLALCHEMY_DATABASE_URI']
        print(f"Database URI: {db_uri}")

        try:
            # Check columns in image_registry
            if 'sqlite' in db_uri:
                with db.engine.connect() as conn:
                    result = conn.execute(text("PRAGMA table_info(image_registry)"))
                    columns = [row.name for row in result]
                    print(f"Columns in image_registry: {columns}")

                    if 'visibility' in columns:
                        print("SUCCESS: 'visibility' column exists.")
                    else:
                        print("FAILURE: 'visibility' column MISSING.")

                        # Attempt migration again immediately if missing
                        print("Attempting to add column via SQL...")
                        try:
                            # Split into two commands if needed, but ADD COLUMN should be fine
                            conn.execute(text("ALTER TABLE image_registry ADD COLUMN visibility VARCHAR(20) DEFAULT 'public'"))
                            conn.commit()
                            print("Migration executed successfully.")
                        except Exception as e:
                            print(f"Migration Failed: {e}")

            else:
                print("Not SQLite, running generic check...")
                # Generic SQLAlchemy check?
                # ...
                pass

        except Exception as e:
            print(f"Error checking schema: {e}")

if __name__ == "__main__":
    check_schema()
