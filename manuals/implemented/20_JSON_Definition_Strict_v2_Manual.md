# 20. JSON定義マニュアル（Phase3 strict v2 正本）

**最終更新日**: 2026-05-02  
**適用範囲**: スキル特記JSON / バフ定義JSON / フィールド効果JSON / GM運用入力  
**ステータス**: 現行正本（Source of Truth）

---

## 1. 基本原則
1. `schema` は必須。値は `skill_json_rule_v2`。  
2. 効果判定は内部キー基準（`id`, `buff_id`, `name`）。  
3. 表示は表示キー基準（`display_name`）。  
4. `buff_name` 単独指定は許可しない。  
5. `APPLY_BUFF` / `REMOVE_BUFF` は `buff_id` 必須。  
6. 解決不能・不整合はエラー停止（黙殺禁止）。

---

## 2. スキル特記JSON（rule_data）
最小形:

```json
{
  "schema": "skill_json_rule_v2",
  "id": "SKILL_X00",
  "power_bonus": [],
  "cost": [],
  "effects": []
}
```

必須:
- `schema`
- `effects`（空配列可）

推奨:
- `id`
- `tags`
- `target_scope`

---

## 3. APPLY_BUFF / REMOVE_BUFF
### 3.1 APPLY_BUFF
必須キー:
- `type`: `APPLY_BUFF`
- `target`
- `buff_id`

例:
```json
{
  "timing": "HIT",
  "type": "APPLY_BUFF",
  "target": "target",
  "buff_id": "Bu-32",
  "lasting": 1,
  "delay": 0,
  "data": { "value": 3, "display_name": "筋力強化" }
}
```

### 3.2 REMOVE_BUFF
必須キー:
- `type`: `REMOVE_BUFF`
- `target`
- `buff_id`

例:
```json
{
  "timing": "HIT",
  "type": "REMOVE_BUFF",
  "target": "target",
  "buff_id": "Bu-32"
}
```

禁止:
- `buff_name` 単独指定

---

## 4. `data.value` 規約
1. 型は `int` のみ。  
2. `%系`は `value=20` を `+20%` として解釈。  
3. 説明文テンプレート `{{value}}` は `data.value` で置換。  
4. 必須置換値不足はエラー停止。

---

## 5. バフ定義（カタログ）
必須:
- `id`（または `バフID`）
- `name`
- `effect`

推奨:
- `display_name`
- `description`
- `flavor`

補足:
- `Bu-32`〜`Bu-47` はサーバ実装で効果解釈が固定される。

---

## 6. フィールド効果（skill_constraints）
`skill_constraints` は配列で持つ。  
要素の必須:
- `id`
- `mode` (`block` or `add_cost`)
- `match`

例:
```json
{
  "id": "field_fp_block",
  "mode": "block",
  "priority": 100,
  "match": { "cost_types": ["FP"] },
  "reason": "FP消費技封印"
}
```

---

## 7. 旧仕様からの移行ルール
1. `schema` 未指定JSONは修正対象。  
2. `APPLY_BUFF` の `buff_name` は `buff_id` へ置換。  
3. `REMOVE_BUFF` の `buff_name` は `buff_id` へ置換。  
4. 動的命名バフ（`Power_Atk5` 等）は廃止し、`buff_id + data.value` へ統一。

---

## 8. GM運用入力ルール
1. GMバフ付与API: `buff_id` 必須。  
2. GMバフ解除API: `buff_id` 必須。  
3. UI入力欄も `buff_id` 専用。  
4. `buff_id` 不正・未解決は即エラー。

---

## 9. テストと監査
必須テスト:
- `tests/test_phase3_strict_rehearsal.py`
- `tests/test_phase3_non_battle_input_audit.py`
- `tests/test_skill_catalog_smoke.py`（JSON lint）

監査観点:
- `schema_missing == 0`
- `apply_buff_no_buff_id == 0`
- `remove_buff_no_buff_id == 0`
- `buff_name_only == 0`

---

## 10. 参照優先順位
1. この文書（20）  
2. `17_Phase3_Strict_Errata.md`  
3. 実装コード / テスト  
4. 旧マニュアル（履歴用途）
