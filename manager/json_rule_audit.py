from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from manager.cache_paths import REPO_ROOT

AUDIT_LOG_DIR = REPO_ROOT / "logs"
AUDIT_LOG_FILE = AUDIT_LOG_DIR / "json_rule_v2_audit.jsonl"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_audit(event_type: str, **payload) -> None:
    try:
        AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)
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
