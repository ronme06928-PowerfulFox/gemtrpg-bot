# スキルロジック実装リファレンス（実装準拠）

**最終更新日**: 2026-02-23  
**対象実装**: `manager/game_logic.py` / `manager/battle/core.py` / `events/battle/common_routes.py`

---

## 0. 本書の位置づけ

- 本書は「現在のコードで実際にどう動くか」をまとめた実装準拠リファレンスです。
- 旧来の手動テスト用バグ調査メモは本書へ統合し、恒常仕様のみを残しています。
- Select/Resolve の戦闘進行そのものは `manuals/08_SelectResolve_Spec.md` を正とします。

---

## 1. 効果処理の基本モデル

`process_skill_effects(...)` は、`effects[]` を上から順に走査し、以下で処理します。

1. `timing` 完全一致の効果のみ対象化  
2. 対象選定（`self`, `target`, `ALL_ENEMIES`, `ALL_ALLIES`, `ALL`, `NEXT_ALLY`, `target_select=RANDOM`）  
3. 条件判定（`check_condition`）  
4. 変更予約（`changes_to_apply`）を蓄積  
5. 呼び出し側で状態へ反映

重要:

- 同一 `effects[]` 内では、先に評価された効果結果が後続の条件判定へ反映されます（逐次シミュレーション）。
- そのため「効果1で状態付与 -> 効果2でその状態を条件判定」は同一タイミング内で成立します。

---

## 2. 条件判定（condition）

### 2.1 対応ソース

- `source: self | target | target_skill | skill(actor_skill)`

### 2.2 対応演算子

- 数値比較: `GTE`, `LTE`, `GT`, `LT`, `EQUALS`
- 配列/タグ: `CONTAINS`

### 2.3 `速度` と `速度値` の違い

- `速度`: 通常ステータス（`params` / バフ込み）  
- `速度値`: ラウンドごとの initiative 実値（ロール結果）

`param: 速度値` の評価順:

1. `context.timeline` の `speed`
2. `context.battle_state.slots[*].initiative`
3. キャラの `totalSpeed`
4. 見つからなければ `0`

---

## 3. Effect Type 実装一覧

| Type | 概要 | 主な追加仕様 |
| :--- | :--- | :--- |
| `APPLY_STATE` | 状態異常・数値付与 | 亀裂（正値付与）は1R1回制限 |
| `APPLY_STATE_PER_N` | 参照値Nごとの状態付与 | `source/source_param/per_N/value/max_value` |
| `MULTIPLY_STATE` | 状態値を乗算 | `int(x * multiplier + 0.5)` で丸め |
| `APPLY_BUFF` | バフ付与 | `buff_id` から名称解決可 |
| `REMOVE_BUFF` | バフ解除 | 名前一致削除 |
| `DAMAGE_BONUS` | 追加ダメージ | `total_bonus_damage` へ加算 |
| `MODIFY_ROLL` | ロール補正 | ロール値補正として加算 |
| `MODIFY_BASE_POWER` | 基礎威力補正 | baseレーン加算 |
| `MODIFY_FINAL_POWER` | 最終威力補正 | finalレーン加算 |
| `FORCE_UNOPPOSED` | 一方攻撃化要求 | Select/Resolve側で解釈 |
| `USE_SKILL_AGAIN` | 同スキル再使用要求 | Resolve層で仮想スロット差し込み |
| `CUSTOM_EFFECT` | プラグイン効果 | `plugins/*` 実装へ委譲 |

`USE_SKILL_AGAIN` の実データ:

- `max_reuses`（既定1）
- `consume_cost`（既定false）
- `reuse_cost`（任意。差し込み時に支払い判定）

---

## 4. CUSTOM_EFFECT 実装名

主に以下が運用対象です。

- `破裂爆発`
- `亀裂崩壊_DAMAGE`
- `出血氾濫`
- `戦慄殺到`
- `荊棘飛散`
- `DRAIN_HP`

後方互換:

- `APPLY_SKILL_DAMAGE_AGAIN` は旧式。Select/Resolve では再使用要求へ読み替えます。

---

## 5. 状態異常・バフの制約

### 5.1 亀裂の1R1回制限

- 対象 `flags.fissure_received_this_round` が true の場合、正値の亀裂付与は不発。
- 負値付与（減少）は制限しません。
- ラウンド更新でフラグはリセットされます。

### 5.2 Speed系バフ

- `Bu-11`（加速）/`Bu-12`（減速）は RoundStart initiative 計算にのみ反映。
- ロール後に消去され、通常バフ一覧へ残りません。

---

## 6. 威力計算レーン（base/dice/final）

`calculate_skill_preview(...)` は以下を分離して計算します。

- baseレーン: `基礎威力` + `power_bonus(apply_to=base)` + `MODIFY_BASE_POWER`
- diceレーン: `ダイス威力` + `power_bonus(apply_to=dice)`
- finalレーン: `power_bonus(apply_to=final)` + `MODIFY_FINAL_POWER`

結果は `power_breakdown` と `build_power_result_snapshot(...)` で追跡可能です。

---

## 7. Select/Resolve でのタイミング実行

### 7.1 フェーズタイミング

- `RESOLVE_START`: Resolve開始直後、コミット済みスロットごと
- `RESOLVE_STEP_END`: `clash/one_sided/mass_*` の各trace確定直後
- `RESOLVE_END`: Resolve完了直前、コミット済みスロットごと

### 7.2 one-sided 内部順

1. `PRE_MATCH`（攻防）
2. `BEFORE_POWER_ROLL`（攻撃側）
3. 威力ロール
4. `UNOPPOSED`
5. `HIT`
6. ダメージ反映
7. `AFTER_DAMAGE_APPLY`（攻防）

---

## 8. 再使用チェーン（USE_SKILL_AGAIN）

- Resolve中に `single_queue` へ仮想スロットを動的挿入します。
- スロットIDは `origin_slot__EX1`, `origin_slot__EX2`, ...。
- UI向けラベルは元trace step基準で `n-EX`, `n-EX2`。
- `reuse_cost` 不足時は当該再使用だけ生成せずスキップ。
- 実装上の連鎖ハード上限は20。

---

## 9. 実装整合チェック（主要テスト）

- Select/Resolve回り: `tests/test_select_resolve_smoke.py`
- 速度値/initiative回り: `tests/test_speed_value_select_resolve.py`
- 威力補正フレームワーク: `tests/test_power_modifier_framework.py`
- 権限制御: `tests/test_intent_authorization_routes.py`
- 亀裂制限: `tests/test_fissure.py`

仕様変更時は上記テストの期待値とマニュアル記述を同時更新してください。
