import sys
import os

# Add parent directory to path to import app and extensions
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("GEMTRPG_DISABLE_DEFAULT_APP", "1")

from app import create_app
from extensions import db
from sqlalchemy import text


app = create_app(run_startup=False, register_sockets=False)

def migrate():
    with app.app_context():
        print("Starting migration: Add visibility column to image_registry")

        # Check if column exists
        check_sql = text("SELECT column_name FROM information_schema.columns WHERE table_name='image_registry' AND column_name='visibility'")
        result = db.session.execute(check_sql).fetchone()

        if result:
            print("Column 'visibility' already exists. Skipping.")
        else:
            try:
                # Add column
                alter_sql = text("ALTER TABLE image_registry ADD COLUMN visibility VARCHAR(20) DEFAULT 'public'")
                db.session.execute(alter_sql)
                db.session.commit()
                print("Successfully added 'visibility' column.")
            except Exception as e:
                db.session.rollback()
                print(f"Error adding column: {e}")

if __name__ == "__main__":
    migrate()
