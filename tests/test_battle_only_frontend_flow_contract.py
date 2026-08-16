from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_battle_store_preserves_play_mode_from_server_payload():
    source = (ROOT / "static/js/battle/core/BattleStore.js").read_text(encoding="utf-8")
    assert "play_mode: payload.play_mode || this._state.play_mode" in source


def test_battle_only_round_end_can_complete_without_resolve_phase_snapshot():
    source = (ROOT / "static/js/battle/components/ResolveFlowPanel.js").read_text(encoding="utf-8")
    marker = "if (this._isBattleOnlyMode(stateNow)) return true;"
    reconnect_guard = "return this._roundSawResolvePhase ||"
    assert marker in source
    assert reconnect_guard in source
    assert source.index(marker) < source.index(reconnect_guard)


def test_shared_resolve_cursor_replaces_local_auto_round_end_request():
    panel = (ROOT / "static/js/battle/components/ResolveFlowPanel.js").read_text(encoding="utf-8")
    client = (ROOT / "static/js/battle/core/SocketClient.js").read_text(encoding="utf-8")
    assert "socketClient.sendRoundEnd(roomName, payload.round)" not in panel
    assert "socketClient.sendResolveFlowAdvance(payload)" in panel
    assert "expected_revision:" in panel
    assert "sendResolveFlowClaim(payload)" in client


def test_battle_start_request_carries_latest_draft_snapshot():
    source = (ROOT / "static/js/modals/battle_only_draft_modal.js").read_text(encoding="utf-8")
    assert "draftPayload = sendDraftUpdate({ emit: false })" in source
    assert "draft_payload: draftPayload" in source


def test_token_click_does_not_start_drag_or_move_request():
    source = (ROOT / "static/js/visual/visual_controls.js").read_text(encoding="utf-8")
    drag_source = source.split("window.setupBattleTokenDrag = function () {", 1)[1]
    drag_source = drag_source.split("window.enterAttackTargetingMode", 1)[0]
    assert "if (e.target.closest('.slot-badge-container')) return;" in drag_source
    no_move_guard = "if (!hasMovedSignificantDistance) {"
    move_emit = "socket.emit('request_move_token'"
    assert no_move_guard in drag_source
    assert move_emit in drag_source
    assert drag_source.index(no_move_guard) < drag_source.index(move_emit)


def test_existing_token_move_uses_differential_arrow_refresh():
    source = (ROOT / "static/js/visual/visual_socket.js").read_text(encoding="utf-8")
    moved_handler = source.split("registerSocketHandler('character_moved'", 1)[1]
    moved_handler = moved_handler.split("// --- Wide Match Modals ---", 1)[0]
    assert "delete window._localCharPositions[charId]" in moved_handler
    assert "window.renderArrows()" in moved_handler
