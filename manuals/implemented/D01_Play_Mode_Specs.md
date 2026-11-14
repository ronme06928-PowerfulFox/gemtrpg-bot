<!-- 旧: 05_PvE_Mode_Spec / 17_Battle_Only_Play_Mode_Spec / 18_Stage_Field_Effect_Spec を統合 (2026-05-09) -->

# プレイモード・ステージ仕様書

**最終更新日**: 2026-08-16
**系統**: D — プレイモード仕様
**統合元**: 05_PvE_Mode_Spec / 17_Battle_Only_Play_Mode_Spec / 18_Stage_Field_Effect_Spec

---

## 本書の構成

1. PvEモード仕様（旧05）
2. 戦闘専用プレイモード仕様（旧17）
3. ステージ効果仕様（旧18）
4. ユニット管理（計画61）
5. プリセット配置・原子的適用（計画44）

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

- ラウンド開始時 (`process_new_round` / `process_battle_start`)
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

# Part 2: 戦闘専用プレイモード仕様

最終更新: 2026-04-18  
対象: 実装運用（Current）  
移管元: `manuals/planned/10_Battle_Only_Play_Mode_Implementation_Plan.md`

---

## 0. 本書の位置づけ

本書は、戦闘専用プレイモードの「実装済み仕様」をまとめた運用仕様です。  
計画書で扱っていた内容のうち、現在のコードに反映済みの項目を `implemented/` 側へ移管しています。

---

## 1. 戦闘準備
対象ルームで閲覧可能なユニット・編成・ステージを参照する。GM が戦闘用下書きを組み、戦闘突入時にユニットから実行時キャラクターを生成する。戦績はルーム状態に残す。配置と認可は Part 4・5 を参照。

# Part 3: ステージ効果仕様

最終更新: 2026-04-22  
対象: 戦闘専用モードのステージプリセット効果

---

## 1. 方針
ステージ効果は、戦闘専用モードのステージプリセットに紐づく場ルールです。

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

戦闘専用ルームでは、選択中ステージの情報が `battle_only` と戦闘状態へ反映されます。

- `battle_only.stage_field_effect_profile`
- `battle_only.stage_field_effect_enabled`
- `battle_only.stage_avatar_enabled`
- `battle_only.stage_avatar_profile`
- `state.stage_field_effect_profile`
- `state.stage_avatar_profile`
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

戦闘中のVisual画面では、ステージ効果カードから詳細を確認できます。

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

- `events/socket_battle_only.py`
- `manager/field_effects.py`
- `manager/battle/common_manager.py`
- `manager/game_logic.py`
- `static/js/modals/battle_only_stage_preset_modal.js`
- `static/js/modals/battle_only_quick_start_modal.js`
- `static/js/visual/visual_ui.js`

主なテストは次の通りです。

- `tests/test_battle_only_catalog.py`
- `tests/test_stage_field_effects_runtime.py`

# Part 4: ユニット管理（計画61）

`catalog_entries` と `catalog_history` の種類を `unit`、`formation`、`stage`、`unit_collection` とする。ID は U-001、F-001、ST-001、SC-01 の形式。分類は `collection_id`、編成の陣営は `type`、メンバーは `{unit_id, count, pattern_id}` で保存する。

公開範囲は `public` と `staff`。後者は制作者・アプリ管理者と、ルームを指定したときにそのルームの GM が閲覧できる。編集は制作者・アプリ管理者が直接行う。更新時は `base_revision` が必要で、競合時は再読込する。復元は新しい版を追加する。廃止は取り消せ、使用中の資源も廃止できる。削除前に使用中の参照を検査する。

ユニットの形は計画61 §3.5 に従う。マスター ID の欠落・廃止、未所持スキルを指すパターン、不正な既定、編成とユニットの陣営不一致、不明なパターンは保存を止める。公開の編成・ステージから staff を参照する場合、廃止済みユニット資源を参照する場合、敵のパターン未設定は注意として返す。

### HTTP API

ユニット資源の HTTP API は `/api/units`。一覧は `GET /api/units[/<kind>]`、各資源は `/<kind>/<entry_id>`。GM の閲覧には `?room=<ルーム名>` を付け、一覧で廃止済みを含めるときは `include_deprecated=1` を付ける。履歴と使用中の一覧はそれぞれ `/history`、`/references`。

制作者は `POST /<kind>` で新規、`PUT /<kind>/<entry_id>` で更新する。`payload` と `visibility` を送り、更新時は `base_revision` も送る。保存前チェックは `POST /<kind>/check`、キャラ JSON の読み取りは `POST /import-character` に `character` を送る。廃止の変更は `POST /<kind>/<entry_id>/deprecation` に `deprecated`、復元は `POST /<kind>/<entry_id>/restore` に `revision` を指定する。廃止の変更、復元、`DELETE /<kind>/<entry_id>` には `base_revision` を添える。

# Part 5: プリセット配置・原子的適用（計画44・61）

## 1. 共通配置契約

- 通常ルームと戦闘専用下書きは、`manager/preset_deployment.py`の同じカタログ、正規化、プレビュー、適用処理を使う。
- 配置できるのは対象ルームの`owner`または`gm`だけであり、配置直前に参照先、公開範囲、陣営許可を再検証する。
- 一度の確定で新規生成できるキャラクターは、最終的に有効な編成と単体追加を合算して100体までとする。101体以上はプレビューと確定の両方で拒否する。
- 配置内容は、ステージ要素、味方・敵編成、単体キャラクターの順でルーム状態の複製へ適用する。全処理と戦闘開始時効果の初期化が成功した場合だけ実ルーム状態を一括置換する。
- プレビューは実ルーム状態、保存予約、Socket通知、ログへ副作用を出さない。確定成功時だけ保存予約を1回、状態通知を1回行い、初期化中のログをまとめて送る。

## 2. 通常ルームへの配置

- ステージの背景、フィールド効果、ステージアバターを選択項目に従って反映する。
- 敵編成は既存敵との置換、味方編成は既存味方への追加を既定とし、配置画面から追加・置換を切り替えられる。単体キャラクターは常に追加する。
- 味方の担当ユーザーが未指定または現在のルーム参加者に存在しない場合、配置を実行したGMを担当にする。
- 新規キャラクターは空き座標へ自動配置し、配置後の細かな位置は既存フィールド操作で調整する。
- 置換で外れたキャラクターの所有者、タイムライン、戦闘スロット、意図、AI矢印への参照を同時に除去する。

## 3. 戦闘専用下書きへの配置

- ステージまたは編成は対応する味方・敵下書きを置換し、単体キャラクターは下書きへ追加する。
- ステージ背景は`battle_only.stage_background_profile`に保持し、下書き反映時に通常の背景適用処理でルーム状態へ反映する。フィールド効果とステージアバターは既存の戦闘突入処理へ渡す。
- 反映後に敵数、味方数、必要味方人数、担当ユーザー、キャラクター参照をサーバーで検証する。阻害事項がなければ`ready: true`、不足があれば`issues`と`ready: false`を返す。
- 阻害事項が残っていても下書きへの反映自体は確定し、GMは詳細調整で修正できる。戦闘突入導線は`ready: true`の場合だけ有効にする。

## 4. Socketと冪等性

- `request_preset_deployment_catalog` / `preset_deployment_catalog`: 閲覧可能なキャラクター、味方編成、敵編成、ステージ、コレクション、区分件数、ブックマーク、参加ユーザーを返す。
- `request_preset_deployment_preview` / `preset_deployment_preview`: 一時状態で変更件数と準備可否を検証する。`request_version`を往復し、クライアントは古い応答を無視する。
- `request_preset_deployment_apply` / `preset_deployment_applied`: `operation_id`を必須とし、同じIDの再送には初回結果を返して重複生成しない。
- 適用済み操作はメモリキャッシュだけでなく`room_state.preset_deployment_operations`へ最大64件保存する。プロセス再起動後も同じルーム状態から重複要求を判定できる。
- 互換用の旧通常ルーム適用イベントは残す。新しい配置画面だけが共通イベントを使う。

## 5. 主な実装・テスト

- 実装: `manager/preset_deployment.py`、`events/socket_preset_deployment.py`、`manager/room_preset_apply.py`、`events/socket_battle_only.py`
- テスト: `tests/test_preset_deployment.py`、`tests/test_preset_deployment_socket.py`

## 行動チャートの「行動しない」（2026-08-16）

`slot_generation_mode:step_actions`の各`actions`要素には、通常のスキルIDと予約値`__NO_ACTION__`を混在できる。編集UIでは`（行動しない）`として選択し、この要素の対象条件は無効化する。

- `__NO_ACTION__`の位置には通常行動スロットを生成せず、`behavior_no_action`の非行動アンカーを生成する。
- 同じステップ内の前後のスキルは、元の配列位置を`behavior_plan_index`として保持するため、スキルと対象条件がずれない。
- `actions:[]`も行動数0のまま扱うが、フィールド上のキャラクターを攻撃対象に残すため非行動アンカーを1件生成する。
- 非行動アンカーはPvE自動intent作成へ渡さず、対象としてのみ利用する。

途中参戦キャラクターへ行動チャートを初期化する仕組みは、この仕様には含めない。

# Part 6: ユニット資源の永続化と移送

旧DBでは起動時にキャラ・編成・ステージ・分類の ID と参照を付け替え、公開以外を staff にする。保存済みルームの配置・戦闘下書きの参照も付け替え、変換後に旧2表を削除する。個人の所有権・共有設定・編成内のパターンの写しは移行対象外。

制作者は分類か全件を JSON に書き出せる。範囲外の参照先も同梱する。取り込みは新規・上書きと参照チェックを先に表示し、確定時に版を照合してまとめて保存する。

制作者用 API は `GET /api/units/export`（任意の `collection_id`）、`POST /api/units/import/preview`（`package`）、`POST /api/units/import/confirm`（`package` と、確認時の版を `種類:ID` ごとに添える `base_revisions`）。新規の版には `null` を指定する。

# Part 7: Resolve共有進行のプレイモード差（2026-08-16）

通常ルームと戦闘専用ルームは、Resolveの計算・trace snapshot・共有presentationの仕組みを共用する。どちらも表示位置はroom全体で同期され、各閲覧者が独立して「次へ」を進める方式ではない。

## 通常ルーム

- Resolveの開始と初期進行役はGMに限定する。
- 進行役以外の参加者は同じ現在ステップを閲覧し、進行操作はできない。
- 別のGMは明示的な引継ぎ操作で進行役を交代できる。一般Playerは、進行役が不在でも引き継げない。
- 共有演出完了時にラウンド終了処理まで行うが、次ラウンドは自動開始しない。GMの通常操作を待つ。

## 戦闘専用ルーム

- 初期進行役は`battle_only.controller_user_id`に保存された戦闘開始者とする。欠損時だけResolve開始者を使う。
- 進行役がSocket上で当該roomにいない場合、参加者は明示的な引継ぎ操作を行える。進行役が在室中に一般参加者が奪取することはできない。GMは明示的に引き継げる。
- 宣言操作設定が`intent_control_mode:all`でも、演出進行役は一人だけである。
- 共有演出が`completed`になった後に限り、ラウンド終了処理と次ラウンド開始をサーバーが連続実行する。
- 勝敗確定・`pending_auto_reset`時は次ラウンドを開始せず、共有演出完了後に既存の自動リセットへ渡す。
- 旧クライアント等からのローカルな`request_end_round`は、共有presentationが`playing`の間は無視する。

進行役の退出・切断時は最新の`controller_present:false`をroomへ配信する。再入室だけでカーソル、ラウンド、演出完了状態は変化しない。
