# 24. Renderデプロイ前チェックリスト（JSON定義V2移行）

## 1. 目的
- `skill_json_rule_v2` 運用を Render 本番へ安全に反映する。
- 本番障害時に即時ロールバックできる状態を先に作る。

## 2. 事前固定（今回）
- 対象: スキル特記JSON（V2）中心
- ルール:
1. `schema: skill_json_rule_v2` 前提
2. `APPLY_BUFF/REMOVE_BUFF` は `buff_id` 必須
3. 自然言語ビルダーは `的中時` のみ許可（`中時/命中時` 禁止）

## 3. デプロイ前チェック
- [ ] `data/cache/skills_cache.json` をバックアップ済み
- [ ] `data/cache/buff_catalog_cache.json` をバックアップ済み
- [ ] `data/cache/battle_only_presets_cache.json` をバックアップ済み
- [ ] 直前リリースのコミットSHAを記録済み（ロールバック用）
- [ ] 失敗時の担当者/連絡先を決めた

## 4. ローカル/CIテスト
- [ ] `python -m py_compile app.py` が成功
- [ ] `test_skill_catalog_smoke.py`（JSON lint）が成功
- [ ] `test_json_rule_v2_phase1.py` が成功
- [ ] `test_phase3_strict_rehearsal.py` が成功
- [ ] `test_phase3_non_battle_input_audit.py` が成功

## 5. データ整合チェック
- [ ] スキルJSONに `schema` 未指定が 0 件
- [ ] `APPLY_BUFF` で `buff_id` 未指定が 0 件
- [ ] `REMOVE_BUFF` で `buff_id` 未指定が 0 件
- [ ] 参照 `buff_id` が全て `buff_catalog_cache` に存在
- [ ] 自然言語ビルダー入力の代表文でJSON生成成功（最低5ケース）

## 6. Renderデプロイ実行
- [ ] GitHub main（または本番ブランチ）へマージ
- [ ] Render のデプロイ開始を確認
- [ ] 起動ログで import/compile エラーなし
- [ ] `/api/get_skill_data` が200で返る
- [ ] `/api/get_buff_data` が200で返る

## 7. デプロイ後スモーク（実機）
- [ ] 宣言→確定が正常（`actor missing` なし）
- [ ] `的中時` 付与系スキルが正常発動
- [ ] `buff_id` 付与/解除が正常
- [ ] 特記（条件付き威力補正）が正常
- [ ] 自然言語ビルダー:
  - [ ] 整形JSON表示が正常
  - [ ] コピー時1行JSONが正常
  - [ ] 監査ログ（失敗時）出力を確認

## 8. 監視（当日）
- [ ] `logs/json_rule_v2_audit.jsonl` の failure 件数を確認
- [ ] battle_error の急増がないことを確認
- [ ] 主要操作（宣言・解決・ラウンド終了）を1周確認

## 9. ロールバック条件
- [ ] 宣言不能/確定不能が再現する
- [ ] 特記JSON解釈失敗が多発する
- [ ] `buff_id` 参照不整合で進行不可
- [ ] 重大バグの暫定回避策がない

## 10. ロールバック手順（最小）
1. 直前安定コミットへ戻す（GitHub）
2. Render 再デプロイを実行
3. `/api/get_skill_data` と宣言フローを再確認
4. 障害期間中の編集データを突合

## 11. 完了判定
- [ ] デプロイ後24時間、重大障害なし
- [ ] failure監査ログが許容範囲内
- [ ] テスト担当の確認完了
- [ ] 次フェーズ着手可否を記録
