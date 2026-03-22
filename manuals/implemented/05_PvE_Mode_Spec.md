# PvEモードおよび戦闘行動予告（矢印）仕様書

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
