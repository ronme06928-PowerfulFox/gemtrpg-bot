from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize("scenario", ["disabled", "ordered", "ack_first", "hidden", "timeout", "stop", "unavailable", "isolation", "limits", "wiring"])
def test_intent_performance_frontend(scenario):
    result = subprocess.run(
        ["node", "tests/support/intent_performance_runner.mjs", scenario],
        cwd=Path(__file__).resolve().parents[1], capture_output=True,
        text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
