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


def test_behavior_flow_editor_distinguishes_insertion_from_appending():
    source = EDITOR_SOURCE.read_text(encoding="utf-8")

    assert "insertStepBtn.textContent = '＋挿入';" in source
    assert ">末尾に追加</button>" in source
