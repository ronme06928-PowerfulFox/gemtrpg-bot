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

## 自動テストと確認用出力

テストの成否は `assert` や `pytest.raises` で検証する。PASS/FAILを表示するだけで終了しない。ファイル出力の検証が必要な場合は `tmp_path` を使い、リポジトリ直下に結果ファイルを作らない。通常の実行結果はpytestの出力を利用する。

順次効果の条件判定は `tests/test_sequential_effects.py` に集約する。`process_skill_effects` は仮想状態で後続条件を評価して変更命令を返し、実キャラクターへの反映は呼出し側が行うため、返却命令と入力の未変更を確認する。

保存の検証は `tests/test_persistence_recovery.py` の実SQLite・障害注入と、`tests/test_persistence_process_recovery.py` の別プロセス・正常終了・強制終了・バックアップ復元で補完する。通常のルーム・戦闘テストの保存モックは維持し、現役DBや本番接続を検証に使わない。検証範囲と実行コマンドは[保存・復元確認手順](../operations/persistence_recovery_runbook.md)を参照する。

保存を対象としないSocket認証・モード切替のテストでは、遅延保存だけでなく `flush_room_state_now` や保存を行う所有者登録ヘルパーも呼出し先でモックする。架空ルームの保存要求をグローバルに残さず、テスト後の保存タスクや終了時処理に流さない。所有者登録・権限・保存そのものは、それぞれの責務のテストで検証する。

状態配信のローカル性能比較は[計測手順](../operations/state_delivery_measurement.md)を参照する。ツールの契約は `tests/test_state_delivery_benchmark.py` で検証し、所要時間に固定の合否閾値は設けない。本番回線・ブラウザ描画の確認は別途行う。

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

宣言の任意計測は `tests/test_intent_performance.py` と `tests/test_intent_performance_frontend.py`、認可との組合せは `tests/test_intent_authorization_routes.py` で確認する。実ブラウザ用の合成fixtureは `tests/support/intent_performance_browser.mjs`。模擬通信の所要時間を本番の速度として扱わない。手順は[宣言の応答計測](../operations/intent_performance_measurement.md)。
