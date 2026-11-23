<!-- 旧: 05_PvE_Mode_Spec / 17_Battle_Only_Play_Mode_Spec / 18_Stage_Field_Effect_Spec を統合 (2026-05-09) -->

# プレイモード・ステージ仕様書

**最終更新日**: 2026-08-16
**系統**: D — プレイモード仕様
**統合元**: 05_PvE_Mode_Spec / 17_Battle_Only_Play_Mode_Spec / 18_Stage_Field_Effect_Spec

---

## 本書の構成

1. PvEモード仕様（旧05）
3. ステージ効果仕様（旧18）
4. ユニット管理（計画61）
5. 待機列と登場（計画61）
8. 戦闘専用ルームの廃止（計画65）

---

# Part 1: PvEモードおよび敵行動チャート仕様

**最終更新日**: 2026-02-27
**対象実装**: `manager/battle/common_manager.py` / `manager/battle/enemy_behavior.py` / `events/socket_char.py`

## 1. 概要 (Overview)

本機能は、TRPGセッションにおいてGMの負担を軽減し、戦闘の視認性を向上させることを目的とする。
主に以下の2点で構成される。

1. **PvEモード**: 敵キャラクター（Enemy）の行動指針（誰を狙うか、どのスキルを使うか）をシステムが補助・自動化するモード。
2. **行動予告矢印 (Arrow Display)**: 敵が現在どのキャラクターを狙っているかを、マップ上に矢印で可視化する機能。

---

## 2. データ構造 (Data Structure)

### 2.1 ルーム状態 (`room_state`) の拡張

`battleState` オブジェクトに以下のプロパティを追加する。

| プロパティ名 | 型 | 説明 |
| :--- | :--- | :--- |
| `battle_mode` | `string` | 現在の戦闘モード。`'pvp'` (デフォルト) または `'pve'`。 |
| `ai_target_arrows` | `Array<Object>` | AIが算出したターゲット情報のリスト。 |

**`ai_target_arrows` の要素構造:**

```json
{
  "from_id": "char_id_enemy_01",  // 攻撃者のID
  "to_id": "char_id_ally_02",    // 目標のID
  "type": "attack",              // 矢印の種類（将来拡張用: 'heal', 'support' など）
  "visible": true                // 表示フラグ（潜伏などのため）
}
```

### 2.2 キャラクターデータ (`character`) の拡張

各キャラクターオブジェクトに以下のプロパティを追加・使用する。

| プロパティ名 | 型 | 説明 |
| :--- | :--- | :--- |
| `type` | `string` | キャラクター種別。`'ally'` (味方), `'enemy'` (敵), `'npc'` (中立)。既存プロパティの活用。 |
| `auto_skill_select` | `boolean` | `true` の場合、ターン開始時にAIがスキルを自動提案する。 |
| `ai_suggested_skill_id` | `string` | AIが選択したスキルのID（一時保存用）。 |

---

## 3. サーバーサイドロジック (Server-Side Logic)

### 3.1 ターゲット決定ロジック (`ai_select_targets`)

**実行タイミング:**

- ラウンド開始時（`process_round_start`）
- 敵キャラクター出現時（増援など）

**処理フロー:**

1. **攻撃者リスト作成**: `type: 'enemy'` かつ `hp > 0` のキャラクターを抽出。
2. **対象リスト作成**: `type: 'ally'` かつ `hp > 0` かつ `x >= 0` (配置済み) のキャラクターを抽出。
3. **ターゲット割り当て**:
    - 各攻撃者について、対象リストからランダムに1体を選択。（※v1.0仕様）
    - 将来的に「ヘイト値（Aggro）」や「現在HPの低い順」などのロジックを追加可能にする。
4. **状態保存**: 結果を `state['ai_target_arrows']` に格納し、`socket.emit('state_updated')` で全クライアントに配信。

### 3.2 スキル提案ロジック (`ai_suggest_skill`)

**実行タイミング:**

- 敵キャラクターのターン開始時 (`process_next_turn`)

**処理フロー:**

1. 手番キャラクターが `auto_skill_select: true` か確認。
2. 所持スキル (`commands`) を解析。
3. 現在のMP/FPで発動可能なスキルをフィルタリング。
    - ※「即時発動」タグや「広域」タグのスキルはAI操作の複雑さを避けるため、v1.0では除外を推奨。
4. 候補からランダムに1つ選択し、`ai_suggested_skill_id` にセット。
5. GM画面に「推奨スキル: [スキル名]」と表示、あるいは自動で宣言ボタンを選択状態にする。

---

## 4. クライアントサイド実装 (Client-Side Logic)

### 4.1 矢印描画 (`ArrowRenderer.js` / `MapRenderer.js`)

**概要:**
`ai_target_arrows` データに基づき、マップ上にベクター線（SVGまたはCanvas）を描画する。
PvEモードかつ、`type: 'enemy'` の手番、あるいは常時表示の設定に従う。

**★座標計算の重要仕様:**
過去の不具合（ズーム時のズレ）を防ぐため、**DOM要素の位置 (`getBoundingClientRect`) に依存してはならない。** 必ず論理座標から計算する。

- **計算式**:
  - `StartX = (Attacker.gridX * GRID_SIZE) + (GRID_SIZE / 2)`
  - `StartY = (Attacker.gridY * GRID_SIZE) + (GRID_SIZE / 2)`
  - `EndX = (Target.gridX * GRID_SIZE) + (GRID_SIZE / 2)`
  - `EndY = (Target.gridY * GRID_SIZE) + (GRID_SIZE / 2)`
- **定数**:
  - `GRID_SIZE`: 60px (標準) ※設定により可変の場合は `state.map_data.grid_size` を参照。

**描画レイヤー:**

- `z-index`: トークンより下、背景マップより上。
- `pointer-events`: `none` (クリック判定を阻害しないこと)。

**更新トリガー:**

- `state_updated`: 矢印データの変更時。
- `character_moved`: キャラクター移動時（矢印の始点・終点を再計算）。

### 4.2 UIコントロール

**アクションドック (`ActionDock.js`) 追加項目:**

1. **モード切替ボタン (GMのみ)**
    - アイコン: ⚔️(PvP) / 🤖(PvE)
    - 機能: クリックで `request_switch_battle_mode` イベントを送信。
    - 表示: 現在のモードを色やアイコンで明示。

2. **矢印表示切替ボタン (全員)**
    - アイコン: 👁️(Visible) / 🙈(Hidden)
    - 機能: クライアントサイドでのみ矢印レイヤーの `display` を toggle する。
    - デフォルト: PvEモード時はON、PvPモード時はOFF。

---

## 5. エラーハンドリングと安全性 (Safety Measures)

1. **未配置/死亡キャラクターへの対応**
    - ターゲット決定時、`x < 0` (未配置) や `hp <= 0` (死亡) のキャラクターは対象外とする。
    - 矢印描画時、対象キャラクターがマップ上に存在しない場合は矢印を描画しない（エラー落ちを防ぐ）。

2. **同期ズレ対策**
    - サーバーからの `state_updated` を正とする。
    - クライアント側で勝手に矢印を追加・削除しない。

3. **ロールバック機能**
    - 万が一挙動がおかしい場合のために、機能を完全に無効化できる設定（Feature Flag）を設けることが望ましい。

---

## 6. 敵行動チャート（Behavior Profile）拡張

### 6.1 目的
- PvEの敵intent生成を「ランダム/AI提案」だけでなく、GM定義のループ型行動チャートで制御する。

### 6.2 定義データ
- 保存先: `character.flags.behavior_profile`
- 主キー:
  - `enabled` (bool)
  - `slot_generation_mode` (`step_actions` / `character_action_count`)
  - `initial_loop_id` (string)
  - `loops[loop_id].steps[].actions` (slot順のスキルID配列)
  - `loops[loop_id].steps[].targets` (`actions`と同じ添字に対応する対象指定配列)
  - `loops[loop_id].steps[].on_no_target` (`actions`と同じ添字に対応する対象不在処理。現在は`cancel`のみ)
  - `loops[loop_id].steps[].next_loop_id` (任意: 当該step実行後に遷移するループID)
  - `loops[loop_id].steps[].next_reset_step_index` (任意: `next_loop_id` 遷移時に先頭stepへ戻すか。既定 `true`)
  - `loops[loop_id].transitions[]` (`priority`, `when_all`, `to_loop_id`, `reset_step_index`)

`transitions[].when_all[]`は`source`、`param`、`operator`、`value`を持つ。`source:self`かつ`param:HP割合`は、実行時の`hp / maxHp * 100`を0～100へ丸め込んだ割合として評価する。最大HPが欠損、数値化不能、0以下の場合は条件不成立とし、HP0のキャラクターを誤って0%と判定しない。既存データ互換として`HP比率`、`hp_percent`、`hp_ratio`も同じ意味で受理する。

`targets`の各要素は、旧形式の対象方針文字列、または優先順に並べた対象候補配列を受け付ける。

```json
{
  "actions": ["Sk-Example"],
  "targets": [[
    {
      "team": "same_team",
      "required_tag_ids": ["瓦礫"],
      "selection": "random"
    },
    {
      "team": "opposing_team",
      "required_tag_ids": [],
      "selection": "random"
    }
  ]]
}
```

- `team`: `opposing_team` / `same_team` / `any` / `self`
- `required_tag_ids`: 対象に必要な有効タグ。複数指定時はAND条件
- `selection`: 候補内の選択方法。`random` / `fastest` / `slowest`
- 候補は先頭から評価し、対象が1体以上見つかった最初の候補を採用する。
- 候補はスキル側の`target_scope`も満たす必要がある。陣営をまたぐ候補列を使うスキルは`target_scope:any`とする。
- `self`以外の候補では、行動者が複数スロットを持つ場合も同じ行動者の全スロットを除外する。
- 全候補が空の場合は同じスキルを対象なしで確定し、不発として扱う。別スキルや暗黙の対象へフォールバックしない。

### 6.3 実行時データ
- 保存先: `battle_state.behavior_runtime`
- 例:
  - `active_loop_id`, `step_index`, `last_round`, `last_skill_ids`
- 意図:
  - 定義（profile）と実行カーソル（runtime）を分離し、ユニット配置/ID再発行時の破損を防ぐ。

### 6.4 実行優先順位
1. `behavior_profile.enabled=true` かつ有効loopあり: チャートを優先
2. チャート指定スキルが不正/空: `auto_skill_select` 系AI提案にフォールバック
3. profile未設定: 従来AI挙動を維持

### 6.5 ユニットと行動パターン
メインメニューのユニット管理で敵ユニットの「行動パターン」から共通エディターを開く。ルームでは配置済みの敵の右クリックから同じエディターを開き、その戦闘中の調整を行う。

ユニットは名前付きの `patterns` と `default_pattern_id` を持つ。編成はメンバーごとに `pattern_id` を指定できる。配置時は指定、既定の順で解決し、敵だけの `flags.behavior_profile` に写す。

### 6.6 実行エンジン
- 行動チャート実行は `manager/battle/enemy_behavior.py` で正規化・評価・次ステップ更新を行う。
- Selectフェーズでの敵intent自動生成（`_apply_pve_auto_enemy_intents`）に組み込み、敵ごとに `behavior_runtime` を参照して決定する。
- 遷移条件が不成立の場合は同一ループ内 step を進行し、step終端では `repeat` 設定に従って先頭復帰または末尾維持する。
- `steps[].next_loop_id` が指定されたstepは、そのstep使用後に `advance_step_pointer` で指定loopへ遷移する（次ラウンドから有効）。
- 実行順は「条件遷移（`transitions`）判定」→「step選択・使用」→「step使用後遷移（`next_loop_id`）」。

### 6.7 GM運用（UI）
- 敵キャラ設定から `behavior_profile` を JSON で編集できる（最小UI）。
- フローチャート編集UIでは、各ラウンドに「スキル使用後にループ遷移」チェックを持ち、ON時に遷移先ループのプルダウンを表示する。内部データの`step`キーは互換性のため維持する。
- 各スキル行には順序付き対象候補を追加できる。候補ごとに陣営、必須タグ、選択方法を設定し、上下移動と削除ができる。
- 必須タグはカンマ、読点、改行区切りで入力し、保存時に重複と空文字を除去する。
- ループ遷移条件の自身パラメータには「HP割合（%）」を表示し、値欄を0～100の数値入力として扱う。保存値の`param`は`HP割合`とする。

### 6.8 保存前チェック
ステップのスキルはユニットの所持スキルから選ぶ。パターンの最初の1つを自動で既定にし、既定を削除する場合は同時に別の既定を選ぶ。

### 6.9 チャート駆動スロット生成

- `slot_generation_mode: step_actions`では、RoundStartで確定したstepの空でない`actions`1件につき、行動スロットを1個生成する。キャラクターの`行動回数`は参照せず、`actions: []`は0スロットとして扱う。
- `slot_generation_mode: character_action_count`では、従来どおりキャラクターの`行動回数`からスロット数を決める。フィールド欠損・未知値はこの互換方式へ正規化する。
- チャート駆動方式の確定結果は`battle_state.behavior_round_plan`へラウンド単位で保存する。同じラウンドのRoundStart再実行やintent再生成ではスナップショットを再利用し、stepを重複して進めない。
- `actions[i]`、`targets[i]`、`on_no_target[i]`は同じ行動へ対応する。対象候補はRoundStart時点の戦場から検索し、`action_slot_mode: none`の対象可能キャラクターは`target_only`スロットを介して候補に含める。
- `on_no_target: cancel`で候補がない場合、そのスロットだけを`status: cancelled`かつ`disabled: true`として確定する。intentには予定スキルID、`cancelled: true`、`cancel_reason: no_target`を残すが、Resolveキューには入れず、コスト・使用回数・スキル効果を発生させない。
- チャート駆動方式で未知または使用不能なスキルを指定した場合も、`cancel_reason: skill_unavailable`として同様にキャンセルし、AI提案へ置換しない。互換方式では従来のフォールバックを維持する。
- ラウンド開始時に出現済みの召喚物は候補になる。同ラウンドのSelect完了後またはResolve中に出現した対象を、そのラウンドの確定済みintentへ遡って追加しない。

---

# Part 3: ステージ効果仕様

最終更新: 2026-04-22  
対象: 待機列で登場させるステージの効果

---

## 1. 方針
ステージ効果は、ステージに紐づく場ルールです。

- 効果の発生源はステージのみです。
- ユニット由来の効果発生は扱いません。
- ステージアバターは表示専用です。
- 戦闘ロジックは `stage_field_effect_profile.rules` のみを評価します。

---

## 2. データ構造
ステージプリセットは次の追加キーを持てます。

```json
{
  "field_effect_profile": {
    "version": 1,
    "rules": []
  },
  "stage_avatar": {
    "enabled": true,
    "name": "ステージ名",
    "description": "表示説明",
    "icon": "STAGE"
  }
}
```

待機列からステージを登場させると、選んだ適用項目がルーム状態に反映されます。

- `state.stage_field_effect_profile`
- `state.stage_avatar_profile`
- `state.stage_avatar_enabled`
- `state.field_effects`

---

## 3. 効果ルール
`field_effect_profile.rules[]` に設定できる主なキーは次の通りです。

- `type`: 必須。効果種別。
- `scope`: 任意。`ALL` / `ALLY` / `ENEMY`。省略時は `ALL`。
- `priority`: 任意。整数。高い順で評価順を安定化します。
- `value`: 任意。効果量。実処理では整数として扱います。
- `rule_id`: 任意。ログや識別用。
- `state_name`: 状態異常付与時の状態名。
- `condition`: 条件付き効果の条件。

対応済みの `type` は次の3種類です。

- `SPEED_ROLL_MOD`: 速度ロール補正。
- `DAMAGE_DEALT_MOD`: 与ダメージ補正。
- `APPLY_STATE_ON_CONDITION`: 条件成立時に状態を付与。

`condition` は次の形です。

```json
{
  "param": "HP",
  "operator": "LTE",
  "value": 50
}
```

`operator` は `GT` / `GTE` / `LT` / `LTE` / `EQ` / `NE` を使えます。

---

## 4. ステージアバター
`stage_avatar` は実処理には影響しません。  
戦闘中にステージ効果を見つけやすくするための表示情報です。

- `enabled`: 表示有効フラグ。
- `name`: 表示名。
- `description`: 説明文。
- `icon`: 短いアイコン文字列。

---

## 5. UI
ステージ効果の編集画面は PR61-2 で提供する。

- 効果ルールは「効果ルールを追加」で追加します。
- 初期状態では効果ルールは0件です。
- 効果ルールごとに折りたたみできます。
- 種類、対象、値、優先度、条件をフォームで設定できます。
- 上級者向けJSON編集欄はフォーム内容と同期します。

---

## 6. サンプル
```json
{
  "field_effect_profile": {
    "version": 1,
    "rules": [
      {
        "rule_id": "spd_down_1",
        "type": "SPEED_ROLL_MOD",
        "scope": "ALL",
        "priority": 100,
        "value": -1
      },
      {
        "rule_id": "dmg_up_enemy",
        "type": "DAMAGE_DEALT_MOD",
        "scope": "ENEMY",
        "priority": 50,
        "value": 2
      },
      {
        "rule_id": "bleed_low_hp",
        "type": "APPLY_STATE_ON_CONDITION",
        "scope": "ENEMY",
        "priority": 10,
        "state_name": "出血",
        "value": 1,
        "condition": {
          "param": "HP",
          "operator": "LTE",
          "value": 50
        }
      }
    ]
  },
  "stage_avatar": {
    "enabled": true,
    "name": "血霧闘技場",
    "description": "傷が開きやすい不吉な空間",
    "icon": "BLOOD"
  }
}
```

---

## 7. 実装対象
主な実装ファイルは次の通りです。

- `manager/field_effects.py`
- `manager/battle/common_manager.py`
- `manager/game_logic.py`
- `static/js/visual/visual_ui.js`

主なテストは次の通りです。

- `tests/test_stage_field_effects_runtime.py`

# Part 4: ユニット管理（計画61）

`catalog_entries` と `catalog_history` の種類を `unit`、`formation`、`stage`、`unit_collection` とする。ID は U-001、F-001、ST-001、SC-01 の形式。分類は `collection_id`、編成の陣営は `type`、メンバーは `{unit_id, count, pattern_id}` で保存する。

公開範囲は `public` と `staff`。後者は制作者・アプリ管理者と、ルームを指定したときにそのルームの GM が閲覧できる。編集は制作者・アプリ管理者が直接行う。更新時は `base_revision` が必要で、競合時は再読込する。復元は新しい版を追加する。廃止は取り消せ、使用中の資源も廃止できる。削除前に使用中の参照を検査する。

### ユニットの項目

敵とNPCを含むルーム用のキャラクター資源を項目別に保存する。プレイヤーの持ちキャラは [F01 Part 9](F01_Operations_Manual.md) を参照。

| 項目 | 保存する値 |
|---|---|
| 基本情報 | `name`、`image`、配置できる陣営（`allow_ally`、`allow_enemy`）、シナリオキャラクター（`scenario`）、GMのみ操作可能（`gm_only`）、分類（`collection_id`）、タグ（`tags`、`disabled_tags`） |
| ステータス | 最大HP・MP（`hp`、`mp`）、初期HP・MP（`initial_hp`、`initial_mp`）、ラベルと値を持つ `params` |
| スキルと所持品 | `skills` は `{id, name, hidden}` の順序付き一覧。パッシブ（`passives`）と輝化スキル（`radiance`）はマスターID、`items` はアイテムIDと個数。その他のパレット行は `other_lines` |
| 行動設定 | `behavior` の対象自動選択（`auto_target`）、スキル自動選択（`auto_skill`）、予定スキル公開（`show_planned`）、行動スロット（`slot_mode`）、スキル制約（`constraints`） |
| 行動パターン | `patterns` の各要素に `{id, name, note, profile}`。既定のIDは `default_pattern_id` |

FP・出血などの状態は配置時に0から始める。初期効果が必要なら、戦闘突入時効果（`battle_start_effect`）を持つパッシブで表す。JSONインポートは `states` とHP・MP以外のステータス行を破棄し、解析の結果に表示する。既存ユニットと履歴の `states` は起動時に除去する。

### 行動パターンと編成

敵ユニットは名前付きパターンを複数持てる。ID は所有するユニット内で一意で、履歴はユニットと共有する。最初のパターンは自動で既定になり、1件以上ある間は既定を1つ選ぶ。既定を削除するには先に別のパターンを既定にする。編成で指定中のパターンは、その参照を外してから削除する。

敵編成の各枠はユニット内の `pattern_id` を参照する。未指定の枠はそのユニットの既定を使う。複数の編成が同じパターンを参照している場合、そのパターンの変更はどの編成にも反映される。複製は独立したパターンを作る。他ユニットへの複製で未所持スキルがあれば置き換えるかステップから外す。敵編成の「複製して編集」で作ったパターンと、それを選択する枠は編成の保存時に一括で確定する。

### 配置時の組み立てと検査

通常ルームと[シミュレーター](F03_Battle_Balance_Simulator_CLI.md)は `manager/units/characters.py` の共通処理で組み立てる。`commands` は `skills` の順に最新版マスターのチャットパレットから生成し、固有名称があれば `【ID 固有名称】` に置き換え、`other_lines` を末尾に足す。敵の `flags.behavior_profile` には編成の指定、既定の順で解決したパターンを設定する。パターンがなければ自動選択に任せる。味方への配置ではパターンを設定しない。

マスターIDの欠落・廃止、未所持スキルを指すパターン、不正な既定、編成とユニットの陣営不一致、不明なパターンは保存を止める。公開の編成・ステージから staff を参照する場合、廃止済みユニット資源を参照する場合、敵のパターン未設定は注意として返す。参照APIでユニットが使うマスターIDと、編成・ステージでの使用箇所を確認できる。

### HTTP API

ユニット資源の HTTP API は `/api/units`。一覧は `GET /api/units[/<kind>]`、各資源は `/<kind>/<entry_id>`。GM の閲覧には `?room=<ルーム名>` を付け、一覧で廃止済みを含めるときは `include_deprecated=1` を付ける。履歴と使用中の一覧はそれぞれ `/history`、`/references`。

制作者は `POST /<kind>` で新規、`PUT /<kind>/<entry_id>` で更新する。`payload` と `visibility` を送り、更新時は `base_revision` も送る。保存前チェックは `POST /<kind>/check`、キャラ JSON の読み取りは `POST /import-character` に `character` を送る。廃止の変更は `POST /<kind>/<entry_id>/deprecation` に `deprecated`、復元は `POST /<kind>/<entry_id>/restore` に `revision` を指定する。廃止の変更、復元、`DELETE /<kind>/<entry_id>` には `base_revision` を添える。

# Part 5: 待機列と登場（計画61）

## 1. 遭遇の準備

- 待機列はルーム状態に保存する。各遭遇は名前・メモ・資源IDと数量・適用設定・担当・実行済みの印を持つ。各資源の内容は登場時に最新版を参照する。
- 対象ルームに入室しているオーナー・GMだけが取得・検査・保存・削除できる。参加者向けルーム状態配信には待機列と操作履歴を含めない。仮置きは操作中のGMの画面にだけ表示する。
- 保存時と適用時に資源の有効性・閲覧権限・陣営・人数を検査する。1回に追加できるのは100体まで。通常ルームのステージ味方編成は既定で無効で、使う場合は追加のみ。担当未指定はGM。

## 2. 通常ルームでの登場

- 「登場」で盤面を表示し、中心マスを選ぶ。ドラッグで盤面移動、短いクリックで位置選択、タッチでは「ここに置く」、キーボードは矢印とEnter。自動配置とEscapeでの取消も可能。
- 確認には維持・除外・追加の名前と人数、背景とフィールド効果の変更、空き不足数を表示する。中心からの距離順で空きマスを割り当て、確定時に最新の空きマスで再計算する。入りきらないキャラクターはルームに追加し、座標未設定とする。中心指定なしでは従来の陣営別の自動配置を行う。
- フィールド効果の反映は、既存の一覧をステージの効果で差し替える。選択した背景・アバターを反映する。除外したキャラクターのスロット・意図等の参照も取り除く。
- 通常ルームでは「戦闘突入」の確定時に、生存中の全キャラクターに戦闘突入時効果（`BATTLE_START` / `battle_start_effect`）を処理する。戦闘中の登場・キャラクター追加は参加時、召喚は召喚時に処理する。同じ戦闘への参加時に一度適用し、終結後の再突入では改めて処理する。HP・MP・FPを戻すリセットでも処理する。
- 待機列・予定外の増援・キャラクター追加・召喚で途中参加したキャラクターは、次のラウンドから行動する。登場ラウンドの行動枠生成と終了時の未行動チェックの対象から外す。
- 確定後は遭遇に「済」を表示する。再使用できる。予定外の増援は待機列を経由せず、敵ユニット1体または敵編成を同じ方法で追加する。

## 3. プレビューと適用

- プレビューはルーム状態の複製で計算し、状態・ログ・DBは更新しない。成功した確定だけを一括反映する。
- 適用操作は操作IDを指定する。同じIDの再送は初回結果を返す。保存済みルーム状態にも直近64件の操作結果を保持する。

## 行動チャートの「行動しない」（2026-08-16）

`slot_generation_mode:step_actions`の各`actions`要素には、通常のスキルIDと予約値`__NO_ACTION__`を混在できる。編集UIでは`（行動しない）`として選択し、この要素の対象条件は無効化する。

- `__NO_ACTION__`の位置には通常行動スロットを生成せず、`behavior_no_action`の非行動アンカーを生成する。
- 同じステップ内の前後のスキルは、元の配列位置を`behavior_plan_index`として保持するため、スキルと対象条件がずれない。
- `actions:[]`も行動数0のまま扱うが、フィールド上のキャラクターを攻撃対象に残すため非行動アンカーを1件生成する。
- 非行動アンカーはPvE自動intent作成へ渡さず、対象としてのみ利用する。

途中参戦キャラクターへ行動チャートを初期化する仕組みは、この仕様には含めない。

# Part 6: ユニット資源の永続化と移送

旧DBでは起動時にキャラ・編成・ステージ・分類の ID と参照を付け替え、公開以外を staff にする。保存済みルームの配置・待機列の参照も付け替え、変換後に旧2表を削除する。個人の所有権・共有設定・編成内のパターンの写しは移行対象外。

制作者は分類か全件を JSON に書き出せる。範囲外の参照先も同梱する。取り込みは新規・上書きと参照チェックを先に表示し、確定時に版を照合してまとめて保存する。

制作者用 API は `GET /api/units/export`（任意の `collection_id`）、`POST /api/units/import/preview`（`package`）、`POST /api/units/import/confirm`（`package` と、確認時の版を `種類:ID` ごとに添える `base_revisions`）。新規の版には `null` を指定する。

# Part 7: Resolveの共有進行

Resolveの表示位置はルーム全体で同期する。

- Resolveの開始と初期進行役はGMに限定する。
- 進行役以外の参加者は同じ現在ステップを閲覧し、進行操作はできない。
- 別のGMは明示的な引継ぎ操作で進行役を交代できる。一般Playerは、進行役が不在でも引き継げない。
- 共有演出完了時にラウンド終了処理まで行うが、次ラウンドは自動開始しない。GMの通常操作を待つ。

進行役の退出・切断時は最新の`controller_present:false`をroomへ配信する。再入室だけでカーソル、ラウンド、演出完了状態は変化しない。

## ユニットの図鑑用の印（計画66 PR66-4）

ユニットのmarksは文字列配列（既定[]）。enemy・hollow・knownを受け付け、未知値と重複を拒否する。allow_enemyが偽でないユニット（項目が無い物も含む）を図鑑の対象にする。knownは管理画面の敵として配置できるユニットに入力欄を出す。印は一覧・詳細の札と一覧の絞り込みにも使う。publicの敵は未解禁なら？？？、staffの敵は本人が出会うまで存在も件数も伏せる。制作者・アプリ管理者は全部閲覧できる。

## ルームの図鑑の権限（計画66 PR66-5）

GET /api/encyclopedia?room=<ルーム名>ではresolve_room_roleとGM_ROLESでGMを判定する。本人がそのルームのGMならcan_view_allを真にし、自分の出会いで見る切り替えも許可する。ルーム外や通常の参加者には本人の出会い・公開範囲を適用する。

---

# Part 8: 戦闘専用ルームの廃止（計画65、2026-11-16 決定）

ルームは通常ルームだけ。戦闘専用ルーム（`play_mode == "battle_only"`）は使われていなかったので、画面・サーバー・資料・刊行物から消した（PR65-1、PR65-2 は 2026-11-22）。戦闘だけ遊びたい人は、通常ルームを作って自分が GM になる。

- **保存済みのルーム**：起動時の移行と読み込みで `play_mode` を `"normal"` にし、`battle_only` の項目（下書き・戦績）を捨てる。通常ルームとして開ける。
- **残した部品**：全滅による勝敗の判定は `manager/battle/battle_result.py` の `estimate_battle_result(state)`（シミュレーターとホロウが使う）。味方・敵の自動配置は `manager/sim/positions.py`（シミュレーターだけ）。待機列の権限の確認は `events/preset_deployment_access.py`。
- **GM なしで進めるための特別扱い**は一緒に消した。ホロウダンジョン（計画35 §5.4）で「ホスト」の権限として作り直す。消す前の挙動を下に残す。コードは計画65 PR65-1 の直前のコミットから参照できる。

| # | 場所 | 戦闘専用での挙動 | 通常ルーム |
|---|---|---|---|
| 1 | `events/battle/common_routes.py` `on_request_end_round` | PL もラウンド終了できる。解決表示の再生中は終了させない | GM のみ |
| 2 | 同 `on_request_reset_battle` | PL もリセットできる | GM のみ |
| 3 | 同 解決開始（1266行付近） | PL も解決を開始できる | GM のみ |
| 4 | 同 `_get_battle_only_intent_control_policy` と宣言の権限（656行付近） | 宣言できる人を「全員が全キャラ分（`all`）」と「開始した人と GM（`starter_only`）」で切り替える | 所有者・GM |
| 5 | 同 `_start_resolve_presentation_for_request` と `events/battle/resolve_presentation_routes.py` | 解決表示の進行役は戦闘を始めた人。進行役が部屋にいなければ PL も引き継げる | Resolve を始めた GM。引き継ぎは GM のみ |
| 6 | `manager/battle/common_manager.py` `move_token_logic`、`events/socket_char.py` の移動・削除・駒の大きさ | 誰でも他人の駒を動かせる・消せる・大きさを変えられる | 所有者・GM |
| 7 | `manager/battle/resolve_auto_runtime.py` `_maybe_finalize_battle_only_result`・`_auto_reset_battle_only_field` | 全滅で勝敗を自動で決め、解決表示の後に盤面を自動でリセットする | GM が戦闘終結で結果を選ぶ |
| 8 | `manager/battle/resolve_auto_single_phase.py` `_try_auto_advance_battle_only_round`、`common_routes._complete_round_after_resolve` | 解決表示の後、ラウンド終了と次のラウンド開始を自動で行う | GM が R開始を押す |

## 伏せたパッシブとラウンドの進行

ラウンド開始時に、配置済みの生存・未離脱キャラの HP 割合とラウンド数を判定する。行動チャートのループには、そのループの行動を最初に計画する際に公開する `reveal_passive_ids` を指定できる。公開したパッシブはそのラウンドの宣言に効く。公開は戦闘終了後も維持され、待機列から新たに配置したキャラではユニットの伏せた状態を使う。

参加者向けの状態には伏せた数だけを含める。通常ルームの GM には詳細も送る。演習場では、戦闘には同じ仕組みを使い、初期応答では伏せた詳細を送らない。

伏せた項目を除いた公開マスター応答には `X-Gemtrpg-Redacted: 1` を付ける。`--pull` は省略を含む公開応答でも止まらず、伏せた分だけ手元の版で補って取り込む（F01「--pull」、2026-11-23）。
