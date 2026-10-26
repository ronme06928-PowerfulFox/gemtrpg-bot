<!-- 旧: 06_Visual_Battle_Architecture + 07_Visual_Battle_Code_Spec を統合。06が正本。(2026-05-09) -->

# ビジュアルバトル アーキテクチャ仕様書

**最終更新日**: 2026-05-09
**系統**: E — UI / フロントエンド
**統合元**: 06_Visual_Battle_Architecture / 07_Visual_Battle_Code_Spec

---

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

D11修正（2026-10-18）：`battle/index.js` はDOM準備後、Socketの有無に依存せずStore・`BoardPresentationCoordinator`・`VisualMap`の購読を初期化する。認証前のSocket待ちを打ち切った結果、盤面の状態が初期値で固定される経路をなくす。Socketの購読は既存の `main.js::initializeSocketIO` の登録・接続処理から `SocketClient.initialize()` で開始し、同一Socketへの再実行では重複登録しない。時間制限付きのポーリングは使わない。

完全リセット後の駒の残り（2026-10-22）：盤面を描く状態は `visual_map.js::selectBoardRenderState` で選ぶ。演出中に固定された表示用の状態にキャラクターがいればそれを使い、表示用の状態が `BattleStore` の最新状態と同じなら、キャラクターが0人でもそれを使う。以前は0人のときに `main.js` の `let battleState`（`window.battleState` とは別の、更新が遅れる変数）へ戻っていたため、完全リセットの直後にリセット前の駒が残り、ページを切り替えるまで消えなかった。スロットの札を描く `renderSlotBadgesForAllTokens` のキャラクター一覧も同じ関数で選ぶ。

保存済み表示位置の復元と駒の可視性（2026-10-22）：`localStorage` の倍率・X/Yが有効なとき（F01「盤面の表示位置（D13・作業B10）」）は画面の大きさを見ずにそのまま復元するため、広い画面で保存した位置を狭い画面で開くと駒がすべて画面外になることがあった。復元した場合はページ読み込み後の最初の1回だけ、表示領域の寸法が0でなく配置済みの駒（x,y≥0かつHP>0）が1つ以上ある描画時に `visual_controls.js::ensureRestoredViewShowsTokens` が駒の中心を画面座標へ変換して確認する。1つでも表示領域内にあれば保存位置をそのまま維持し、すべて外なら倍率は変えずに駒の中心の範囲の中央を表示領域の中央へ合わせ、その位置を保存し直す。確認は1回で終わり、以後ユーザーが動かした表示位置は補正しない。

検証：旧リトライ期限を超えてからSocketを生成するNode回帰テストで、Storeには2スロットがあるのにCoordinatorは0スロットのままになることを修正前に再現。修正後は遅延ログイン・DOM前のSocket生成・モジュール読込前のSocket生成が成功し、再初期化でもSocket購読は増えない。ローカル通常ルーム・幅1265pxのPLでも、未ログイン画面で2秒以上経過後にログインし、再読込なしの入室で2スロットの表示と自分の宣言パネルの表示を確認した。関連11件と全件936 passed / 2 skipped、フロントエンドビルド・文字検査・差分検査が成功。ブラウザでの切断・再接続とモバイルは未確認。

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

### 4.3 ログ描画ポリシー

- ユーザーチャットは完全にテキストとして描画し、HTMLタグを実行しない。
- システムログのみ、アプリが生成した既存ログ互換のために `<br>`, `<strong>`, `<b>` を限定的に復元する。
- 解決ログなどサーバー側で `html.escape` 済みの本文は、`&gt;`, `&lt;`, `&amp;`, `&quot;`, `&#39;` を一段だけ復元してから描画する。
- ログ受信の入口（`logToBattleLog`）は `static/js/common/log_core.js` にあり、Visualログ描画は `static/js/visual/visual_ui.js` が担う（計画書32で旧テキスト戦闘UIを廃止し一本化済み）。

---

## 5. PvEモードとAIロジック (PvE Mode)

**関連ファイル:** `manuals/implemented/05_PvE_Mode_Spec.md` (統合済み)

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

**関連ファイル:** `manuals/implemented/12_Character_Modal_Spec.md` (統合済み)

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

## 8. 2026-03 UI反映メモ

Manual14 由来の UI 改善のうち、画面構造として恒常化した内容をここに記録する。

### 8.1 マップ上の Select/Resolve 表示

- `visual_map.css` のスロット番号バッジは、状態異常アイコン帯と干渉しないようトークン上部へ退避する。
- `visual_arrows.js` の矢印アンカーは、スロット数字を隠さない位置へ寄せて描画する。
- この調整は表示上の可読性改善であり、対象選択や Resolve 判定のロジックには影響しない。

### 8.2 戦闘中の情報量制御

- `#visual-timeline-area` は UI 上では非表示にしてよい。
- ただし `timeline` データ自体は battle state 内で維持し、整列や解決順判定に使い続ける。
- フローティングテキストは戦闘フェーズ中に一斉表示されると読みにくいため、`select / resolve_mass / resolve_single / round_end` 中は抑止可能とする。
- 戦闘中の結果表示はマップ上フローティングより `ResolveFlowPanel` とログを優先する。

### 8.3 Resolve オーバーレイ

- Resolve 表示は、スクロール量を抑えるため情報の塊を圧縮して配置する。
- `ResolveFlowPanel` は勝敗・総ダメージ・内訳をサマリブロックとしてまとめてよい。
- attacker / defender の立ち絵、および `mass_summation` の参加者簡易表示を許可する。
- `tiebreak` 情報は現在表示中の対戦カードに限って補助表示し、常時一覧化はしない。

### 8.4 Select の宣言パネル配置（2026-03-31）

- `DeclarePanel`（`#select-resolve-declare-panel`）は、`map-viewport` 左下固定ではなく、右列サイドバー上のオーバーレイ表示を標準とする。
- 生成先は `#declare-panel-sidebar-host` を優先し、存在しない場合のみ `#visual-chat-area -> #map-viewport -> #visual-battle-container` の順でフォールバックする。
- 右列表示時のレイアウトは `.declare-panel--sidebar` を使用し、縦方向は右列の上端（R開始/R終了ボタン帯）から下端まで使う。
- 横幅は「従来値の約1.5倍」を目安に拡張し、実装上は `clamp(520px, calc(100% * 1.5), 760px)` を基準とする。
- 本変更は視認性改善のためのUI配置調整であり、Select/Resolve の判定ロジック・通信仕様には影響しない。

### 8.5 キャラクター操作の拒否通知（計画50、2026-10-18）

- `visual_socket.js` の一元登録で `move_denied` と `character_operation_denied` を同じハンドラーで購読する。後者は削除・駒サイズ変更の所有者チェックで使う。通常の駒移動・未配置一覧からの配置・詳細からの未配置化で、サーバーが拒否した本人にだけ表示する。
- 既存の `visual-toast` と同じ画面内通知方式で「このキャラクターを操作する権限がありません」を3秒間表示する。`alert` は使わず、通知はマウス操作を妨げない。スクリーンリーダー向けに `role="status"` を指定する。
- 同一の通知は1件だけ表示する。直前の拒否から3秒未満の拒否では通知を追加せず、表示時間も延長しない。拒否が続いている間は再表示を抑え、3秒以上途切れた後の新しい拒否では再び表示する。
- サーバーから届くメッセージはHTMLへ挿入せず、上記の固定文言を `textContent` で設定する。通知処理はキャラクターの座標・権限・保存状態を変更しない。
- サーバーの権限判定と `move_denied` のペイロードは変更しない。拒否された操作が状態へ反映されないことはサーバー側の所有者チェックで保証する。
- 検証（2026-10-18）：実際のSocket購読を使うNode回帰テストで、初回表示・連続抑制・消去・静穏後の再表示・固定文言・非モーダルを確認。権限と移動差分の関連23テスト、全件916 passed / 2 skipped、フロントエンドビルドが成功。ローカル通常ルームのPLで、自分の駒の配置成功と、敵の「配置」拒否時のトースト表示・自動消去をブラウザ確認した。確認幅は1265px。
- 削除・サイズ変更への拡張検証（2026-10-18）：非所有者の他人・敵への操作、持ち主・GMの正常操作、戦闘専用モード、非在室、対象不在を検証。拒否時にアクティブマッチ・保存・更新配信が変わらず、要求元だけへ通知されることを確認した。両イベントの通知表示・連打抑制をNodeで検証し、関連38件と全件933 passed / 2 skippedが成功。再ビルド・文字検査を実施。今回の削除・サイズ変更のブラウザ実機確認は未実施。

### 8.6 盤面の背景画像（2026-10-27）

- `#game-map` の初期表示は `visual_map.css` が描く90px格子（`linear-gradient` 2本、`background-size: 90px 90px`）とする。
- `battle_map_data.background_image` があるときは、`visual_map.js` の `applyBattleMapBackground` が `#game-map` のインラインに `background-image`・`background-size: contain`・`background-repeat: no-repeat`・`background-position: center` を設定する。
- 背景がないときは、上記4つのインライン指定をすべて外す。これにより背景を外した後も CSS の90px格子に戻る（以前は `background-image` だけを外し、`contain` などが残って格子が崩れていた）。


---

## 補足: コード仕様追補（旧07より）

旧07（`07_Visual_Battle_Code_Spec.md`）のほぼ全内容は上記06に内包済み。以下の情報のみ06に記載がないため補足する。

### グローバル変数の追補

| 変数名 | 初期値 | 説明 |
| :--- | :--- | :--- |
| `visualMapHandlers` | `{}` | マップ操作イベントリスナーの参照保持（削除用）。 |

### 旧ファイルの後方互換性

旧 `tab_visual_battle.js` は空のファイルとして残されており、後方互換性のため `index.html` で読み込まれていますが、実質的な処理は行いません。

---

## 2026-07 追補: 旧テキスト戦闘UIの廃止（計画書32）

計画書32（2026-07-08 実装完了・削除済み）により、旧テキスト戦闘UI（`static/3_battlefield.html`＋
`static/js/tab_battlefield.js`）を廃止し、ビジュアル戦闘（本書が扱うアーキテクチャ）へ一本化した。

### 構成変更

- `static/js/common/log_core.js`（新規）: ログ受信の入口 `logToBattleLog`・`_isDuplicateBleedLogLine`・
  `_normalizeLogMessageForDisplay` の移設先。`visual_socket.js` の `installBattleLogDeferHook` が
  `window.logToBattleLog` を wrap するため、`CLASSIC_SCRIPTS` では `visual_socket.js` より前に配置する。
- `static/js/common/char_json.js`（新規）: キャラJSON読込 `parseCharacterJsonToCharacterData`・
  `loadCharacterFromJSON` の移設先（`modals.js` の➕キャラ追加モーダルが参照）。
- `static/js/tab_battlefield.js` / `static/3_battlefield.html`: 削除。
- 死にファイル3点を削除: `static/js/wide_match_functions.js`・`static/js/wide_match_dock.js`・
  `static/js/battle/utils/DomUtils_backup.js`。
- `static/js/visual/visual_wide.js` の `openVisualWideMatchModal`（呼び出し元ゼロの死にコード。内部の
  `socket.emit('request_wide_match', ...)` はサーバハンドラが存在しない no-op イベントだった）と、
  その唯一の呼び出し先だった `renderVisualWideDefenders` を削除。広域攻撃の実処理は
  `wide_match_synced.js` の `wide_declare_skill` / `execute_synced_wide_match` 経由のまま変更なし。
- サーバ側 `events/battle/common_routes.py` の `request_declare_wide_skill_users` ハンドラを削除
  （フロント呼び出し元ゼロ・テストなしを確認済み）。

### 意図的に残したもの

- `events/battle/duel_routes.py` の `declare_skill` ハンドラは**削除しなかった**。フロントからの
  emit は無いが、`tests/test_match_integraton.py`（253行・267行）が `on_declare_skill` を直接呼び出して
  権限拒否等の挙動を検証しており、サーバー単体としては検証済みの契約であるため。テストを書き換えて
  まで削除するのは計画書32のスコープを超えると判断し、「テスト無修正で全通過」を優先した。
- `static/js/tab_skill_search.js`（呼び出し元ゼロだがバンドルには残存）は計画書32のスコープ外とし、
  存廃判断は計画書28に委ねている。

## 非行動スロットの表示と操作（2026-08-16）

非行動アンカーと一時的な行動不能スロットは、ひび割れた丸いバッジで表示する。速度値は表示せず`—`とし、恒久非行動・行動チャート待機は灰色、混乱は紫灰色を使う。ツールチップには理由と「攻撃対象には指定可能」を表示する。

- 単クリックは対象選択中のみ対象指定として機能し、それ以外では何もしない。
- ダブルクリックは宣言パネルを開かず、キャラクター詳細を表示する。
- GMを含め、非行動バッジを宣言元として選択できない。
- 通常スロットの`SYS-STRUGGLE`表示と操作は変更しない。

実装: `static/js/visual/visual_map.js`、`static/js/battle/components/DeclarePanel.js`、`static/css/modules/visual_map.css`。
