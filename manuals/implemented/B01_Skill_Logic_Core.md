<!-- 旧: 08_Skill_Logic_Reference.md + 13_Fissure_Round_Management_Spec.md を統合 (2026-05-09) -->

# スキルロジック実装リファレンス Part 1: 効果処理コア

**最終更新日**: 2026-05-09
**系統**: B — 戦闘・スキル仕様
**統合元**: 08_Skill_Logic_Reference / 13_Fissure_Round_Management_Spec

---

## 本書の構成

- Part 1（本書）: 効果処理コア — effect 処理基本・条件判定・亀裂仕様
- Part 2: → B02_Skill_Logic_Extensions.md（GRANT_SKILL/召喚/自滅/Fallback/スタックVariant）
- 戦闘進行: → B03_SelectResolve_Spec.md

---

# スキルロジック実装リファレンス（実装準拠）

**最終更新日**: 2026-05-09  
**対象実装**: `manager/game_logic.py` / `manager/battle/` / `events/battle/common_routes.py`

---

## 0. 本書の位置づけ

- 本書は「現在のコードで実際にどう動くか」をまとめた実装準拠リファレンスです。
- 旧来の手動テスト用バグ調査メモは本書へ統合し、恒常仕様のみを残しています。
- Select/Resolve の戦闘進行そのものは `manuals/implemented/B03_SelectResolve_Spec.md` を正とします。

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

### 2.4 状態異常スタック合算パラメータ

- `condition.param` には次を指定できる。
  - `状態異常スタック合計:<状態名1>,<状態名2>,...`
- `状態異常スタック合計` の省略形（状態名の列挙なし）は無効。
- 全種合算したい場合も、必ず全状態名を列挙する。
  - 例: `状態異常スタック合計:出血,破裂,亀裂,戦慄,荊棘`
- 列挙形式は、指定した状態名のみを合算する（区切りは `,` / `、` / `・`）。
- 合算対象は正値（`value > 0`）のみ。

### 2.5 `APPLY_BUFF_PER_N` の source 解決

- `source=self` は使用者を参照する。
- `source=target` かつ `target=self` の場合は、同タイミングの自己バフ増減後状態ではなく「元の対象（命中先）」を参照する。
- これにより「対象の状態異常合計を基準に、自分へ蓄力/凝魔を得る」が安定して成立する。

---

## 3. Effect Type 実装一覧

| Type | 概要 | 主な追加仕様 |
| :--- | :--- | :--- |
| `APPLY_STATE` | 状態異常・数値付与 | 亀裂（正値付与）は継続ラウンド付きバケット管理 / 受け手側 `state_receive_bonus` を合算 |
| `APPLY_STATE_PER_N` | 参照値Nごとの状態付与 | `source/source_param/per_N/value/max_value` |
| `APPLY_BUFF_PER_N` | 参照値Nごとのバフスタック付与 | `source/source_param/per_N/value/max_count` |
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

### 5.1 亀裂の付与とダメージ参照

- 正値の亀裂付与に、同一ラウンド内の対象ごとの回数制限はありません。
- 新たに付与された亀裂は、その付与を発生させた同じダメージには乗らず、次にスキルでダメージを受ける時から有効です。
- 負値付与（減少）は従来どおり制限しません。
- 旧仕様の `flags.fissure_received_this_round` が保存済みルームに残っていても、現在の付与判定では参照しません。

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
  - `lasting` は更新されず、最初に付与された値を維持する。

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

---

## 11. 2026-04 追補: 凝魔・蓄力の処理仕様

### 11.1 付与
- `APPLY_BUFF` で `buff_name = 凝魔 / 蓄力` を付与した場合、同名スタックへ加算する。
- `lasting` 未指定時は `-1`（無期限）を既定値として扱う。

### 11.2 消費effect
- `CONSUME_BUFF_COUNT_FOR_GAIN`:
  - `consume_required` を満たす時だけ消費と `gains` を適用。
  - 不足時は不発（消費なし・獲得なし）。
- `CONSUME_BUFF_COUNT_FOR_POWER`:
  - 実消費量 `min(current_count, consume_max)` を算出。
  - 実消費量が `min_consume` 未満なら不発。
  - `value_per_stack` と `apply_to(base/final)` で威力補正を生成。

### 11.3 condition参照
- `check_condition` は `param` に `<バフ名>_count` / `buff_count:<バフ名>` を受理する。
- `check_condition` は `param` に `状態異常スタック合計:<状態名...>` を受理する（省略形は禁止）。

### 11.4 `APPLY_BUFF_PER_N`（凝魔/蓄力のNごと付与）
- `apply_count = floor(source_value / per_N) * value` で付与スタック数を算出する。
- `max_count` があれば `apply_count` に上限をかける。
- 実付与時は通常 `APPLY_BUFF` と同じスタック加算経路へ流し込み、ログは「付与」と「スタック増分」を分離して出力する。

---

## 12. 2026-05 追補: バトル条件 / 繰り返しエフェクト / ランダム単体ターゲット

### 12.1 `condition.source=battle`（ラウンド数条件）

`check_condition` の `source` に `battle` を指定すると、バトルの進行状態（現在ラウンド数）を参照できる。

**対応 `param`**:

| param | 意味 |
|---|---|
| `round` | 現在のラウンド数（整数）|

**解決順序**:
1. `context["round"]`
2. `context["current_round"]`
3. `context["battle_state"]["round"]`
4. 取得不能時は `0` を返す（条件 `false` になりやすい設計）

**JSON 例**:
```json
{
  "condition": {
    "source": "battle",
    "param": "round",
    "operator": "GTE",
    "value": 3
  }
}
```
→ 3ラウンド以降のみ発動。`EQUALS` で「ちょうど N ラウンド目のみ」も可。

**ポイント**:
- `source=battle` はキャラクター状態（self/target）と独立しているため、`source_obj` は空オブジェクト `{}` として渡される。
- condition の `source=battle` は `power_bonus_rules` の `condition` にも使用可能。

---

### 12.2 `effects[].repeat_count`（エフェクト繰り返し）

`effects[]` の各エントリに `repeat_count` を付与すると、そのエフェクトを **N 回分展開**してから処理する。  
実装上は `process_skill_effects()` の冒頭で `_expand_repeated_effects()` がリストを展開し、以降は通常のエフェクトループが処理する。

**フィールド仕様**:

| フィールド | 型 | 既定値 | 説明 |
|---|---|---|---|
| `repeat_count` | 正の整数 | `1` | このエフェクトを何回繰り返すか |

**動作ルール**:
- 1回ごとに通常の `condition` 判定を行う（条件を満たさなければ1回でもスキップ）
- 1回ごとに通常の `target` 解決を行う（`target_select=RANDOM` は毎回再抽選）
- 省略 / `1` の場合は従来と同等の動作

**JSON 例（出血+2 を 3 回）**:
```json
{
  "timing": "HIT",
  "type": "APPLY_STATE",
  "target": "target",
  "state_name": "出血",
  "value": 2,
  "repeat_count": 3
}
```
→ 対象に出血+2 が 3 回適用される（合計 +6 相当）。

**JSON 例（ランダム対象に毎回別の対象で 3 回）**:
```json
{
  "timing": "HIT",
  "type": "APPLY_STATE",
  "target_select": "RANDOM",
  "target_filter": "ENEMY",
  "target_count": 1,
  "state_name": "出血",
  "value": 1,
  "repeat_count": 3
}
```
→ 毎回 ENEMY からランダムに 1 体を選んで出血+1 を 3 回与える（対象は毎回変わりうる）。

---

### 12.3 `target.type=random_single`（ランダム単体ターゲット）

> **注意**: これはスキルのエフェクト内 `target` ではなく、**バトルインテント**（誰を狙うか宣言）レベルの設定です。  
> 主に NPC / PvE 自動バトルで「毎ラウンドランダムな敵を狙わせる」用途に使います。

**インテント形式**:
```json
{
  "target": {
    "type": "random_single",
    "random_target_scope": "enemy"
  }
}
```

**`random_target_scope` の値**:

| 値 | 対象 |
|---|---|
| `enemy`（既定） | 攻撃側と反対チームの生存・配置済みスロット |
| `ally` | 攻撃側と同チームの生存・配置済みスロット（自スロット除く） |
| `any` | チーム問わず生存・配置済みスロット（自スロット除く） |

**動作タイミング**:
- `resolve_random_intents(state, battle_state, intents)` が `_build_resolve_queues()` 直前に呼ばれ、`random_single` を `single_slot` に書き換える。
- 候補が存在しない場合（全滅など）は自動で `type: none`（対象なし）にフォールバック。

**実装ファイル**:
- `events/battle/common_routes.py` — `_default_target()` / `_validate_and_normalize_target()`
- `manager/battle/resolve_queue_helpers.py` — `resolve_random_intents()`
- `manager/battle/resolve_auto_runtime.py` / `resolve_auto_mass_phase.py` — 呼び出し箇所

---

## 13. 2026-06 追補: スキル使用可否基盤（Phase 1）

### 13.1 evaluate_skill_access / list_usable_skill_ids

スキルの使用可否は `manager/battle/skill_access.py` が一元管理する。

| 関数 | 概要 |
|---|---|
| `evaluate_skill_access(actor, skill_id, ...)` | 単スキルの可否・有効コスト・ブロック理由を返す |
| `list_regular_usable_skill_ids(actor, ...)` | 使用可能スキル ID リストを返す（フォールバックなし） |
| `list_usable_skill_ids(actor, allow_fallback=True, ...)` | 候補ゼロ時は `["SYS-STRUGGLE"]` を返す |
| `get_effective_skill_cost(actor, skill_id, ...)` | `skill_constraints` 適用後の最終コストを返す |
| `collect_skill_constraints(actor, battle_state)` | actor バフ・フィールド効果から制約を集約する |

**戻り値の形式（`evaluate_skill_access`）**:
```python
{
    "usable": bool,
    "blocked_reasons": ["封印中（魔法）"],  # 空リストなら通過
    "effective_cost": [{"type": "FP", "value": 4}],
    "matched_rule_ids": ["cc_magic_block"]
}
```

### 13.2 SYS-STRUGGLE フォールバック

- ID: `SYS-STRUGGLE`、名前: `どうにかもがく`
- 定義: `manager/battle/system_skills.py`
- 用途: キャラの全スキルが封印された場合に限り、`list_usable_skill_ids(allow_fallback=True)` が返す
- `evaluate_skill_access` では常に `usable=True`（フォールバックを封印しない）

### 13.3 commit 時の再検証

`battle_intent_commit` イベントハンドラ（`events/battle/common_routes.py`）で
`evaluate_skill_access()` を呼び、`usable=False` なら即エラー返却。
計算済み `effective_cost` を `intent['effective_cost']` に保存し、解決時に `_apply_cost()` が優先使用する。

### 13.4 フロント連携（usable_skill_ids）

`battle_state_updated` ペイロードに `usable_skill_ids: { slot_id: [skill_id, ...] }` を同梱。
BattleStore が `usableSkillIds` として保持し、DeclarePanel のスキルピッカー・ドロップダウンが
リスト外スキルを `is-sealed`（封印表示）でマークする。サーバー側の判定が正本であり、
フロント表示はあくまで UX 補助。

**実装ファイル**:
- `manager/battle/skill_access.py` — コア判定ロジック全体
- `manager/battle/system_skills.py` — SYS-STRUGGLE 定義
- `manager/battle/select_resolve_state.py` — `_build_usable_skill_ids()` でペイロード生成
- `events/battle/common_routes.py` — commit 時再検証
- `static/js/battle/core/BattleStore.js` — `usableSkillIds` ストア管理
- `static/js/battle/components/DeclarePanel.js` — `is-sealed` 表示

---

## 亀裂ラウンド管理仕様（統合）

**文書種別**: 実装仕様（implemented）  
**ステータス**: 実装済み  
**対象コード**: `manager/game_logic.py`, `manager/battle/condition_eval.py`, `manager/battle/buff_power.py`, `manager/battle/skill_effect_helpers.py`, `manager/utils.py`, `manager/battle/common_manager.py`, `manager/battle/core.py`, `plugins/fissure.py`

---

## 1. 仕様要点（亀裂）

本仕様では、亀裂付与の管理を次のルールで統一する。

1. `APPLY_STATE` で `state_name: "亀裂"` かつ `value > 0` の場合:
   - `rounds > 0` が指定されていれば、新方式（時限亀裂バフ管理）で付与
   - `rounds` 未指定なら、旧方式（永続の状態異常加算）で付与
2. `APPLY_STATE_PER_N` で `state_name: "亀裂"` かつ `value > 0` の場合:
   - `rounds > 0` 指定時のみ新方式で付与
   - `rounds` 未指定時は旧方式のまま
3. `APPLY_FISSURE_BUFFED` も引き続き利用可能（新方式に合流）

---

## 2. 新方式のデータ管理（亀裂）

### 2.1 亀裂バフの表現

新方式では `special_buffs` に `buff_id: "Bu-Fissure"` を作成して管理する。  
バフ名は `亀裂_R{rounds}`（例: `亀裂_R4`）を使用する。

代表例:

```json
{
  "name": "亀裂_R4",
  "buff_id": "Bu-Fissure",
  "lasting": 4,
  "count": 3,
  "data": {
    "fissure_count": 3,
    "original_rounds": 4
  }
}
```

### 2.2 スタック規則（亀裂）

1. 同一 `original_rounds` の既存バフがある場合:
   - `count` のみ加算
   - `lasting` は更新しない（延長しない）
2. `original_rounds` が異なる場合:
   - 別バケットとして新規作成

---

## 3. 亀裂付与量上昇バフ（突き崩す等）の確定挙動

`_Crack` / `_CrackOnce` の `state_bonus(stat="亀裂")` は、新方式でも適用される。  
付与量は次で確定する。

`final_amount = base_amount + bonus_amount`

この `final_amount` は、**使用したスキルが指定した `rounds` の亀裂バケットへそのまま加算**する。  
増量分だけ別ラウンドのバケットを作ることはしない。

`_CrackOnce` は、実際に亀裂付与が成立した時のみ消費する。

---

## 4. 終了処理と崩壊処理（亀裂）

### 4.1 ラウンド終了時

`Bu-Fissure` の `lasting` が 0 になったら、対応する `count` 分だけ `亀裂` ステータスを減算してからバフを削除する。

### 4.2 亀裂崩壊時

`亀裂崩壊_DAMAGE` / `FISSURE_COLLAPSE` で亀裂を消費する際は、`亀裂` ステータス減算とあわせて `Bu-Fissure` バケットも整合して削除する。

---

## 5. スキルJSON書き換えガイド（亀裂）

### 5.1 推奨方針

実装済み方針に合わせ、既存 `APPLY_STATE` 形式に `rounds` を追加する移行を推奨する。

- `rounds` あり: 時限亀裂
- `rounds` なし: 永続亀裂（旧仕様互換）

### 5.2 変換ルール

1. `APPLY_STATE` + `state_name: "亀裂"` + `value > 0`:
   - 時限化したい場合は `rounds` を追加
2. `APPLY_STATE_PER_N` + `state_name: "亀裂"` + `value > 0`:
   - 時限化したい場合は `rounds` を追加
3. `value <= 0` の亀裂減算・消費:
   - 既存定義を維持（書き換え不要）
4. 亀裂崩壊系 `CUSTOM_EFFECT`:
   - JSON変更不要（実装側で `Bu-Fissure` 整合クリア）
5. 増量バフを付与するスキル（例: `突き崩す_CrackOnce1`）:
   - 原則変更不要
   - 亀裂を実際に付与するスキル側に `rounds` を設定すること

### 5.3 書き換え例

#### 例A: `APPLY_STATE` を時限化（推奨）

変更前:

```json
{
  "timing": "HIT",
  "type": "APPLY_STATE",
  "target": "target",
  "state_name": "亀裂",
  "value": 1
}
```

変更後:

```json
{
  "timing": "HIT",
  "type": "APPLY_STATE",
  "target": "target",
  "state_name": "亀裂",
  "value": 1,
  "rounds": 3
}
```

#### 例B: `APPLY_STATE_PER_N` を時限化

変更前:

```json
{
  "timing": "HIT",
  "type": "APPLY_STATE_PER_N",
  "source": "self",
  "source_param": "戦慄",
  "per_N": 2,
  "target": "target",
  "state_name": "亀裂",
  "value": 1,
  "max_value": 2
}
```

変更後:

```json
{
  "timing": "HIT",
  "type": "APPLY_STATE_PER_N",
  "source": "self",
  "source_param": "戦慄",
  "per_N": 2,
  "target": "target",
  "state_name": "亀裂",
  "value": 1,
  "max_value": 2,
  "rounds": 3
}
```

#### 例C: 明示的に `APPLY_FISSURE_BUFFED` を使う場合（互換）

```json
{
  "timing": "HIT",
  "type": "APPLY_FISSURE_BUFFED",
  "target": "target",
  "rounds": 3,
  "value": 1
}
```

---

## 6. 実装確認チェック（亀裂）

1. `rounds` 付き `APPLY_STATE` で亀裂が `Bu-Fissure` 管理に入ること
2. `rounds` なし `APPLY_STATE` が旧挙動（永続）を維持すること
3. `_Crack` / `_CrackOnce` 増量分がスキル指定 `rounds` バケットに合算されること
4. ラウンド満了で `count` 分だけ `亀裂` が減算されること
5. 崩壊時に `Bu-Fissure` バケットが整合して消去されること
