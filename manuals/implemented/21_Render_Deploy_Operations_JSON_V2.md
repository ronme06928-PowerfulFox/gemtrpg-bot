# 21. Renderデプロイ運用（JSON定義V2）

最終更新: 2026-05-02  
状態: 実装済み・本番反映済み

---

## 1. デプロイ前に固定すべき条件
1. `schema=skill_json_rule_v2`
2. `APPLY_BUFF/REMOVE_BUFF` は `buff_id` 必須
3. 自然言語入力では `的中時` を使用（`中時/命中時` 禁止）

---

## 2. 事前チェック
1. `skills_cache.json` バックアップ
2. `buff_catalog_cache.json` バックアップ
3. `battle_only_presets_cache.json` バックアップ
4. 直前安定コミットSHAの記録

---

## 3. 反映後スモーク
1. 宣言→確定が正常
2. `的中時` 付与系が正常
3. `buff_id` 付与/解除が正常
4. 特記（条件補正）が正常
5. 自然言語ビルダーが整形表示/1行コピーで動作

---

## 4. 監視
1. `logs/json_rule_v2_audit.jsonl` の failure 件数
2. battle_error の急増有無
3. 主要フロー（宣言/解決/ラウンド終了）

---

## 5. ロールバック条件
1. 宣言確定不能の再現
2. 特記解釈失敗の多発
3. `buff_id` 参照不整合で進行不可

---

## 6. ロールバック最小手順
1. 直前安定コミットへ戻す
2. Render再デプロイ
3. `/api/get_skill_data` と宣言フローを再確認
