# 状態異常スタック合計効果 実装計画

**最終更新日**: 2026-03-23
**対象バージョン**: Current
**対象機能**: 状態異常スタック合計参照効果

---

## 1. Scope

- 目的: 対象に付与されている状態異常スタック数の合計を参照し、ダメージや任意状態異常付与量を決定できる基盤を追加する。
- 対象:
  - [manager/game_logic.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/game_logic.py)
  - [manager/utils.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/utils.py)
  - [manager/skill_effects.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/skill_effects.py)
  - [manager/battle/core.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/battle/core.py)
  - 関連テストと実装済みマニュアル
- 非対象:
  - 陣営用語整理
  - UI文言変更
  - バフ/デバフ名称体系の全面見直し

---

## 2. Current-State Investigation

### 2.1 効果解決の中心は `process_skill_effects(...)`

- [manager/game_logic.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/game_logic.py) が `APPLY_STATE`, `APPLY_STATE_PER_N`, `APPLY_BUFF`, `CUSTOM_DAMAGE` などを解釈している。
- `APPLY_STATE_PER_N` は既に「参照値を N ごとに換算して状態異常を付与する」枠組みを持つ。

### 2.2 単一状態は読めるが、全状態異常の合計は読めない

- [manager/utils.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/utils.py) の `get_status_value(...)` は単一の `state` / `param` を返す。
- 現状は「対象に付いている複数状態異常のスタック合計」を 1 つの参照値として扱う経路がない。

### 2.3 ダメージ系と状態異常付与系は分けて考えた方が自然

- 状態異常付与は `APPLY_STATE_PER_N` へ接続しやすい。
- ダメージは `CUSTOM_DAMAGE` 系のログ、ダメージソース、on-damage 系との整合が必要で、専用 effect の方が責務が明確。

---

## 3. Requested Behavior Breakdown

今回実現したい挙動は次の 2 系統に分けられる。

1. 状態異常スタック合計を参照してダメージを与える
2. 状態異常スタック合計を参照して任意状態異常を N ごとに M 付与する

そのため、まずは「合計スタック数を返す共通参照値」を追加し、その上で使い道を増やすのが最も保守しやすい。

---

## 4. Implementation Policy

- 方針A: 先に共通参照値を追加する。
- 方針B: 状態異常付与は既存 `APPLY_STATE_PER_N` を再利用する。
- 方針C: ダメージは `CUSTOM_DAMAGE` 系の専用 effect として追加する。
- 方針D: 初期実装では「`states` にある正の値の合計」を基準とし、フィルタ拡張は後続に回す。

---

## 5. Detailed Plan

### Phase 1: 共通参照値の追加

主変更先:

- [manager/game_logic.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/game_logic.py)
- 必要に応じて [manager/utils.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/utils.py)

実装内容:

- `get_total_status_stacks(...)` 相当の共通ヘルパーを追加する。
- 初期仕様:
  - 入力: `char_obj`
  - 対象: `char_obj["states"]`
  - 集計対象: `value > 0` の状態
  - 返り値: 全状態異常スタック数の整数合計
- 効果解決中に読める参照値として次を受け付ける。
  - `total_status_stacks`
  - `状態異常スタック合計`

完了条件:

- 任意キャラの状態異常スタック合計を安定して参照できる。

### Phase 2: `APPLY_STATE_PER_N` への接続

主変更先:

- [manager/game_logic.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/game_logic.py)
- [tests/test_skill_catalog_smoke.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/tests/test_skill_catalog_smoke.py)

実装内容:

- `APPLY_STATE_PER_N` の `source_param` として `total_status_stacks` を利用可能にする。
- これにより次のような定義が可能になる。

```json
{
  "timing": "HIT",
  "type": "APPLY_STATE_PER_N",
  "target": "target",
  "source": "target",
  "source_param": "total_status_stacks",
  "state_name": "破裂",
  "per_N": 3,
  "value": 1
}
```

完了条件:

- 状態異常スタック合計を使って、任意状態異常の N ごと付与が既存 effect で記述できる。

### Phase 3: ダメージ用 effect の追加

主変更先:

- [manager/game_logic.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/game_logic.py)
- [manager/skill_effects.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/skill_effects.py)
- [manager/battle/core.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/battle/core.py)

候補 effect:

- `CUSTOM_DAMAGE_PER_N`
- または `CUSTOM_DAMAGE_FROM_PARAM`

推奨形:

```json
{
  "timing": "HIT",
  "type": "CUSTOM_DAMAGE_PER_N",
  "target": "target",
  "source": "target",
  "source_param": "total_status_stacks",
  "per_N": 3,
  "value": 1,
  "max_value": 10,
  "damage_name": "状態異常破裂"
}
```

実装内容:

- 参照値を N ごとに換算して `CUSTOM_DAMAGE` 相当の変更予約を生成する。
- 既存ログ、`DamageSource.SKILL_EFFECT`、on-damage 系処理に自然に接続する。

完了条件:

- 状態異常スタック合計ベースの追加ダメージが、既存ダメージ経路へ統合される。

### Phase 4: 将来拡張の受け皿

初期版では必須ではないが、次の余地を残して設計する。

- `status_stack_filter: all | debuff | buff`
- `status_names: [...]`
- `exclude_status_names: [...]`

これにより、将来「特定状態だけ数える」派生仕様へ進めやすくなる。

---

## 6. Test Plan

### 6.1 Unit tests

追加・更新先候補:

- 新規 `tests/test_status_stack_total_effects.py`
- [tests/test_skill_catalog_smoke.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/tests/test_skill_catalog_smoke.py)

主ケース:

1. `states` が空なら合計 0
2. 複数状態異常の合計が正しく算出される
3. `APPLY_STATE_PER_N + total_status_stacks` が期待値どおり動く
4. `max_value` が効く
5. 解決中の前段変化を反映して再計算される

### 6.2 Integration tests

追加先候補:

- [tests/test_select_resolve_smoke.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/tests/test_select_resolve_smoke.py)

主ケース:

1. 状態異常スタック合計参照ダメージがログ込みで自然に反映される
2. 既存スキル挙動を壊していない

---

## 7. Risks and Mitigations

- リスク: 何を「状態異常」と数えるかが曖昧
  - 対策: 初期版は `states` の正値合計に限定する
- リスク: ダメージまで `APPLY_STATE_PER_N` に寄せると責務が曖昧
  - 対策: ダメージは別 effect に分ける
- リスク: 既存スキルとの兼ね合いで解決順が崩れる
  - 対策: 既存 `simulated_chars` ベースの流れに合わせ、同一ターン再計算のテストを先に置く

---

## 8. Proposed Change List

- [manager/game_logic.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/game_logic.py)
- [manager/utils.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/utils.py)
- [manager/skill_effects.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/skill_effects.py)
- [manager/battle/core.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/battle/core.py)
- [manuals/implemented/03_Integrated_Data_Definitions.md](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manuals/implemented/03_Integrated_Data_Definitions.md)
- [manuals/implemented/08_Skill_Logic_Reference.md](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manuals/implemented/08_Skill_Logic_Reference.md)
- 新規 `tests/test_status_stack_total_effects.py`

---

## 9. Acceptance Criteria

1. 状態異常スタック合計を返す共通参照値が追加されている。
2. その参照値を使って「N ごとに任意状態異常 M 付与」が実現できる。
3. その参照値を使って「N ごとにダメージ M」が実現できる。
4. 既存スキルの挙動を壊さない。
