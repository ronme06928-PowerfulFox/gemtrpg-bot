"""相場逸脱WARNは日常運用（--update・CI）には組み込まず、任意確認用に留める方針の回帰テスト。

データが壊れていなければ相場の多少の逸脱は運用上気にしないという判断のため、
`lint` のデフォルト実行では WARN を計算・表示せず、`--warn` を明示した時だけ見せる。
"""
import json

from scripts.skill_catalog_tool import main


def test_lint_default_does_not_check_warnings(capsys):
    exit_code = main(["lint", "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["warnings_checked"] is False
    assert "warnings" not in payload


def test_lint_warn_flag_includes_warnings(capsys):
    exit_code = main(["lint", "--warn", "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["warnings_checked"] is True
    assert "warnings" in payload


def test_lint_text_output_notes_warn_is_optional(capsys):
    exit_code = main(["lint"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "未確認" in out
    assert "--warn" in out


def test_lint_exit_code_is_unaffected_by_warnings(capsys):
    # --warn を付けても、ERROR がなければ exit code は 0 のまま
    # （相場逸脱は運用のブロッカーにしない、という方針の直接的な検証）。
    assert main(["lint", "--warn"]) == 0
