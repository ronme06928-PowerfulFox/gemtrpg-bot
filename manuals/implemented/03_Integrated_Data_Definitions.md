# 03. 統合データ定義マニュアル（Phase3 strict版）

最終更新: 2026-05-05  
対象: 実装済み（Current）

---

## 0. 本書の位置づけ
- 本書はデータ定義の運用ガイド。
- 厳密な正本は `manuals/implemented/20_JSON_Definition_Strict_v2_Manual.md`。
- 旧資料に矛盾がある場合は `17_Phase3_Strict_Errata.md` を優先。

---

## 1. スキル定義（skills_cache / 特記処理）

### 1.1 基本
- `特記処理` は JSON文字列。
- ルートに `schema: "skill_json_rule_v2"` を必須で含める。
- `effects` は配列（空可）。

### 1.2 最小テンプレート
```json
{"schema":"skill_json_rule_v2","id":"SKILL_X00","power_bonus":[],"cost":[],"effects":[]}
```

### 1.3 effect共通ルール
- 必須: `type`, `timing`（型ごとの必須キーは別表に従う）
- `APPLY_BUFF` / `REMOVE_BUFF` は `buff_id` 必須
- `APPLY_BUFF_PER_N` も `buff_id` 必須（`source/source_param/per_N/value` を併用）
- `buff_name` 単独指定は禁止
- `condition.param` で状態異常スタック合算を使う場合、状態名列挙を必須とする  
  例: `状態異常スタック合計:出血,破裂,亀裂,戦慄,荊棘`
- 全種合算でも、必ず全状態名を明示列挙する

---

## 2. バフ定義（buff_catalog）

### 2.1 基本
- バフは `buff_id` で識別する。
- 判定ロジックは `buff_id` 基準。
- 表示は `display_name` 優先。

### 2.2 値駆動バフ
- 強度は `data.value`（int）で指定。
- `%系` は `value=20 => +20%`。
- `Bu-32`〜`Bu-47` はサーバ実装で固定解釈。

---

## 3. APPLY_BUFF / REMOVE_BUFF

### 3.1 APPLY_BUFF
```json
{"timing":"HIT","type":"APPLY_BUFF","target":"target","buff_id":"Bu-32","lasting":1,"delay":0,"data":{"value":3,"display_name":"筋力強化"}}
```

### 3.2 REMOVE_BUFF
```json
{"timing":"HIT","type":"REMOVE_BUFF","target":"target","buff_id":"Bu-32"}
```

---

## 4. フィールド効果（skill_constraints）

### 4.1 定義
- 配列で定義する。
- 要素必須: `id`, `mode`, `match`
- `mode`: `block` or `add_cost`

### 4.2 例
```json
{"id":"field_fp_block","mode":"block","priority":100,"match":{"cost_types":["FP"]},"reason":"FP消費技封印"}
```

---

## 5. GM運用ルール
- GMバフ付与: `buff_id` 必須
- GMバフ解除: `buff_id` 必須
- `buff_name` ベース運用は行わない

---

## 6. 推奨テスト
- `tests/test_phase3_strict_rehearsal.py`
- `tests/test_phase3_non_battle_input_audit.py`
- `tests/test_skill_catalog_smoke.py`（JSON lint）

---

## 7. 補足
- 旧「動的命名バフ」（例: `Power_Atk5`）は運用終了。
- 新規データ作成時は必ず `20_JSON_Definition_Strict_v2_Manual.md` のテンプレートを使用する。
