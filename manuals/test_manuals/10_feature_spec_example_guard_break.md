# 10 New Feature Spec Example: Guard Break (防御崩し)

## Feature Name
- Guard Break (防御崩し)

## Responsibility
- 変更責務:
  - `manager/battle/skill_rules.py`（タグ/判定ルール）
  - `manager/battle/resolve_match_runtime.py`（clash/one-sided時の適用）
  - `manager/battle/resolve_auto_single_phase.py`（single phase分岐の整合）
  - `manager/battle/resolve_legacy_log_adapter.py`（ログ表示整形）
- 影響責務:
  - `manager/battle/resolve_effect_runtime.py`（状態適用と差分反映）
  - `manager/battle/resolve_trace_runtime.py`（trace detail整合）

## Risk Summary
- 主要リスク1: clash結果と状態付与タイミングがずれて、表示と内部状態が乖離する。
- 主要リスク2: one-sided経路では発火するがmass経路では発火しない、または逆。
- 主要リスク3: 既存の回避/防御/強硬攻撃分岐と競合し、勝敗判定が変わる。

## Automated Tests
- 追加テスト:
  - `tests/test_select_resolve_smoke.py` に Guard Break 正常系/境界系/競合系ケースを追加
  - `tests/test_skill_target_tags.py` にタグ解釈とログ整形の単体ケースを追加
- 既存回帰:
```powershell
pytest -q tests/test_select_resolve_smoke.py tests/test_skill_target_tags.py
pytest -q tests/test_match_integraton.py tests/test_unified_calc.py
pytest -q tests/test_pve_auto_intents.py tests/test_battle_ai_skill_selection.py
pytest -q tests/test_python_module_size_guard.py
```

## Test Cases
1. 正常系
- 入力:
  - 攻撃側が Guard Break タグ付きスキルで clash 勝利
  - 防御側は防御系スキル
- 期待値:
  - 防御側に `guard_broken` 相当状態が1段階付与される
  - ログに「防御崩し」発生行が1回だけ出る
  - trace detail に該当ステップが含まれる

2. 境界系
- 入力:
  - Guard Break 連続発動（同ラウンド2回）
  - 既に `guard_broken` が付与済み
- 期待値:
  - 上限ルール（例: 2段階まで）がある場合は上限で止まる
  - 追加不能時にログが重複しない

3. 異常系
- 入力:
  - 対象が不在（unplaced）または target invalid
- 期待値:
  - fizzle になり、状態変化は発生しない
  - エラーで処理停止せずラウンド進行は継続する

## Real Machine Checks
- UI/ログ確認:
  - clash勝利時に「防御崩し」ログが結果行と矛盾なく表示される
  - ポップアップ詳細の skill / outcome / statuses が一致する
- ラウンド跨ぎ確認:
  - 次ラウンド開始時に状態持続ターンが正しく減る
  - round_end後のリセット対象外データが消えない
- 長時間確認:
  - 5ラウンド以上連続で Guard Break を混在させても進行停止しない

## Done Criteria
- 追加テストと既存回帰がすべてパス
- 既存の clash / one-sided / hard followup 分岐に回帰なし
- 実機チェック項目の完了
- テスト仕様書の更新（このドキュメントを正式版へ昇格または複製）
