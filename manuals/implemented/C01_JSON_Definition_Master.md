<!-- 旧: 20 / 17_Phase3_Strict_Errata / 15 / 03 を統合。20 が正本。(2026-05-09) -->

# JSON定義マニュアル（正本・統合版）

**最終更新日**: 2026-11-10（計画60 PR60-14：マスター7種類のDB管理）
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
入力場所はマスターデータの「スキル」→編集→「文章から効果を作る」。コスト・発動時効果・特記の文章を決まった文型で読み、特記処理を生成する。PR60-23 の読み取り規則と往復の比較は末尾の追補を参照。認識しない行は列・原文・理由を表示して特記処理を維持する。成功後はフォーム・JSONで内容を確かめ、保存・申請・承認を行う。早見表は同タブの折りたたみから開き、JSONタブでコピーできる。

旧ビルダーのページ・`/json_builder`・`/api/json_builder_reference`・`/api/json_nl_builder_audit` は廃止。読み取りは `static/js/master_data/skill_text.js` が担当する。

### 5.1 入力列
1. コスト
2. 発動時効果
3. 特記
4. タグ（任意）
5. `id`（任意）

### 5.2 運用ルール
1. `的中時` を使用する。
2. `中時` / `命中時` は禁止語彙（エラー）。
3. 文区切りは `。` と改行のみ。
4. 変換不能時は全停止。
5. JSONタブで表示中のスキル全体を整形JSONのままコピーする。

### 5.3 検査と履歴
文章の読み取り専用のHTTP監査ログは廃止した。下書きの保存・申請・承認の検査と公開履歴は管理APIの既存処理を使う。

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
- 省略 / `1` は出力不要（文章から作るでも従来どおり自動省略）。

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
- 正本はDBの `catalog_entries`（`kind="buff"`）。空のときだけ `data/cache/buff_catalog_cache.json` の53件を履歴とともに取り込む。Sheetsからは更新しない。修正は制作者の下書き→申請→アプリ管理者の承認を通す。管理APIとロビーのマスターデータ画面で用語・バフを扱う（計画60 PR60-8）。
- 公開IDは `Bu-` + 2桁以上の数字。項目は必須の内部名 `name`、`display_name`・`description`・`flavor`（文字列、既定空）、`effect`（オブジェクト、既定 `{}`）、`default_duration`（整数、既定1）。`-1` は解除まで、1以上はラウンド数。内部名はバフ間で一意で、公開後は変更できない。表示名は変更できる。
- 検査は問題の一覧（`level, field, message`）を返す。書きかけは保存でき、申請では形・用語参照先の欠落を止め、承認では仮IDも止める。廃止用語への参照は注意だけ。`effect.type="plugin"` のバフは、そのバフIDが `plugins/buffs/` の `BUFF_IDS` に登録されている必要がある（戦闘はプラグインをバフIDで呼び、`effect.name` は使わない）。新規の仮IDの下書きは申請まで注意、承認で止める。それ以外の効果の内部構造はここでは検査しない。
- 配信・戦闘・アイテムはDBから読み込む共有辞書 `all_buff_data` を参照する。廃止後も辞書に残り `deprecated: true` が付き、既存の戦闘で使える。静的定義と動的命名バフの処理は変更しない。
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

マッチ結果後の順序は `END_MATCH` → `WIN` → `LOSE` → 荊棘処理 → スキルダメージ判定用の状態参照 → `HIT` → HP反映 → `AFTER_DAMAGE_APPLY` を基準とする。この基準は `one_sided` / `clash` / `mass_individual` に適用する。`mass_summation` は複数防御側の合算結果を扱うため、攻撃側スキルは1回、参加防御側スキルは参加者ごとに1回として `END_MATCH` / `WIN` / `LOSE` を評価する。

亀裂など「スキルダメージ判定で参照される状態」を同じマッチのダメージへ乗せたい場合は、`END_MATCH` / `WIN` / `LOSE` で付与する。`HIT` / `AFTER_DAMAGE_APPLY` で付与した亀裂は、その付与を発生させた同じダメージには乗らない。

荊棘重絡で同じマッチの荊棘消滅を肩代わりしたい場合も、`END_MATCH` / `WIN` / `LOSE` 以前に付与する。`HIT` で付与した荊棘重絡は、そのマッチの荊棘処理には間に合わない。

引き分けでは攻防双方の `END_MATCH` のみを実行し、`WIN` / `LOSE` は実行しない。

`AFTER_DAMAGE_APPLY` の `base_damage` には、one-sided / clash / mass_summation ともに実際に HP へ反映されたダメージ量を渡す。防御・回避などでダメージが発生しなかった側は 0 になる。

`mass_summation` では `attacker_win` 時の攻撃側効果は代表対象（実ダメージ対象の先頭）に対して実行する。`defender_win` 時は参加防御側スキルの `WIN` / `AFTER_DAMAGE_APPLY` を参加者ごとに攻撃者へ実行し、攻撃側スキルの `LOSE` は1回だけ実行する。`draw` では攻防双方の `END_MATCH` のみを実行する。

`同時攻撃` / `相互命中` は JSON timing として追加しない。相互指定は `clash` の `attacker_win` / `defender_win` / `draw` に正規化されるため、両者へダメージを出したい場合は `HIT` / `AFTER_DAMAGE_APPLY` / `CUSTOM_DAMAGE` などの効果で表現する。

`THORNS` と `SKILL_DAMAGE_CALC` は JSON の `timing` としては公開しない。`THORNS` は荊棘のシステム処理、`SKILL_DAMAGE_CALC` は亀裂などを参照する内部境界名として扱う。スキル JSON でこの境界より前に状態を反映したい場合は `END_MATCH` / `WIN` / `LOSE` を使い、境界より後の命中時効果は `HIT` を使う。

2026-06-30 時点の現行キャッシュのうち `radiance_skills_cache.json` と `passives_cache.json` には `END_MATCH` 効果は存在しない。`skills_cache.json` には E-06（SKILL_E06）が `END_MATCH` タイミングを持ち、draw 時も `_run_select_resolve_result_timing` 経由で正常発火する。旧 migration log には過去データとして `END_MATCH` が残るが、現行キャッシュの挙動には影響しない。

---

## 12. 2026-07 追補: スキルカタログ lint / 相場レポート生成ツール

計画書31（2026-07-08 実装完了・削除済み）により、スキルJSON定義（`特記処理`＝JSON rule v2）のスキーマ検証と相場レポート生成を行う統合CLIを整備した。2026-07-20に、スキル追加のたびにF02の生成表を同期する運用を廃止し、相場レポートをオンデマンド確認へ変更した。

### 12.1 ツールの所在と使い方

CLI入口は `scripts/skill_catalog_tool.py`。サブコマンド2つ。キャッシュ読込・ERROR検証の共通処理は `manager/skill_catalog_validation.py` に集約し、マスター更新とCLIが同じ関数を使う。アプリ本体はCLIモジュールをimportせず、引数処理・標準出力の設定・任意WARN・相場レポートはCLI側へ置く。

```bash
python scripts/skill_catalog_tool.py lint                    # スキーマ検証（ERRORのみ）
python scripts/skill_catalog_tool.py lint --warn             # 相場逸脱WARNも任意確認
python scripts/skill_catalog_tool.py lint --json              # JSON形式で出力
python scripts/skill_catalog_tool.py build-market-rate         # 現在の相場レポートを標準出力
```

### 12.2 lint（ERROR / WARN の2段階、WARNは既定で非表示）

- **ERROR（exit 1、常時検査）**: `manager/json_rule_v2.py` の `extract_and_normalize_skill_rule_data(strict=True)` と `normalize_skill_constraints_rows`（`effect.data.skill_constraints` に埋め込まれる封印/コスト増ルール、本書 §6 参照）を全スキルに適用し、JSONパース不能・schema欠落・buff_id/skill_constraints参照切れを検出する。**これはデータ破損の検出であり、CIで常に実行される。管理APIでは申請・承認時に同じ厳密な読み取りを使う。**
- **WARN（exit codeに影響しない、`--warn` 指定時のみ計算・表示）**: `manuals/implemented/F02_Battle_Balance_Designer_Skill_Manual.md` の「スキルバランス調整基準（確定版）」からの相場逸脱を検出する。カテゴリは `power_stage`（期待威力が段階帯から乖離）・`cost`（使用コストが基準から乖離）・`state_value`（状態異常付与量が実勢レンジ外、HIT timingのみ判定対象）・`acquire_cost`（未承認の取得3以上）・`action_economy`（`USE_SKILL_AGAIN`/`SUMMON_CHARACTER`/`GRANT_SKILL`の未承認保有者）。
  - **運用方針**: データが壊れていなければ相場の多少の逸脱は運用上気にしない、という判断により、WARNはCIには組み込んでいない（`lint`のデフォルト実行では計算すらしない）。任意でスキルバランスを見直したい時だけ `python scripts/skill_catalog_tool.py lint --warn` を手動実行する。
- 相場基準値・承認済み例外は `scripts/skill_catalog_tool.py` 内の定数（`POWER_STAGE_BASELINE`・`COST_BASELINE`・`STATE_VALUE_RANGE`・`ACQUIRE_HIGH_APPROVED`・`ACTION_ECONOMY_APPROVED`・`WARN_ALLOWLIST`）で管理する（機械判定用の設定であり、F02の確定基準セクションが引き続き人手管理の正本）。F02の確定基準を更新した場合はこれらの定数も見直すこと。
- `power_bonus[]` や条件付き `DAMAGE_BONUS`/`MODIFY_ROLL` を持つスキルは、単純な「基礎威力+ダイス期待値」では実質威力を表せないため `power_stage` 判定の対象外とする。

### 12.3 オンデマンド相場レポート（build-market-rate）

- `data/cache/skills_cache.json` から、現行カタログの構成・期待威力・コスト・効果タイミング・状態異常付与量・特殊効果の使用実績をMarkdownで標準出力する。F02は変更しない。
- レポートは分析時点の参考情報であり、ファイルへの転記・同期・コミットは不要。スキル追加や公開のたびに実行する必要もない。
- 大量追加後、F02の確定基準を見直すとき、または個別スキルを既存相場と比較したいときに任意実行する。日常CIでは実行しない。

### 12.4 管理API・CIとの関係

検証処理の定義元は `manager/skill_catalog_validation.py`。相場の注意は `manager/skill_catalog_warnings.py` に置き、CLIと管理用検査で共用する。管理APIの申請・承認では厳密な読み取りと参照検査のERRORで公開を止め、相場逸脱はWARNINGとして下書きの `problems` に返す。

CI（`.github/workflows/skill-smoke.yml`）はファイルに対する `lint`（`--warn` なし）を必須検査とする。`--update` とSheetsからの取得は廃止した。相場レポートは任意実行に留める。

### 12.5 関連テスト

`tests/test_skill_catalog_tool_lint.py`・`tests/test_skill_catalog_tool_warn.py`・`tests/test_skill_catalog_tool_cli.py`・`tests/test_skill_catalog_tool_market_rate.py`・`tests/test_data_manager_lint_hook.py`。`test_skill_catalog_tool_cli.py` は「`lint` のデフォルト実行はWARNを計算しない／`--warn` 指定時のみ計算する／WARNの有無にかかわらずexit codeは0のまま」と「相場レポートは標準出力するだけ」という運用方針を回帰検証する。`tests/test_skill_catalog_tool_market_rate.py` はF02との同期ではなく、現在のキャッシュからレポートを正しく組み立てることを検証する。

---

## 13. キャラクタータグ（2026-07-20実装）

キャラクターの固定分類は、キャラクターJSON直下の`tag_ids`へ保存する。一時的に無効化されたタグは削除せず、`disabled_tag_ids`にも格納する。

```json
{
  "tag_ids": ["出身:シンシア", "種別:瓦礫"],
  "disabled_tag_ids": ["種別:瓦礫"]
}
```

- 両フィールドは`string[]`。欠損・配列以外は空配列として扱う。
- 前後空白と空文字を除去し、最初の出現順を保って完全一致の重複を除去する。
- `disabled_tag_ids`は`tag_ids`の部分集合へ正規化する。
- 有効タグ取得ヘルパーは`tag_ids - disabled_tag_ids`を返す。conditionとPvE行動チャートの`required_tag_ids`は有効タグだけを参照する。
- GMが作成するscenarioキャラクターの自由タグは1件25文字以内、改行不可、個数上限なし。
- プレイヤーキャラクターの送信JSONにある任意タグと無効化指定は信用しない。出身、ボーナス国、取得済み輝化スキルからサーバー側で再構築する。
- 出身とボーナス国はそれぞれ`出身:国名`を生成する。同じ国なら重複を1件へまとめる。
- 輝化スキルの付与タグはDBのトップレベル`granted_tag_ids`に文字列の配列で持ち、公開API・キャッシュも同じ形とする。旧Sheetsの区切り文字列の読み取りは廃止した。
- 独立したタグマスターは持たない。

正規化・派生処理の正本は`manager/character_tags.py`。持ちキャラ作成・更新、ルーム投入、戦闘専用プリセット、ルームプリセット、召喚で同じデータ契約を維持する。プレイヤーキャラクターの保存・投入時には、取得済み輝化スキルのコスト合計が通過点を超えていないこともサーバー側で検証する。

関連テストは`tests/test_character_tags.py`、`tests/test_owned_characters_api.py`、`tests/test_add_character_owned_character.py`、`tests/test_room_preset_apply.py`。

---

## 14. 文字列conditionと最大HPダメージ（2026-07-20実装）

キャラクターを参照するconditionでは、`param`に`name`、`baseName`、`tag_ids`を指定できる。

- `EQUALS`: 両辺が数値として解釈できる場合は数値一致。それ以外のスカラー値は文字列の完全一致。
- `CONTAINS`: 参照値が文字列なら部分一致、配列なら要素の完全一致。
- `tag_ids`: `disabled_tag_ids`を除いた有効タグ配列を参照する。
- 未知param、対象不在、型に合わない演算はfalseとする。

```json
{
  "source": "target",
  "param": "tag_ids",
  "operator": "CONTAINS",
  "value": "種別:瓦礫"
}
```

`CUSTOM_EFFECT`の`DEAL_TARGET_MAX_HP_DAMAGE`は、対象の`maxHp`と同じ値のダメージを即時に与える。与ダメージ倍率、被ダメージ倍率、軽減を適用しない。対象不在、`maxHp`不明、0以下では不発となる。

```json
{
  "timing": "HIT",
  "type": "CUSTOM_EFFECT",
  "target": "target",
  "value": "DEAL_TARGET_MAX_HP_DAMAGE"
}
```

この効果は通常のconditionと組み合わせられる。HPが既に0の対象へ適用しても死亡時効果は再発しない。

---

## 15. 召喚戦闘オブジェクトとフィールド集計（2026-07-31実装）

### 15.1 召喚テンプレートの特記JSON

召喚テンプレートの`特記JSON`では、次のキーを正式に使用できる。

```json
{
  "tag_ids": ["瓦礫"],
  "disabled_tag_ids": [],
  "SPassive": ["Pa-07"],
  "special_buffs": [],
  "flags": {}
}
```

文字列配列は空文字を除いて順序を保ったまま重複を除く。`SPassive`は特記JSONを先、専用の「パッシブスキル」列を後として結合する。専用列が空でも特記JSON側を消さない。不正な型はテンプレートIDとキー名を警告し、安全な空値へ変換する。

### 15.2 非行動設定

特殊パッシブの効果本体へ次を指定すると、通常行動スロットを生成しない。

```json
{"action_slot_mode":"none"}
```

対象選択用の内部アンカーは別途生成されるため、HPを持つ攻撃対象としては残る。

### 15.3 死亡原因の参照

`on_death`では次を使用できる。

- condition: `source="death_context"`, `param="killer_team"`。スキルによる死亡原因キャラクターの陣営を`ally`または`enemy`で返す。
- target: `KILLER`。スキルでHPを0にしたキャラクター。
- target: `KILLER_TEAM`。`KILLER`と同陣営で、配置済み・生存中・未離脱の全キャラクター。

死亡原因またはスキルIDがない場合は対象なし・条件falseとなる。

### 15.4 `SCHEDULE_EFFECT`

`RESOLVE_START`で予約し、指定ラウンド後のラウンド開始時にnested effectを実行する。

```json
{
  "timing": "RESOLVE_START",
  "type": "SCHEDULE_EFFECT",
  "target": "self",
  "round_offset": 1,
  "repeat_count": 2,
  "effect": {
    "type": "SUMMON_CHARACTER",
    "summon_template_id": "U-02"
  }
}
```

予約は発生元スロット・スキル・ラウンド・nested effectから作る一意キーで重複を防止する。発生元が実行予定ラウンドまでに戦闘不能になっても、成立済みの予約は実行する。現時点のnested effect実装は`SUMMON_CHARACTER`。

### 15.5 フィールドキャラクターフィルター

`target="FILTERED_CHARACTERS"`または`APPLY_BUFF_FROM_CHARACTER_COUNT`では、次の`character_filter`を使う。

```json
{
  "team": "same_team",
  "required_tag_ids": ["瓦礫"],
  "excluded_tag_ids": [],
  "alive": true,
  "placed": true
}
```

`team`は`same_team`、`opposing_team`、`any`に対応する。タグは`disabled_tag_ids`を除いた有効タグで完全一致判定する。

`APPLY_BUFF_FROM_CHARACTER_COUNT`は一致数×`value_per_character`を、指定バフの`data.power_bonus`（既定`apply_to="final"`）へ設定する。

```json
{
  "timing": "RESOLVE_START",
  "type": "APPLY_BUFF_FROM_CHARACTER_COUNT",
  "target": "self",
  "buff_name": "瓦礫吸収",
  "lasting": 1,
  "delay": 0,
  "value_per_character": 1,
  "apply_to": "final",
  "character_filter": {
    "team": "same_team",
    "required_tag_ids": ["瓦礫"],
    "alive": true,
    "placed": true
  }
}
```

---

## 16. シナリオNo.2用JSON完成例と読み方（2026-07-31）

この節は、シナリオNo.2『瓦礫で鋳るは魔の鋼』で追加したデータを、当時の項目名と効果JSONの完成形で示す。現在はSheetsへ貼り付けず、管理APIでDBの下書きに対応する項目を入れ、承認して公開する。
JSONを読むときは、原則として次の順番で確認する。

1. JSON全体が何の定義かを、対象の種類と`schema`で確認する。
2. スキルJSONでは、誰を選べるかを`target_scope`で確認する。
3. `effects`を先頭から読み、各効果の発動時期を`timing`で確認する。
4. 各効果の処理を`type`、処理対象を`target`で確認する。
5. `condition`や`character_filter`があれば、処理対象をさらに絞り込む。
6. `value`、`lasting`、`delay`、`repeat_count`などの数値を最後に確認する。

### 16.1 同じ「タグ」に見えるキーの区別

| 記法 | 意味 |
|---|---|
| `tags` | スキル自体の分類・挙動を表す文字列配列 |
| `tag_ids` | キャラクターが持つ固定分類。例: `瓦礫` |
| `disabled_tag_ids` | 一時的に無効化されているキャラクタータグ |
| `required_tag_ids` | フィルター対象に要求するキャラクタータグ |
| `excluded_tag_ids` | フィルター対象から除外するキャラクタータグ |

`tag_ids`を条件から読むときは、`disabled_tag_ids`に含まれる値を除いた有効タグだけを使う。

### 16.2 `Pa-07 魔力の籠った鉄塊`

入力先は特殊パッシブシートの「効果JSON」セル。

```json
{"action_slot_mode":"none","on_death":[{"timing":"IMMEDIATE","type":"APPLY_BUFF","target":"KILLER_TEAM","buff_id":"Bu-51","lasting":2,"delay":1,"condition":{"source":"death_context","param":"killer_team","operator":"EQUALS","value":"ally"}},{"timing":"IMMEDIATE","type":"APPLY_BUFF","target":"KILLER","buff_id":"Bu-52","lasting":3,"delay":1,"condition":{"source":"death_context","param":"killer_team","operator":"EQUALS","value":"enemy"}}]}
```

上から順に、次のように読む。

- `action_slot_mode:"none"`: このパッシブを持つキャラクターは通常行動スロットを生成しない。攻撃対象としては残る。
- `on_death`: HPが0になったときに評価する効果の配列。
- 1件目の`condition`: スキルによる破壊者が味方陣営ならtrue。
- 1件目の`target:"KILLER_TEAM"`: 破壊者と同陣営の配置済み・生存中・未離脱キャラクター全員。
- 1件目の`APPLY_BUFF`: `Bu-51`を2ラウンド、1ラウンド遅延で付与する。
- 2件目の`condition`: スキルによる破壊者が敵陣営ならtrue。
- 2件目の`target:"KILLER"`: 破壊したキャラクター本人。
- 2件目の`APPLY_BUFF`: `Bu-52`を3ラウンド、1ラウンド遅延で付与する。

`delay:1`により、どちらのバフも付与された次のラウンドから有効になる。死亡原因にスキルIDがない場合、この分岐は発動しない。

### 16.3 `U-02 鉄交じりの瓦礫`

召喚テンプレートシートでは、専用列と特記JSONを分けて入力する。

| 入力列 | 値 |
|---|---|
| パッシブスキル | `Pa-07` |
| 特記JSON | `{"tag_ids":["瓦礫"]}` |

特記JSONだけへまとめる場合は、次の形式も使用できる。

```json
{"tag_ids":["瓦礫"],"SPassive":["Pa-07"]}
```

専用の「パッシブスキル」列と`SPassive`の両方に同じIDがあっても、ロード時に完全一致の重複を除去する。

### 16.4 `Bu-51 鉄の恩恵`と`Bu-52 鉄の剛力`

`Bu-51`の効果JSON:

```json
{"power_bonus":[{"operation":"FIXED","value":2,"apply_to":"final"}]}
```

標準持続時間は`2`。

`Bu-52`の効果JSON:

```json
{"power_bonus":[{"operation":"FIXED","value":1,"apply_to":"final"}]}
```

標準持続時間は`3`。

`operation:"FIXED"`は固定値加算、`apply_to:"final"`は最終威力への適用を表す。`Pa-07`から付与する場合は、パッシブ側の`lasting`がその付与の継続時間となり、バフ側の標準持続時間は直接付与時の既定値として残る。

### 16.5 `E-33 鉄根刺突`

入力先はスキルシートの「特記JSON」または「特記処理」セル。

```json
{"schema":"skill_json_rule_v2","id":"SKILL_E33","target_scope":"opposing_team","power_bonus":[],"cost":[],"effects":[{"timing":"RESOLVE_START","type":"APPLY_BUFF_FROM_CHARACTER_COUNT","target":"self","buff_name":"瓦礫吸収","lasting":1,"delay":0,"value_per_character":1,"apply_to":"final","character_filter":{"team":"same_team","required_tag_ids":["瓦礫"],"alive":true,"placed":true}},{"timing":"RESOLVE_START","type":"CUSTOM_EFFECT","target":"FILTERED_CHARACTERS","value":"DEAL_TARGET_MAX_HP_DAMAGE","character_filter":{"team":"same_team","required_tag_ids":["瓦礫"],"alive":true,"placed":true}},{"timing":"HIT","type":"APPLY_STATE","target":"target","state_name":"破裂","value":10},{"timing":"HIT","type":"APPLY_STATE","target":"target","state_name":"亀裂","value":3,"rounds":3}]}
```

`effects`は次の4件。

1. `RESOLVE_START`で、使用者と同陣営にいる生存・配置済みの`瓦礫`を数え、1体につき最終威力を+1する一時バフを使用者へ付与する。
2. 同じ条件に一致する全キャラクターへ最大HPと同値のダメージを与え、瓦礫を一括破壊する。
3. スキルが対象へ的中したとき、《破裂》10を付与する。
4. スキルが対象へ的中したとき、《亀裂》3を3ラウンド付与する。

ここでの`buff_name`は、バフ図鑑をID参照して付与する通常の`APPLY_BUFF`とは異なる。`APPLY_BUFF_FROM_CHARACTER_COUNT`が、その場で可変値の一時バフを作るための表示名である。

### 16.6 `E-34 暴れ回る`

```json
{"schema":"skill_json_rule_v2","id":"SKILL_E34","target_scope":"opposing_team","power_bonus":[],"cost":[],"effects":[{"timing":"RESOLVE_START","type":"SCHEDULE_EFFECT","target":"self","round_offset":1,"repeat_count":2,"effect":{"type":"SUMMON_CHARACTER","summon_template_id":"U-02"}}]}
```

- `SCHEDULE_EFFECT`: 内側の`effect`を将来ラウンドへ予約する。
- `round_offset:1`: 使用した次のラウンド開始時に実行する。
- `repeat_count:2`: 内側の召喚効果を2回実行する。
- `summon_template_id:"U-02"`: `鉄交じりの瓦礫`を召喚する。

同じ予約の再処理では召喚数を増やさない。使用者が次ラウンドまでに戦闘不能になっても、成立済みの予約は実行する。

### 16.7 `E-35 瓦礫を狙う`

```json
{"schema":"skill_json_rule_v2","id":"SKILL_E35","target_scope":"any","power_bonus":[],"cost":[],"effects":[{"timing":"HIT","type":"DAMAGE_BONUS","target":"target","value":20,"condition":{"source":"target","param":"tag_ids","operator":"CONTAINS","value":"瓦礫"}}]}
```

- `target_scope:"any"`: 味方・敵のどちらも対象に選べる。
- `timing:"HIT"`: 対象への的中時に評価する。
- `type:"DAMAGE_BONUS"`: 通常ダメージへ追加ダメージを加える。
- `condition.source:"target"`: 条件の参照元は攻撃対象。
- `param:"tag_ids"`と`operator:"CONTAINS"`: 対象の有効タグ配列に指定値が含まれるかを判定する。
- `value:"瓦礫"`: 要求するタグ。
- effect直下の`value:20`: 条件成立時の追加ダメージ。

対象が`瓦礫`タグを持たない場合、通常部分だけを解決し、追加20ダメージは発生しない。

### 16.8 入力後の確認

本番のマスターデータ7種類の公開後は `--pull` を実行する。

```bash
python app.py --pull
python scripts/skill_catalog_tool.py lint
```

その後、キャッシュで次を確認する。

- `data/cache/passives_cache.json`: `Pa-07.effect`
- `data/cache/summon_templates_cache.json`: `U-02.tag_ids`と`U-02.SPassive`
- `data/cache/buff_catalog_cache.json`: `Bu-51`と`Bu-52`
- `data/cache/skills_cache.json`: `E-33`、`E-34`、`E-35`

## 17. 効果スキーマ配信 API（計画60 PR60-1）

`GET /api/effect_schemas` は認証なしで `{"effect_types": EFFECT_SCHEMAS, "custom_effects": CUSTOM_EFFECT_SCHEMAS, "common_fields": COMMON_EFFECT_FIELDS, "target_labels": TARGET_LABELS}` を返す。DB・ルーム状態は変更しない。
各効果タイプは `label`・`description`・`internal`・`fields`・`summary`・`example` を持つ。`fields` は共通キーを除く effect のキーを記載し、入れ子は `data.count` のように表す。型は `int`・`number`・`string`・`bool`・`json`・`state_ref`・`buff_ref`・`skill_ref`・`summon_ref`・`glossary_ref`。
`required` は現行の入力契約を表す。代替キーが使える場合は説明へ併記する。このAPIは保存前検査を追加しない。
`internal=True` は `FORCE_UNOPPOSED`・`APPLY_FISSURE_BUFFED` のみ。ほかは `False`。名前別のカスタム効果は `label`・`description`・`fields` を持つ。
`render_effect_summary(effect)` は説明テンプレートへ値を埋め、対象を日本語化し、不足値を `?` とする。未知の効果タイプも `?` を返す。入れ子キーを読み、値を再びテンプレートとして解釈しない。
スキル専用画面は効果スキーマをAPIから読み込む。文章の読み取りは §5、保存・申請・承認の検査は管理APIで行う。

## スキルのDB正本・管理API（計画60 PR60-10）

通常スキル138件の正本は `catalog_entries` のkind=skill。空のときだけskills_cache.jsonから初回取り込みする。SYS-のシステムスキルはDBに保存せず、辞書を更新するたびにコード定義から追加する。管理APIの権限・保存・申請・承認は用語・バフと共通。専用画面はマスターデータの「スキル」から開く（PR60-11、E02 Part 15）。

保存項目は必須のデフォルト名称、チャットパレット、分類（物理・魔法・補助・防御・回避）、距離（近接・遠隔・広域-個別・広域-合算・空）、属性（打撃・斬撃・貫通・空）、取得コスト・基礎威力・ダイス威力・コスト・特記・発動時効果（文字列）、特記処理（オブジェクト、既定{}）。スキルIDとtagsは保存しない。配信では特記処理をJSON文字列（空の{}は空文字列）に戻し、分類・特記処理.tags・発動時効果の[即時発動]から従来と同じ順でtagsを作る。deprecatedは廃止時だけ付け、既存の配信形式を保つ。

新規下書きではid_prefix（Ps・Pb・Pp・Ms・Mb・Mp・D・B・C・E）が必須。next_id?prefix=Psでそのカテゴリの次の番号を求める。承認の正式IDは選んだ接頭辞と一致させる。既存スキルの下書きは公開IDから接頭辞を決める。

形と特記処理の厳密な読み取り、バフIDの参照切れは申請を止め、未公開の仮IDは承認を止める。X-のバフ下書きは申請まで参照でき、バフ承認時にスキル下書き内の仮IDも置き換える。廃止バフ・未知のbuff_name・相場逸脱・定型と異なるチャットパレットは注意だけ。定型は基礎威力＋ダイス威力＋物理/魔法補正の1d項＋【ID 名称】で、物理・魔法以外は補正項を付けない。効果の共通項目timing・targetの候補はjson_rule_v2の定義を正とし、conditionはsource・param・operator・valueで表す。効果スキーマAPIにも共通項目を返す。

参照箇所は他スキル・アイテム・特殊パッシブ・輝化スキル・召喚テンプレートの値（JSON文字列内も含む）から求める。公開・廃止・復元後は共有辞書を更新し、catalog_updatedで画面側のallSkillDataを読み直す。読み終わるまで古い辞書を保ち、古い通信応答で新しい辞書を上書きしない。

新規スキルのチャットパレット等に含まれる自身の仮IDは、承認時に選ばれた正式IDへ置き換えてから公開検査を行う（PR60-11）。他の未公開の仮IDは引き続き承認を止める。

## 残る4種類のDB管理（計画60 PR60-14）

アイテム（item/I-・3件）、特殊パッシブ（passive/Pa-・8件）、輝化スキル（radiance/S-・9件）、召喚テンプレート（summon/U-・3件）もcatalog_entriesを正本とする。各種類が空の場合だけ種類別キャッシュから履歴付きで取り込む。公開APIの辞書の形はキャッシュと同じで、前3種はid、召喚はbaseNameを配信時に付ける。管理用payloadにはIDを含めない。

項目は計画60 §5.13の定義に従う。名前は必須。itemはdescription/flavor/consumable/usable/round_limit/effect、passiveはcost/description/flavor/effect、radianceは同項目にduration/granted_tag_idsを持つ。summonは現行キャッシュの19項目を型付きで持つ。効果のオブジェクトの内容と戦闘処理は変更しない。

召喚テンプレートの項目は次のとおり。

| 項目 | 型 |
|---|---|
| `baseName` | 配信時の正式ID（管理payloadには含めない） |
| `name` | 文字列、必須 |
| `hp`・`maxHp`・`mp`・`maxMp` | 整数 |
| `initial_skill_ids`・`hidden_skills`・`SPassive`・`radiance_skills` | 文字列の配列 |
| `inventory` | オブジェクト |
| `summon_duration_mode` | 文字列 |
| `summon_duration` | 整数 |
| `allow_duplicate_same_team` | 真偽値 |
| `params`・`special_buffs` | 配列 |
| `tag_ids`・`disabled_tag_ids` | 文字列の配列 |
| `flags` | オブジェクト |

召喚のinitial_skill_ids・hidden_skillsはskill、SPassiveはpassive、radiance_skillsはradianceを参照する。公開版・下書きのどちらにも存在しないIDはエラー、廃止版の参照は注意。承認時は未解決のX-を禁止する。本文の用語リンク検査は全種類共通。使われている所は公開辞書を走査して求め、ファイルやローダーの古いキャッシュへ戻らない。公開・廃止・復元後は次の読み出しから新しい公開辞書を使う。

### 管理画面の条件付き表示（計画60 PR60-17）

`EFFECT_SCHEMAS` の各fieldに任意の `visible_when` を持たせる。形は効果内のパスと一致する値の辞書（例：`{"state_name":"亀裂"}`）。すべて一致するときだけ欄を表示する。`APPLY_STATE.rounds`・`source` に適用し、`/api/effect_schemas` でそのまま配信する。表示用の印だけで、実行・検査・保存の意味は変えない。隠れた値も削除しない。

### 効果スキーマの系統（計画60 PR60-19）

EFFECT_SCHEMASの各タイプはgroupを持つ。配信と管理画面だけの情報で、戦闘の実行・保存・読み取り規則は変えない。系統と表示順は「状態異常」「バフ」「スタック」「威力・ロール」「ダメージ・回復」「行動・進行」「特殊」。管理画面の効果タイプはこの系統でまとめる。

### コスト欄と補正を適用しない特記（計画60 PR60-20）

スキルの文章の欄は `コスト`・`発動時効果`・`特記`。取得に使う経験値は `取得コスト`、戦闘の支払い設定は `特記処理.cost` のまま。E-14の「出血を5得る」は使用の代償としてコスト欄に残す。旧キーは起動時に公開・下書き・履歴のスキルだけで移し、両方のキーを持つ行があれば移行を取り消して起動を中止する。通常の読み手は新キーだけを読む。

分類が物理なら「このスキルには物理補正を適用しない。」、魔法なら「このスキルには魔法補正を適用しない。」を特記の独立した文に書く。用語リンクを外して比較し、末尾の「。」は省略できる。分類に合う文はパレットの定型と「項目から作る」から補正項を外し、文章の読み取りでは効果に変換せず読み飛ばす。新しい保存項目は作らない。

### 効果タイプ追加の依頼文

マスターデータ管理画面の「効果のリクエスト」で「依頼文としてコピー」を押すと、欲しい効果、文の例、近い効果タイプ、元の下書きの効果 JSON を Markdown で取得できる。下書きが消えていれば公開中の版を参照する。新しい効果タイプの実装では `manager/battle/effect_handlers/` の `HANDLERS` と `SCHEMAS` をそろえ、`tests/test_effect_schemas.py` でキーの一致を確かめる。

### スキルの文章を読み取る規則（PR60-23）

発動時効果では、行頭のタイミングを次の指定まで引き継ぐ。「〜なら、」は条件として読み、続く効果の対象と分ける。「より高い／大きい」は GT、「より低い／小さい」は LT とする。空欄は効果を作らない。スキルの行頭の「即時発動」は PRE_MATCH、「戦闘開始時」は RESOLVE_START として読む。再使用の回数、亀裂崩壊の消費量に応じた効果、付与の上限は、直前の該当する効果にまとめる。蓄力・凝魔を消費して FP・MP・HP を得る文は消費と獲得を一つの効果にする。

「ラウンド後に」は付与の遅れ、「ラウンド後まで」は今のラウンドを含む持続。出血遷延は count で数える。出血氾濫の対象は既定で相手とし、「自分に」と書けば自分になる。ラウンド終了の指示はタグで表す。タグの日本語名と英字の別名は重ねない。

往復の比較では、キーの順序・空の配列やオブジェクト・画面から渡す target_scope を除く。対象の省略と target、delay の省略と 0、lasting の省略と -1、重複した stat や data.buff_id、data.count と直下の count、表示専用の flavor と data.display_name をそろえる。タグの並びと、異なるタイミング同士の効果の並びは比較から除く。同じタイミング内の効果の順序は保つ。再使用の既定回数は1。威力補正は operation に統一し、省略時は FIXED、apply_to の既定は base、threshold の既定は1とする。単純な GTE 条件の固定加算と同じ source・param・threshold の FIXED_IF_EXISTS は同じ意味として比較する。

### 効果から文章を作る規則（PR60-24）

文章生成は読み取りと同じ文型を使う。発動時効果は最初に出た順のタイミングごとにまとめ、条件を本文の前に置く。用語図鑑の名前は用語リンクにし、補正を付けない特記の定型文は引き継ぐ。

同じタイミングで資源数を条件にした基礎威力加算と、その資源を同じ数だけ消費する効果は、順に実行される一組を一文にできる。加算値が消費数で割り切れる組は、スタックごとの加算と区別できるように文末に「(固定)」を付ける。再使用の上限は1回の使用ごとの回数を示す「この効果による再使用はN回まで」と書く。生成した文章は往復の比較と同じ意味の規則で検証する。
