from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITOR_SOURCE = ROOT / "static/js/modals/behavior_flow_editor_modal.js"


def test_behavior_flow_editor_can_insert_a_blank_round_before_any_round():
    source = EDITOR_SOURCE.read_text(encoding="utf-8")

    assert "insertStepBtn.dataset.stepInsertBefore = String(idx);" in source
    assert "editorEl.querySelectorAll('[data-step-insert-before]')" in source
    assert "loop.steps.splice(idx, 0, {" in source
    assert "targets: [normalizeBehaviorTargetCandidates(BEHAVIOR_STEP_TARGET_POLICY_DEFAULT)]" in source
    assert "on_no_target: ['cancel']" in source
    assert "next_loop_id: null" in source
    assert "next_reset_step_index: true" in source


def test_behavior_flow_editor_has_one_implementation_and_keeps_no_action():
    source = EDITOR_SOURCE.read_text(encoding="utf-8")
    modals = (ROOT / "static/js/modals.js").read_text(encoding="utf-8")
    assert "function openBehaviorFlowEditorModal" not in modals
    assert "window.openBehaviorFlowEditorModal(targetChar)" in modals
    assert source.count("function openBehaviorFlowEditorModal") == 1
    assert "BEHAVIOR_STEP_ACTION_NO_ACTION" in source
    assert "onSave(normalized" in source


def test_behavior_flow_editor_distinguishes_insertion_from_appending():
    source = EDITOR_SOURCE.read_text(encoding="utf-8")

    assert "insertStepBtn.textContent = '＋挿入';" in source
    assert ">末尾に追加</button>" in source
