"""Create private PostgreSQL archives; never restore into a database.

Manual and scheduled backups share one path. See manuals/operations/postgres_backup_runbook.md.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import parse_qsl, unquote, urlsplit
from uuid import uuid4
import warnings


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP_ROOT = ROOT / "_local" / "backups" / "postgres"
DEFAULT_PG_BIN = ROOT / "_local" / "tools" / "postgresql" / "bin"
REQUIRED_TABLES = {"users", "rooms", "room_members", "owned_characters", "room_log_archives"}
JST = timezone(timedelta(hours=9))
CREDENTIAL_TARGET = "GemDiceBot/backup-database-url"
AUTO_LOG = "auto.log"
KEEP_DAILY = 7
KEEP_WEEKLY = 12
STALE_AFTER = timedelta(hours=48)


class BackupError(Exception):
    """An operator-readable error containing no connection credentials."""


@dataclass(frozen=True)
class Toolchain:
    pg_dump: Path
    pg_restore: Path
    dump_version: str
    restore_version: str


@dataclass(frozen=True, repr=False)
class Connection:
    host: str
    port: str
    database: str
    user: str
    password: str
    sslmode: str
    channel_binding: str


def parse_connection_url(value: str) -> Connection:
    try:
        url = urlsplit(value.strip())
        if url.scheme not in {"postgres", "postgresql"}:
            raise ValueError()
        host = url.hostname or ""
        port_value = url.port if url.port is not None else 5432
        if not 1 <= port_value <= 65535:
            raise ValueError()
        port = str(port_value)
        user, password = unquote(url.username or ""), unquote(url.password or "")
        database = unquote(url.path.removeprefix("/"))
        options = dict(parse_qsl(url.query, keep_blank_values=True))
        if not host or not user or not password or not re.fullmatch(r"[\w.-]+", database):
            raise ValueError()
        if url.fragment or set(options) - {"sslmode", "channel_binding"}:
            raise ValueError()
        if any(any(char in field for char in "\x00\r\n") for field in (host, user, password, database)):
            raise ValueError()
        if "," in host or "-pooler." in host.lower():
            raise BackupError("NeonのConnection poolingをオフにした直接接続URLを使用してください。")
        sslmode = options.get("sslmode", "require")
        local_test = host.lower() in {"localhost", "127.0.0.1", "::1"} and sslmode == "disable"
        if sslmode not in {"require", "verify-ca", "verify-full"} and not local_test:
            raise BackupError("外部DBへの接続にはsslmode=require以上が必要です。")
        binding = options.get("channel_binding", "prefer")
        if binding not in {"disable", "prefer", "require"}:
            raise ValueError()
        return Connection(host, port, database, user, password, sslmode, binding)
    except (ValueError, TypeError):
        raise BackupError("接続URLの形式を確認してください。URL全体をログやチャットへ貼り付けないでください。") from None


def _clean_environment():
    allowed = {
        "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP",
        "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH",
    }
    env = {
        key: value for key, value in os.environ.items()
        if key.upper() in allowed
    }
    env.update(LANG="C", LC_ALL="C")
    return env


@contextmanager
def connection_environment(connection: Connection):
    path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", prefix="gemdice-pgpass-", delete=False
        ) as handle:
            path = Path(handle.name)
            fields = [connection.host, connection.port, connection.database, connection.user, connection.password]
            handle.write(":".join(field.replace("\\", "\\\\").replace(":", "\\:") for field in fields) + "\n")
        env = _clean_environment()
        env.update(
            PGHOST=connection.host, PGPORT=connection.port, PGDATABASE=connection.database,
            PGUSER=connection.user, PGPASSFILE=str(path), PGSSLMODE=connection.sslmode,
            PGCHANNELBINDING=connection.channel_binding, PGCONNECT_TIMEOUT="15",
            PGAPPNAME="GemDiceBot manual backup", PGOPTIONS="-c default_transaction_read_only=on",
        )
        yield env
    finally:
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                raise BackupError(f"一時認証ファイルを削除できませんでした。次のファイルを手動で削除してください: {path}") from None


def _run(args, *, env=None, capture=False):
    try:
        result = subprocess.run(
            [str(arg) for arg in args], env=env if env is not None else _clean_environment(),
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", timeout=600,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired:
        raise BackupError("PostgreSQLツールが時間内に完了しませんでした。成功済みのバックアップは維持します。") from None
    except OSError:
        raise BackupError("PostgreSQLツールを起動できません。配置と実行権限を確認してください。") from None
    if result.returncode:
        # Native errors can contain a connection URI or password. Never echo them.
        raise BackupError("PostgreSQLツールが失敗しました。認証・接続先・クライアントの版を確認してください。")
    return result


def find_tools(pg_bin: Path | None = None) -> Toolchain:
    suffix = ".exe" if os.name == "nt" else ""
    paths = []
    versions = []
    for name in ("pg_dump", "pg_restore"):
        candidate = (pg_bin or DEFAULT_PG_BIN) / (name + suffix)
        if not candidate.is_file() and pg_bin is None:
            found = shutil.which(name)
            candidate = Path(found) if found else candidate
        if not candidate.is_file():
            raise BackupError("pg_dumpとpg_restoreが必要です。_local/tools/postgresql/bin/ または --pg-bin を確認してください。")
        output = _run([candidate, "--version"], capture=True).stdout
        match = re.search(r"PostgreSQL\) (\d+(?:\.\d+)*)", output)
        if not match:
            raise BackupError("PostgreSQLツールの版を確認できませんでした。")
        paths.append(candidate)
        versions.append(match[1])
    if versions[0].split(".")[0] != versions[1].split(".")[0]:
        raise BackupError("pg_dumpとpg_restoreのメジャー版をそろえてください。")
    return Toolchain(*paths, *versions)


def _digest(path: Path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def _verify_archive(path: Path, tools: Toolchain):
    listing = _run([tools.pg_restore, "--list", path], capture=True).stdout
    tables = set(re.findall(r"^\d+;\s+\d+\s+\d+\s+TABLE\s+public\s+(\S+)", listing, re.MULTILINE))
    if REQUIRED_TABLES - tables:
        raise BackupError("GemDiceBotの主要テーブルが見つかりません。バックアップ対象DBを確認してください。")
    # No --dbname: generate SQL only and discard stdout, never execute a restore.
    _run([tools.pg_restore, "--no-owner", "--no-acl", "--file=-", path])
    return tables


def _remove_incomplete(folder: Path):
    # Delete only this invocation's files; never recurse into backups.
    for name in ("manifest.json", "database.dump", ".incomplete"):
        (folder / name).unlink(missing_ok=True)
    folder.rmdir()


def create_backup(url: str, tools: Toolchain, output_root: Path, trigger: str = "manual") -> Path:
    connection = parse_connection_url(url)
    output_root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(JST)
    stage = output_root / (now.strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:12])
    stage.mkdir(mode=0o700)
    published = False
    try:
        (stage / ".incomplete").touch(exist_ok=False)
        dump = stage / "database.dump"
        with connection_environment(connection) as env:
            _run([
                tools.pg_dump, "--format=custom", "--no-owner", "--no-acl",
                "--no-password", "--lock-wait-timeout=10s", "--file", dump,
            ], env=env)
        if not dump.is_file() or not dump.stat().st_size:
            raise BackupError("バックアップファイルが作成されませんでした。")
        tables = _verify_archive(dump, tools)
        manifest = {
            "schema_version": 1, "created_at": now.isoformat(), "format": "postgresql-custom",
            "size_bytes": dump.stat().st_size, "sha256": _digest(dump),
            "pg_dump_version": tools.dump_version, "pg_restore_version": tools.restore_version,
            "checked_tables": sorted(REQUIRED_TABLES), "public_table_count": len(tables),
            "verification": "archive-readable-not-restored", "trigger": trigger,
        }
        with (stage / "manifest.json").open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        (stage / ".incomplete").unlink()
        published = True
        return stage
    finally:
        if not published:
            _remove_incomplete(stage)


def verify_backup(folder: Path, tools: Toolchain):
    if (folder / ".incomplete").exists():
        raise BackupError("未完了のバックアップです。成功済みの原本を使用してください。")
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        dump = folder / "database.dump"
        if (
            manifest["schema_version"] != 1 or manifest["format"] != "postgresql-custom"
            or dump.stat().st_size != manifest["size_bytes"] or _digest(dump) != manifest["sha256"]
        ):
            raise ValueError()
        if int(tools.restore_version.split(".")[0]) < int(manifest["pg_dump_version"].split(".")[0]):
            raise BackupError("作成時より古いpg_restoreでは検査できません。クライアントを更新してください。")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise BackupError("バックアップの記録・サイズ・SHA-256が一致しません。原本を保持して確認してください。") from None
    _verify_archive(dump, tools)
    return manifest


def _completed_backups(root: Path):
    """Yield (folder, created_at, trigger) for finished backups; skip anything unreadable."""
    if not root.is_dir():
        return
    for folder in root.iterdir():
        if not folder.is_dir() or (folder / ".incomplete").exists():
            continue
        try:
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            created = datetime.fromisoformat(manifest["created_at"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        yield folder, created, manifest.get("trigger", "manual")


def expired_backups(entries, now):
    """Keys of automatic backups past retention: newest per day for 7 days, then newest per ISO week for 12 more weeks."""
    autos = sorted(((created, key) for key, created, trigger in entries if trigger == "auto"), reverse=True)
    recent_days = {(now - timedelta(days=offset)).astimezone(JST).date() for offset in range(KEEP_DAILY)}
    oldest = now - timedelta(days=KEEP_DAILY, weeks=KEEP_WEEKLY)
    kept_days, kept_weeks, expired = set(), set(), []
    for created, key in autos:
        day = created.astimezone(JST).date()
        if day in recent_days:
            if day in kept_days:
                expired.append(key)
            kept_days.add(day)
            continue
        week = day.isocalendar()[:2]
        if week in kept_weeks or created < oldest:
            expired.append(key)
        else:
            kept_weeks.add(week)
    return expired


def prune_backups(root: Path, now):
    """Delete expired automatic backups whose folder holds only the dump and manifest."""
    for folder in expired_backups(list(_completed_backups(root)), now):
        if {p.name for p in folder.iterdir()} != {"database.dump", "manifest.json"}:
            continue
        (folder / "database.dump").unlink()
        (folder / "manifest.json").unlink()
        folder.rmdir()


def backup_status(root: Path, now):
    latest = max(_completed_backups(root), key=lambda entry: entry[1], default=None)
    log = root / AUTO_LOG
    lines = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
    info = None if latest is None else {
        "folder": latest[0].name, "created_at": latest[1].isoformat(), "trigger": latest[2],
    }
    return {
        "latest": info, "warning": latest is None or now - latest[1] > STALE_AFTER,
        "last_auto_log": lines[-1] if lines else None,
    }


def _log_auto(root: Path, message: str):
    root.mkdir(parents=True, exist_ok=True)
    with (root / AUTO_LOG).open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{datetime.now(JST).isoformat(timespec='seconds')} {message}\n")


NOTICE_SCRIPT = (
    "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
    "$x = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
    "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
    "$t = $x.GetElementsByTagName('text');"
    "$t.Item(0).AppendChild($x.CreateTextNode('GemDiceBot DB backup')) > $null;"
    "$t.Item(1).AppendChild($x.CreateTextNode($env:GEMDICE_NOTICE)) > $null;"
    "$id = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe';"
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($id).Show("
    "[Windows.UI.Notifications.ToastNotification]::new($x))"
)


def notify(message: str):
    """Show a Windows notification. The message travels in the environment, not the command line."""
    if os.name != "nt":
        return
    env = _clean_environment()
    env["GEMDICE_NOTICE"] = message
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", NOTICE_SCRIPT],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        pass


CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168


def _credential_api():
    import ctypes
    from ctypes import wintypes

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR),
        ]

    api = ctypes.WinDLL("advapi32", use_last_error=True)
    api.CredReadW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(CREDENTIAL)),
    ]
    api.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIAL), wintypes.DWORD]
    api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    api.CredFree.argtypes = [ctypes.c_void_p]
    return ctypes, api, CREDENTIAL


def read_stored_url():
    """The URL saved by store-credential, or None."""
    if os.name != "nt":
        return None
    ctypes, api, CREDENTIAL = _credential_api()
    pointer = ctypes.POINTER(CREDENTIAL)()
    if not api.CredReadW(CREDENTIAL_TARGET, CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
        if ctypes.get_last_error() == ERROR_NOT_FOUND:
            return None
        raise BackupError("資格情報マネージャーを読めませんでした。")
    try:
        cred = pointer.contents
        return ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize).decode("utf-16-le")
    finally:
        api.CredFree(pointer)


def write_stored_url(url: str):
    if os.name != "nt":
        raise BackupError("資格情報マネージャーは Windows でだけ使えます。")
    ctypes, api, CREDENTIAL = _credential_api()
    blob = url.encode("utf-16-le")
    buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    cred = CREDENTIAL(
        Type=CRED_TYPE_GENERIC, TargetName=CREDENTIAL_TARGET, CredentialBlobSize=len(blob),
        CredentialBlob=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
        Persist=CRED_PERSIST_LOCAL_MACHINE, UserName="gemdice-backup",
    )
    if not api.CredWriteW(ctypes.byref(cred), 0):
        raise BackupError("資格情報マネージャーへ保存できませんでした。")


def delete_stored_url():
    if os.name != "nt":
        return
    ctypes, api, _ = _credential_api()
    if not api.CredDeleteW(CREDENTIAL_TARGET, CRED_TYPE_GENERIC, 0) and ctypes.get_last_error() != ERROR_NOT_FOUND:
        raise BackupError("資格情報マネージャーから削除できませんでした。")


def run_auto_backup(tools: Toolchain, root: Path):
    try:
        url = os.environ.get("GEMDICE_BACKUP_DATABASE_URL") or read_stored_url()
        if not url:
            raise BackupError("接続URLが登録されていません。store-credential で登録してください。")
        folder = create_backup(url, tools, root, trigger="auto")
        prune_backups(root, datetime.now(JST))
    except (BackupError, OSError) as error:
        message = str(error) if isinstance(error, BackupError) else "ローカルファイルの操作に失敗しました。"
        _log_auto(root, f"失敗 {message}")
        notify(f"自動の控えを取れませんでした。{message}")
        raise
    _log_auto(root, f"成功 {folder.name}")
    return folder


def _store_credential():
    url = _read_connection_url(prompt_only=True)
    parse_connection_url(url)
    write_stored_url(url)
    print(f"資格情報マネージャーに保存しました（{CREDENTIAL_TARGET}）。接続はまだ確かめていません。")


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "引数が不正です。接続URLは引数に含めず、非表示入力を使用してください。\n")


def _read_connection_url(prompt_only=False):
    value = None if prompt_only else os.environ.get("GEMDICE_BACKUP_DATABASE_URL")
    if value:
        return value
    if not sys.stdin.isatty():
        raise BackupError("対話端末で実行してください。自動実行では専用環境変数を使用できます。")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            return getpass.getpass("Neonの直接接続URL（非表示。チャットへ送らない）: ")
        except (getpass.GetPassWarning, EOFError):
            raise BackupError("非表示入力を利用できません。対話端末で実行してください。") from None


def main(argv=None):
    parser = SafeArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin", type=Path, help="PostgreSQLのbinフォルダ")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="クライアント確認のみ。DBへ接続しない")
    commands.add_parser("backup", help="DBをPCへ保存。元DBへ書き込まない").add_argument(
        "--auto", action="store_true", help="定期実行用。登録したURLを使い、古い自動の控えを消し、失敗を通知する")
    commands.add_parser("verify", help="保管済みファイルを再検査。DBへ接続しない").add_argument("folder", type=Path)
    commands.add_parser("status", help="最後に取れた控えの日時。DBへ接続しない")
    commands.add_parser("store-credential", help="接続URLを資格情報マネージャーへ保存。DBへ接続しない")
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            status = backup_status(DEFAULT_BACKUP_ROOT, datetime.now(JST))
            print(json.dumps(status, ensure_ascii=False, indent=2))
            if status["warning"]:
                print("注意：2日より新しい控えがありません。", file=sys.stderr)
            return 1 if status["warning"] else 0
        if args.command == "store-credential":
            _store_credential()
            return 0
        tools = find_tools(args.pg_bin)
        if args.command == "backup" and args.auto:
            folder = run_auto_backup(tools, DEFAULT_BACKUP_ROOT)
            print(f"自動の控えを作成・検査しました: {folder}")
        elif args.command == "doctor":
            print(json.dumps({"ready": True, "pg_dump": tools.dump_version, "pg_restore": tools.restore_version}))
        elif args.command == "backup":
            url = _read_connection_url()
            print("バックアップを取得・検査しています。")
            folder = create_backup(url, tools, DEFAULT_BACKUP_ROOT)
            print(f"バックアップ作成・アーカイブ読込検査に成功しました: {folder}")
        else:
            verify_backup(args.folder, tools)
            print("サイズ・SHA-256・アーカイブ読込検査に成功しました。DBへの復元は行っていません。")
        return 0
    except KeyboardInterrupt:
        print("キャンセルしました。既存バックアップは維持しています。", file=sys.stderr)
        return 130
    except (BackupError, OSError) as error:
        message = str(error) if isinstance(error, BackupError) else "ローカルファイルの操作に失敗しました。保管先を確認してください。"
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
