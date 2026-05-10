# 23. Scorpion Crystal Retaliation Plan

**作成日**: 2026-05-09  
**ステータス**: Draft  
**対象**: サソリ系敵キャラクターの「被弾時に攻撃者へ反応する結晶毒パッシブ」

---

## 1. 目的

サソリモチーフの敵に対して、以下の性質を実装できる基盤を作る。

- 敵がダメージを受けたときに反応する
- 反応先は基本的に攻撃者
- 反応内容はまず「固定ダメージ」
- 将来的には「状態異常付与」「バフ/デバフ付与」「条件付き発動」に拡張できる

このため、単発の専用処理ではなく「被弾リアクション」用の汎用パッシブ/バフ枠を追加する方針を取る。

---

## 2. 現状整理

### 2.1 すでにあるもの

- `manager/utils.py::apply_passive_effect_buffs`
  - パッシブ効果を `special_buffs` に展開する仕組みがある
- `manager/buff_catalog.py`
  - `on_damage_state` を持つバフ定義がある
  - 例: `*_BleedReactN`, `Bu-47`
- `manager/battle/runtime_actions.py::process_on_damage_buffs`
  - 被弾時反応の入口がある
- `manager/battle/core.py`
  - Select/Resolve 系へ `process_on_damage_buffs` を注入している
- `manager/battle/resolve_match_runtime.py`, `manager/battle/resolve_effect_runtime.py`
  - 同名の委譲用プレースホルダがある

### 2.2 今の不足

- `process_on_damage_buffs` は被弾者しか受け取らない
- 現在の `on_damage_state` は「被弾者自身に状態を積む」用途のみ
- 攻撃者へ返すダメージ、状態異常、バフ/デバフの汎用表現がない
- どの攻撃者から受けた被弾かを安全に参照する経路が統一されていない

---

## 3. 実装方針

### 3.1 段階分け

#### Phase 1: 最小実装

サソリ結晶用に、被弾時に攻撃者へ固定ダメージを返す。

- 目的: コンセプト敵を最短で成立させる
- 対応内容:
  - 被弾者
  - 攻撃者
  - 被ダメージ量
  - ログ出力
  - 固定反撃ダメージ

#### Phase 2: 汎用化

同じ入口で以下も扱えるようにする。

- 攻撃者へ状態異常付与
- 攻撃者へバフ/デバフ付与
- 被弾者自身への副作用
- 条件付き発動
  - 近接のみ
  - ダメージが 1 以上
  - ラウンド内回数制限
  - 結晶スタック消費時のみ

Phase 1 を先に通し、その形を壊さず Phase 2 に拡張する。

---

## 4. 推奨データ設計

### 4.1 新しい効果キー案

既存の `on_damage_state` は残しつつ、攻撃者反応用に新キーを追加する。

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "damage": 2
  }
}
```

Phase 2 では以下まで広げる。

```json
{
  "on_damage_reaction": {
    "target": "attacker",
    "damage": 2,
    "apply_state": [
      { "name": "毒", "value": 2 }
    ],
    "apply_buff": [
      { "buff_id": "Bu-XX", "lasting": 2, "delay": 0 }
    ],
    "condition": {
      "damage_gte": 1
    },
    "max_triggers_per_action": 1
  }
}
```

### 4.2 `target` の候補

- `attacker`
- `self`

必要になるまで増やさず、まずはこの 2 種で十分。

### 4.3 既存キーとの住み分け

- `on_damage_state`
  - 後方互換のため維持
  - 既存の「被弾者自身に状態を積む」処理に使う
- `on_damage_reaction`
  - 新設
  - 攻撃者参照や複合効果はこちらに寄せる

この分離で既存仕様を壊しにくくする。

---

## 5. コード変更ポイント

### 5.1 中心処理

最優先の変更箇所:

- `manager/battle/runtime_actions.py::process_on_damage_buffs`

ここを、被弾者だけでなく攻撃者も受け取れる形に拡張する。

現状イメージ:

```python
process_on_damage_buffs(room, target_char, incoming_damage, source, log_snippets)
```

変更案:

```python
process_on_damage_buffs(
    room,
    target_char,
    incoming_damage,
    source,
    log_snippets,
    attacker_char=None,
    context=None,
)
```

### 5.2 呼び出し元

`process_on_damage_buffs(...)` を呼んでいる箇所で、攻撃者を渡す。

主な対象:

- `manager/battle/duel_solver.py`
- `manager/battle/resolve_match_runtime.py`
- `manager/battle/resolve_effect_runtime.py`
- `manager/skill_effects.py`
- 必要なら `manager/battle/wide_solver.py` 経由のルートも確認

### 5.3 委譲スタブ

以下のプレースホルダ関数もシグネチャを揃える。

- `manager/battle/resolve_match_runtime.py::process_on_damage_buffs`
- `manager/battle/resolve_effect_runtime.py::process_on_damage_buffs`

ここを揃えないと Select/Resolve 系の委譲で引数不整合が起きる。

### 5.4 パッシブ定義

パッシブ JSON 側では、最初は専用パッシブを 1 本作る。

例:

- `Crystalline Scorpion Hide`
- 説明: 被弾時、砕けた毒晶片が攻撃者へ飛散し固定ダメージ

実際の効果量や条件は後から調整する前提でよい。

---

## 6. 処理フロー案

1. 攻撃で対象がダメージを受ける
2. 既存どおり HP 減少を適用する
3. `process_on_damage_buffs(...)` を呼ぶ
4. 被弾者の `special_buffs` を走査する
5. `on_damage_state` があれば従来どおり処理する
6. `on_damage_reaction` があれば `target` を解決する
7. `target=attacker` かつ攻撃者が存在する場合のみ反応適用
8. 固定ダメージや状態異常付与を適用する
9. ログを追加する
10. 返却値は既存互換を意識して「追加で発生したHPダメージ量」を返す

---

## 7. 仕様上の注意点

### 7.1 反撃ダメージはカウンター攻撃ではない

今回は「通常攻撃の再実行」ではなく、反応ダメージとして扱う方が安全。

- 命中判定をしない
- 再帰的に再反撃を誘発しない
- スキル使用扱いにしない

つまり「結晶片ダメージ」という独立ダメージソースとして扱う。

### 7.2 無限反応の防止

反応ダメージがさらに `process_on_damage_buffs` を誘発すると連鎖事故になる。

対策案:

- ダメージソースに `retaliation` を明示する
- `retaliation` 由来のダメージでは `on_damage_reaction` を再発動させない

最低限、Phase 1 でここは必須。

### 7.3 死亡済み攻撃者

被弾反応を処理する時点で攻撃者 HP が 0 以下のケースを想定する。

- 反応先が戦闘不能なら適用しない
- ログだけ残すかは実装時に統一する

### 7.4 広域攻撃

広域攻撃では 1 攻撃者が複数対象へ与ダメする。

- 被弾者ごとに個別に反応
- 反応先は同じ攻撃者

これは今回のコンセプトと相性がよいので、特別扱いせず個別処理でよい。

---

## 8. テスト計画

### 8.1 単体テスト

新規または追記候補:

- `tests/test_phase2_value_driven_buffs.py`
  - `on_damage_state` 既存互換を維持
- `tests/test_passive_effect_buffs.py`
  - パッシブ展開後に `on_damage_reaction` が保持されること
- 新規 `tests/test_retaliation_passive.py`
  - 被弾時に攻撃者へ固定ダメージ
  - 攻撃者未指定時は安全に無視
  - 反応ダメージで再帰しない

### 8.2 統合テスト

- 一対一の通常攻撃で反応する
- One-sided / Clash / Select-Resolve 委譲ルートで同じように反応する
- 広域攻撃で複数回発動する

### 8.3 回帰確認

既存の以下に影響しやすい:

- `tests/test_select_resolve_smoke.py`
- `tests/test_skill_catalog_smoke.py`
- `tests/test_phase2_value_driven_buffs.py`

---

## 9. 実装順

1. `on_damage_reaction` のデータ仕様を追加
2. `process_on_damage_buffs` に `attacker_char` を追加
3. 主要な呼び出し元へ攻撃者引き回しを入れる
4. 反応ダメージの再帰防止を入れる
5. サソリ用パッシブを 1 本追加
6. 単体テスト
7. Select/Resolve 系の回帰テスト

---

## 10. サソリ敵への当て込み例

最初の敵実装では、以下くらいが扱いやすい。

- パッシブ名: `毒晶外殻`
- 効果:
  - 被弾時、攻撃者へ 2 ダメージ
  - 将来拡張で `毒` や `出血` を付けられる

演出上は「結晶片が砕けて飛ぶ」ログを出せるようにしておくと、敵コンセプトが伝わりやすい。

---

## 11. 結論

この機能は既存の `on_damage_state` を無理に拡張するより、

- 後方互換を保ちつつ
- `process_on_damage_buffs` を攻撃者参照可能にし
- `on_damage_reaction` を新設する

のが最も安全。

最初は「固定反撃ダメージ」のみで通し、その後に状態異常・バフ・デバフを同じ枠へ追加する実装が妥当。
