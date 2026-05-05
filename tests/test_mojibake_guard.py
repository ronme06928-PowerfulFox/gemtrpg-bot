import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/check_mojibake_markers.py")


def _run_guard(root):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_mojibake_guard_passes_repository():
    result = _run_guard(".")

    assert result.returncode == 0, result.stderr
    assert "[mojibake-guard] OK" in result.stdout


def test_mojibake_guard_detects_corrupted_marker(tmp_path):
    bad_file = tmp_path / "bad.py"
    bad_file.write_text(f'value = "{chr(0x7E67)}"\n', encoding="utf-8")

    result = _run_guard(tmp_path)

    assert result.returncode == 1
    assert "mojibake marker U+7E67" in result.stderr


def test_mojibake_guard_detects_question_placeholder_in_label(tmp_path):
    bad_file = tmp_path / "bad.py"
    bad_file.write_text('row = {"label": "' + "??" + '"}\n', encoding="utf-8")

    result = _run_guard(tmp_path)

    assert result.returncode == 1
    assert "suspicious question-mark placeholder" in result.stderr
