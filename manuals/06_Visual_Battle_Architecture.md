# ビジュアルバトル・アーキテクチャ仕様書

## 1. 概要 (Overview)

本仕様書は、リファクタリング（2026-02-10実施）後の「ビジュアルバトル（Visual Battle）」タブのコード構造、データフロー、およびPvEモード等の派生機能について記述します。

**ファイル配置:** `static/js/visual/`
**エントリーポイント:** `visual_main.js` (`setupVisualBattleTab`)
**依存関係:** `socket.io.js`

---

## 2. モジュール構造 (Module Structure)

`static/js/visual/` 以下のファイル構成と責務は以下の通りです。従来の巨大な `tab_visual_battle.js` は廃止され、以下のモジュール群に分割されました。

| ファイル名 | 責務・内容 |
| :--- | :--- |
| **`visual_globals.js`** | **グローバル状態と定数**。<br>`battleState`, `visualScale`, `visualOffsetX/Y`, `VISUAL_MAX_LOG_ITEMS` などのグローバル変数を定義・初期化します。他の全モジュールから参照されます。 |
| **`visual_main.js`** | **エントリーポイント**。<br>`setupVisualBattleTab` 関数を定義し、各コンポーネント（マップ、UI、Socket）の初期化順序を制御します。DOMの準備確認や初回描画のトリガーも行います。 |
| **`visual_map.js`** | **マップ描画**。<br>`renderVisualMap` 関数を含み、背景画像とキャラクタートークン (`createMapToken`) の生成・配置、広域ボタンの制御を行います。 |
| **`visual_arrows.js`** | **矢印描画**。<br>PvEモードにおける敵の狙い（ターゲット）を可視化するSVG矢印の描画を担当します。 |
| **`visual_controls.js`** | **入力操作**。<br>マップのパン・ズーム操作 (`setupMapControls`)、トークンのドラッグ＆ドロップ移動ロジック (`setupBattleTokenDrag`)、視点保存 (`localStorage`) を担当します。 |
| **`visual_ui.js`** | **UIコンポーネント**。<br>アクションドックの初期化、タイムラインの表示制御、バトルログの追記 (`appendVisualLogLine`) を担当します。 |
| **`visual_panel.js`** | **デュエル（1vs1）パネル**。<br>`renderMatchPanelFromState` を中心に、対決画面の描画、スキル選択、コスト計算、宣言送信ロジックを制御します。 |
| **`visual_wide.js`** | **広域戦闘（1vsMany）**。<br>広域・乱戦用のモーダル制御 (`openVisualWideMatchModal`)、防御側リストの生成、一括実行処理を担当します。 |
| **`visual_socket.js`** | **通信ハンドラ**。<br>`socket.on` イベントリスナー（`state_updated`, `skill_declaration_result`, `character_moved` 等）を一元管理し、適切な描画関数を呼び出します。 |

---

## 3. グローバル状態 (Global State)

状態変数は `visual_globals.js` で初期化され、`window` オブジェクトを通じて共有されます。

| 変数名 | 型 | 初期値 | 説明 |
| :--- | :--- | :--- | :--- |
| `visualScale` | `number` | `0.7` | マップのズーム倍率。`localStorage` に保存されます。 |
| `visualOffsetX` | `number` | `-900` | マップのX軸オフセット。`localStorage` に保存されます。 |
| `visualOffsetY` | `number` | `-900` | マップのY軸オフセット。`localStorage` に保存されます。 |
| `battleState` | `Object` | `null` | サーバー同期されたルームの最新状態。`match_modal_opened` 等のイベント駆動で更新されます。 |
| `attackTargetingState` | `Object` | `{isTargeting:false}` | 攻撃対象選択モードの状態管理。 |
| `VISUAL_MAX_LOG_ITEMS` | `number` | `100` | ビジュアルログの最大表示件数。 |

---

## 4. 主要フローとデータ同期 (Flows & Sync)

### 4.1 初期化フロー (`visual_main.js`)

1. **DOMロード**: `setupVisualBattleTab()` が呼び出される。
2. **コンポーネント初期化**: `TimelineComponent`, `ActionDockComponent`, `VisualMapComponent` 等の初期化関数を実行。
3. **イベント登録**: `setupMapControls`, `setupVisualSidebarControls` でDOMイベントを設定。
4. **Socket登録**: `setupVisualSocketHandlers()` でサーバーイベントをリッスン開始（多重登録防止ガードあり）。
5. **初回描画**: 既存の `battleState` があれば、即座にマップやUIを描画。

### 4.2 状態同期フロー (`visual_socket.js`)

マルチプレイ環境での同期は以下のイベントを通じて行われます。

- **`state_updated`**: ルーム全体のフルステート更新。マップ、タイムライン、ラウンド数、ログ履歴を一括更新します。
- **`character_moved`**: キャラクター移動の差分更新。トークンのCSS `top`/`left` を直接操作し、アニメーションさせます。
- **`new_log`**: チャットおよびシステムログの受信。`main.js` 経由で `logToBattleLog` が呼ばれ、ビジュアルログエリアに追記されます。

---

## 5. PvEモードとAIロジック (PvE Mode)

**関連ファイル:** `manuals/05_PvE_Mode_Spec.md` (統合済み)

### 5.1 概要

敵キャラクターの行動指針（ターゲット）をシステムが補助・自動化する機能です。

### 5.2 データ構造

`room_state` に以下のプロパティが追加されています。

- `battle_mode`: `'pvp'` または `'pve'`。
- `ai_target_arrows`: AIが算出したターゲット情報のリスト。`{from_id, to_id, type, visible}`。

### 5.3 サーバーサイドロジック

- **ターゲット決定 (`process_round_start`)**:
  - ラウンド開始時、敵キャラクター（`type: enemy`）は「配置済みの生存している味方（`type: ally`）」からランダムにターゲットを選択します。
  - 結果は `ai_target_arrows` に保存され、クライアントに配信されます。

### 5.4 クライアントサイド実装 (`visual_arrows.js`)

- **矢印描画**: `map-arrow-layer` (SVG) にベジェ曲線を描画します。
- **更新タイミング**: `renderVisualMap` 内で呼び出され、トークン位置に追従します。
- **表示条件**: PvEモード時のみ、敵からの矢印を表示します（PvP時は非表示）。

---

## 6. UIコンポーネント仕様 (UI Components)

**関連ファイル:** `manuals/character_modal_spec.md` (統合済み)

### 6.1 キャラクター詳細モーダル

不具合を防ぐため、以下の仕様で固定されています。

- **コンテナ幅**: **固定 `650px`**（スマホ等は `max-width: 90vw`）。
- **スクロール**: 横スクロール禁止 (`overflow-x: hidden`)。
- **パラメータ表示**: 3列×3行のCSS Grid。
- **特殊効果・スキル**: `<details>` タグを用いた折りたたみ式。

### 6.2 広域マッチモーダル (`visual_wide.js`)

- **同期**: `open_wide_declaration_modal` イベントで全クライアントに一斉に開かれます。
- **状態保持**: 攻撃者が宣言するまで、他のプレイヤーの選択状態（防御・回避など）は保持されます。
- **不具合修正**: ラウンド終了時に `isWideUser` フラグがサーバー側でリセットされるようになり、次ラウンドでの暴発を防いでいます。

---

## 7. 今後の拡張 (Future Extensions)

- **視点保存の改善**: 現在は `localStorage` に保存していますが、サーバーサイドでユーザー設定として保持することを検討中。
- **エフェクト演出**: 攻撃時やダメージ時の視覚エフェクトの実装。
- **モバイル対応強化**: タッチ操作でのマップスクロールの感度調整。
