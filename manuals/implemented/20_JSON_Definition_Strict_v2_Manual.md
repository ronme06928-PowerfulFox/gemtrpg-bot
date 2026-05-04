# 20. JSON定義マニュアル（Phase3 strict v2 正本）

最終更新: 2026-05-02  
対象: 実装済み（Current）

---

## 1. 基本方針
1. `schema` は必須。値は `skill_json_rule_v2`。
2. `APPLY_BUFF` / `REMOVE_BUFF` は `buff_id` 必須。
3. `buff_name` 単独指定は新規入力で禁止。
4. 不整合はエラー停止（黙って補正しない）。

---

## 2. スキル特記JSON（rule_data）
### 2.1 最小形
```json
{
  "schema": "skill_json_rule_v2",
  "id": "SKILL_X00",
  "power_bonus": [],
  "cost": [],
  "effects": []
}
```

### 2.2 必須/推奨
- 必須: `schema`, `effects`（配列）
- 推奨: `id`, `tags`, `target_scope`

---

## 3. バフ付与/解除
### 3.1 APPLY_BUFF
```json
{"timing":"HIT","type":"APPLY_BUFF","target":"target","buff_id":"Bu-32","lasting":1,"delay":0,"data":{"value":3}}
```

### 3.2 REMOVE_BUFF
```json
{"timing":"HIT","type":"REMOVE_BUFF","target":"target","buff_id":"Bu-32"}
```

### 3.3 禁止
- `buff_name` のみで付与/解除

---

## 4. data.value と説明文
1. `data.value` は `int` を使用。
2. `%系` は `value=20` を `+20%` と解釈。
3. 説明文テンプレート `{{value}}` は `data.value` で置換。

---

## 4.1 condition.param（状態異常スタック合算）
1. `condition.param` で状態異常スタック合算を使う場合は、必ず状態名を列挙する。  
   例: `状態異常スタック合計:出血,破裂,亀裂,戦慄,荊棘`
2. `状態異常スタック合計` の省略記法（状態名なし）は strict では不正。
3. 区切りは `,` / `、` / `・` を許可。

---

## 5. 自然言語JSON生成（実装済み）
対象ツール: `CharaCreator/json_definition_builder.html`

### 5.1 入力列
1. 使用時効果
2. 発動時効果
3. 特記
4. タグ（任意）
5. `id`（任意）

### 5.2 運用ルール
1. `的中時` を使用する。
2. `中時` / `命中時` は禁止語彙（エラー）。
3. 文区切りは `。` と改行のみ。
4. 変換不能時は全停止。
5. 表示は整形JSON、コピーは1行JSON。

### 5.3 監査ログ
- API: `/api/json_nl_builder_audit`
- 失敗時: 必ず記録
- 成功時: サンプリング記録（20%）

---

## 6. フィールド制約（skill_constraints）
```json
{
  "id": "rule_x",
  "mode": "block",
  "priority": 100,
  "match": {},
  "reason": "..."
}
```

- `mode=block`: 使用禁止
- `mode=add_cost`: コスト追加

---

## 7. テスト基準
- `tests/test_skill_catalog_smoke.py`（JSON lint）
- `tests/test_phase3_strict_rehearsal.py`
- `tests/test_phase3_non_battle_input_audit.py`

完了判定:
- `schema_missing == 0`
- `apply_buff_no_buff_id == 0`
- `remove_buff_no_buff_id == 0`

---

## 8. 参照優先順位
1. 本書（20）
2. `implemented/17_Phase3_Strict_Errata.md`
3. `implemented/15_JSON_Definition_Master.md`
