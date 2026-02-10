# ビジュアルバトル・コード仕様書

## 1. 概要

本仕様書は、リファクタリング（2026-02-10実施）後の「ビジュアルバトル（Visual Battle）」タブのコード構造について記述します。
かつての巨大な `tab_visual_battle.js` は、機能ごとに分割された複数のモジュール群によって構成されています。

**配置ディレクトリ:** `static/js/visual/`
**エントリーポイント:** `visual_main.js` (`setupVisualBattleTab`)

---

## 2. モジュール構造 (Module Structure)

`static/js/visual/` 以下のファイル構成と責務は以下の通りです。

| ファイル名 | 責務・内容 |
| :--- | :--- |
| **`visual_globals.js`** | **グローバル状態と定数**。<br>`battleState`, `visualScale`, `visualOffsetX/Y`, `VISUAL_MAX_LOG_ITEMS` などのグローバル変数を定義・初期化します。他の全モジュールから参照されます。 |
| **`visual_main.js`** | **エントリーポイント**。<br>`setupVisualBattleTab` 関数を定義し、各コンポーネント（マップ、UI、Socket）の初期化順序を制御します。DOMの準備確認や初回描画のトリガーも行います。 |
| **`visual_map.js`** | **マップ描画**。<br>`renderVisualMap` 関数を含み、背景画像とキャラクタートークン (`createMapToken`) の生成・配置を行います。 |
| **`visual_controls.js`** | **入力操作**。<br>マップのパン・ズーム操作 (`setupMapControls`)、トークンのドラッグ＆ドロップ移動ロジック (`setupBattleTokenDrag`) を担当します。 |
| **`visual_ui.js`** | **UIコンポーネント**。<br>アクションドックの初期化、タイムラインの表示制御、バトルログの追記 (`appendVisualLogLine`) を担当します。 |
| **`visual_panel.js`** | **デュエル（1vs1）パネル**。<br>`renderMatchPanelFromState` を中心に、対決画面の描画、スキル選択、コスト計算、宣言送信ロジックを制御します。 |
| **`visual_wide.js`** | **広域戦闘（1vsMany）**。<br>広域・乱戦用のモーダル制御 (`openVisualWideMatchModal`)、防御側リストの生成、一括実行処理を担当します。 |
| **`visual_socket.js`** | **通信ハンドラ**。<br>`socket.on` イベントリスナー（`state_updated`, `skill_declaration_result` 等）を一元管理し、適切な描画関数を呼び出します。 |

※ 旧 `tab_visual_battle.js` は空のファイルとして残されており、後方互換性のため `index.html` で読み込まれていますが、実質的な処理は行いません。

---

## 3. グローバル変数 (Global State Variables)

状態変数は `visual_globals.js` で初期化され、`window` オブジェクトを通じて共有されます。

| 変数名 | 初期値 | 説明 |
| :--- | :--- | :--- |
| `visualScale` | `0.7` | マップのズーム倍率。 |
| `visualOffsetX/Y` | `-900` | マップの表示オフセット座標。 |
| `battleState` | `null` | サーバー同期されたルームの最新状態。 |
| `attackTargetingState` | `{isTargeting:false}` | 攻撃対象選択モードの状態管理。 |
| `visualMapHandlers` | `{}` | マップ操作イベントリスナーの参照保持（削除用）。 |
| `VISUAL_MAX_LOG_ITEMS` | `100` | ビジュアルログの最大表示件数。 |

---

## 4. 主要フロー (Key Flows)

### 4.1 初期化フロー (`visual_main.js`)

1. `setupVisualBattleTab()` が呼び出される。
2. 各コンポーネントの初期化関数 (`initializeActionDock`, `setupMapControls` 等) を順次実行。
3. `setupVisualSocketHandlers()` でSocketイベントを登録。
4. `battleState` が存在すれば、`renderVisualMap`, `renderLogHistory` などで初回描画を行う。

### 4.2 状態更新フロー (`visual_socket.js`)

1. サーバーから `state_updated` イベント受信。
2. `battleState` グローバル変数を更新。
3. 以下の描画関数をトリガー:
   - `renderVisualMap()` (マップ・トークン)
   - `renderMatchPanelFromState()` (デュエルパネル)
   - `renderVisualLogHistory()` (ログ)
   - `updateVisualRoundDisplay()` (ラウンド数)

---

## 5. 今後の拡張 (Future Extensions)

**フェーズ3予定:**

- **PvEモード**: 自動ターゲット選定ロジックと連携。
- **矢印表示**: `visual_arrows.js` (仮) を追加し、ターゲット可視化を行う。
- **視点保存**: `visual_controls.js` に `localStorage` への保存処理を追加。
