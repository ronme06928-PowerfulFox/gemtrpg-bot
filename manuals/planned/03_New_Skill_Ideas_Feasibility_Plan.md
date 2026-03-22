**最終更新日**: 2026-03-15
**対象バージョン**: Current
**対象機能**: 行動阻害系スキル / フォールバック技 / 逆襲 / 気合い / 経過ターン条件 / ランダムターゲット

---

## 1. 本書の目的

意見箱で挙がった以下の案について、現行コードを前提に「今の実装でどこまで乗るか」「どこを直せば安全に実装できるか」を整理する。

- 行動阻害系スキル
  - FP消費の技を使えなくする
  - 要求FP+1
  - コスト参照の封印
  - カテゴリ参照の封印
  - 距離参照の封印
  - 属性参照の封印
- 何も使えない状態専用の特殊スキル（いわゆる「わるあがき」枠）
- そのターン被ダメージがあれば与ダメ増加 + その相手への追加ダメージ（逆襲）
- 1ターン行動を消費して次の攻撃の与ダメを 2.5 倍（気合い）
- 経過ターンを発動条件にしたスキル
- ランダムターゲット技（敵味方含む）

---

## 2. 現状調査サマリ

### 2.1 既存の強み

- スキル効果の拡張点は既にある
  - `manager/game_logic.py::process_skill_effects`
  - `condition`
  - `effects[]`
  - `CUSTOM_EFFECT`
- 与ダメ倍率・被ダメ倍率の基盤は既にある
  - `manager/game_logic.py::compute_damage_multipliers`
  - `manager/battle/core.py::process_on_hit_buffs`
- Select/Resolve 側には対象整形とスロット管理の基盤がある
  - `events/battle/common_routes.py::_normalize_target_by_skill_compat`
  - `events/battle/common_routes.py::_build_tags`
- AI 側には「使えるスキル一覧」を作る入口がある
  - `manager/battle/battle_ai.py::list_usable_skill_ids`

### 2.2 先に認識すべき制約

- Select/Resolve のサーバー側は、現状 `battle_intent_commit` で「そのキャラがそのスキルを本当に使えるか」を検証していない。
  - `events/battle/common_routes.py::on_battle_intent_commit`
  - つまり、現状のままではクライアント側だけで封印や追加コストを実装しても、ソケット直叩きで回避される。
- コスト検証は現状ほぼ UI 側だけ。
  - `static/js/battle/components/DeclarePanel.js::_evaluateCost`
  - `manager/battle/core.py::verify_skill_cost` は AI で使われているが、プレイヤーの宣言確定では使われていない。
- DeclarePanel は `commands` からスキルを1件も拾えないと、全スキル一覧へフォールバックする。
  - `static/js/battle/components/DeclarePanel.js::_extractActorSkillCandidates`
  - そのため「封印したので commands を空にする」は危険。逆に全スキルが見えてしまう。
- Resolve 必須スロット判定は「行動可能かどうか」で決まり、「使えるスキルがあるかどうか」は見ていない。
  - `events/battle/common_routes.py::_required_slots`
  - そのため、全スキル封印だけ実装すると「宣言できずに進行停止」になりやすい。
- 条件式 `condition` は現状 `self / target / target_skill / skill / actor_skill / relation` のみ。
  - `manager/game_logic.py::check_condition`
  - 戦闘ラウンド数を直接参照できない。
- ランダム対象は現状「スキル効果の対象解決」にだけある。
  - `manager/game_logic.py::process_skill_effects` の `target_select=RANDOM`
  - 宣言スキル本体のターゲット型としては未対応。
- バフ基底クラスには `on_round_start` / `on_round_end` / `modify_target` / `on_skill_declare` が定義されているが、現行戦闘ループで汎用的に呼ばれていない。
  - `plugins/buffs/base.py`
  - そのため「バフフックだけで全部やる」設計は避けた方が安全。

### 2.3 結論

各案はすべて実装可能。ただし、まず「スキル使用可否をサーバー側で一元判定する層」を作らないと、封印系・追加コスト系・フォールバック技は破綻しやすい。

---

## 3. 優先して入れるべき共通基盤

## 3.1 新規で作るべき共通判定層

新規モジュールを追加し、スキル選択可否をサーバー側で一元化する。

推奨ファイル:

- `manager/battle/skill_access.py`

最低限ここに持たせる関数:

- `extract_declared_skill_ids(actor)`
- `build_skill_reference(skill_id, skill_data)`
- `collect_skill_constraints(actor)`
- `evaluate_skill_access(actor, skill_id, room_state=None, battle_state=None, slot_id=None)`
- `get_usable_skill_ids(actor, room_state=None, battle_state=None, slot_id=None, allow_fallback=True)`
- `get_effective_skill_cost(actor, skill_id, skill_data, room_state=None, battle_state=None, slot_id=None)`

`evaluate_skill_access(...)` の戻り値推奨:

```python
{
    "allowed": True,
    "reasons": [],
    "effective_cost": [{"type": "FP", "value": 2}],
    "matched_rules": [],
    "is_fallback": False,
}
```

### 3.2 この共通層を呼ぶ場所

- `manager/battle/battle_ai.py::list_usable_skill_ids`
  - AI と PvE の選択肢を共通化する
- `events/battle/common_routes.py::on_battle_intent_change_skill`
  - UI 上のプレビュー時点で不正スキルを弾く
- `events/battle/common_routes.py::on_battle_intent_commit`
  - 宣言確定時にサーバー側で最終検証する
- `manager/battle/core.py::_apply_cost`
  - 実消費コストを「生コスト」ではなく「実効コスト」に置き換える
- `manager/battle/common_manager.py::build_select_resolve_state_payload`
  - 可能なら `slot_usable_skill_ids` か `slot_skill_access` を payload に乗せ、UI の候補表示もサーバー準拠にする
- `static/js/battle/components/DeclarePanel.js`
  - `commands` 文字列の生パースより、サーバーが返した候補を優先表示する

### 3.3 スキル制約の持ち方

封印や追加コストは、個別実装を乱立させず「スキル制約ルール」として統一するのがよい。

推奨保持場所:

- `char["special_buffs"][].data.skill_constraints`
- または `char["flags"]["skill_constraints"]`

推奨形式:

```json
[
  {
    "mode": "block",
    "match": { "cost_types": ["FP"] },
    "reason": "FP消費技封印"
  },
  {
    "mode": "add_cost",
    "match": { "cost_types": ["FP"] },
    "add_cost": [{ "type": "FP", "value": 1 }],
    "reason": "FP要求+1"
  }
]
```

`match` で最低限対応したい項目:

- `skill_id`
- `tags`
- `category`
- `distance`
- `attribute`
- `cost_types`
- `cost_min`
- `cost_max`
- `target_scope`

---

## 4. 案ごとの実現可能性と実装方針

## 4.1 行動阻害系スキル

### 実現可能性

- 実装可能
- 優先度は高い
- 難易度は中

### 現状との相性

- 封印条件そのものは、スキルメタ情報を正規化すれば実装しやすい
- ただし現状は「プレイヤー宣言時のサーバー検証」が弱いので、そこを直さないと成立しない

### 推奨実装

封印・追加コストを「スキル制約ルール」に寄せる。

対応例:

- FP消費技を振れない
  - `mode=block`, `match.cost_types=["FP"]`
- 要求FP+1
  - `mode=add_cost`, `match.cost_types=["FP"]`, `add_cost=[{"type":"FP","value":1}]`
- コスト参照の封印
  - `match.cost_types=["MP"]`
  - `match.cost_min={"FP":1}` のような閾値条件
- カテゴリ参照の封印
  - `match.category=["物理"]`
- 距離参照の封印
  - `match.distance=["遠隔"]`
- 属性参照の封印
  - `match.attribute=["火"]`

### 実装の要点

- `build_skill_reference(...)` でスキルデータを正規化する
  - `category`
  - `distance`
  - `attribute`
  - `tags`
  - `cost`
- `evaluate_skill_access(...)` で
  - まずスキル所有確認
  - 次に封印判定
  - 次に実効コスト計算
  - 最後に支払可否判定
- `battle_intent_commit` で `allowed=False` ならサーバーエラーを返す
- `_apply_cost` でも同じ実効コストを使う
  - 宣言時と実消費時の不一致を防ぐため

### 注意

- 追加コストを UI だけで増やすのは不可
- `verify_skill_cost` をそのまま流用するだけでは足りない
  - AI 用の単純な生コスト確認だから

## 4.2 フォールバック技（わるあがき枠）

### 実現可能性

- 実装必須
- 難易度は中
- 行動阻害系を入れるなら同時実装推奨

### 現状との相性

- 現状は「使える技が1つもない」状態を前提にしていない
- `_required_slots` はそのキャラを待機対象に残すため、進行が止まりうる

### 推奨実装

予約済みのシステムスキルを1つ用意し、「通常候補が空ならそれだけを返す」方式にする。

推奨内部ID:

- `SYS-STRUGGLE`

推奨仕様:

- コストなし
- 固定小ダメージ
- 命中対象は通常の単体敵
- `system_fallback` タグを付ける
- 通常の封印ルールでは対象外にする

### 実装の要点

- `extensions.all_skill_data` に起動時登録するか、ロード後に差し込む
- `get_usable_skill_ids(...)` で通常候補が空なら `SYS-STRUGGLE` を返す
- `build_select_resolve_state_payload` で UI にも見せる
- `DeclarePanel` は `commands` が空なら全スキルフォールバックする現挙動をやめる
  - 「サーバーから来た候補だけを表示」に変える

### なぜ先に必要か

封印だけ先に入れると、

- プレイヤーは宣言できない
- GM は Resolve に進めない
- PvE AI も `None` を返しやすい

という詰み状態が起きる。

## 4.3 逆襲（被ダメで与ダメ増加 + 加害者特攻）

### 実現可能性

- 実装可能
- 難易度は中

### 現状との相性

- 与ダメ加算・倍率の入口はある
  - `process_on_hit_buffs`
  - `compute_damage_multipliers`
- ただし「このターン被ダメしたか」「誰に殴られたか」の記録が現状ない

### 推奨実装

各キャラに「被ダメ記録」を持たせる。

推奨保持:

```json
{
  "damage_taken_this_round": 8,
  "damage_sources_this_round": {
    "char_A": 5,
    "char_B": 3
  }
}
```

推奨配置:

- `char["flags"]` 配下
- もしくは `char["combat_memory"]`

### 実装の要点

- HP を減らした全経路で `record_damage_taken(defender, attacker, amount)` を呼ぶ
  - `manager/battle/core.py`
  - `manager/battle/duel_solver.py`
  - `manager/battle/wide_solver.py`
  - `manager/skill_effects.py` の即時ダメージ適用
- ラウンド終了でリセットする
  - `manager/battle/common_manager.py::process_full_round_end`
- 判定方法は2段階に分ける
  - 被ダメしていれば全体与ダメボーナス
  - さらに `current_target_id` が `damage_sources_this_round` に含まれていれば追加ボーナス

### 実装方式

以下のどちらかでよい。

- 方式A: 新しい `condition.source`
  - `source: "battle_context"`
  - `param: "damage_taken_this_round"` や `param: "target_damaged_me_this_round"`
- 方式B: 専用 `CUSTOM_EFFECT` / 専用バフ
  - 逆襲バフが `process_on_hit_buffs` で追加ダメージを返す

初回実装は 方式B の方が事故が少ない。

## 4.4 気合い（次の攻撃 2.5 倍）

### 実現可能性

- 実装可能
- 難易度は中

### 現状との相性

- 「攻撃時にダメージを増やす」入口は既にある
  - `process_on_hit_buffs`
- 一方で、汎用 `on_round_start` / `on_round_end` フックには依存しにくい

### 推奨実装

専用バフとして実装し、次にダメージを与える瞬間に消費する。

推奨:

- 新規バフ `Bu-Charge`
- 新規プラグイン `plugins/buffs/charge.py`
- `on_hit_damage_calculation` で `damage_val * 2.5` を返す
- 発動後はバフを自分で削除する

### 実装の要点

- 技そのものは非ダメージスキル
  - その行動枠を消費して自己バフを付与する
- バフ側で「次のダメージ発生時だけ」乗算する
- 「そのターン限定」にするならラウンド終了で消える期限も必要
- 「次の攻撃まで持続」にするなら、未使用のまま1ラウンド以上またぐ仕様を明文化する

### 推奨仕様

最初は以下が無難。

- 次の「ダメージを与えるスキル」1回にだけ有効
- 非ダメージスキルでは消費しない
- ラウンドをまたいでも維持
- ただし `expire_round` を持たせ、長く残りすぎないよう 1 ラウンド後に失効

## 4.5 経過ターンを発動条件にしたスキル

### 実現可能性

- 実装可能
- 難易度は低〜中

### 現状との相性

- 現状の `condition` ではラウンド数を直接読めない
- ただし `check_condition` は拡張しやすい

### 推奨実装

`condition.source` に戦闘文脈を追加する。

推奨追加:

- `source: "battle"`
- `param: "round"`

例:

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

### 実装の要点

- `manager/game_logic.py::check_condition`
- `manager/game_logic.py::_get_value_for_condition`

ここで `context` から `round` を返せるようにする。

推奨参照順:

- `context["battle_state"]["round"]`
- なければ `context["room_state"]["round"]`
- なければ `context["round"]`

### 補足

「隠しステートを毎ラウンド加算して判定する」でも理論上は可能だが、

- 毎ラウンド更新の汎用フックが弱い
- 見えない状態管理が増える

ため、素直に `round` を条件ソースへ追加した方が保守しやすい。

## 4.6 ランダムターゲット技（敵味方含む）

### 実現可能性

- 実装可能
- 難易度は中〜やや高

### 現状との相性

- 既にある `target_select=RANDOM` は「effects の対象」だけ
- 宣言スキル本体のターゲット型は
  - `none`
  - `single_slot`
  - `mass_individual`
  - `mass_summation`
  のみ
- AI 行動にはランダム対象ポリシーが既にある
  - `target_enemy_random`
  - `target_ally_random`

### 推奨実装

本体ターゲット用に新しいターゲット型を追加する。

推奨:

- `target.type = "random_single"`

スキル側の宣言:

```json
{
  "target_mode": "random_single",
  "random_target_scope": "any"
}
```

### 実装の要点

- `events/battle/common_routes.py::_validate_and_normalize_target`
  - `random_single` を受理する
- `events/battle/common_routes.py::_normalize_target_by_skill_compat`
  - ランダム対象スキルなら `random_single` を許可する
- `events/battle/common_routes.py::_build_tags`
  - 初回実装では `no_redirect=true` 推奨
- Resolve 実行直前に実ターゲットを抽選して、intent を `single_slot` に確定する
  - 生存
  - 配置済み
  - scope 条件
  を満たす候補から選ぶ

### なぜ `no_redirect` 推奨か

ランダム対象のまま宣言させると、既存の redirect/clash ロジックと噛み合いにくい。

初回は、

- ランダム対象技は redirect 対象外
- Resolve 直前に確定

とした方が既存ロジックを壊しにくい。

---

## 4.7 同一効果を複数回発動する JSON 定義

### 実現可能性

- 実装可能
- 難易度は低〜中
- 将来の多段技・連鎖技に対して効果が大きい

### 背景

現状は同じ効果を複数回発動したい場合、`effects[]` に同じオブジェクトを複製して書く必要がある。  
この方式は以下の問題を生みやすい。

- データが冗長になり、調整ミス（片方だけ値が違う）が起きる
- 説明文と実データの対応が追いづらい
- 将来の lint / 可視化で「同一意図の繰り返し」を扱いづらい

### 方式比較

方式A（推奨）: 各 effect に `repeat_count` を追加

- 例:
  - `{"timing":"HIT","type":"APPLY_STATE","state_name":"出血","value":2,"repeat_count":3}`
- 利点:
  - 既存 `type` を増やさずに済む
  - 実行エンジンの変更が最小
  - 既存の効果解釈（`APPLY_STATE` / `CUSTOM_EFFECT` 等）を再利用できる
- 欠点:
  - 「1回ごとに別 target にしたい」等の高度制御は別途設計が必要

方式B: `REPEAT_EFFECT` ラッパーを新設

- 例:
  - `{"type":"REPEAT_EFFECT","count":3,"effect":{...}}`
- 利点:
  - 意図が明示的
- 欠点:
  - `SUPPORTED_EFFECT_TYPES` 追加や lint/実行器の分岐が増える
  - ネスト処理が必要になり、初期導入のコストが上がる

結論: 初期導入は方式A（`repeat_count`）を推奨。

### 推奨仕様（v1）

- フィールド名: `repeat_count`
- 型: 正の整数
- 既定値: `1`
- 範囲: `1..20`（上限は安全装置）
- 実行意味: **その effect を `repeat_count` 回並べて書いた場合と同等**

動作ルール:

- 1回ごとに通常の `condition` 判定を行う
- 1回ごとに通常の target 解決を行う
  - `target_select=RANDOM` は回ごとに再抽選される
- 1回ごとに通常の副作用（consume / buff削除 / custom logs）を行う

### JSON 例

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

```json
{
  "effects": [
    {
      "timing": "HIT",
      "type": "CUSTOM_EFFECT",
      "value": "出血氾濫",
      "repeat_count": 2
    }
  ]
}
```

### 実装の要点

- `manager/game_logic.py::process_skill_effects` の冒頭で繰り返し展開を行う
  - 補助関数例: `_expand_repeated_effects(effects_array, max_repeat=20)`
  - 展開時は `repeat_count` を除いた effect を `N` 回複製
- 既存の effect 実行ロジック本体は変更しない（展開後データをそのまま処理）
- `tests/test_skill_catalog_smoke.py` の lint に `repeat_count` 検証を追加
  - 整数か
  - `1..20` か

### 注意点

- DoS 的な大量展開を防ぐため、`repeat_count` 上限は必須
- ログの可読性を維持するため、必要なら `"(1/3)"` 形式の補助ログを追加する
- 初期版は「多段間隔」「途中中断条件」「repeatネスト」は扱わない

---

## 5. 実装順序（推奨）

### Phase 1: 共通基盤

- `manager/battle/skill_access.py` を追加
- サーバー側でスキル使用可否を一元化
- `battle_intent_commit` にサーバー検証を追加
- `_apply_cost` を実効コスト対応に変更

### Phase 2: UI 同期

- `build_select_resolve_state_payload` に候補スキル一覧を積む
- `DeclarePanel` を「payload ベースの候補表示」に変更
- `commands` 空時の全スキルフォールバックを廃止

### Phase 3: 行動阻害 + フォールバック

- スキル制約ルールを実装
- `SYS-STRUGGLE` を導入
- AI / PvE / プレイヤーUI を統一

### Phase 4: 戦闘メモリ系

- 被ダメ記録
- 逆襲
- 気合い

### Phase 5: 条件 / ターゲット拡張

- `condition.source=battle`
- `target.type=random_single`

### Phase 6: effect JSON 繰り返し定義

- `repeat_count` 仕様を追加
- `process_skill_effects` で繰り返し展開
- lint / smoke / サンプルデータを同期

この順序なら、封印系を入れた瞬間に進行不能になる事故を避けられる。

---

## 6. 実装時の重要チェックポイント

## 6.1 サーバー権威になっているか

最重要。

確認点:

- クライアントを改造しても、封印中スキルを `battle_intent_commit` できないか
- 追加コストを払えない状態で commit が通らないか
- `commands` にないスキルIDを直接送っても弾かれるか

UI だけで防いでも不十分。

## 6.2 宣言時と解決時でコストが一致しているか

確認点:

- DeclarePanel の表示コスト
- commit 時の検証コスト
- `_apply_cost` の実消費

この3つが同じ計算を見ているか。

1つでもズレると、

- 宣言できるのに発動時に失敗
- 宣言できないのに本当は払える
- 表示だけ FP+1 で実消費が増えていない

が起きる。

## 6.3 フォールバック技で進行停止しないか

確認点:

- 全スキル封印時に候補が `SYS-STRUGGLE` のみになるか
- AI が `None` ではなくフォールバック技を選ぶか
- GM の Resolve ready 判定が詰まらないか

## 6.4 被ダメ記録の更新漏れがないか

確認点:

- Select/Resolve
- 旧 duel
- wide
- `CUSTOM_EFFECT`
- 追撃
- 反射

どのダメージ経路で記録され、どの経路で抜けているか。

逆襲系はここが最も壊れやすい。

## 6.5 ラウンド境界で状態が正しく消えるか

確認点:

- 被ダメ記録
- 気合いの未使用バフ
- 一時的な制約
- フォールバック用の一時候補

「消し忘れ」と「早く消えすぎ」の両方を見る。

## 6.6 ランダム対象のログが再現できるか

確認点:

- Resolve trace に「最終的に誰へ当たったか」が残るか
- 観戦側 UI と操作者 UI で表示が一致するか
- リプレイ時に混乱しない粒度でログが出るか

ランダム対象は、演算そのものよりログ不整合で荒れやすい。

## 6.7 既存の redirect / clash / mass と干渉しないか

確認点:

- ランダム対象技が redirect に巻き込まれないか
- 味方指定封印や `target_scope=ally` と衝突しないか
- mass スキルに追加コストや封印が正しく乗るか
- `USE_SKILL_AGAIN` で再使用時も封印・実効コスト判定が壊れないか

---

## 7. 最小テスト項目

最低でも以下を追加する。

- 「FP消費技封印」中は FP コスト持ちだけ commit 不可
- 「要求FP+1」中は表示・commit・実消費が全て同じ値になる
- 全スキル封印時に `SYS-STRUGGLE` のみ使用可能
- 全スキル封印時でも Resolve ready が詰まらない
- 被ダメしたターンのみ逆襲補正が乗る
- 同ターンに自分を殴った相手へだけ追加逆襲ダメージが乗る
- 気合いは次のダメージスキル1回だけ 2.5 倍になり、その後は消える
- `condition.source=battle, param=round` が 1R/2R/3R で正しく切り替わる
- ランダム対象技が `random_single` で有効候補からのみ選ばれる
- ランダム対象技が有効候補ゼロのとき安全に不発または規定フォールバックになる
- `repeat_count=3` が同一 effect 3件手書きと同じ結果になる
- `repeat_count` が 0 / 負数 / 上限超過のとき lint で失敗する
- `target_select=RANDOM` + `repeat_count` で各回が独立抽選になる

---

## 8. 実装判断の要点（要約）

- 行動阻害系は「個別ギミック」ではなく「スキル制約ルール」に統一した方が拡張しやすい
- フォールバック技は、行動阻害系を安全に入れるための前提機能
- 逆襲と気合いは、既存のダメージ補正基盤を使えるが「戦闘メモリ」の追加が必要
- 経過ターン条件は `condition` 拡張が最短
- ランダムターゲット技は新 target type を追加し、初回は `no_redirect` 前提で入れるのが安全
- 同一効果複数回発動は `repeat_count` を標準化するとデータ保守性が上がる

---

本書は実装着手前の設計合意用ドキュメントです。実装後は `03_Integrated_Data_Definitions.md` と `07_Skill_Logic_Reference.md` に統合してください。
