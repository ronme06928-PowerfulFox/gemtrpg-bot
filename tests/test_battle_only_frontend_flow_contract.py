import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_store_round_start_accepts_complete_snapshot_without_erasing_intents():
    source = (ROOT / "static/js/battle/core/BattleStore.js").read_text(encoding="utf-8")
    assert "play_mode: payload.play_mode || this._state.play_mode" in source
    assert "intents: has('intents') ? (payload.intents || {})" in source
    assert "resolvePresentation: has('presentation')" in source
    assert "usableSkillIds: has('usable_skill_ids')" in source


def test_shared_resolve_cursor_and_completed_rejoin_contract():
    panel = (ROOT / "static/js/battle/components/ResolveFlowPanel.js").read_text(encoding="utf-8")
    client = (ROOT / "static/js/battle/core/SocketClient.js").read_text(encoding="utf-8")
    battle_only_marker = "if (this._isBattleOnlyMode(stateNow)) return true;"
    reconnect_guard = "return this._roundSawResolvePhase ||"

    assert battle_only_marker in panel
    assert reconnect_guard in panel
    assert panel.index(battle_only_marker) < panel.index(reconnect_guard)
    assert "socketClient.sendRoundEnd(roomName, payload.round)" not in panel
    assert "socketClient.sendResolveFlowAdvance(payload)" in panel
    assert "expected_revision:" in panel
    assert "sendResolveFlowClaim(payload)" in client
    assert "if (this._isResolvePresentationCompleted(state)) return;" in panel
    assert "phase === 'round_end' && this._isResolvePresentationCompleted(state)" in panel


def test_resolve_popup_uses_one_shell_from_request_through_first_match():
    panel = (ROOT / "static/js/battle/components/ResolveFlowPanel.js").read_text(encoding="utf-8")
    dock = (ROOT / "static/js/battle/components/ActionDock.js").read_text(encoding="utf-8")
    client = (ROOT / "static/js/battle/core/SocketClient.js").read_text(encoding="utf-8")

    assert "eventBus.emit('battle:resolve:start:requested'" in dock
    assert "this._unsubscribeStartRequestedEvent = eventBus.on('battle:resolve:start:requested'" in panel
    assert "(phase === 'select' && this._resolveStartPending)" in panel
    assert "this._isResolvePresentationActive(phase)" in panel
    assert "return this._emit('battle_resolve_start'" in client
    assert "_playNextStep({ forceLocalClock = false } = {})" in panel
    assert "const isFirstPresentedMatch = !isIntroStep && this._presentedStepCount === 0;" in panel
    assert "const useSharedClock = !resetVisibleClock" in panel
    assert "this._waitingForFirstTrace && this._playQueue.length > 0 && canPlayback" in panel
    assert "this._waitingForFirstTrace ? 'RESOLVING...' : 'BATTLE START'" in panel
    assert '<div class="resolve-flow-content"></div>' in panel
    assert "contentIntro.innerHTML =" in panel
    assert "panelContent.innerHTML =" in panel

    click_handler = dock.split("btn.addEventListener('click'", 1)[1]
    clear_error = "store.clearBattleError();"
    send_start = "socketClient.sendResolveStart(roomName || null)"
    assert clear_error in click_handler
    assert click_handler.index(clear_error) < click_handler.index(send_start)
    assert "this._unsubscribeBattleErrorEvent = eventBus.on('battle:error'" in panel
    assert "this._onResolveStartError(payload || {});" in panel
    assert "this._resolveStartPending && phase === 'select' && state?.battleError" not in panel

    node_script = r"""
import { ResolveFlowPanel } from './static/js/battle/components/ResolveFlowPanel.js';

globalThis.store = { state: {} };
const flow = new ResolveFlowPanel();
flow._roundKey = 'battle-1:4';
flow._resolveOpeningRoundKey = 'battle-1:4';
flow._resolveStartPending = false;
flow._introShownRounds.add('battle-1:4');
flow._activeStep = { kind: 'battle_start', stepIndex: -1 };
let rendered = 0;
let removed = 0;
flow._renderStep = () => { rendered += 1; };
flow._removePanel = () => { removed += 1; };

const delayedSelectSnapshot = {
  mode: 'battle',
  battle_id: 'battle-1',
  round: 4,
  phase: 'select',
  resolveTrace: [],
  resolvePresentation: { status: 'playing' }
};
globalThis.store.state = delayedSelectSnapshot;
flow._onStateUpdated(delayedSelectSnapshot);

if (removed !== 0 || rendered !== 1 || !flow._activeStep) {
  throw new Error('delayed select snapshot interrupted the resolve opening');
}
if (!flow._shouldWaitForFirstTrace(delayedSelectSnapshot)) {
  throw new Error('resolve opening did not remain latched before the first trace');
}
"""
    subprocess.run(
        ["node", "--input-type=module", "-e", node_script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


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
