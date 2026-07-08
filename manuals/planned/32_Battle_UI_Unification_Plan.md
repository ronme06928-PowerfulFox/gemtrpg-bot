# 32 戦闘UI一本化計画（旧テキスト戦闘の廃止）

**作成日**: 2026-07-08
**位置づけ**: 旧テキスト戦闘UI（`static/3_battlefield.html`＋`static/js/tab_battlefield.js`、隠しタブでのみ到達可）を廃止し、ビジュアル戦闘（`static/js/battle/`＋`visual/`）に一本化する計画。計画書28 G16（死にコード整理）の拡張版。議論前のたたき台（§7 を一問一答で確定してから実装）。

---

## 1. 目的

- 新旧2系統の戦闘UIロジック重複（ログ・チャット・タイムライン・マッチ処理）を解消し、フロント改修時の影響範囲を明確にする。
- 到達不能な旧UIコード（約1300行超＋HTML）と死にファイルを削除し、バンドルサイズと保守負荷を下げる。

## 2. 現状分析（2026-07-08 調査）

### 2.1 到達経路の事実

- `main.js:975` `joinRoom()` は常に `loadTabContent('visual')` を呼び、`3_battlefield.html` はタブUI（`display:none`）経由でしか読み込まれない。
- ただし `tab_battlefield.js` にはタブと無関係に**現行ビジュアル画面が依存する関数が同居**しており、ファイルごと削除はできない。

### 2.2 ビジュアル画面が tab_battlefield.js に依存している箇所（移設必須）

| 機能 | 定義 | 依存元 |
|---|---|---|
| ログ受信の入口 `logToBattleLog`（＋`_isDuplicateBleedLogLine` / `_normalizeLogMessageForDisplay`） | `tab_battlefield.js:128-187` | `main.js:1119`（`new_log`）が常時呼ぶ。`visual_socket.js:478-520` が解決フロー演出のためにこの関数を **wrap**（`installBattleLogDeferHook`）。内部で `window.appendVisualLogBatch`（visual_ui.js:280）へ転送 |
| キャラJSON読込 `parseCharacterJsonToCharacterData`（window公開）/ `loadCharacterFromJSON` | `tab_battlefield.js:25-126` | `modals.js:2861,2867`（`openCharLoadModal` ＝ ビジュアルドックの➕キャラ追加から起動） |

**この2群以外に、旧タブにあってビジュアルに無い「機能」は実質ゼロ**（チャット・ダイス・ログ・タイムライン・ルーム操作はすべて `visual-*` IDの独自実装が存在）。

### 2.3 削除可能なもの（調査で確定）

- `3_battlefield.html` 全体＋`main.js` の `tab-battlefield` 分岐（:1183-1185, 1214-1217）＋隠しタブUI
- `tab_battlefield.js` の旧タブ専用群: `setupBattlefieldTab`（内部の旧socketハンドラ :1510-1668 含む）、`setupActionColumn`、`renderTokenList`、`renderTimeline`、`openWideDeclarationModal`、`openLogHistoryModal`、`openCharSettingsModal`（呼び出し0件）、`fetchSkillMetadata`、`appendLogLineToElement` / `renderLogHistory` / `MAX_LOG_ITEMS`（`log-area` 専用）
- 重複ダイス関数: `tab_battlefield.js` 版 `rollDiceCommand` / `safeMathEvaluate`（ロード順で `legacy_globals.js:222,229` 版が `window` を上書きしており実質シャドウ済み）
- **死にファイル3点**（参照0件・バンドル外を確認済み）: `static/js/wide_match_functions.js`、`static/js/wide_match_dock.js`、`static/js/battle/utils/DomUtils_backup.js`
- `static/js/tab_skill_search.js`（バンドルには入るが `setupSkillSearchTab` の呼び出し0件）— **去就は28 P2-3（復活or削除）の決定に従う**

### 2.4 Socket イベントの整理対象

| イベント | 状況 | 処置案 |
|---|---|---|
| `request_skill_declaration` / `request_match` / `request_state_update` / `battle_intent_*` / `wide_routes.py` 系 | ビジュアルが使用中 | **残す** |
| `request_declare_wide_skill_users`（common_routes.py:134） | 旧タブの `openWideDeclarationModal` のみが emit | 旧タブ削除に伴い**フロント emit 撤去**。サーバハンドラの削除は §7 |
| `request_wide_match` | 両側から emit されるが**サーバハンドラが存在しない**（no-op のレガシー） | emit を両ファイルから撤去可（`tab_battlefield.js:859`、`visual_wide.js:269`） |
| `declare_skill`（duel_routes.py:98） | フロントから emit する箇所が見つからない | **要精査**のうえ削除判断（§7） |

## 3. 対象範囲

### 触るもの
- `static/js/tab_battlefield.js`（大部分削除・共有関数の移設元）、`static/3_battlefield.html`（削除）
- 新規: 共有ログ関数・キャラJSON読込関数の移設先ファイル（名称は §7）
- `static/js/main.js`（タブ分岐除去）、`static/index.html`（隠しタブ除去）、`scripts/build_frontend.mjs`（`CLASSIC_SCRIPTS` 更新）
- `static/js/visual/visual_wide.js`（`request_wide_match` emit 除去）
- （判断後）`events/battle/duel_routes.py` / `common_routes.py` の未使用ハンドラ

### 触らないもの（禁止事項）
- ビジュアル戦闘の挙動・見た目（`battle/`・`visual/`・`wide_match_synced.js`・`modals.js` の機能変更なし）
- ビジュアルが使用中の socket イベント（上表「残す」）
- `legacy_globals.js` のダイス関数（共有ダイスの正本として維持）

## 4. 設計方針

### 4.1 移設の要点（最重要の壊れポイント）

- `logToBattleLog` は移設後も **`window.logToBattleLog` としてグローバル公開**し、`visual_socket.js` の `installBattleLogDeferHook` が wrap する前に定義されるよう **`CLASSIC_SCRIPTS` のロード順を維持**する（`__resolveWrapped` / `__resolveOriginal` の仕組みを壊さない）。
- 移設時に旧 `log-area` への書き込み分岐は削除してよいが、`visual-log-area` 転送分岐（現 :154-165）は保持必須。
- `parseCharacterJsonToCharacterData` は `window` 公開のまま移設（`modals.js` が参照）。

### 4.2 手順（調査レポートの最小手順を採用）

1. 共有2群を新ファイル（例: `static/js/common/log_core.js`・`static/js/common/char_json.js`）へ切り出し、`CLASSIC_SCRIPTS` に **tab_battlefield.js より前・visual_socket 参照より前**の位置で追加
2. `tab_battlefield.js` の残り全部と `3_battlefield.html` を削除、`CLASSIC_SCRIPTS` から除外
3. `main.js` のタブ分岐・`index.html` の隠しタブを除去
4. 死にファイル3点を削除
5. `request_wide_match` emit（visual_wide.js）と旧イベントの整理
6. `npm run build` → 実画面確認

## 5. 実装段階

| Phase | 内容 | 検証 |
|---|---|---|
| 1 | 共有2群の移設（機能変更なし、tab_battlefield.js は残したまま二重定義を避けて委譲） | `npm run build` 後、チャット送信・`/roll`・ログ受信・解決フロー中のログ遅延演出・➕キャラJSON追加が全て動く |
| 2 | 旧タブ本体の削除（tab_battlefield.js / 3_battlefield.html / main.js 分岐 / 隠しタブ） | 同上の実画面確認＋入室〜戦闘1ラウンドの通し確認 |
| 3 | 死にファイル削除＋`request_wide_match` emit 除去 | ビルド成功・広域マッチ（wide_match_synced 経由）の動作確認 |
| 4 | サーバ側の未使用ハンドラ整理（`request_declare_wide_skill_users`、精査後の `declare_skill`） | `pytest -q` 全通過（関連テストの有無を先に確認） |

## 6. 推奨PR分割

1. Phase 1（移設のみ。diff は大きいが挙動不変）
2. Phase 2（旧タブ削除）
3. Phase 3（死にファイル・no-opイベント掃除）
4. Phase 4（サーバハンドラ整理）

各PRで `npm run build` 必須・`static/dist/*` をコミット（AGENTS.md）。

## 7. 未決定事項

| 論点 | 選択肢 | 備考 |
|---|---|---|
| 移設先の構成 | (1) `static/js/common/` に log_core.js / char_json.js 新設 / (2) 既存 `legacy_globals.js` と `modals.js` へ吸収 | (2)はファイル数を増やさないが modals.js（3268行）がさらに肥大化 |
| `tab_skill_search.js` | 削除 / 復活（モーダル再接続） | **28 P2-3 と同一論点。二重決定を避けるため28側で確定し本計画は従う** |
| `declare_skill` サーバハンドラ | 精査のうえ削除 / 温存 | フロント emit 0件だが外部クライアント/過去互換の考慮が要るか |
| `request_declare_wide_skill_users` ハンドラ | フロント撤去と同時にサーバも削除 / サーバは温存 | 削除ならテストの有無を確認 |
| 旧duel UI の扱い | ビジュアルの MatchPanel が `request_match`/`request_skill_declaration` を使うため**サーバ側 duel フローは維持**（確認済み） | 削除対象はあくまで旧タブのフロントコード |
| 実画面検証の方法 | 手動2ブラウザ確認 / preview ツールでの半自動確認 | チャット/ログ/キャラ追加/解決演出の4点は必須チェック |

## 8. 決定事項ログ

（一問一答の議論後に追記する）

| 日付 | 論点 | 決定 | 根拠 |
|---|---|---|---|
| | | | |

## 9. 受け入れ条件

- `3_battlefield.html` / `tab_battlefield.js` / 死にファイル3点がリポジトリから消え、`CLASSIC_SCRIPTS` とバンドルが整合している。
- ビジュアル画面で以下が退行なく動く: チャット送信、`/roll` `/sroll`、ログ受信と解決フロー中のログ遅延演出、ログ履歴モーダル、➕キャラのJSON読込、広域マッチ、決闘（MatchPanel）。
- `pytest -q`・`npm run build`・エンコーディング/文字化けチェック全通過。
- E01/E02（UIアーキテクチャ仕様書）から旧テキスト戦闘への言及が更新され、本計画書が削除されている。
