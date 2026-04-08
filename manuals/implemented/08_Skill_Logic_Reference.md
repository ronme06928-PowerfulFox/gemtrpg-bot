# スキルロジック実装リファレンス（実装準拠）

**最終更新日**: 2026-04-08  
**対象実装**: `manager/game_logic.py` / `manager/battle/core.py` / `events/battle/common_routes.py`

---

## 0. 本書の位置づけ

- 本書は「現在のコードで実際にどう動くか」をまとめた実装準拠リファレンスです。
- 旧来の手動テスト用バグ調査メモは本書へ統合し、恒常仕様のみを残しています。
- Select/Resolve の戦闘進行そのものは `manuals/implemented/09_SelectResolve_Spec.md` を正とします。

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
| `APPLY_STATE` | 状態異常・数値付与 | 亀裂（正値付与）は1R1回制限 / 受け手側 `state_receive_bonus` を合算 |
| `APPLY_STATE_PER_N` | 参照値Nごとの状態付与 | `source/source_param/per_N/value/max_value` |
| `MULTIPLY_STATE` | 状態値を乗算 | `int(x * multiplier + 0.5)` で丸め |
| `APPLY_BUFF` | バフ付与 | `buff_id` から名称解決可 / スタック系は `data.count` |
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
- `出血氾濫`（即時出血処理。ラウンド終了時と同一ロジック）
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

### 5.3 出血処理共通ロジック（`round_end` / `出血氾濫`）

- 出血ダメージ処理は `resolve_bleed_tick(...)` に共通化され、ラウンド終了時と `CUSTOM_EFFECT: 出血氾濫` の両方で同じ規則を使う。
- 1回の処理規則:
  - ダメージは「現在の出血値」ぶん発生
  - `Bu-08`（出血遷延）が有効なら `count` を1消費し、その回の出血値は減衰しない
  - `Bu-08` が無効なら、処理後の出血値は `floor(出血/2)` へ減衰
- `Bu-08` は round 経過で減らず、出血ダメージ処理イベント発生時のみ減少する。
- 互換動作として `count` 未設定の旧 `Bu-08` データは 1 回分として扱う。

### 5.4 震盪（受け手側 `state_receive_bonus`）

- `震盪` はバフ定義の `effect.state_receive_bonus` で定義する。
- 補正は `APPLY_STATE` / `APPLY_STATE_PER_N` の正値付与時のみ適用される。
- `stat="破裂"` とした場合、破裂付与値へ加算される（負値付与には適用しない）。
- 付与側 `state_bonus` と受け手側 `state_receive_bonus` は合算される。
- `consume=true` のルールは受け手（target）側バフを消費する。
- `Bu-29` の再付与は専用挙動:
  - `count` は加算スタックされる（`count` 省略時は +1）。
  - `lasting` は `max(既存, 新規)` を維持する。

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

- `RESOLVE_START`: 戦闘開始時（Resolve開始直後）、コミット済みスロットごと
- `RESOLVE_STEP_END`: `clash/one_sided/mass_*` の各trace確定直後
- `RESOLVE_END`: 戦闘終了時（Resolve完了直前）、コミット済みスロットごと

補足:
- `戦闘突入時` は別概念で、現実装では `BATTLE_START` / `battle_start_effect` が該当する。
- `戦闘離脱時` は用語としては「戦闘フェーズからいなくなる時（離脱/死亡を含む）」を指すが、専用の共通timingはまだ標準化していない。
- 死亡時だけを扱いたい場合は `on_death` を使用する。

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

---

## 10. 2026-02 統合追補（実装確定）

### 10.1 relation条件
- `check_condition` は `source: relation` を受け付ける。
- 利用可能 `param`:
  - `same_team`
  - `target_is_ally`
  - `target_is_enemy`
- 戻り値は 0/1 数値として比較される。

### 10.2 非ダメージスキル
- `deals_damage: false` 指定時:
  - HP減算をスキップ
  - `on_damage` 連鎖をスキップ
  - `HIT/LOSE` 等の効果評価自体は継続

### 10.3 ダメージ倍率の統合
- 新規API: `compute_damage_multipliers(attacker, defender, context)`
  - `incoming`（被ダメ）
  - `outgoing`（与ダメ）
  - `final = incoming * outgoing`
- 動的バフは `_DaIn/_DaCut` に加えて `_DaOut/_DaOutDown` を扱う。
- 既存 `calculate_damage_multiplier(defender)` は互換関数として `incoming` のみ返す。

### 10.4 強硬/牽制（Select/Resolve）
- 強硬敗北時、条件一致で `hard_attack` trace を差し込む。
- 強硬追撃は基礎威力ベースで解決され、回避差し込み優先順を持つ。
- 牽制勝利時は強硬追撃の抑止対象となる（不発）。
- 牽制勝利時の半減は duel/wide 両ソルバの最終ダメージへ適用される。
- UI表示ラベルは `ResolveFlowPanel` で `hard_attack -> 強硬攻撃` を使用する。

### 10.5 再付与フラグ管理
- `newly_applied` 系フラグはラウンド進行で統一クリアされる。
- 目的は「付与直後のみ無効化する on_damage 系」処理の持ち越し防止。

### 10.6 `target_scope=same_team`（互換: `ally`）の固定化
- `target_scope` は `rule_data` / `特記処理` だけでなく、タグ（`味方指定`, `味方対象`, `同陣営`, `同陣営対象`, `同陣営指定`, `ally_target`, `target_ally`）からも推論される。
- `target_scope=opposing_team`（互換: `enemy`）は、`敵対象`, `相手陣営対象`, `相手陣営指定`, `enemy_target`, `target_enemy` を互換入力として受理する。
- `target_scope=same_team`（互換: `ally`）スキルは Select の redirect に参加しない（発生・被適用ともに無効）。
- 同一陣営どうしで片方以上が `target_scope=same_team`（互換: `ally`）スキルの場合、`clash` を作らず `one_sided` として扱う。
- 同一陣営ペアには再回避差し込み（evade insert）を行わない。

### 10.7 clash の勝敗種別ルール
- `attack vs attack` 勝敗確定時は勝者へ `FP+1`（`source=match_win_fp`）を付与する。
- `defense vs defense` 勝敗確定時も同様に `FP+1` を付与する。
- `attack vs defense` は `defense` 側が勝利した場合に限り、勝者へ `FP+1` を付与する。
- `attack vs evade` は `evade` 側が勝利した場合に限り、勝者へ `FP+1` を付与する。
- `defense vs evade` は `fizzle`（不発）として処理し、スキルは未使用扱い・FPも付与しない。
- `evade vs evade` も `fizzle`（不発）として処理し、スキルは未使用扱い・FPも付与しない。
- 上記不発ではコストを消費せず、`RESOLVE_START` / 使用時 / `PRE_MATCH` / `RESOLVE_END` も発動しないが、行動回数だけは消費する。
