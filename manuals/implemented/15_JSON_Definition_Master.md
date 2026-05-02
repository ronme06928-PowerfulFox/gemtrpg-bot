# 15. JSON定義マスター（Phase3 strict運用版）

最終更新: 2026-05-02  
対象: 実装済み（Current）

---

## 0. 目的
この文書は、スキル/バフ/フィールド効果のJSON記法をPhase3 strict運用に合わせて統一する。

参照優先順位:
1. `20_JSON_Definition_Strict_v2_Manual.md`
2. `17_Phase3_Strict_Errata.md`
3. `21_Render_Deploy_Operations_JSON_V2.md`（運用）
4. 本書

---

## 1. 共通必須ルール
1. `schema` は必須: `skill_json_rule_v2`
2. `APPLY_BUFF` は `buff_id` 必須
3. `REMOVE_BUFF` は `buff_id` 必須
4. `buff_name` 単独指定は禁止
5. 不整合はエラー停止

---

## 2. スキル特記（rule_data）

### 2.1 最小形
```json
{
  "schema":"skill_json_rule_v2",
  "id":"SKILL_X00",
  "power_bonus":[],
  "cost":[],
  "effects":[]
}
```

### 2.2 よく使うeffect
- `APPLY_STATE`
- `APPLY_BUFF`
- `REMOVE_BUFF`
- `DAMAGE_BONUS`
- `CUSTOM_EFFECT`
- `GRANT_SKILL`
- `SUMMON_CHARACTER`

---

## 3. バフ関連ルール

### 3.1 APPLY_BUFF
```json
{"timing":"HIT","type":"APPLY_BUFF","target":"target","buff_id":"Bu-32","lasting":1,"delay":0,"data":{"value":3}}
```

### 3.2 REMOVE_BUFF
```json
{"timing":"HIT","type":"REMOVE_BUFF","target":"target","buff_id":"Bu-32"}
```

### 3.3 value駆動
- `data.value` は intのみ
- `%系` は `value=20 => +20%`

---

## 4. フィールド制約（skill_constraints）

### 4.1 形式
```json
{
  "id":"rule_x",
  "mode":"block",
  "priority":100,
  "match":{},
  "reason":"..."
}
```

### 4.2 mode
- `block`: 使用禁止
- `add_cost`: コスト追加

---

## 5. 禁止記法（Phase3）
- `buff_name` だけでバフ付与/解除する記法
- 動的命名バフ（`Power_Atk5` 等）依存
- `schema` 未指定の特記JSON

---

## 6. 実運用チェック
- `schema_missing == 0`
- `apply_buff_no_buff_id == 0`
- `remove_buff_no_buff_id == 0`
- strictリハーサルテストが通る

---

## 7. テンプレート（貼り付け用）

### 7.1 スキル特記2行版
1行目: 管理ラベル  
2行目:
```json
{"schema":"skill_json_rule_v2","id":"SKILL_TEMPLATE","power_bonus":[],"cost":[],"effects":[]}
```

### 7.2 カテゴリ封印例
```json
{"schema":"skill_json_rule_v2","id":"SKILL_CC_MAGIC_BLOCK","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_id":"Bu-XX","lasting":2,"data":{"skill_constraints":[{"id":"cc_magic_block","mode":"block","priority":100,"match":{"category":"魔法"},"reason":"魔法封印"}]}}]}
```

---

## 8. 備考
- 詳細仕様の更新は `20` へ先に反映し、本書は運用向けに追従更新する。
