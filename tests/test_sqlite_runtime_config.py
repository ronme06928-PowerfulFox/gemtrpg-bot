import os

os.environ['GEMTRPG_SKIP_IMPORT_STARTUP'] = '1'

from app import _configure_local_sqlite, create_app
from extensions import db
from sqlalchemy import text


def test_local_sqlite_uses_wal_and_bounded_busy_timeout(tmp_path):
    db_path = tmp_path / 'runtime.db'
    app = create_app(
        config={
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path.as_posix()}',
            'SQLALCHEMY_ENGINE_OPTIONS': {},
        },
        run_startup=False,
        register_sockets=False,
    )

    with app.app_context():
        _configure_local_sqlite(app)
        journal_mode = db.session.execute(text('PRAGMA journal_mode')).scalar()
        busy_timeout = db.session.execute(text('PRAGMA busy_timeout')).scalar()
        assert journal_mode.lower() == 'wal'
        assert busy_timeout == 3000
        db.session.remove()
