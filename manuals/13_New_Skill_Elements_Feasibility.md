**最終更新日**: 2026-02-25
**対象**: 新要素4件の実現可能性評価（Select/Resolve運用）

---

## 1. 結論サマリ

1. **同陣営対象スキル**
- サーバー側の対象制約は**実装済み**（`target_scope=ally/enemy/any`）。
- ただし「先に味方スロットを選ぶと、対応スキルだけをプルダウン表示」は**未実装**。
- 実現性: **高（小〜中改修）**。

2. **対象にダメージを与えないスキル**
- 明示的な `no_damage` 相当のフラグは**未実装**。
- `clash` は既存デュエル委譲で「防御/回避」により0ダメージ化される経路あり。
- ただし `one_sided` は現状、最終的にHP減算を行うため、非ダメージ保証は不可。
- 実現性: **中（戦闘解決ロジック改修が必要）**。

3. **対象が同陣営か否かで発動が変わる効果**
- `target_scope` は「選択可能対象の制約」であり、**効果分岐条件には使えない**。
- `check_condition` は実質「数値比較/配列CONTAINS」で、陣営関係（同陣営/敵対）を直接判定できない。
- 実現性: **中（condition拡張が必要）**。

4. **スキルセット時に、解決フェーズ開始時適用**
- `RESOLVE_START` タイミングは**実装済み**。
- コミット済み・非instantスキルに対し、Resolve開始時に1回適用される。
- 実現性: **高（データ定義で実現可能）**。

---

## 2. 現状実装の根拠

- 対象陣営制約（サーバー）
  - `events/battle/common_routes.py`
  - `_normalize_target_scope`, `_infer_target_scope_from_skill`, `_validate_single_target_scope`, `_normalize_target_by_skill`
- 対象候補制約（フロント）
  - `static/js/battle/components/DeclarePanel.js`
  - `_inferTargetScopeFromSkill`, `_isTargetTeamAllowedByScope`, `_buildTargetOptions`
- 解決フェーズ開始タイミング
  - `manager/battle/core.py`
  - `_apply_phase_timing_for_committed_intents(... timing='RESOLVE_START')`
- 条件判定の現仕様
  - `manager/game_logic.py`
  - `check_condition`, `_get_value_for_condition`
- one-sidedでのダメージ適用
  - `manager/battle/core.py`
  - `_resolve_one_sided_by_existing_logic`（`_update_char_stat(... HP - final_damage)`）
- clash経路
  - `manager/battle/core.py`
  - `_resolve_clash_by_existing_logic`（`duel_solver.execute_duel_match`へ委譲）

---

## 3. 要素別の実装方針

### 3.1 同陣営対象スキル + 逆方向フィルタ（ターゲット先行でスキル絞り込み）

### 現状
- `target_scope=ally` をスキルに付与すれば、サーバーは敵スロット指定を拒否できる。
- UIは「スキル選択後に対象候補を絞る」動作のみ。

### 追加実装
- `DeclarePanel._buildSkillOptions` に `state/sourceSlotId/selectedTargetSlotId` を渡し、
  - 選択済みtargetがある場合、`target_scope` 不一致スキルを候補から除外（またはdisabled表示）。
- `target` 変更時に、現在選択中スキルが不整合なら自動クリア。
- サーバー側バリデーションは現状維持（最終防衛線）。

### 判定
- **実装可能（高）**

---

### 3.2 対象にダメージを与えないスキル

### 現状
- 非ダメージ専用フラグがないため、Select/Resolve one-sidedでは最終的にダメージ計算・HP減算へ進む。
- clashでは既存ルールにより0ダメージになるケースはあるが、スキル仕様として一貫保証できない。

### 追加実装（最小案）
- スキル定義に `deals_damage: false`（または `damage_policy: none`）を追加。
- `manager/battle/core.py` の one-sided/clash後処理で、
  - 当該フラグ時はHP減算・on_damage連鎖をスキップ。
  - 代わりに `effects`（`HIT/UNOPPOSED/AFTER_DAMAGE_APPLY`）は仕様に従って適用。
- プレビュー表示も `min/max_damage=0` へ寄せるか、UIに「非ダメージ」表示を追加。

### 判定
- **実装可能（中）**

---

### 3.3 対象が同陣営か否かで発動変化

### 現状
- `condition` で参照できる値に「actor-targetの関係」はない。
- `source=self/target/...` + 数値比較では、同陣営/敵対の直接条件を書けない。

### 追加実装（推奨）
- `check_condition` に関係判定ソースを追加（例）:
  - `{"source":"relation","param":"same_team","operator":"EQUALS","value":1}`
- `_get_value_for_condition` で actor/target の `type` 比較結果を返す。
- `same_team` 以外に `target_is_ally`, `target_is_enemy` も0/1で返すと運用しやすい。

### 判定
- **実装可能（中）**

---

### 3.4 セットしたスキルを解決開始時に適用

### 現状
- `RESOLVE_START` はすでに実行される。
- コミット済みかつ `instant` でないintentに対し、Resolve開始時1回のみ適用される（timing marksあり）。

### 運用ルール
- 対象スキルの `effects[].timing` に `RESOLVE_START` を指定する。
- 「セット時即発動」にしたくないため、`instant` タグは付けない。

### 判定
- **実装可能（高）**

---

## 4. 影響範囲まとめ

- UI
  - `static/js/battle/components/DeclarePanel.js`
- サーバー（意図/対象検証）
  - 既存の `events/battle/common_routes.py` は維持（必要ならエラーメッセージ微調整）
- 戦闘ロジック
  - `manager/battle/core.py`（非ダメージフラグ導入時）
  - `manager/game_logic.py`（relation条件導入時）
- テスト
  - `tests/test_select_resolve_smoke.py`
  - `tests/test_grant_skill_system.py`
  - `tests/test_skill_catalog_smoke.py`（新フィールド/新conditionソースのlint追加）

---

## 5. 実装優先度（提案）

1. `target_scope` の逆方向UIフィルタ（体験改善、既存仕様と整合）
2. `RESOLVE_START` 運用ルールのデータ適用（即導入可能）
3. relation条件拡張（仕様表現力の拡張）
4. 非ダメージフラグ導入（戦闘計算への影響が最も大きいため最後に段階導入）

---

## 6. 補足

- 本書は「実装可否判断」のための設計メモ。
- 実装確定後は `manuals/03_Integrated_Data_Definitions.md` と `manuals/07_Skill_Logic_Reference.md` に仕様を統合すること。
