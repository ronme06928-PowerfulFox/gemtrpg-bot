from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from manager.cache_paths import REPO_ROOT

AUDIT_LOG_DIR = REPO_ROOT / "logs"
AUDIT_LOG_FILE = AUDIT_LOG_DIR / "json_rule_v2_audit.jsonl"

# 成功イベントはスキル評価のホットパス（宣言プレビュー/ラウンド開始の
# 使用可否判定など）から大量に発火するため、既定では書き込まない。
# デバッグ時のみ JSON_RULE_AUDIT_VERBOSE=1 で有効化する。
VERBOSE_AUDIT = os.environ.get("JSON_RULE_AUDIT_VERBOSE") == "1"

# 追記のたびの mkdir を避けるための初期化フラグ
_dir_ready = False

# 肥大化防止: このサイズを超えたら 1 世代ローテーションする
_MAX_AUDIT_BYTES = 20 * 1024 * 1024


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dir() -> None:
    global _dir_ready
    if _dir_ready:
        return
    AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    _dir_ready = True


def _rotate_if_needed() -> None:
    try:
        if AUDIT_LOG_FILE.exists() and AUDIT_LOG_FILE.stat().st_size > _MAX_AUDIT_BYTES:
            backup = AUDIT_LOG_FILE.with_suffix(".jsonl.1")
            if backup.exists():
                backup.unlink()
            AUDIT_LOG_FILE.rename(backup)
    except OSError:
        pass


def append_audit(event_type: str, **payload) -> None:
    try:
        _ensure_dir()
        _rotate_if_needed()
        row = {
            "ts": _utc_now_iso(),
            "event": str(event_type or "").strip() or "unknown",
            **payload,
        }
        with AUDIT_LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        # audit must never break battle flow
        return


def append_audit_verbose(event_type: str, **payload) -> None:
    """成功イベント等の高頻度監査。既定では no-op（VERBOSE_AUDIT時のみ記録）。"""
    if not VERBOSE_AUDIT:
        return
    append_audit(event_type, **payload)
