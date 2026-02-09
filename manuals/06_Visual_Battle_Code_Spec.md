# ビジュアルバトル・コード仕様書 (`tab_visual_battle.js`)

## 1. 概要

`tab_visual_battle.js` は、「ビジュアルバトル（Visual Battle）」タブを担当するコアとなるクライアントサイドスクリプトです。インタラクティブなマップ操作、キャラクタートークンの管理、戦闘操作UI（デュエル/広域戦闘）、およびSocket.IOを通じたサーバーとのリアルタイム同期を制御します。

**現在の規模:** 約4400行
**主な責務:**

- マップの描画と操作（パン/ズーム/ドラッグ）
- キャラクタートークンの管理（移動、ステータスバー、バッジ）
- 戦闘ロジックとの統合（デュエルおよび広域戦闘モーダル）
- リアルタイムの状態同期

---

## 2. グローバル変数 (Global State Variables)

このファイルは状態を維持するためにいくつかのグローバル変数に依存しています。

| 変数名 | 型 | 説明 |
| :--- | :--- | :--- |
| `visualScale` | `Number` | マップの現在のズームレベル（デフォルト: 1.0）。 |
| `visualOffsetX`, `visualOffsetY` | `Number` | 現在のマップのパン（移動）オフセット（ピクセル単位）。 |
| `battleState` | `Object` | 同期されたバトルルームの状態（キャラクター、ログ、マッチ状況）。`state_updated` イベントで更新されます。 |
| `duelState` | `Object` | アクティブなデュエルマッチの **ローカルUI状態**。`attackerId`, `defenderId`, ロック状態, 宣言コマンドなどを保持します。 |
| `visualWideState` | `Object` | アクティブな広域戦闘実行モーダルの **ローカルUI状態**。`attackerId` や宣言状態を保持します。 |
| `window.allSkillData` | `Object` | `/api/get_skill_data` からロードされたスキルデータのキャッシュ。 |
| `window._matchPanelAutoExpanded` | `Boolean` | リロード後にマッチパネルが繰り返し自動展開されるのを防ぐためのフラグ。 |
| `window._duelLocalCalcCache` | `Object` | 再描画後にUI状態を復元するために計算結果をキャッシュします。 |

---

## 3. コアモジュールと関数 (Core Modules & Functions)

### 3.1. 初期化 (Initialization)

エントリーポイント: `setupVisualBattleTab()`

- **DOMセットアップ:** マップコンテナ、アクションドック、タイムライン、操作ボタンなどを初期化します。
- **Socket リスナー:** `state_updated`, `char:stat:updated`, `request_move_token` などの `socket.on` ハンドラを登録します。
- **ポーリング:** 権限更新のチェック (`window._permissionEnforcerInterval`) や DOMの準備完了確認のためのインターバルを開始します。

### 3.2. マップ描画 (Map Rendering)

コア関数: `renderVisualMap()`

- **Canvas/DOM:** HTML要素 (`div.map-token`) をコンテナ上に絶対配置することで描画します。
- **最適化:**
  - `updateCharacterTokenVisuals(diff)`: ステータス変動時に完全な再描画を避け、HP/MPバーのみを部分的更新します。
  - `_lastRenderedStateStr`: 単純な文字列比較を行い、変更がない場合の `state_updated` による再描画をスキップします。
- **トークン生成 (`createMapToken`)**:
  - HP/MPバー、バッジ、名前ラベル、キャラクター画像のHTMLを生成します。
  - 選択やキャラクター詳細表示 (`showCharacterDetail`) のための `mousedown`/`dblclick` リスナーを追加します。

### 3.3. マップ操作 (Map Controls & Interaction)

コア関数: `setupMapControls()`, `setupBattleTokenDrag()`

- **パン & ズーム:**
  - `#visual-map-content` に対して `transform: translate(...) scale(...)` を更新します。
  - マウスホイールでのズーム、ドラッグでのパン操作をサポートします。
- **トークン・ドラッグアンドドロップ:**
  - `setupBattleTokenDrag()`: カスタムドラッグロジックを実装しています。
  - ピクセル座標と `visualScale` に基づいてグリッド座標を計算します。
  - **楽観的UI (Optimistic UI):** ローカルのDOMを即座に更新し、その後 `request_move_token` を送信します。
- **ターゲットモード:**
  - `enterAttackTargetingMode(attackerId)`: マップを強調表示し、クリックでターゲットを選択できるようにフィルタリングします。
  - `exitAttackTargetingMode()`: 強調表示を解除します。

### 3.4. マッチパネル (Duel)

1対1の戦闘インターフェース用ロジック。

- **同期ロジック:** `renderMatchPanelFromState(matchData)`
  - `battleState.active_match` の変更を検知します。
  - `updateMatchPanelContent` を呼び出し、名前、スキル、結果を表示します。
  - **自己修復 (Self-Correction):** 名前やスキルがサーバー状態と一致しない場合、ローカルUIを強制的に更新します（「冪等な同期」）。
- **ユーザー操作:**
  - `openDuelModal`: `duelState` を初期化し、パネルを展開します。
  - `sendSkillDeclaration`: MP/HP/FPコストを検証し -> `request_skill_declaration` を送信します。
  - `executeMatch`: 最終コマンドを含めて `request_match` を送信します。
- **権限管理:** `canControlCharacter` で所有権やGMステータスをチェックし、ボタンの有効/無効を切り替えます。

### 3.5. 広域戦闘 (Wide Match)

1対多、または多対多の戦闘用ロジック。

- **実行モーダル:** `openVisualWideMatchModal(attackerId)`
  - デュエルパネルとは異なり、専用のモーダル (`#visual-wide-match-modal`) を使用します。
  - すべての有効なターゲット（敵対陣営）をリストアップします。
- **防御側行の生成:** `renderVisualWideDefenders`
  - 各ターゲットに対して、スキル選択、威力計算ボタン、宣言ボタンを持つ行を生成します。
  - 防御側の選択肢から「広域」スキルや「即時発動」スキルを除外します。
- **実行:** 攻撃側のコマンドと、防御側コマンドの配列を含むペイロードで `request_wide_match` を送信します。

### 3.6. ログとチャット (Logging & Chat)

- **ログ履歴:** `openVisualLogHistoryModal()` で `battleState.logs` を表示します。
- **チャット:** `socket.on('chat_message')` で受信し、`#visual-chat-log` に追記します。

---

## 4. 主要なSocketイベント

| イベント名 | 方向 | ペイロード | 説明 |
| :--- | :--- | :--- | :--- |
| `state_updated` | Server -> Client | `BattleState` | ルーム状態の完全同期。`renderVisualMap` と `renderMatchPanelFromState` をトリガーします。 |
| `char:stat:updated` | Server -> Client | `{ id, changes }` | キャラクター・ステータスの差分更新。`updateCharacterTokenVisuals` をトリガーします。 |
| `request_move_token` | Client -> Server | `{ charId, x, y }` | トークンの移動リクエスト。 |
| `request_move_token` | Server -> Client | `{ charId, x, y }` | トークン移動のブロードキャスト。 |
| `request_skill_declaration` | Client -> Server | `{ actor_id, skill_id, ... }` | ユーザーが「計算」または「宣言」をクリックした際に送信。 |
| `skill_declaration_result` | Server -> Client | `{ final_command, damage, ... }` | サーバーでの計算結果。`updateDuelUI` をトリガーします。 |
| `match_modal_opened` | Server -> Client | `{ attacker_id, defender_id }` | デュエルパネルを開くよう指示します。 |
| `request_force_end_match` | Client -> Server | `{ room }` | GMによるマッチの強制終了。 |

---

## 5. リファクタリングのポイントと技術的負債 (Tech Debt)

1. **肥大化したファイル:** 4400行以上あり、可読性と保守性が低下しています。
2. **関心の混在:** 描画ロジック、ビジネスロジック（コスト計算）、Socket通信が混在しています。
3. **複雑な状態同期:**
    - `renderMatchPanelFromState` には、スナップショットとライブデータ間の競合を解決するための複雑な「自己修復」ロジックが含まれています。
    - `duelState`（ローカル）と `battleState.active_match`（サーバー）の重複が同期ズレの原因になりがちです。
4. **コスト検証の重複:** スキルコスト（MP/HP/FP）の確認ロジックが `sendSkillDeclaration` にハードコードされていますが、サーバー側にも同様のロジックが存在するはずです。
5. **直接的なDOM操作:** `document.getElementById` や `innerHTML` の文字列結合が多用されています。
6. **グローバル名前空間の汚染:** 多くの関数や変数が `window` にアタッチされたり、グローバルスコープで宣言されています。

## 6. モジュール化計画 (Modularization Plan)

リファクタリングでは、このファイルを以下のモジュールに分割して `static/js/visual/` に配置する予定です：

| モジュール名 | 責務 |
| :--- | :--- |
| `visual_globals.js` | 共有状態 (`battleState`, `visualScale`) と定数。 |
| `visual_map.js` | マップ描画、トークン生成 (`renderVisualMap`, `createMapToken`)。 |
| `visual_controls.js` | 入力ハンドリング (`setupMapControls`, `setupBattleTokenDrag`)。 |
| `visual_ui.js` | UIコンポーネント (アクションドック, タイムライン, ログモーダル)。 |
| `visual_panel.js` | デュエルマッチパネルのロジック (`renderMatchPanelFromState`, `updateDuelUI`)。 |
| `visual_wide.js` | 広域戦闘モーダルのロジック (`openVisualWideMatchModal`)。 |
| `visual_socket.js` | Socketイベントの登録とディスパッチ。 |
| `visual_main.js` | エントリーポイント (`setupVisualBattleTab`) と全体の調整。 |
