<!-- 旧: 20 / 17_Phase3_Strict_Errata / 15 / 03 を統合。20 が正本。(2026-05-09) -->

# JSON定義マニュアル（正本・統合版）

**最終更新日**: 2026-06-30
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

## 6. スキル制約（skill_constraints）

スキルの使用可否・実効コストを制御する制約ルール。`evaluate_skill_access`（`manager/battle/skill_access.py`）が評価する。

### 6.1 制約ルールの共通フォーマット

```json
{
  "id": "rule_fp_block",
  "mode": "block",
  "priority": 100,
  "match": { "cost_types": ["FP"] },
  "reason": "FP消費技封印"
}
```

```json
{
  "id": "rule_fp_plus1",
  "mode": "add_cost",
  "priority": 50,
  "match": { "cost_types": ["FP"] },
  "add_cost": [{ "type": "FP", "value": 1 }],
  "reason": "要求FP+1"
}
```

### 6.2 フィールド一覧

| フィールド | 型 | 説明 |
|---|---|---|
| `id` | string | ルール識別子（ログ/デバッグ用）。同一 id が複数ソース間で重複すると `JsonRuleV2Error` → `usable=False` |
| `mode` | string | `block`（使用禁止）または `add_cost`（コスト加算） |
| `priority` | int | 評価優先度（小さいほど先。通常 `block=100`, `add_cost=50`） |
| `match` | object | 対象スキルの絞り込み条件（空 `{}` で全スキルに命中） |
| `add_cost` | array | `mode=add_cost` 時に加算するコスト配列 |
| `reason` | string | 使用不可理由の表示文言 |

**`match` キー一覧**:

| キー | 型 | 説明 |
|---|---|---|
| `cost_types` | string[] | コスト種別一致（`"FP"` / `"MP"`） |
| `category` | string | 分類一致（`"魔法"` / `"物理"` / `"補助"` など） |
| `distance` | string | 距離一致（`"近接"` / `"遠隔"` / `"広域-個別"` / `"広域-合算"`） |
| `attribute` | string | 属性一致（`"火"` など） |
| `skill_id` | string | 特定スキルID一致 |
| `tags` | string[] | タグ一致 |
| `cost_min`, `cost_max` | int | 総コスト範囲条件 |

> **注意**: `match` のカテゴリ/距離はスキル本体の `分類`/`距離` キー（日本語キー）を優先参照し、英語キー `category`/`distance` にフォールバックする（B01 §13.5 参照）。

### 6.3 供給元ごとの保持位置

| 供給元 | 保持場所 |
|---|---|
| キャラ個別フラグ由来 | `actor.flags.skill_constraints[]` |
| バフ/デバフ由来 | `actor.special_buffs[].data.skill_constraints[]` |
| フィールド効果（直置き） | `battle_state.field_effects[].skill_constraints[]` |
| フィールドプロファイル経由 | `battle_state.stage_field_effect_profile.rules[]` |
| 戦闘外ルーム由来 | `room_state.field_effects[].skill_constraints[]` |

`field_effects` が非空なら `stage_field_effect_profile.rules` は無視される（排他）。

フィールド効果には `scope` で適用対象を絞れる: `"all"` / `"ally"` / `"enemy"` / `"except_source"`。

### 6.4 評価優先順位

1. `collect_skill_constraints` が flags → special_buffs → field_effects の順で制約を収集
2. `block` が1件でも命中 → 即 `usable=False`（`add_cost` 評価はスキップ、ただし `effective_cost` は計算される）
3. `add_cost` 命中分を累積し `effective_cost` を生成
4. `effective_cost` でリソース不足判定を実施

### 6.5 スキル特記処理JSONテンプレート（`特記処理` 列）

以下は `APPLY_BUFF` で `skill_constraints` を付与するパターン。`lasting` で有効ラウンド数を指定する。

**FP消費技封印（2R）**
```json
{"target_scope":"enemy","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_name":"CC_FP_BLOCK_2R","lasting":2,"data":{"skill_constraints":[{"id":"cc_fp_block","mode":"block","priority":100,"match":{"cost_types":["FP"]},"reason":"FP消費技封印"}]}}]}
```

**魔法分類封印（2R）**
```json
{"target_scope":"enemy","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_name":"CC_CATEGORY_MAGIC_BLOCK_2R","lasting":2,"data":{"skill_constraints":[{"id":"cc_category_magic_block","mode":"block","priority":100,"match":{"category":"魔法"},"reason":"魔法分類封印"}]}}]}
```

**物理分類封印（2R）**
```json
{"target_scope":"enemy","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_name":"CC_CATEGORY_PHYSICAL_BLOCK_2R","lasting":2,"data":{"skill_constraints":[{"id":"cc_category_physical_block","mode":"block","priority":100,"match":{"category":"物理"},"reason":"物理分類封印"}]}}]}
```

**補助分類封印（2R）**
```json
{"target_scope":"enemy","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_name":"CC_CATEGORY_SUPPORT_BLOCK_2R","lasting":2,"data":{"skill_constraints":[{"id":"cc_category_support_block","mode":"block","priority":100,"match":{"category":"補助"},"reason":"補助分類封印"}]}}]}
```

**近接封印（2R）**
```json
{"target_scope":"enemy","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_name":"CC_DISTANCE_MELEE_BLOCK_2R","lasting":2,"data":{"skill_constraints":[{"id":"cc_distance_melee_block","mode":"block","priority":100,"match":{"distance":"近接"},"reason":"近接封印"}]}}]}
```

**FPコスト+1（2R）**
```json
{"target_scope":"enemy","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_name":"CC_FP_PLUS1_2R","lasting":2,"data":{"skill_constraints":[{"id":"cc_fp_plus1","mode":"add_cost","priority":50,"match":{"cost_types":["FP"]},"add_cost":[{"type":"FP","value":1}],"reason":"FP消費+1"}]}}]}
```

**複合（魔法封印 + FP+1、2R）**
```json
{"target_scope":"enemy","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_name":"CC_MAGIC_BLOCK_AND_FP_PLUS1_2R","lasting":2,"data":{"skill_constraints":[{"id":"cc_magic_block","mode":"block","priority":100,"match":{"category":"魔法"},"reason":"魔法分類封印"},{"id":"cc_fp_plus1_combo","mode":"add_cost","priority":50,"match":{"cost_types":["FP"]},"add_cost":[{"type":"FP","value":1}],"reason":"FP消費+1"}]}}]}
```

**全封印（フォールバック確認用、1R）**
```json
{"target_scope":"enemy","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_name":"CC_ALL_BLOCK_1R","lasting":1,"data":{"skill_constraints":[{"id":"cc_all_block","mode":"block","priority":100,"match":{},"reason":"全スキル封印"}]}}]}
```

全封印時は `SYS-STRUGGLE`（どうにかもがく）のみが使用可能になる（B01 §13.2 参照）。

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

---

## 10. 2026-06 追補: SYS-STRUGGLE / state_receive_bonus（Phase 1 / 2-A）

### 10.1 SYS-STRUGGLE（システムフォールバックスキル）

`SYS-STRUGGLE` はキャラの全スキルが封印された場合のフォールバック専用スキル。
通常のスキルカタログ（skills_cache.json）には含まれず、`manager/battle/system_skills.py` に定義される。

- スキル JSON には記載しない（GM・プレイヤーが明示的に取得するスキルではない）
- `list_usable_skill_ids(allow_fallback=True)` が候補ゼロ時のみ返す
- 封印効果（`skill_constraints`）の対象外

### 10.2 バフ定義の `state_receive_bonus`（受け手側状態異常補正）

buff_catalog の `effect` に `state_receive_bonus` リストを定義すると、
このバフを持つキャラが状態異常を受ける際に補正が加算される。

```json
{
  "id": "Bu-29",
  "name": "震盪",
  "effect": {
    "state_receive_bonus": [
      {
        "stat": "破裂",
        "operation": "FIXED",
        "value": 1,
        "consume": false
      }
    ]
  },
  "default_duration": 3
}
```

**フィールド仕様**:

| フィールド | 型 | 説明 |
|---|---|---|
| `stat` | string | 対象の状態異常名（例: `"破裂"`, `"出血"`） |
| `operation` | string | `"FIXED"`（加算値）のみ現行実装 |
| `value` | number | 補正量（正値のみ有効。負値付与には補正しない） |
| `consume` | bool | `true` にすると、発動後にバフを消費（1回限り） |

**注意**:
- `APPLY_STATE` / `APPLY_STATE_PER_N` の正値付与時のみ適用（負値削減には不適用）
- 付与側 `state_bonus` と受け手側 `state_receive_bonus` は合算される
- `Bu-29`（震盪）の再付与は `count` 加算・`lasting` 維持の専用挙動（B01 §5.4 参照）

---

## 11. 2026-06 追補: Select/Resolve 効果タイミング

Select/Resolve は宣言フェーズ（Select）と解決フェーズ（Resolve）で進行する。新規スキル JSON の `effects[].timing` は、原則として下表の基準で選ぶ。

| timing | 実行時期 | 主な用途 |
|---|---|---|
| `RESOLVE_START` | Resolve 開始直後、コミット済みスロットごと | 解決全体の開始時処理 |
| `PRE_MATCH` | 各マッチ開始時 | 使用前の状態付与、使用可否・条件補助 |
| `BEFORE_POWER_ROLL` | 威力ロール直前 | 威力ロール直前の補正 |
| `END_MATCH` | マッチ結果確定直後、`WIN` / `LOSE` より前 | 勝敗に依存しないマッチ終了時処理 |
| `WIN` | 勝者側の結果処理 | 勝利時のみの自己強化・追加効果 |
| `LOSE` | 敗者側の結果処理 | 敗北時のみの自己強化・追加効果 |
| `UNOPPOSED` | 一方攻撃の命中処理前 | 一方攻撃専用効果 |
| `HIT` | 命中時 | 命中で付与される状態異常・追加効果 |
| `AFTER_DAMAGE_APPLY` | HP 反映直後 | 実ダメージ量を参照する追撃・回復・ログ処理 |
| `RESOLVE_STEP_END` | 1 マッチ/一方攻撃/広域処理の表示完了時 | 1 処理単位の後処理 |
| `RESOLVE_END` | Resolve 全処理完了時 | 解決フェーズ終了時の処理 |
| `END_ROUND` | ラウンド終了時 | ラウンド終了処理 |

マッチ結果後の順序は `END_MATCH` → `WIN` → `LOSE` → 荊棘処理 → スキルダメージ判定用の状態参照 → `HIT` → HP反映 → `AFTER_DAMAGE_APPLY` を基準とする。この基準は `one_sided` / `clash` / `mass_individual` のように単一の攻防マッチへ分解できる処理に適用する。`mass_summation` は複数防御側の合算結果を扱うため、`WIN` / `LOSE` の対象単位を決めるまで集団合算固有処理として扱う。

亀裂など「スキルダメージ判定で参照される状態」を同じマッチのダメージへ乗せたい場合は、`END_MATCH` / `WIN` / `LOSE` で付与する。`HIT` / `AFTER_DAMAGE_APPLY` で付与した亀裂は、その付与を発生させた同じダメージには乗らない。

荊棘重絡で同じマッチの荊棘消滅を肩代わりしたい場合も、`END_MATCH` / `WIN` / `LOSE` 以前に付与する。`HIT` で付与した荊棘重絡は、そのマッチの荊棘処理には間に合わない。

`AFTER_DAMAGE_APPLY` の `base_damage` には、one-sided / clash ともに実際に HP へ反映されたダメージ量を渡す。防御・回避などでダメージが発生しなかった側は 0 になる。

2026-06-30 時点の現行キャッシュ（`data/cache/skills_cache.json`, `radiance_skills_cache.json`, `passives_cache.json`）には `END_MATCH` 効果は存在しないため、既存本番データの移行は不要。旧 migration log には過去データとして `END_MATCH` が残るが、現行キャッシュの挙動には影響しない。
