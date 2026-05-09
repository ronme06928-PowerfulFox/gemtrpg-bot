<!-- 旧: 20 / 17_Phase3_Strict_Errata / 15 / 03 を統合。20 が正本。(2026-05-09) -->

# JSON定義マニュアル（正本・統合版）

**最終更新日**: 2026-05-09
**系統**: C — データ定義（JSON）
**統合元**: 20_JSON_Definition_Strict_v2 / 17_Phase3_Strict_Errata / 15_JSON_Definition_Master / 03_Integrated_Data_Definitions
**優先順位**: 本書 > 旧20 = 旧17 > 旧15 > 旧03

---

## 本書の位置づけ

本書は旧 20（strict v2 正本）を中心に、旧 17（Phase3 差分補正）・旧 15（運用マスター）・旧 03（データ定義ガイド）を統合した JSON 定義の唯一正本です。矛盾がある場合は新しい記述（旧20・旧17）を優先します。

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

### 3.3 APPLY_BUFF_PER_N
```json
{"timing":"HIT","type":"APPLY_BUFF_PER_N","target":"self","source":"target","source_param":"状態異常スタック合計:出血,破裂","buff_id":"Bu-30","value":1,"per_N":3,"max_count":7}
```

- `source.source_param` を `per_N` ごとに区切り、`value` スタックずつ `buff_id` を付与する。
- `max_count` 指定時は合計付与スタック数を上限で丸める。
- strict v2 では `buff_id` 必須（`APPLY_BUFF` と同様）。

### 3.4 禁止
- `buff_name` のみで付与/解除

---

## 4. data.value と説明文
1. `data.value` は `int` を使用。
2. `%系` は `value=20` を `+20%` と解釈。
3. 説明文テンプレート `{{value}}` は `data.value` で置換。

---

## 4.1 condition/source_param（状態異常スタック合算）
1. `condition.param` / `power_bonus.param` / `effect.source_param` で状態異常スタック合算を使う場合は、必ず状態名を列挙する。  
   例: `状態異常スタック合計:出血,破裂,亀裂,戦慄,荊棘`
2. `状態異常スタック合計` の省略記法（状態名なし）は strict では不正。
3. 区切りは `,` / `、` / `・` を許可。
4. 全種合算したい場合も「全ての状態名を明示列挙」する（`全種` 等の省略は不可）。

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

### 5.4 発動時効果の対応文型（実装済み）
1. `対象の出血/破裂/...の合計値3につき1、蓄力を得る（最大で7）`  
   -> `APPLY_BUFF_PER_N` 1件に変換（条件段階展開はしない）。
2. `対象の出血・破裂・亀裂の合計が10以上なら基礎威力+3`  
   -> `power_bonus.operation=FIXED` + `condition.param=状態異常スタック合計:...`。
3. `対象の出血・亀裂の合計が6あるごとに最終威力+1（最大で4）`  
   -> `power_bonus.operation=PER_N_BONUS` + `max_bonus`。
4. `（的中時）対象の出血・破裂の合計12につき1、自分のFPを回復`  
   -> `APPLY_STATE_PER_N`（`source=target` + `source_param=状態異常スタック合計:...`）。

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
1. 本書
2. 実装コード（validator / runtime）

---

## 9. Phase 2B 追加仕様（2026-05-09 実装確定）

### 9.1 `condition.source=battle`

ラウンド数を条件にするとき、`source` に `battle` を指定する。

```json
{
  "effects": [
    {
      "timing": "HIT",
      "type": "DAMAGE_BONUS",
      "target": "target",
      "value": 5,
      "condition": {
        "source": "battle",
        "param": "round",
        "operator": "GTE",
        "value": 3
      }
    }
  ]
}
```

- 現在対応している `param` は `round` のみ。
- `power_bonus_rules` の `condition` にも同様に使用可能。

### 9.2 `effects[].repeat_count`

同一エフェクトを N 回繰り返す。省略時は `1`（従来と同等）。

```json
{
  "effects": [
    {
      "timing": "HIT",
      "type": "APPLY_STATE",
      "target": "target",
      "state_name": "出血",
      "value": 2,
      "repeat_count": 3
    }
  ]
}
```

- `condition` がある場合、1 回ごとに条件を再評価する。
- `target_select=RANDOM` がある場合、1 回ごとに対象を再抽選する。
- 省略 / `1` は出力不要（JSONビルダーも自動省略）。

### 9.3 `target.type=random_single`（インテントレベル）

> スキル `effects[]` の `target` フィールドではなく、バトルインテント設定（NPC/AI向け）。

```json
{
  "target": {
    "type": "random_single",
    "random_target_scope": "enemy"
  }
}
```

- `random_target_scope`: `enemy`（既定）/ `ally` / `any`
- Resolve 開始直前に生存・配置済みスロットからランダム選択し `single_slot` に確定する。
- 候補なし時は `none` にフォールバックする。

---

## Phase3 Strict 補正事項（旧17統合）

### Phase3で有効なルール
1. `APPLY_BUFF` は `buff_id` 必須。  
2. `REMOVE_BUFF` は `buff_id` 必須。  
3. `buff_name` 単独指定はエラー。  
4. 動的命名バフ（例: `Power_Atk5`）による効果決定は行わない。  
5. 効果強度は `buff_id + data.value` で扱う。

### 既存資料で読み替える箇所
- `buff_id/buff_name` と書かれている箇所は `buff_id` のみ有効。
- `REMOVE_BUFF needs buff_name` と書かれている箇所は `buff_id` 必須へ読み替え。
- 動的パターン表（`_Atk{N}` 等）は履歴情報としてのみ扱い、現行運用には使わない。

---

## 運用ガイド補足（旧15・旧03統合）

### よく使うeffect一覧（旧15より）
- `APPLY_STATE`
- `APPLY_BUFF`
- `APPLY_BUFF_PER_N`
- `REMOVE_BUFF`
- `DAMAGE_BONUS`
- `CUSTOM_EFFECT`
- `GRANT_SKILL`
- `SUMMON_CHARACTER`

### テンプレート（貼り付け用）

**スキル特記2行版**  
1行目: 管理ラベル  
2行目:
```json
{"schema":"skill_json_rule_v2","id":"SKILL_TEMPLATE","power_bonus":[],"cost":[],"effects":[]}
```

**カテゴリ封印例**
```json
{"schema":"skill_json_rule_v2","id":"SKILL_CC_MAGIC_BLOCK","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_id":"Bu-XX","lasting":2,"data":{"skill_constraints":[{"id":"cc_magic_block","mode":"block","priority":100,"match":{"category":"魔法"},"reason":"魔法封印"}]}}]}
```

### バフ定義（buff_catalog）補足（旧03より）
- バフは `buff_id` で識別する。
- 判定ロジックは `buff_id` 基準。
- 表示は `display_name` 優先。
- `Bu-32`〜`Bu-47` はサーバ実装で固定解釈。

### GM運用ルール（旧03より）
- GMバフ付与: `buff_id` 必須
- GMバフ解除: `buff_id` 必須
- `buff_name` ベース運用は行わない

### フィールド効果 match 記法例（旧03より）
```json
{"id":"field_fp_block","mode":"block","priority":100,"match":{"cost_types":["FP"]},"reason":"FP消費技封印"}
```

### 禁止記法（Phase3）
- `buff_name` だけでバフ付与/解除する記法
- 動的命名バフ（`Power_Atk5` 等）依存
- `schema` 未指定の特記JSON
- 旧「動的命名バフ」（例: `Power_Atk5`）は運用終了。新規データ作成時は必ずセクション2のテンプレートを使用する。
