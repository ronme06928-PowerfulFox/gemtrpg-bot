"""on_request_switch_battle_mode / on_request_ai_suggest_skill の登録回帰テスト。

計画書34の調査中に発見した既存バグ（2026-07-08）: 両ハンドラは実装済みだが
@socketio.on デコレータが欠落しており、フロント（visual_ui.js / visual_panel.js）
からの emit がサーバー側で常に無反応だった。デコレータを追加して修復した際の
回帰防止として、(1) socketio に実際に登録されていること、(2) ハンドラ自体の
権限・戻り値ロジックが正しいこと、の両方を検証する。
"""
import inspect
from types import SimpleNamespace

from events.battle import common_routes


def test_switch_battle_mode_and_ai_suggest_skill_have_socketio_decorator():
    """デコレータ欠落バグの回帰防止。

    ハンドラ関数の直前行に @socketio.on('<event>') があることをソースから確認する
    （socketio.server は Flask app 初期化前のテスト実行時は None のため、
    ランタイムの登録一覧チェックではなくソースベースで検証する）。
    """
    source, _ = inspect.getsourcelines(common_routes)
    text = "".join(source)

    for handler_name, event_name in (
        ("def on_request_switch_battle_mode(", "request_switch_battle_mode"),
        ("def on_request_ai_suggest_skill(", "request_ai_suggest_skill"),
    ):
        idx = text.index(handler_name)
        preceding = text[:idx].splitlines()[-1]
        assert preceding.strip() == f"@socketio.on('{event_name}')", (
            f"{handler_name} の直前に @socketio.on('{event_name}') が無い: {preceding!r}"
        )


def test_switch_battle_mode_gm_only_updates_state(monkeypatch):
    state = {"battle_mode": "pvp"}
    calls = {"save": [], "broadcast": []}

    monkeypatch.setattr(common_routes, "request", SimpleNamespace(sid="sid_test"))
    monkeypatch.setattr(common_routes, "is_sid_in_room", lambda _sid, _room: True)
    monkeypatch.setattr(
        common_routes,
        "get_user_info_from_sid",
        lambda _sid: {"username": "gm_a", "attribute": "GM"},
    )

    import manager.battle.common_manager as common_manager
    monkeypatch.setattr(common_manager, "get_room_state", lambda _room: state)
    monkeypatch.setattr(common_manager, "save_specific_room_state", lambda _room: calls["save"].append(_room))
    monkeypatch.setattr(common_manager, "broadcast_state_update", lambda _room: calls["broadcast"].append(_room))
    monkeypatch.setattr(common_manager, "broadcast_log", lambda *_a, **_k: None)

    common_routes.on_request_switch_battle_mode({"room": "room_t", "mode": "pve"})

    assert state["battle_mode"] == "pve"
    assert calls["save"] == ["room_t"]


def test_switch_battle_mode_denies_non_gm(monkeypatch):
    state = {"battle_mode": "pvp"}

    monkeypatch.setattr(common_routes, "request", SimpleNamespace(sid="sid_test"))
    monkeypatch.setattr(common_routes, "is_sid_in_room", lambda _sid, _room: True)
    monkeypatch.setattr(
        common_routes,
        "get_user_info_from_sid",
        lambda _sid: {"username": "player_a", "attribute": "Player"},
    )

    import manager.battle.common_manager as common_manager
    monkeypatch.setattr(common_manager, "get_room_state", lambda _room: state)

    common_routes.on_request_switch_battle_mode({"room": "room_t", "mode": "pve"})

    assert state["battle_mode"] == "pvp"


def test_ai_suggest_skill_emits_suggestion(monkeypatch):
    state = {"characters": [{"id": "char_a", "commands": ""}]}
    emit_calls = []

    monkeypatch.setattr(common_routes, "request", SimpleNamespace(sid="sid_test"))
    monkeypatch.setattr(
        common_routes,
        "emit",
        lambda event, payload=None: emit_calls.append((event, payload)),
    )

    import manager.battle.common_manager as common_manager
    monkeypatch.setattr(common_manager, "get_room_state", lambda _room: state)
    monkeypatch.setattr(common_manager, "ai_suggest_skill", lambda _char: "Ps-01")

    common_routes.on_request_ai_suggest_skill({"room": "room_t", "charId": "char_a"})

    assert emit_calls == [("ai_skill_suggested", {"charId": "char_a", "skillId": "Ps-01"})]


def test_ai_suggest_skill_returns_none_for_missing_char(monkeypatch):
    state = {"characters": []}
    emit_calls = []

    monkeypatch.setattr(common_routes, "request", SimpleNamespace(sid="sid_test"))
    monkeypatch.setattr(
        common_routes,
        "emit",
        lambda event, payload=None: emit_calls.append((event, payload)),
    )

    import manager.battle.common_manager as common_manager
    monkeypatch.setattr(common_manager, "get_room_state", lambda _room: state)

    common_routes.on_request_ai_suggest_skill({"room": "room_t", "charId": "char_missing"})

    assert emit_calls == [("ai_skill_suggested", {"charId": "char_missing", "skillId": None})]
