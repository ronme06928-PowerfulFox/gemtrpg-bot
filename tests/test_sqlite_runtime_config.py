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


def test_local_sqlite_enforces_foreign_keys_so_room_deletion_cascades(tmp_path):
    from manager.data_manager import delete_room_from_db
    from models import Room, RoomMember, User

    db_path = tmp_path / 'fk.db'
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
        assert db.session.execute(text('PRAGMA foreign_keys')).scalar() == 1

        db.create_all()
        db.session.add(User(id='owner', name='owner'))
        db.session.flush()
        db.session.add(Room(name='R1', owner_id='owner', data={}))
        db.session.flush()
        room_id = Room.query.filter_by(name='R1').one().id
        db.session.add(RoomMember(room_id=room_id, user_id='owner', role='owner'))
        db.session.commit()

        assert delete_room_from_db('R1') is True
        assert RoomMember.query.filter_by(room_id=room_id).count() == 0
        db.session.remove()
