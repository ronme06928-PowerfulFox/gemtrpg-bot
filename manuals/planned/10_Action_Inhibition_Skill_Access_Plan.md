# 10. Action Inhibition / Skill Access Plan

**最終更新日**: 2026-04-27  
**対象バージョン**: Current  
**対象機能**: 行動阻害系（封印・追加コスト）  
**設計前提**: 「キャラ個別デバフ付与」と「フィールド効果の全体適用」を同一基盤で扱う

---

## 1. 目的
- 行動阻害系を個別ギミックで乱立させず、共通の `skill_constraints` 評価基盤で実装する。
- UI 判定だけでなく、`battle_intent_commit` 時点でサーバー強制する。
- 実効コスト（追加コスト込み）を UI / commit / 実消費で一致させる。
- 全封印時の進行停止を防ぐため、`SYS-STRUGGLE` をフォールバックとして維持する。

対象要件:
- FP消費の技を使えなくする
- 要求FP+1
- コスト参照の封印
- カテゴリ参照の封印
- 距離参照の封印
- 属性参照の封印

---

## 2. スコープ（2パターン）

### 2.1 キャラ個別デバフ付与型
- スキルやバフで対象キャラにデバフを付与し、そのキャラのみ制約を受ける。
- 例:
  - 沈黙: カテゴリ `魔法` を封印
  - 重圧: FPコストに `+1`

### 2.2 フィールド効果の全体適用型
- フィールド効果が有効な間、条件に合う全キャラに制約を適用する。
- 例:
  - 重力場: 距離 `遠距離` を封印
  - 魔力乱流: MPコスト技に追加コスト

### 2.3 統一ルール
- 上記2パターンはデータ供給元が異なるだけで、最終的には同じ `skill_constraints` 配列へ正規化して評価する。

---

## 3. データモデル

### 3.1 制約ルールの共通フォーマット
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

### 3.2 `mode`
- `block`: 条件一致時、対象スキルを使用不可にする。
- `add_cost`: 条件一致時、コストを加算する。

### 3.3 `match` 初期対応キー
- `cost_types`
- `cost_min` / `cost_max`
- `category`
- `distance`
- `attribute`
- `skill_id`
- `tags`

### 3.4 供給元ごとの保持位置
- キャラ個別デバフ由来:
  - `char.special_buffs[].data.skill_constraints`
  - または `char.flags.skill_constraints`
- フィールド効果由来:
  - `state.field_effects[].skill_constraints`
  - 必要に応じて `scope`（`all` / `ally` / `enemy` / `except_source`）を持つ

---

## 4. 判定アルゴリズム

### 4.1 収集
- `collect_skill_constraints(actor, room_state=None, battle_state=None, slot_id=None)` で以下を統合:
  - actor自身の制約
  - フィールド効果由来の制約（scopeで対象判定）

### 4.2 評価順序
1. ルールを `priority` 昇順で評価
2. `block` 一致が1件でもあれば使用不可
3. `add_cost` 一致分を累積し `effective_cost` を作成
4. `effective_cost` でリソース不足判定を実施

### 4.3 返却モデル（推奨）
```json
{
  "usable": false,
  "blocked_reasons": ["FP消費技封印"],
  "effective_cost": [{ "type": "FP", "value": 2 }],
  "matched_rule_ids": ["rule_fp_block", "rule_fp_plus1"]
}
```

---

## 5. 優先順位・競合解決
- `block` は `add_cost` より優先。
- 同種 `add_cost` は加算。
- 同一 `id` のルールは重複適用しない。
- `SYS-STRUGGLE` は通常封印の対象外とする（進行不能防止）。

---

## 6. 実装方針

### 6.1 `manager/battle/skill_access.py` の中核化
- 既存ファイルを拡張し、以下を集約:
  - `build_skill_reference(skill_id, skill_data)`
  - `collect_skill_constraints(...)`
  - `evaluate_skill_access(actor, skill_id, room_state=None, battle_state=None, slot_id=None)`
  - `get_effective_skill_cost(actor, skill_id, skill_data, room_state=None, battle_state=None, slot_id=None)`
  - `list_usable_skill_ids(...)`
  - `can_use_skill_id(...)`

### 6.2 反映ポイント
- `events/battle/common_routes.py::on_battle_intent_change_skill`
- `events/battle/common_routes.py::on_battle_intent_commit`
- `manager/battle/resolve_effect_runtime.py::_apply_cost`（`effective_cost` で実消費）
- AI/PvE経路も同判定へ統一（`battle_ai` / `common_manager` 側の使用可能スキル判定）
- 必要なら state payload に `slot_skill_access` を追加

### 6.3 UI連携
- 選択時に「使用不可理由」と「実効コスト」を返せる構造にする。
- commit直前にも同じ判定を再評価し、改ざんや表示ズレを防ぐ。

---

## 7. 運用ルール（寿命・解除）
- キャラ個別制約は、付与元バフ/デバフの `lasting` / `delay` に追従。
- フィールド制約は、`field_effects` の有効期間に追従。
- ラウンド開始時・選択時・commit時に都度再評価し、固定キャッシュしない。

---

## 8. 実装タスク
1. `skill_access.py` の拡張（収集・評価・実効コスト）
2. `on_battle_intent_change_skill` へ判定結果反映（理由・実効コスト）
3. `on_battle_intent_commit` へサーバー強制判定
4. `_apply_cost` を実効コスト対応
5. AI/PvE経路の判定関数を `skill_access` に統一
6. テスト追加

---

## 9. テスト観点
- キャラ個別デバフのみで封印が成立する
- フィールド効果のみで全体封印/追加コストが成立する
- 両者同時適用で優先順位（`block` 優先）が成立する
- 追加コストが複数ルールで加算される
- `battle_intent_change_skill` / `commit` / 実消費で判定が一致する
- mass スキル・`USE_SKILL_AGAIN` でも破綻しない
- 全封印時でも `SYS-STRUGGLE` のみ使用可能で進行停止しない

---

## 10. 実装チェックリスト（ファイル単位）

### 10.1 Core: 判定基盤
- [ ] `manager/battle/skill_access.py`
  - [ ] `collect_skill_constraints(...)` を実装（キャラ由来 + フィールド由来統合）
  - [ ] `build_skill_reference(...)` を実装（`match` 判定用メタ抽出）
  - [ ] `evaluate_skill_access(...)` を実装（`block` / `add_cost` / 理由返却）
  - [ ] `get_effective_skill_cost(...)` を実装（追加コスト反映）
  - [ ] `list_usable_skill_ids(...)` / `can_use_skill_id(...)` を新評価へ接続
  - [ ] `SYS-STRUGGLE` 例外処理を維持

### 10.2 Route: 選択/確定時のサーバー強制
- [ ] `events/battle/common_routes.py`
  - [ ] `on_battle_intent_change_skill` で判定結果を反映（不可理由/実効コスト）
  - [ ] `on_battle_intent_commit` で再評価して強制（クライアント改ざん防止）
  - [ ] 必要なら payload に `slot_skill_access` を追加

### 10.3 Runtime: 実コスト消費
- [ ] `manager/battle/resolve_effect_runtime.py`
  - [ ] `_apply_cost` を `effective_cost` ベースで消費するよう変更
  - [ ] commit 時点の可否判定と消費値の不整合が出ないことを確認

### 10.4 AI/PvE: 判定の一本化
- [ ] `manager/battle/battle_ai.py`
  - [ ] 既存の独自可否判定を `skill_access` ベースへ寄せる
- [ ] `manager/battle/common_manager.py`
  - [ ] PvE 自動選択経路の `list_usable_skill_ids` 参照を統一
- [ ] `manager/battle/pve_intent_planner.py`
  - [ ] 使用可能スキル判定の基盤を統一

### 10.5 Tests: 回帰保証
- [ ] `tests/` 配下に以下ケースを追加
  - [ ] 個別デバフ封印（単体適用）
  - [ ] フィールド封印（全体適用）
  - [ ] `block` 優先 / `add_cost` 加算
  - [ ] `change_skill` / `commit` / `_apply_cost` の一致
  - [ ] mass / `USE_SKILL_AGAIN`
  - [ ] 全封印 + `SYS-STRUGGLE` フォールバック

---

## 11. 実装着手ゲート（要ユーザー確認）
- [ ] このチェックリスト内容で実装着手してよい
- [ ] `slot_skill_access` を state payload に含めるか（含める / 含めない）
- [ ] 制約ルールの初期供給元（どちらから先に有効化するか）
  - [ ] A: キャラ個別デバフから先行
  - [ ] B: フィールド効果から先行
  - [ ] C: 同時有効化

---

## 12. テスト用 特記処理JSON（2行版）

### 12.1 FP消費技封印
```json
{"target_scope":"enemy","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_name":"CC_FP_BLOCK_2R","lasting":2,"data":{"skill_constraints":[{"id":"cc_fp_block","mode":"block","priority":100,"match":{"cost_types":["FP"]},"reason":"FP消費技封印"}]}}]}
```

### 12.2 MP消費技封印
```json
{"target_scope":"enemy","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_name":"CC_MP_BLOCK_2R","lasting":2,"data":{"skill_constraints":[{"id":"cc_mp_block","mode":"block","priority":100,"match":{"cost_types":["MP"]},"reason":"MP消費技封印"}]}}]}
```

### 12.3 分類封印（魔法）
```json
{"target_scope":"enemy","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_name":"CC_CATEGORY_MAGIC_BLOCK_2R","lasting":2,"data":{"skill_constraints":[{"id":"cc_category_magic_block","mode":"block","priority":100,"match":{"category":"魔法"},"reason":"魔法分類封印"}]}}]}
```

### 12.4 分類封印（物理）
```json
{"target_scope":"enemy","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_name":"CC_CATEGORY_PHYSICAL_BLOCK_2R","lasting":2,"data":{"skill_constraints":[{"id":"cc_category_physical_block","mode":"block","priority":100,"match":{"category":"物理"},"reason":"物理分類封印"}]}}]}
```

### 12.5 分類封印（補助）
```json
{"target_scope":"enemy","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_name":"CC_CATEGORY_SUPPORT_BLOCK_2R","lasting":2,"data":{"skill_constraints":[{"id":"cc_category_support_block","mode":"block","priority":100,"match":{"category":"補助"},"reason":"補助分類封印"}]}}]}
```

### 12.6 距離封印（近接）
```json
{"target_scope":"enemy","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_name":"CC_DISTANCE_MELEE_BLOCK_2R","lasting":2,"data":{"skill_constraints":[{"id":"cc_distance_melee_block","mode":"block","priority":100,"match":{"distance":"近接"},"reason":"近接封印"}]}}]}
```

### 12.7 距離封印（遠隔）
```json
{"target_scope":"enemy","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_name":"CC_DISTANCE_RANGED_BLOCK_2R","lasting":2,"data":{"skill_constraints":[{"id":"cc_distance_ranged_block","mode":"block","priority":100,"match":{"distance":"遠隔"},"reason":"遠隔封印"}]}}]}
```

### 12.8 距離封印（広域-個別）
```json
{"target_scope":"enemy","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_name":"CC_DISTANCE_MASS_INDIVIDUAL_BLOCK_2R","lasting":2,"data":{"skill_constraints":[{"id":"cc_distance_mass_individual_block","mode":"block","priority":100,"match":{"distance":"広域-個別"},"reason":"広域-個別封印"}]}}]}
```

### 12.9 距離封印（広域-合算）
```json
{"target_scope":"enemy","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_name":"CC_DISTANCE_MASS_SUM_BLOCK_2R","lasting":2,"data":{"skill_constraints":[{"id":"cc_distance_mass_sum_block","mode":"block","priority":100,"match":{"distance":"広域-合算"},"reason":"広域-合算封印"}]}}]}
```

### 12.10 FPコスト+1
```json
{"target_scope":"enemy","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_name":"CC_FP_PLUS1_2R","lasting":2,"data":{"skill_constraints":[{"id":"cc_fp_plus1","mode":"add_cost","priority":50,"match":{"cost_types":["FP"]},"add_cost":[{"type":"FP","value":1}],"reason":"FP消費+1"}]}}]}
```

### 12.11 MPコスト+1
```json
{"target_scope":"enemy","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_name":"CC_MP_PLUS1_2R","lasting":2,"data":{"skill_constraints":[{"id":"cc_mp_plus1","mode":"add_cost","priority":50,"match":{"cost_types":["MP"]},"add_cost":[{"type":"MP","value":1}],"reason":"MP消費+1"}]}}]}
```

### 12.12 複合（魔法封印 + FP+1）
```json
{"target_scope":"enemy","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_name":"CC_MAGIC_BLOCK_AND_FP_PLUS1_2R","lasting":2,"data":{"skill_constraints":[{"id":"cc_magic_block","mode":"block","priority":100,"match":{"category":"魔法"},"reason":"魔法分類封印"},{"id":"cc_fp_plus1_combo","mode":"add_cost","priority":50,"match":{"cost_types":["FP"]},"add_cost":[{"type":"FP","value":1}],"reason":"FP消費+1"}]}}]}
```

### 12.13 全封印（フォールバック確認用）
```json
{"target_scope":"enemy","effects":[{"timing":"PRE_MATCH","type":"APPLY_BUFF","target":"target","buff_name":"CC_ALL_BLOCK_1R","lasting":1,"data":{"skill_constraints":[{"id":"cc_all_block","mode":"block","priority":100,"match":{},"reason":"全スキル封印"}]}}]}
```

---

## 13. 設定キーの意味

### 13.1 スキル側（`特記処理`）
- `target_scope`: スキル対象陣営。`enemy` は敵側対象。
- `effects`: 発動効果配列。
- `timing`: 効果発動タイミング。ここでは `PRE_MATCH` を想定。
- `type`: 効果種別。ここでは `APPLY_BUFF` を使用。
- `target`: 効果対象。`target` は選択した対象へ適用。
- `buff_name`: 付与バフ名（表示/識別用）。
- `lasting`: 効果ラウンド数。
- `delay`: 効果開始遅延（任意）。
- `data`: バフ追加データ。

### 13.2 制約側（`data.skill_constraints[]`）
- `id`: ルール識別子（ログ/デバッグ用、一意推奨）。
- `mode`: 制約モード。
  - `block`: 条件一致スキルを使用不可にする。
  - `add_cost`: 条件一致スキルへ追加コストを与える。
- `priority`: 評価優先度（小さいほど先に評価）。
- `match`: 対象スキル条件。
  - `cost_types`: コスト種別一致（`FP` / `MP`）。
  - `category`: 分類一致（`魔法` / `物理` / `補助`）。
  - `distance`: 距離一致（`近接` / `遠隔` / `広域-個別` / `広域-合算`）。
  - `skill_id`: 特定スキルID一致（任意）。
  - `tags`: タグ一致（任意）。
  - `cost_min`, `cost_max`: 総コスト範囲条件（任意）。
- `add_cost`: `mode=add_cost` 時に加算するコスト配列。
  - `type`: コスト種別（`FP` / `MP` など）。
  - `value`: 加算量（正整数）。
- `reason`: 使用不可時や説明表示に使う理由文言。
