"""戦闘専用ルームの進行中戦績を一貫して終了させる補助処理。"""

from datetime import datetime, timezone


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def finalize_in_progress_records(bo, *, result="aborted", reason=None):
    """進行中の戦績をすべて終了し、戦闘専用状態を下書きへ戻す。"""
    if not isinstance(bo, dict):
        return []

    finished = []
    records = bo.get("records")
    if not isinstance(records, list):
        records = []
        bo["records"] = records

    ended_at = _now_iso()
    for record in records:
        if not isinstance(record, dict):
            continue
        if str(record.get("status") or "").strip().lower() != "in_battle":
            continue
        record["status"] = "finished"
        record["result"] = str(result or "aborted").strip().lower() or "aborted"
        record["ended_at"] = ended_at
        if reason:
            record["end_reason"] = str(reason)
        finished.append(record)

    bo["active_record_id"] = None
    bo["status"] = "draft"
    bo["pending_auto_reset"] = False
    bo["pending_auto_reset_round"] = None
    return finished


def repair_orphaned_records(bo):
    """下書き状態に取り残された進行中戦績を中断済みに直す。"""
    if not isinstance(bo, dict):
        return []
    if str(bo.get("status") or "").strip().lower() == "in_battle":
        return []
    records = bo.get("records") if isinstance(bo.get("records"), list) else []
    if not any(
        isinstance(record, dict)
        and str(record.get("status") or "").strip().lower() == "in_battle"
        for record in records
    ):
        if bo.get("active_record_id"):
            bo["active_record_id"] = None
        return []
    return finalize_in_progress_records(
        bo,
        result="aborted",
        reason="orphaned_state_recovery",
    )
