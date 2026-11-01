"""Separate-process save/restart and SQLite backup tests using synthetic data."""

import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import textwrap

import pytest


ROOT = Path(__file__).resolve().parents[1]
DRIVER = textwrap.dedent("""
    import copy
    import os
    from pathlib import Path
    import sqlite3
    import sys
    import time

    sys.path.insert(0, sys.argv[1])
    from sqlalchemy import event
    from app import _configure_local_sqlite, create_app
    from extensions import db
    from manager import room_manager
    from manager.data_manager import read_saved_room, read_saved_rooms_with_owners
    from models import Room, RoomLogArchive, RoomMember, User

    path, mode, argument = Path(sys.argv[2]), sys.argv[3], sys.argv[4]
    app = create_app(
        config={
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + path.as_posix(),
            'SQLALCHEMY_ENGINE_OPTIONS': {},
        },
        run_startup=False,
        register_sockets=False,
    )
    assert app.config['SQLALCHEMY_DATABASE_URI'] == 'sqlite:///' + path.as_posix()
    with app.app_context():
        _configure_local_sqlite(app)
        if mode == 'read':
            expected_round = int(argument)
            assert read_saved_room('recovery-room')['round'] == expected_round
            assert room_manager.active_room_states == {}
            state = room_manager.get_room_state('recovery-room')
            assert state['round'] == expected_round
            expected_hp = 10 if expected_round == 1 else 5
            assert state['characters'][0]['hp'] == expected_hp
            assert state['characters'][0]['x'] == (1 if expected_round == 1 else 2.5)
            assert state['battle_state']['declared'] == (expected_round == 3)
            assert state['logs'][0]['message'] == ('initial' if expected_round == 1 else 'latest')
            assert state['character_owners'] == {'char-1': 'owner'}
            room = Room.query.filter_by(name='recovery-room').one()
            assert room.owner_id == 'owner'
            assert User.query.filter_by(id='owner').one().name == 'Synthetic recovery owner'
            assert RoomMember.query.filter_by(room_id=room.id, user_id='owner').one().role == 'owner'
            assert RoomLogArchive.query.filter_by(room_id=room.id).one().message == 'archived'
            assert read_saved_rooms_with_owners() == [
                {'name': 'recovery-room', 'owner_id': 'owner', 'play_mode': 'normal', 'battle_only_stage_id': None}
            ]
        else:
            assert mode in {'debounce', 'exit', 'abort', 'exit-retry', 'exit-exhausted', 'immediate-exit-retry', 'backup'}
            db.create_all()
            db.session.add(User(id='owner', name='Synthetic recovery owner'))
            db.session.flush()
            initial = {
                'round': 1,
                'characters': [{'id': 'char-1', 'hp': 10, 'x': 1}],
                'battle_state': {'declared': False},
                'logs': [{'log_id': 2, 'message': 'initial'}],
                'character_owners': {'char-1': 'owner'},
                'play_mode': 'normal',
            }
            room = Room(name='recovery-room', owner_id='owner', data=initial)
            db.session.add(room)
            db.session.flush()
            db.session.add(RoomMember(room_id=room.id, user_id='owner', role='owner'))
            db.session.add(RoomLogArchive(room_id=room.id, room_name=room.name, log_id=1, message='archived'))
            db.session.commit()
            state = copy.deepcopy(initial)
            room_manager.active_room_states[room.name] = state
            if mode not in {'debounce', 'backup'}:
                room_manager._SAVE_DEBOUNCE_SECONDS = 60
            state['round'] = 2
            if mode != 'immediate-exit-retry':
                assert room_manager.save_specific_room_state(room.name)
            state['round'] = 3
            state['characters'][0].update(hp=5, x=2.5)
            state['battle_state']['declared'] = True
            state['logs'][0]['message'] = 'latest'
            if mode == 'immediate-exit-retry':
                failures = [True]
                def fail_immediate_commit(_connection):
                    if failures:
                        failures.pop()
                        raise RuntimeError('synthetic first immediate save failure')
                event.listen(db.engine, 'commit', fail_immediate_commit)
                assert room_manager._app_ref is None
                assert room_manager.flush_room_state_now(room.name) is False
            else:
                assert room_manager.save_specific_room_state(room.name)
            assert read_saved_room(room.name)['round'] == 1

            if mode in {'debounce', 'backup'}:
                deadline = time.monotonic() + 12
                while True:
                    db.session.expire_all()
                    if read_saved_room(room.name)['round'] == 3:
                        break
                    assert time.monotonic() < deadline, 'Background save did not commit'
                    time.sleep(0.05)
                assert room_manager._dirty_rooms == set()
                if mode == 'backup':
                    wal = Path(str(path) + '-wal')
                    assert wal.exists() and wal.stat().st_size > 0
                    with sqlite3.connect(path) as source, sqlite3.connect(argument) as backup:
                        source.backup(backup)
                        assert backup.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
            elif mode == 'abort':
                os._exit(0)
            elif mode in {'exit-retry', 'exit-exhausted'}:
                failures = [True] if mode == 'exit-retry' else [True, True]
                def fail_commit(_connection):
                    if failures:
                        failures.pop()
                        raise RuntimeError('synthetic temporary database outage')
                event.listen(db.engine, 'commit', fail_commit)
                if mode == 'exit-exhausted':
                    room_manager._flush_dirty_rooms_once()
                    room_manager._flush_dirty_rooms_once()
                    assert room_manager._dirty_rooms == {'recovery-room'}
                    assert read_saved_room(room.name)['round'] == 1
            # Normal interpreter exit must flush pending state via atexit.
""")


def _run(path, mode, argument="unused"):
    env = os.environ.copy()
    env.pop("RENDER", None)
    env.pop("DATABASE_URL", None)
    env.update(
        APP_ENV="testing",
        FLASK_ENV="testing",
        GEMTRPG_DISABLE_DEFAULT_APP="1",
        GEMTRPG_SKIP_IMPORT_STARTUP="1",
        PYTHONIOENCODING="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-u", "-c", DRIVER, str(ROOT), str(path), mode, str(argument)],
        cwd=path.parent,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=40,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


@pytest.mark.parametrize(
    "mode, expected_round",
    [("debounce", 3), ("exit", 3), ("abort", 1), ("exit-retry", 3), ("exit-exhausted", 3), ("immediate-exit-retry", 3)],
)
def test_fresh_process_restores_last_committed_state(tmp_path, mode, expected_round):
    path = tmp_path / "recovery.db"
    result = _run(path, mode)
    if mode in {"exit", "exit-retry", "exit-exhausted", "immediate-exit-retry"}:
        assert "[SHUTDOWN] (1/1) Saved room: recovery-room" in result.stdout
    if mode == "abort":
        assert "[SHUTDOWN]" not in result.stdout
    _run(path, "read", expected_round)


def test_online_backup_with_wal_restores_room_and_related_records(tmp_path):
    path = tmp_path / "source.db"
    backup_path = tmp_path / "backup.db"
    restored_path = tmp_path / "restored.db"
    _run(path, "backup", backup_path)
    with sqlite3.connect(backup_path) as source, sqlite3.connect(restored_path) as restored:
        source.backup(restored)
        assert restored.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    _run(restored_path, "read", 3)
