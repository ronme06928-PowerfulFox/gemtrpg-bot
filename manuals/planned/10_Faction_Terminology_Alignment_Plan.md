# 陣営用語整理 実装計画

**最終更新日**: 2026-03-23
**対象バージョン**: Current
**対象機能**: 陣営用語整理

---

## 1. Scope

- 目的: `味方/敵` と `ally/enemy` の混在で生じる認知負荷を下げ、仕様語・表示語・内部キーの役割を整理する。
- 対象:
  - `target_scope` と relation 条件の仕様整理
  - `味方指定` など既存タグの位置づけ整理
  - 関連マニュアルと最低限の UI ヘルプ文言
- 非対象:
  - `ally/enemy` 内部キーの全面廃止
  - 任意陣営表示名機能の本実装
  - 状態異常スタック合計効果

---

## 2. Current-State Investigation

### 2.1 内部判定は `ally/enemy` に強く依存している

- サーバー側:
  - [manager/game_logic.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/game_logic.py)
  - [manager/battle/core.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/battle/core.py)
  - [manager/battle/common_manager.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/battle/common_manager.py)
  - [events/battle/common_routes.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/events/battle/common_routes.py)
- フロント側:
  - [static/js/battle/components/DeclarePanel.js](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/static/js/battle/components/DeclarePanel.js)
  - [static/js/visual/visual_map.js](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/static/js/visual/visual_map.js)

### 2.2 仕様上は `same_team` が既に存在する

- `condition.source=relation` では `same_team`, `target_is_ally`, `target_is_enemy` が使える。
- したがって、仕様語を `同陣営/相手陣営` に寄せるための土台は既にある。

### 2.3 `味方指定` は現在「タグから `target_scope=ally` を推論するための互換キー」

- [manager/battle/core.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/battle/core.py)
- [events/battle/common_routes.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/events/battle/common_routes.py)
- [static/js/battle/components/DeclarePanel.js](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/static/js/battle/components/DeclarePanel.js)

現状の意味:

- `味方指定`
- `ally_target`
- `target_ally`

これらは実質的に「対象陣営は術者と同じ側」を表している。

---

## 3. Terminology Policy

用語整理後は、次の 3 層を明確に分ける。

1. 内部キー
   - `ally`
   - `enemy`
2. 仕様語
   - `同陣営`
   - `相手陣営`
3. 表示語
   - UI やログでは文脈に応じて `味方`
   - UI やログでは文脈に応じて `敵`

要点:

- 仕様語としては `味方/敵` より `同陣営/相手陣営` を優先する。
- 内部キーは当面 `ally/enemy` のまま維持する。

---

## 4. `味方指定` タグの位置づけ

### 4.1 整理後の立ち位置

- `味方指定` は **正本の仕様語ではなく、旧データ互換のためのタグ alias** とする。
- その意味は「術者から見て同陣営を対象にする」であり、本質は `味方` ではなく `同陣営`。

### 4.2 正本で推奨する書き方

新規 JSON 定義では、タグより `target_scope` を優先する。

推奨:

```json
{
  "tags": ["非ダメージ"],
  "target_scope": "same_team",
  "effects": [
    {
      "timing": "RESOLVE_START",
      "type": "APPLY_BUFF",
      "target": "target",
      "buff_name": "筋力強化_Atk1",
      "lasting": 1,
      "delay": 0
    }
  ]
}
```

互換として有効:

```json
{
  "tags": ["非ダメージ", "味方指定"],
  "power_bonus": [],
  "cost": [],
  "effects": [
    {
      "timing": "RESOLVE_START",
      "type": "APPLY_BUFF",
      "target": "target",
      "buff_name": "筋力強化_Atk1",
      "lasting": 1,
      "delay": 0
    }
  ]
}
```

### 4.3 方針

- `味方指定` / `ally_target` / `target_ally` は引き続き受理する
- ただし文書上は「互換タグ」として扱う
- 新規仕様では `target_scope: "same_team"` を主とする

---

## 5. Detailed Plan

### Phase 1: `target_scope` の正本語を整理

主変更先:

- [manager/battle/core.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/battle/core.py)
- [manager/battle/common_manager.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/battle/common_manager.py)
- [events/battle/common_routes.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/events/battle/common_routes.py)
- [static/js/battle/components/DeclarePanel.js](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/static/js/battle/components/DeclarePanel.js)
- [static/js/visual/visual_map.js](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/static/js/visual/visual_map.js)

実装内容:

- `target_scope` の受理値に次を追加する。
  - `same_team`
  - `opposing_team`
- 内部では次へ正規化する。
  - `same_team` -> `ally`
  - `opposing_team` -> `enemy`

完了条件:

- 新規スキル定義で `same_team/opposing_team` を使える。
- 既存 `ally/enemy` はそのまま使える。

### Phase 2: 互換タグの位置づけを固定

主変更先:

- [manager/battle/core.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/battle/core.py)
- [events/battle/common_routes.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/events/battle/common_routes.py)
- [static/js/battle/components/DeclarePanel.js](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/static/js/battle/components/DeclarePanel.js)

実装内容:

- 既存タグ:
  - `味方指定`
  - `味方対象`
  - `ally_target`
  - `target_ally`
- これらはすべて `target_scope=same_team` 相当の互換 alias として扱う。
- `敵対象` / `enemy_target` も同様に `opposing_team` 側の互換 alias として整理する。

完了条件:

- タグ由来推論は残るが、仕様上は「正本ではない」ことが明記される。

### Phase 3: relation 条件の語を整理

主変更先:

- [manager/game_logic.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/game_logic.py)
- 実装済みマニュアル

実装内容:

- `same_team` を relation 条件の主語として格上げする。
- `target_is_ally`, `target_is_enemy` は互換 alias として残す。
- 文書上は `target_is_ally` を「術者から見て同陣営」、`target_is_enemy` を「術者から見て相手陣営」と説明する。

完了条件:

- 条件式の説明が `味方/敵` 依存から少し離れ、文脈依存の誤解が減る。

### Phase 4: 文書・ヘルプ文言更新

主変更先:

- [manuals/implemented/03_Integrated_Data_Definitions.md](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manuals/implemented/03_Integrated_Data_Definitions.md)
- [manuals/implemented/08_Skill_Logic_Reference.md](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manuals/implemented/08_Skill_Logic_Reference.md)
- [manuals/implemented/09_SelectResolve_Spec.md](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manuals/implemented/09_SelectResolve_Spec.md)
- [static/js/modals.js](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/static/js/modals.js)

実装内容:

- `味方指定` の説明を「互換タグ」に変更する。
- 新規定義では `target_scope: "same_team"` を推奨と明記する。
- ヘルプ文言では `同陣営対象` / `相手陣営対象` を優先し、必要なら括弧で `味方対象` / `敵対象` を併記する。

完了条件:

- JSON 設計書と UI ヘルプの語が揃う。

### Phase 5: 任意表示名は別タスク化

これは今回の用語整理と切り離す。

理由:

- 「仕様語をどうするか」と「UI上の陣営ラベルを何にするか」は別の論点
- 同時に扱うと判断が混線しやすい

---

## 6. Test Plan

### 6.1 Unit tests

追加・更新先候補:

- [tests/test_battle_multiplier_relation.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/tests/test_battle_multiplier_relation.py)
- [tests/test_skill_target_tags.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/tests/test_skill_target_tags.py)

主ケース:

1. `target_scope=same_team` が既存 `ally` と同義に動く
2. `target_scope=opposing_team` が既存 `enemy` と同義に動く
3. `味方指定` タグが `same_team` 相当に解釈される
4. `敵対象` タグが `opposing_team` 相当に解釈される
5. `same_team` relation 条件が既存ケースを壊さない

### 6.2 Frontend smoke

確認対象:

- [static/js/battle/components/DeclarePanel.js](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/static/js/battle/components/DeclarePanel.js)
- [static/js/modals.js](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/static/js/modals.js)

主ケース:

1. 新旧表記のスキルがどちらも対象選択可能
2. ヘルプ文言が「互換タグ」として読める内容になっている

---

## 7. Risks and Mitigations

- リスク: `味方指定` を急に非推奨化すると既存データ作者が混乱する
  - 対策: 「互換として継続サポート」と明記する
- リスク: `same_team` を導入しても UI 表示が全部変わるわけではない
  - 対策: 仕様語と表示語は別レイヤとして説明する
- リスク: 内部キーまで変える話と混同される
  - 対策: 内部キー `ally/enemy` は当面維持と明記する

---

## 8. Proposed Change List

- [manager/game_logic.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/game_logic.py)
- [manager/battle/core.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/battle/core.py)
- [manager/battle/common_manager.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manager/battle/common_manager.py)
- [events/battle/common_routes.py](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/events/battle/common_routes.py)
- [static/js/battle/components/DeclarePanel.js](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/static/js/battle/components/DeclarePanel.js)
- [static/js/visual/visual_map.js](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/static/js/visual/visual_map.js)
- [static/js/modals.js](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/static/js/modals.js)
- [manuals/implemented/03_Integrated_Data_Definitions.md](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manuals/implemented/03_Integrated_Data_Definitions.md)
- [manuals/implemented/08_Skill_Logic_Reference.md](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manuals/implemented/08_Skill_Logic_Reference.md)
- [manuals/implemented/09_SelectResolve_Spec.md](C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/manuals/implemented/09_SelectResolve_Spec.md)

---

## 9. Acceptance Criteria

1. 新規仕様で `same_team/opposing_team` を使って対象陣営を表現できる。
2. `味方指定` を含む既存タグは互換 alias として引き続き動作する。
3. 実装済みマニュアル上で `味方指定` は「互換タグ」、`target_scope` は「正本の指定方法」と整理されている。
4. 内部キー `ally/enemy` を維持したまま、仕様語と表示語の役割分担が明示されている。
