"""Automatic backups: stored URL, retention, failure notice and status (postgres_backup_runbook)."""

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from scripts import backup_postgres as backup
from tests.test_backup_postgres import URL, backup_root, runner, tools  # noqa: F401 (fixtures)


NOW = datetime(2026, 11, 17, 12, 0, tzinfo=backup.JST)


def _write(root, name, created, trigger, extra=None):
    folder = root / name
    folder.mkdir()
    (folder / "database.dump").write_bytes(b"PGDMP")
    manifest = {"schema_version": 1, "created_at": created.isoformat(), "format": "postgresql-custom"}
    if trigger:
        manifest["trigger"] = trigger
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if extra:
        (folder / extra).write_text("x", encoding="utf-8")
    return folder


def test_manifest_records_the_trigger(backup_root, tools, runner):
    manual = backup.create_backup(URL, tools, backup_root)
    auto = backup.create_backup(URL, tools, backup_root, trigger="auto")
    read = lambda folder: json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert read(manual)["trigger"] == "manual"
    assert read(auto)["trigger"] == "auto"


def test_retention_keeps_seven_days_then_twelve_weeks_and_never_manual():
    entries = []
    for day in range(120):
        for hour in (12, 20):
            entries.append((f"auto-{day}-{hour}", NOW - timedelta(days=day) + timedelta(hours=hour - 12), "auto"))
    entries.append(("manual-old", NOW - timedelta(days=300), "manual"))
    entries.append(("legacy", NOW - timedelta(days=200), None))
    expired = set(backup.expired_backups(entries, NOW))
    kept = {name for name, *_ in entries} - expired
    daily = {f"auto-{day}-20" for day in range(7)}
    assert daily <= kept
    assert not {f"auto-{day}-12" for day in range(7)} & kept
    assert {"manual-old", "legacy"} <= kept
    weekly = kept - daily - {"manual-old", "legacy"}
    ages = [int(name.split("-")[1]) for name in weekly]
    weeks = {(NOW - timedelta(days=age)).isocalendar()[:2] for age in ages}
    assert len(weeks) == len(weekly) and len(weekly) in (12, 13)
    assert max(ages) <= 7 + 7 * 12 and 7 + 7 * 12 - max(ages) < 7


def test_prune_deletes_only_plain_complete_auto_backups(backup_root):
    old = NOW - timedelta(days=60)
    expired = [_write(backup_root, f"a{i}", old + timedelta(hours=i), "auto") for i in range(3)]
    odd = _write(backup_root, "odd", old - timedelta(days=1), "auto", extra="notes.txt")
    unfinished = _write(backup_root, "unfinished", old - timedelta(days=2), "auto", extra=".incomplete")
    manual = _write(backup_root, "manual", old - timedelta(days=3), "manual")
    backup.prune_backups(backup_root, NOW)
    remaining = {p.name for p in backup_root.iterdir()}
    assert remaining == {"a2", "odd", "unfinished", "manual"}
    assert all(not p.exists() for p in expired[:2])
    assert (odd / "notes.txt").exists() and (unfinished / ".incomplete").exists() and manual.exists()


@pytest.fixture
def auto_env(backup_root, monkeypatch, tools, runner):
    notices = []
    monkeypatch.setattr(backup, "DEFAULT_BACKUP_ROOT", backup_root)
    monkeypatch.setattr(backup, "find_tools", lambda _path=None: tools)
    monkeypatch.setattr(backup, "notify", notices.append)
    return notices


def test_auto_backup_logs_success_without_secrets(backup_root, auto_env, capsys):
    assert backup.main(["backup", "--auto"]) == 0
    folders = [p for p in backup_root.iterdir() if p.is_dir()]
    assert len(folders) == 1
    assert json.loads((folders[0] / "manifest.json").read_text(encoding="utf-8"))["trigger"] == "auto"
    log = (backup_root / "auto.log").read_text(encoding="utf-8")
    assert "成功" in log and URL not in log and "p:a" not in log
    assert auto_env == []


def test_auto_backup_reads_the_stored_url_when_no_variable(backup_root, auto_env, monkeypatch):
    monkeypatch.delenv("GEMDICE_BACKUP_DATABASE_URL")
    monkeypatch.setattr(backup, "read_stored_url", lambda: URL)
    assert backup.main(["backup", "--auto"]) == 0


def test_auto_backup_never_prompts(backup_root, auto_env, monkeypatch):
    monkeypatch.delenv("GEMDICE_BACKUP_DATABASE_URL")
    monkeypatch.setattr(backup, "read_stored_url", lambda: None)
    monkeypatch.setattr(backup.getpass, "getpass", lambda _prompt: pytest.fail("auto must not prompt"))
    assert backup.main(["backup", "--auto"]) == 1
    assert len(auto_env) == 1 and "store-credential" in auto_env[0]
    assert "失敗" in (backup_root / "auto.log").read_text(encoding="utf-8")


def test_auto_failure_notifies_and_logs_without_secrets(backup_root, auto_env, monkeypatch):
    secret = "postgresql://owner:topsecret@remote.example/db?sslmode=disable"
    monkeypatch.setenv("GEMDICE_BACKUP_DATABASE_URL", secret)
    assert backup.main(["backup", "--auto"]) == 1
    log = (backup_root / "auto.log").read_text(encoding="utf-8")
    assert len(auto_env) == 1
    for text in (log, auto_env[0]):
        assert "topsecret" not in text and secret not in text
    assert [p for p in backup_root.iterdir() if p.is_dir()] == []


def test_auto_success_prunes_old_auto_backups(backup_root, auto_env):
    old = _write(backup_root, "old", datetime.now(backup.JST) - timedelta(days=400), "auto")
    assert backup.main(["backup", "--auto"]) == 0
    assert not old.exists()


def test_status_reports_age_and_warns_after_two_days(backup_root):
    assert backup.backup_status(backup_root, NOW)["warning"]
    _write(backup_root, "recent", NOW - timedelta(hours=30), "auto")
    status = backup.backup_status(backup_root, NOW)
    assert not status["warning"] and status["latest"]["trigger"] == "auto"
    stale = backup_root / "recent"
    (stale / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "created_at": (NOW - timedelta(hours=49)).isoformat(), "trigger": "auto"}),
        encoding="utf-8")
    assert backup.backup_status(backup_root, NOW)["warning"]


def test_status_ignores_incomplete_folders(backup_root):
    _write(backup_root, "half", NOW - timedelta(hours=1), "auto", extra=".incomplete")
    assert backup.backup_status(backup_root, NOW)["latest"] is None


def test_status_command_exit_code(backup_root, monkeypatch, capsys):
    monkeypatch.setattr(backup, "DEFAULT_BACKUP_ROOT", backup_root)
    monkeypatch.setattr(backup, "find_tools", lambda _path=None: pytest.fail("status needs no tools"))
    assert backup.main(["status"]) == 1
    _write(backup_root, "now", datetime.now(backup.JST), "manual")
    assert backup.main(["status"]) == 0
    assert "manual" in capsys.readouterr().out


def test_store_credential_validates_without_echo(monkeypatch, capsys):
    stored = []
    monkeypatch.setattr(backup, "find_tools", lambda _path=None: pytest.fail("store needs no tools"))
    monkeypatch.setattr(backup, "write_stored_url", stored.append)
    monkeypatch.setattr(backup.sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.delenv("GEMDICE_BACKUP_DATABASE_URL", raising=False)
    monkeypatch.setattr(backup.getpass, "getpass", lambda _prompt: "postgresql://owner:secret@ep-x-pooler.neon.tech/db")
    assert backup.main(["store-credential"]) == 1
    assert stored == []
    monkeypatch.setattr(backup.getpass, "getpass", lambda _prompt: URL)
    assert backup.main(["store-credential"]) == 0
    assert stored == [URL]
    captured = capsys.readouterr()
    assert "secret" not in captured.out + captured.err and URL not in captured.out + captured.err


def test_notice_passes_the_message_outside_the_command_line(monkeypatch):
    calls = []
    monkeypatch.setattr(backup.subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr(backup.os, "name", "nt")
    backup.notify("控えを取れませんでした")
    args, kwargs = calls[0]
    assert "控えを取れませんでした" not in " ".join(map(str, args))
    assert kwargs["env"]["GEMDICE_NOTICE"] == "控えを取れませんでした"


@pytest.mark.skipif(os.name != "nt", reason="Windows Credential Manager only")
def test_credential_manager_round_trip(monkeypatch):
    monkeypatch.setattr(backup, "CREDENTIAL_TARGET", f"GemDiceBot/test-{uuid4().hex}")
    try:
        assert backup.read_stored_url() is None
        backup.write_stored_url(URL)
        assert backup.read_stored_url() == URL
    finally:
        backup.delete_stored_url()
    assert backup.read_stored_url() is None


def test_task_registration_script():
    path = backup.ROOT / "scripts" / "register_backup_task.ps1"
    raw = path.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    text = raw.decode("utf-8")
    for needle in ("-StartWhenAvailable", "-Daily", "12:00", "backup --auto", "GemDiceBot DB backup", "pythonw.exe"):
        assert needle in text
    assert "postgres://" not in text and "postgresql://" not in text
