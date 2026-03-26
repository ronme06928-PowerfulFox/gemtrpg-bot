# テストマニュアル Index

## 目的
このフォルダは、機能責務ごとのテスト観点を即参照できるように整理した運用マニュアルです。
新機能追加時に既存観点を漏らさず再利用することを目的とします。

## 使い方
1. 変更対象の責務に対応する仕様書を開く。
2. `自動テスト` を最小セットとして先に実行する。
3. `実機確認` チェックリストを実施する。
4. 影響範囲が広い場合は `90_real_machine_checklist.md` を通す。
5. 新機能の場合は `99_new_feature_test_template.md` を複製して追記する。

## ドキュメント一覧
- `01_select_resolve_core.md`: Select/Resolve 全体の入口とフェーズ遷移
- `02_mass_phase.md`: mass 解決（mass_individual / mass_summation）
- `03_single_phase_and_reuse.md`: single 解決、競合、再使用チェーン
- `04_clash_and_duel_delegate.md`: clash/one-sided/hard followup の委譲解決
- `05_pve_ai_and_round_end.md`: PvE意図生成、AI選択、ラウンド終端処理
- `90_real_machine_checklist.md`: 実機確認の重点チェック
- `99_new_feature_test_template.md`: 新機能用テスト仕様テンプレート

## クイック実行コマンド
```powershell
pytest -q tests/test_select_resolve_smoke.py tests/test_skill_target_tags.py
pytest -q tests/test_pve_auto_intents.py tests/test_battle_ai_skill_selection.py
pytest -q tests/test_match_integraton.py tests/test_round_end_summon_lock.py tests/test_unified_calc.py
pytest -q tests/test_python_module_size_guard.py
```
