"""Restore check helpers: Neon-only column options are dropped, the newest finished backup is chosen."""

from datetime import timedelta
import json

import pytest

from scripts import backup_postgres as backup
from scripts import restore_postgres_check as restore
from tests.test_backup_postgres import backup_root  # noqa: F401 (fixture)
from tests.test_backup_postgres_auto import NOW, _write


def test_neon_column_options_are_dropped_and_nothing_else(tmp_path):
    source, target = tmp_path / "in.sql", tmp_path / "out.sql"
    lines = [
        "CREATE TABLE public.rooms (id integer);\n",
        "ALTER TABLE ONLY public.rooms ALTER COLUMN id SET (pg_attver=269515664);\n",
        "COPY public.rooms (id) FROM stdin;\n",
        "1\tSET (pg_attver=1);\n",
        "\\.\n",
        "ALTER TABLE ONLY public.rooms ALTER COLUMN name SET (n_distinct=5);\n",
    ]
    source.write_text("".join(lines), encoding="utf-8", newline="")
    assert restore.strip_neon_options(source, target) == 1
    assert target.read_text(encoding="utf-8") == "".join(lines[:1] + lines[2:])


def test_latest_backup_skips_incomplete(backup_root):
    _write(backup_root, "older", NOW - timedelta(days=2), "manual")
    _write(backup_root, "newest-but-unfinished", NOW, "auto", extra=".incomplete")
    assert restore.latest_backup(backup_root).name == "older"


def test_no_backup_is_an_error(backup_root):
    with pytest.raises(backup.BackupError):
        restore.latest_backup(backup_root)


def test_restore_never_targets_anything_but_loopback():
    source = (backup.ROOT / "scripts" / "restore_postgres_check.py").read_text(encoding="utf-8")
    assert "neon.tech" not in source and "DATABASE_URL\", None" in source
    assert source.count("127.0.0.1") >= 4 and "0.0.0.0" not in source
