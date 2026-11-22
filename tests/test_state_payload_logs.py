"""全体の配信からログ履歴を外す（PERF-PAYLOAD、E01 §4.2）。"""
from pathlib import Path

import manager.room_manager as room_manager

ROOT = Path(__file__).resolve().parents[1]


def _state():
    return {
        "characters": [{"id": "c1", "name": "セラ"}],
        "logs": [{"log_id": 1, "message": "こんにちは", "type": "chat"}],
        "encounter_queue": [{"name": "secret"}],
        "round": 2,
    }


def test_broadcast_omits_logs_and_private_fields(monkeypatch):
    sent = []
    monkeypatch.setattr(room_manager, "_safe_emit", lambda name, payload, **kw: sent.append((name, payload, kw)))
    state = _state()
    room_manager.broadcast_participant_state("R1", state)
    (name, payload, kw), = sent
    assert name == "state_updated" and kw == {"to": "R1"}
    assert "logs" not in payload and "encounter_queue" not in payload
    assert payload["characters"] == state["characters"] and payload["round"] == 2
    # 配信用の写しを変えても、元の状態は変わらない。
    payload["characters"][0]["name"] = "変更"
    assert state["characters"][0]["name"] == "セラ" and state["logs"]


def test_join_snapshot_keeps_logs():
    payload = room_manager.build_participant_state(_state())
    assert payload["logs"][0]["message"] == "こんにちは"
    assert "encounter_queue" not in payload


def test_clearing_logs_tells_everyone(monkeypatch):
    sent = []
    monkeypatch.setattr(room_manager, "_safe_emit", lambda name, payload, **kw: sent.append((name, kw)))
    room_manager.broadcast_logs_cleared("R1")
    assert sent == [("logs_cleared", {"to": "R1"})]
    common = (ROOT / "manager/battle/common_manager.py").read_text(encoding="utf-8")
    reset = common[common.index("if mode == 'logs':"):common.index("return", common.index("if mode == 'logs':"))]
    assert "broadcast_logs_cleared(room)" in reset


def test_browser_keeps_its_log_history():
    main = (ROOT / "static/js/main.js").read_text(encoding="utf-8")
    handler = main[main.index("registerAppSocketHandler('state_updated'"):]
    handler = handler[:handler.index("registerAppSocketHandler(", 10)]
    assert "previousState?.logs" in handler
    assert "registerAppSocketHandler('logs_cleared'" in main
    ui = (ROOT / "static/js/visual/visual_ui.js").read_text(encoding="utf-8")
    append = ui[ui.index("window.appendVisualLogBatch = function"):]
    assert "querySelector('.visual-log-empty')?.remove()" in append[:400]
