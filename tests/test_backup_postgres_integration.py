"""Opt-in disposable PostgreSQL: dump, offline verification and real restore."""

import base64
import hashlib
import json
import os
from pathlib import Path
import random
import socket
import subprocess
import tempfile
from urllib.parse import quote

import pytest

from scripts import backup_postgres as backup


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_BACKUP_INTEGRATION") != "1",
    reason="Set RUN_POSTGRES_BACKUP_INTEGRATION=1 to use a disposable local PostgreSQL.",
)


def _command(args):
    # initdb/pg_ctl spawn children; inherited PIPE handles can prevent EOF on Windows.
    with tempfile.TemporaryFile() as log:
        result = subprocess.run(
            [str(value) for value in args], env=backup._clean_environment(),
            stdout=log, stderr=subprocess.STDOUT, timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        log.seek(0)
        assert result.returncode == 0, log.read().decode("utf-8", errors="replace")


@pytest.fixture(scope="module")
def postgres(tmp_path_factory):
    import psycopg2
    from flask import Flask
    from extensions import db
    from models import OwnedCharacter, Room, RoomLogArchive, RoomMember, User

    tools = backup.find_tools()
    bin_dir = tools.pg_dump.parent
    suffix = ".exe" if os.name == "nt" else ""
    initdb, pg_ctl = bin_dir / ("initdb" + suffix), bin_dir / ("pg_ctl" + suffix)
    if not initdb.is_file() or not pg_ctl.is_file():
        pytest.skip("Disposable-server executables are not installed.")
    root = tmp_path_factory.mktemp("postgres_cluster")
    data = root / "data"
    password = "synthetic:p\\ass"
    pwfile = root / "init-password"
    pwfile.write_text(password + "\n", encoding="utf-8")
    try:
        _command([
            initdb, "-D", data, "-U", "backup_test", "--encoding=UTF8", "--no-locale",
            "--auth-host=scram-sha-256", "--auth-local=trust", "--pwfile", pwfile,
        ])
    finally:
        pwfile.unlink(missing_ok=True)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    options = f"-h 127.0.0.1 -p {port} -c ssl=off"
    def uri(name, secret=password):
        return f"postgresql://backup_test:{quote(secret, safe='')}@127.0.0.1:{port}/{name}?sslmode=disable"

    try:
        _command([pg_ctl, "-D", data, "-l", root / "server.log", "-o", options, "-w", "start"])
        admin = psycopg2.connect(uri("postgres"))
        try:
            admin.autocommit = True
            with admin.cursor() as cursor:
                cursor.execute("CREATE DATABASE backup_source")
                cursor.execute("CREATE DATABASE backup_restored")
        finally:
            admin.close()
        app = Flask("backup_integration")
        app.config.update(
            SQLALCHEMY_DATABASE_URI=uri("backup_source").replace("postgresql://", "postgresql+psycopg2://", 1),
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(app)
        state = {
            "round": 3, "characters": [{"id": "C", "hp": 5, "x": 2.5}],
            "logs": [{"log_id": 2, "message": "合成ログ"}],
            "backup_probe": base64.b64encode(random.Random(11).randbytes(200_000)).decode("ascii"),
        }
        with app.app_context():
            db.create_all()
            db.session.add(User(id="owner", name="Synthetic owner", password_hash="not-real"))
            db.session.flush()
            room = Room(name="synthetic-room", owner_id="owner", data=state)
            db.session.add(room)
            db.session.flush()
            db.session.add(RoomMember(room_id=room.id, user_id="owner", role="owner"))
            db.session.add(RoomLogArchive(room_id=room.id, room_name=room.name, log_id=1, message="合成の保管ログ"))
            db.session.add(OwnedCharacter(id="C", user_id="owner", name="Synthetic character", data={"hp": 5}))
            db.session.commit()
            db.session.remove()
            db.engine.dispose()
        yield {"tools": tools, "uri": uri, "state": state}
    finally:
        if (data / "postmaster.pid").exists():
            _command([pg_ctl, "-D", data, "-m", "fast", "-w", "stop"])


def test_dump_and_restore_preserve_application_data(postgres, tmp_path):
    import psycopg2

    tools = postgres["tools"]
    folder = backup.create_backup(postgres["uri"]("backup_source"), tools, tmp_path)
    manifest = backup.verify_backup(folder, tools)
    assert manifest["public_table_count"] == 10
    target = backup.parse_connection_url(postgres["uri"]("backup_restored"))
    assert target.host == "127.0.0.1"
    with backup.connection_environment(target) as env:
        env.pop("PGOPTIONS")  # Only this disposable destination is writable.
        backup._run([
            tools.pg_restore, "--exit-on-error", "--no-owner", "--no-acl",
            "--dbname", "backup_restored", folder / "database.dump",
        ], env=env)
    for name in ("backup_source", "backup_restored"):
        with psycopg2.connect(postgres["uri"](name)) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT data, owner_id FROM rooms WHERE name='synthetic-room'")
                state, owner = cursor.fetchone()
                assert state == postgres["state"]
                assert owner == "owner"
                cursor.execute("SELECT role FROM room_members WHERE user_id='owner'")
                assert cursor.fetchone()[0] == "owner"
                cursor.execute("SELECT message FROM room_log_archives")
                assert cursor.fetchone()[0] == "合成の保管ログ"
                cursor.execute("SELECT data FROM owned_characters WHERE id='C'")
                assert cursor.fetchone()[0] == {"hp": 5}
                cursor.execute("SELECT password_hash FROM users WHERE id='owner'")
                assert cursor.fetchone()[0] == "not-real"


def test_truncated_data_is_rejected_even_when_listing_and_hash_pass(postgres, tmp_path):
    tools = postgres["tools"]
    folder = backup.create_backup(postgres["uri"]("backup_source"), tools, tmp_path)
    dump = folder / "database.dump"
    raw = dump.read_bytes()
    dump.write_bytes(raw[:len(raw) // 2])
    metadata = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    metadata.update(size_bytes=dump.stat().st_size, sha256=hashlib.sha256(dump.read_bytes()).hexdigest())
    (folder / "manifest.json").write_text(json.dumps(metadata), encoding="utf-8")
    # TOC-only checks can succeed even though table data is unreadable.
    backup._run([tools.pg_restore, "--list", dump], capture=True)
    with pytest.raises(backup.BackupError):
        backup.verify_backup(folder, tools)


def test_bad_password_is_not_published_or_echoed(postgres, tmp_path):
    wrong = "wrong-synthetic-password"
    with pytest.raises(backup.BackupError) as caught:
        backup.create_backup(postgres["uri"]("backup_source", wrong), postgres["tools"], tmp_path)
    assert wrong not in str(caught.value)
    assert list(tmp_path.iterdir()) == []
