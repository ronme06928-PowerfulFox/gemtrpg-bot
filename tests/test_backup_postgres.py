"""Backup boundaries: secrets, incomplete output, offline checks and originals."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import sys
from types import SimpleNamespace

import pytest

from scripts import backup_postgres as backup


URL = "postgresql://owner:p%3Aa%5Css@ep-example.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"


@pytest.fixture
def backup_root():
    # Directory rename is restricted in Windows AppContainer's default Temp.
    base = (backup.ROOT / "_local" / "backup_unit_checks").resolve()
    assert base.is_relative_to(backup.ROOT)
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="check-", dir=base) as name:
        path = Path(name).resolve()
        assert path.is_relative_to(base)
        yield path


@pytest.fixture
def tools():
    return backup.Toolchain(Path("pg_dump"), Path("pg_restore"), "18.6", "18.6")


@pytest.fixture
def runner(monkeypatch):
    calls = []

    def run(args, **kwargs):
        args = [str(value) for value in args]
        calls.append((args, kwargs))
        assert URL not in repr(args)
        assert "PGPASSWORD" not in kwargs["env"]
        assert "GEMDICE_BACKUP_DATABASE_URL" not in kwargs["env"]
        assert "UNRELATED_API_KEY" not in kwargs["env"]
        if args[0] == "pg_dump":
            assert "--no-password" in args
            assert "--dbname" not in args and "-d" not in args
            assert kwargs["env"]["PGOPTIONS"] == "-c default_transaction_read_only=on"
            password_path = Path(kwargs["env"]["PGPASSFILE"])
            assert password_path.read_text(encoding="utf-8").endswith("owner:p\\:a\\\\ss\n")
            Path(args[args.index("--file") + 1]).write_bytes(b"PGDMP-synthetic-archive")
        else:
            assert "PGHOST" not in kwargs["env"] and "PGPASSFILE" not in kwargs["env"]
            assert "--dbname" not in args and "-d" not in args
            if "--list" in args:
                listing = "\n".join(f"1; 1259 100 TABLE public {name} owner" for name in backup.REQUIRED_TABLES)
                return SimpleNamespace(returncode=0, stdout=listing, stderr="")
            assert "--file=-" in args
            assert kwargs["stdout"] == subprocess.DEVNULL
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(backup.subprocess, "run", run)
    monkeypatch.setenv("PGSERVICE", "must-not-inherit")
    monkeypatch.setenv("PGPASSWORD", "must-not-inherit")
    monkeypatch.setenv("GEMDICE_BACKUP_DATABASE_URL", URL)
    monkeypatch.setenv("UNRELATED_API_KEY", "must-not-forward")
    return calls


def test_success_is_verified_before_publish_and_contains_no_connection_secret(backup_root, tools, runner):
    folder = backup.create_backup(URL, tools, backup_root)
    assert folder.is_dir() and not folder.name.startswith(".")
    assert set(p.name for p in folder.iterdir()) == {"database.dump", "manifest.json"}
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["format"] == "postgresql-custom"
    assert manifest["size_bytes"] == len(b"PGDMP-synthetic-archive")
    assert manifest["created_at"].endswith("+09:00")
    assert manifest["verification"] == "archive-readable-not-restored"
    assert URL not in json.dumps(manifest) and "p:a\\ss" not in json.dumps(manifest)
    assert not Path(runner[0][1]["env"]["PGPASSFILE"]).exists()
    assert len(runner) == 3
    assert backup.verify_backup(folder, tools) == manifest


@pytest.mark.parametrize("failure", ["dump", "list", "read", "timeout", "cancel"])
def test_failure_removes_only_its_own_incomplete_output(backup_root, monkeypatch, tools, runner, failure):
    original = backup_root / "previous"
    original.mkdir()
    (original / "database.dump").write_bytes(b"keep-original")
    run = backup.subprocess.run
    credentials = []

    def fail(args, **kwargs):
        if args[0] == "pg_dump":
            credentials.append(Path(kwargs["env"]["PGPASSFILE"]))
        step = "dump" if args[0] == "pg_dump" else "list" if "--list" in args else "read"
        if failure in {step, "timeout", "cancel"}:
            if failure == "timeout":
                raise subprocess.TimeoutExpired(args, 1, stderr=URL)
            if failure == "cancel":
                raise KeyboardInterrupt()
            return SimpleNamespace(returncode=1, stdout="", stderr=URL)
        return run(args, **kwargs)

    monkeypatch.setattr(backup.subprocess, "run", fail)
    expected = KeyboardInterrupt if failure == "cancel" else backup.BackupError
    with pytest.raises(expected) as caught:
        backup.create_backup(URL, tools, backup_root)
    assert URL not in str(caught.value)
    assert list(backup_root.iterdir()) == [original]
    assert (original / "database.dump").read_bytes() == b"keep-original"
    assert credentials and all(not p.exists() for p in credentials)


def test_incomplete_app_database_is_not_published(backup_root, monkeypatch, tools, runner):
    run = backup.subprocess.run

    def incomplete(args, **kwargs):
        result = run(args, **kwargs)
        if "--list" in args:
            result.stdout = "1; 1259 100 TABLE public unrelated owner"
        return result

    monkeypatch.setattr(backup.subprocess, "run", incomplete)
    with pytest.raises(backup.BackupError):
        backup.create_backup(URL, tools, backup_root)
    assert list(backup_root.iterdir()) == []


def test_modified_backup_is_rejected_before_running_restore(backup_root, tools, runner):
    folder = backup.create_backup(URL, tools, backup_root)
    (folder / "database.dump").write_bytes(b"modified")
    calls_before = len(runner)
    with pytest.raises(backup.BackupError):
        backup.verify_backup(folder, tools)
    assert len(runner) == calls_before


def test_incomplete_marker_prevents_accepting_an_otherwise_valid_archive(backup_root, tools, runner):
    folder = backup.create_backup(URL, tools, backup_root)
    (folder / ".incomplete").touch()
    calls_before = len(runner)
    with pytest.raises(backup.BackupError):
        backup.verify_backup(folder, tools)
    assert len(runner) == calls_before


@pytest.mark.parametrize("url", [
    "sqlite:///local.db",
    "postgresql://owner:secret@ep-test-pooler.aws.neon.tech/neondb",
    "postgresql://owner:secret@remote.example/db?sslmode=disable",
    "postgresql://owner:secret@remote.example/db?sslmode=prefer",
    "postgresql://owner:secret@remote.example/db?options=-c%20default_transaction_read_only=off",
    "postgresql://owner:secret@remote.example:99999/db",
    "postgresql://owner:secret@remote.example:0/db",
    "postgresql://owner:secret%0Ainjected@remote.example/db",
    "postgresql://owner@remote.example/db",
])
def test_invalid_or_unsafe_connection_is_rejected_without_echo(url):
    with pytest.raises(backup.BackupError) as caught:
        backup.parse_connection_url(url)
    assert url not in str(caught.value)
    assert "secret" not in str(caught.value)


def test_loopback_only_can_use_plaintext_for_disposable_database():
    connection = backup.parse_connection_url("postgresql://test:fake@127.0.0.1/test?sslmode=disable")
    assert connection.sslmode == "disable"


def test_credential_cleanup_failure_reports_only_the_temporary_path(monkeypatch):
    original_unlink = Path.unlink
    password_path = None
    try:
        with pytest.raises(backup.BackupError) as caught:
            with backup.connection_environment(backup.parse_connection_url(URL)) as env:
                password_path = Path(env["PGPASSFILE"])

                def locked(path, **kwargs):
                    if path == password_path:
                        raise PermissionError(URL)
                    return original_unlink(path, **kwargs)

                monkeypatch.setattr(Path, "unlink", locked)
        assert str(password_path) in str(caught.value)
        assert URL not in str(caught.value)
    finally:
        if password_path is not None:
            original_unlink(password_path, missing_ok=True)


def test_cli_errors_never_echo_url(backup_root, monkeypatch, capsys, tools, runner):
    monkeypatch.setattr(backup, "DEFAULT_BACKUP_ROOT", backup_root)
    monkeypatch.setattr(backup, "find_tools", lambda _path=None: tools)
    monkeypatch.setenv("GEMDICE_BACKUP_DATABASE_URL", "postgresql://owner:secret@remote/db?sslmode=disable")
    assert backup.main(["backup"]) == 1
    captured = capsys.readouterr()
    assert "secret" not in captured.out + captured.err


def test_cli_rejects_url_argument_without_repeating_it(capsys):
    with pytest.raises(SystemExit):
        backup.main(["backup", URL])
    captured = capsys.readouterr()
    assert URL not in captured.out + captured.err


def test_missing_tools_do_not_prompt_for_credentials(monkeypatch, capsys):
    def missing(_path=None):
        raise backup.BackupError("PostgreSQLクライアントが必要です")

    monkeypatch.setattr(backup, "find_tools", missing)
    monkeypatch.setattr(backup.getpass, "getpass", lambda _prompt: pytest.fail("must check tools first"))
    assert backup.main(["backup"]) == 1
    assert "PostgreSQL" in capsys.readouterr().err


def test_tool_import_never_loads_application_or_dotenv():
    code = (
        "import builtins, runpy\n"
        "original = builtins.__import__\n"
        "def guarded(name, *args, **kwargs):\n"
        "    assert name.split('.')[0] not in {'app', 'extensions', 'dotenv'}, name\n"
        "    return original(name, *args, **kwargs)\n"
        "builtins.__import__ = guarded\n"
        f"runpy.run_path({str(backup.ROOT / 'scripts/backup_postgres.py')!r})\n"
    )
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
