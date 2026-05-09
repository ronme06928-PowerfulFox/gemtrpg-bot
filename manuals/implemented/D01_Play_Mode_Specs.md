<!-- 旧: 05_PvE_Mode_Spec / 17_Battle_Only_Play_Mode_Spec / 18_Stage_Field_Effect_Spec を統合 (2026-05-09) -->

# プレイモード・ステージ仕様書

**最終更新日**: 2026-05-09
**系統**: D — プレイモード仕様
**統合元**: 05_PvE_Mode_Spec / 17_Battle_Only_Play_Mode_Spec / 18_Stage_Field_Effect_Spec

---

## 本書の構成

1. PvEモード仕様（旧05）
2. 戦闘専用プレイモード仕様（旧17）
3. ステージ効果仕様（旧18）

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
  - `initial_loop_id` (string)
  - `loops[loop_id].steps[].actions` (slot順のスキルID配列)
  - `loops[loop_id].steps[].next_loop_id` (任意: 当該step実行後に遷移するループID)
  - `loops[loop_id].steps[].next_reset_step_index` (任意: `next_loop_id` 遷移時に先頭stepへ戻すか。既定 `true`)
  - `loops[loop_id].transitions[]` (`priority`, `when_all`, `to_loop_id`, `reset_step_index`)

### 6.3 実行時データ
- 保存先: `battle_state.behavior_runtime`
- 例:
  - `active_loop_id`, `step_index`, `last_round`, `last_skill_ids`
- 意図:
  - 定義（profile）と実行カーソル（runtime）を分離し、プリセット読込/ID再発行時の破損を防ぐ。

### 6.4 実行優先順位
1. `behavior_profile.enabled=true` かつ有効loopあり: チャートを優先
2. チャート指定スキルが不正/空: `auto_skill_select` 系AI提案にフォールバック
3. profile未設定: 従来AI挙動を維持

### 6.5 プリセット同梱
- `behavior_profile` は敵プリセット v2 に含まれる。
- プリセットJSON搬出入で schema 検証後に保存できる。

### 6.6 実行エンジン
- 行動チャート実行は `manager/battle/enemy_behavior.py` で正規化・評価・次ステップ更新を行う。
- Selectフェーズでの敵intent自動生成（`_apply_pve_auto_enemy_intents`）に組み込み、敵ごとに `behavior_runtime` を参照して決定する。
- 遷移条件が不成立の場合は同一ループ内 step を進行し、step終端では `repeat` 設定に従って先頭復帰または末尾維持する。
- `steps[].next_loop_id` が指定されたstepは、そのstep使用後に `advance_step_pointer` で指定loopへ遷移する（次ラウンドから有効）。
- 実行順は「条件遷移（`transitions`）判定」→「step選択・使用」→「step使用後遷移（`next_loop_id`）」。

### 6.7 GM運用（UI）
- 敵キャラ設定から `behavior_profile` を JSON で編集できる（最小UI）。
- フローチャート編集UIでは、各stepに「スキル使用後にループ遷移」チェックを持ち、ON時に遷移先ループのプルダウンを表示する。
- プリセット管理モーダルで JSON搬出（Export）/JSON取込（Import）が可能。
- 取込時は schema と payload を検証し、破損データは保存しない。

### 6.8 権限と互換
- プリセット保存/読込/削除/搬出入はサーバー側で GM 権限チェックを行う。
- 既存プリセットは正規化を通して v2 互換へ寄せる。
- `behavior_profile` 未設定の敵は従来の AI 提案ロジックで動作し、旧運用を維持する。

### 6.9 関連テスト
- `tests/test_enemy_behavior_profile.py`
- `tests/test_preset_permissions.py`
- `tests/test_preset_json_transfer.py`
- `tests/test_pve_auto_intents.py`

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

## 1. 実装済みの中核仕様

1. 戦闘専用モード用プリセットストアを `version:2` で管理する。
1. キャラクタープリセットを JSON 無変換で保存する。
1. 敵編成プリセット、味方編成プリセット、ステージプリセットを個別管理する。
1. 公開範囲（`gm` / `public`）に応じた閲覧制御を行う。
1. プリセット CRUD は GM のみ許可する。
1. 戦闘専用ルームでの戦闘突入は参加者導線を提供する（公開プリセット前提）。
1. 戦闘突入時に陣営を `ally` / `enemy` へ明示設定する。
1. 戦闘専用モードを PVE 前提で運用し、敵矢印表示を既定有効にする。
1. 戦績はルーム状態に保持し、エクスポートを提供する。
1. 敵編成・味方編成・ステージプリセットは全体 JSON 出力に対応する。

---

## 2. データモデル（実装）

プリセット保存は `data/cache/battle_only_presets_cache.json` を使用する。  
主要キー:

- `character_presets`
- `enemy_formations`
- `ally_formations`
- `stage_presets`

ルーム状態は `room_state.battle_only` を使用する。  
主要キー:

- `status` (`lobby` / `draft` / `in_battle`)
- `selected_stage_id`
- `ally_mode` (`preset` / `room_existing`)
- `enemy_formation_id`
- `ally_formation_id`
- `required_ally_count`
- `enemy_entries`
- `ally_entries`
- `records`

---

## 3. UI 構成（実装）

主要モーダル:

- `キャラクタープリセット編集`
- `編成プリセット管理`（ハブ）
- `敵編成プリセット編集`
- `味方編成プリセット編集`
- `ステージプリセット編集`
- `戦闘専用 かんたん戦闘突入`
- `戦闘専用編成`

方針:

- キャラクター素材管理と編成管理を分離する。
- プレイヤー向けには「ステージ選択→戦闘突入」の短経路を提供する。

---

## 4. サーバーイベント（実装）

既存イベント群に加え、以下を実装済み:

- `request_bo_enemy_formation_save` / `delete` / `list`
- `request_bo_ally_formation_save` / `delete` / `list`
- `request_bo_stage_preset_save` / `delete` / `list`
- `request_bo_select_stage_preset`
- `request_bo_set_ally_mode`
- `request_bo_validate_entry`
- `request_bo_export_enemy_formations_json`
- `request_bo_export_ally_formations_json`
- `request_bo_export_stage_presets_json`
- `request_bo_record_export`

---

## 5. 運用上の注意

1. 管理系操作（保存・編集・削除）は GM 権限が必要。
1. 非GMは公開範囲 `public` のプリセットのみ参照可能。
1. `room_existing` 利用時は `required_ally_count` を満たす必要がある。
1. ルームを跨ぐ永続はプリセットのみ。戦績はルーム生存中データとして扱う。

---

## 6. 計画書からの移管方針

以下は `planned/10` から本書へ移管済み:

1. 戦闘専用モード再設計の要件確定事項
1. v2 ストア設計方針
1. モーダル分離方針
1. ステージプリセット導線
1. JSON エクスポート方針

`planned` 側には本トピックの旧計画書を残さず、今後は本書を正本として更新する。

---

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
ステージプリセット管理画面では、JSONを直接書かなくてもステージ効果を編集できます。

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
