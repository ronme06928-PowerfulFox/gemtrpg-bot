# 28 TRPGプレイ体験改善計画（アプリ全体スキャン起点）

**作成日**: 2026-07-07
**位置づけ**: アプリ全体（バックエンド・フロントエンド・マニュアル/既存計画）をスキャンし、「アプリとしてよりよくTRPGを遊べるようにする」観点で改善候補を整理した計画書。本書は議論前のたたき台であり、`manuals/planning_process.md` の一問一答方式で優先度・方式を確定してから実装に入る。

---

## 1. 目的

- セッションの「記録が残る・信頼できる・止まらない」を底上げする（ログ保全、ダイスの公平性、保存信頼性）。
- GMの運営負荷を下げる（巻き戻し、行動順の手動調整、待機者への通知）。
- 長時間プレイの快適性を上げる（ショートカット、ダークモード、検索導線）。

スキルロジック新規追加（封印・逆襲・気合い等）や増援・駒枠画像は**既存計画の管轄**とし、本書では扱わない（§3）。

## 2. 調査サマリ（2026-07-07 全体スキャン）

### 現状の強み
- Select/Resolve フェーズ制のビジュアル戦闘、PvE敵AI（行動チャート）、戦闘専用モードのプリセットv2、探索モード、GMバフ/アイテム操作、アカウント/ルーム権限システムが実装済み（`manuals/implemented/` A〜F 系統参照）。
- プリセット・敵編成・戦績はJSONエクスポート/インポート可能。

### 発見した主なギャップ（根拠付き）
| # | ギャップ | 根拠 |
|---|---|---|
| G1 | セッションログは最新500件で切り捨て、エクスポート導線なし | `manager/room_manager.py:481`（`state['logs'][-500:]`）、フロントも `MAX_LOG_ITEMS = 200`（`static/js/tab_battlefield.js:169`） |
| G2 | チャットダイス（`/roll` `/sroll`）はクライアントの `Math.random` で計算 | `static/js/tab_battlefield.js:310-337` — 改竄可能でサーバー権威性がない |
| G3 | DB保存はデバウンス2秒＋失敗時リトライなし | `manager/room_manager.py:315,348-352` — クラッシュ時に直近操作が消失しうる |
| G4 | 戦闘操作のundoが皆無（全リセット/強制終了のみ） | `events/battle/common_routes.py:207,225` |
| G5 | イニシアチブは速度から自動算出のみ、GMの手動並べ替え不可 | `manager/battle/select_resolve_state.py:324-333` |
| G6 | 手番・宣言待ちの通知手段がダイスSEのみ（タブ非アクティブ時に気づけない） | `static/js/sound_fx.js`、`Notification` API 未使用 |
| G7 | キーボードショートカットがほぼ皆無（ダイアログEsc/Enter、チャットEnterのみ） | `static/js/main.js:156-159`、`static/js/tab_battlefield.js:1298-1300` |
| G8 | ダークモード非対応（`prefers-color-scheme` 指定ゼロ） | `static/css/` 全体 |
| G9 | スキル横断検索が死にコード化（定義のみで未呼び出し） | `static/js/tab_skill_search.js:2` |
| G10 | ログのフリーワード検索がない（all/chat/system フィルタのみ） | ログ履歴モーダル（`static/js/` ログUI） |
| G11 | ドックの絵文字アイコン群に `aria-label` がない | `static/4_visual_battle.html:5-21` |
| G12 | 観戦者ロールがない（owner/gm/player の3種のみ） | `models.py:109` |
| G13 | 1ルーム＝1戦闘固定（`battle_id = f"battle_{room}"` 決め打ち） | `manager/battle/common_manager.py:556,747,1131` ほか |
| G14 | シナリオ/キャンペーン管理・ハンドアウト機能なし | scenario/campaign 系のコードなし |
| G15 | BGM/効果音の同期配信なし | bgm/audio 系のサーバーコードなし |
| G16 | 死にコード・開発残骸の混在 | `static/js/wide_match_functions.js` / `wide_match_dock.js` / `battle/utils/DomUtils_backup.js`、ルート直下 `battle_state.json` / `saved_rooms.json` / `error.log`、`manager/temp_logic_draft.py` |

## 3. 既存計画との住み分け（本書で扱わないもの）

| テーマ | 管轄計画書 |
|---|---|
| 逆襲（被ダメターン限定の与ダメ増加） | `planned/12_Retaliation_Plan.md`（旧03を統合済み。加害者反応は C02 被弾反応として実装済み） |
| 気合い | `planned/13_Charge_Kiai_Plan.md`（旧03を統合済み） |
| 増援機能 | `planned/16_Reinforcement_Feature_Separate_Plan.md` |
| キャラ駒の枠画像デザイン | `planned/24_TokenFrame_Image_Design_Plan.md` |
| アイテム在庫不足の回帰テスト・GM操作ログ見える化 | `planned/04_TRPG_Session_Improvement_Feasibility_Plan.md` 残課題 |
| 戦闘UI一本化（G16の死にコード削除を含む） | `planned/32_Battle_UI_Unification_Plan.md`（本書 Phase 5 の JS 死にコード分は32へ移管。ルート直下の残骸ファイル整理のみ本書に残る） |

※ 旧 `planned/03_New_Skill_Ideas_Feasibility_Plan.md`（行動阻害系・わるあがき・共通判定層）は2026-07-07の棚卸しで中核の実装完了を確認し削除。仕様は `B01_Skill_Logic_Core.md` §13 / `B02_Skill_Logic_Extensions.md`（SYS-STRUGGLE） / `C01_JSON_Definition_Master.md` §6・§10 が正本。

※ 04 残課題の「GM操作ログの見える化」は、本書 P1-3（操作履歴）と実装が重なるため、着手時に 04 から本書へ吸収するか判断する。

## 4. 改善提案一覧

### P0 — セッションの信頼性・記録（最優先）

#### P0-1 セッションログのエクスポートと検索（G1, G10）
- **提案**: (a) GM操作でルームログをテキスト/JSONでダウンロードできるエクスポートAPI（既存の戦績エクスポート `request_bo_record_*` と同型のパターン）。(b) ログ履歴モーダルにフリーワード検索（フロント内フィルタで十分）。
- **効果**: セッション後の「ログ整形・リプレイ公開」というTRPG文化圏の基本ニーズに応える。500件切り捨て問題の実害も緩和（切り捨て前に手動保存できる）。
- **影響範囲**: `manager/room_manager.py`（ログ取得）、`events/socket_main.py` or `routes/`（エクスポート導線）、ログ履歴モーダルJS。

#### P0-2 サーバーサイドダイスロール（G2）
- **提案**: `request_chat` の `/roll` `/sroll` をサーバー側 `manager/dice_roller.py` で振る。フロントは式の送信と結果表示に専念。表示フォーマット（`式 = (出目) = 合計`）は現行踏襲。
- **効果**: 出目の改竄を防ぎ、ダイスボットとしての公平性を担保する。TRPGツールとして最も基本的な信頼性。
- **影響範囲**: `events/socket_main.py`（request_chat）、`static/js/tab_battlefield.js:310-337`（ローカル計算の除去）。`sroll`（シークレット）の宛先制御はサーバー側で行うことで真に秘匿になる副次効果あり。

#### P0-3 保存信頼性の強化（G3）
- **提案**: (a) デバウンス保存失敗時の再スケジュール（1回リトライ＋失敗ログ）。(b) ラウンド終了・戦闘終了・モード切替など節目イベントでの即時フラッシュ。
- **影響範囲**: `manager/room_manager.py:315-352` 周辺のみ。デバウンス設計（AGENTS.md 記載の2秒集約）は維持する。

### P1 — GM運営支援

#### P1-1 手番・宣言待ち通知（G6）
- **提案**: (a) 自分の宣言待ち/手番時にタブタイトルを点滅（`document.title` 切替）。(b) 任意許可制のブラウザ `Notification`。(c) 宣言待ちSE（`sound_fx.js` 拡張、ON/OFF は既存のSEトグルに従属）。
- **影響範囲**: フロントのみ（`battle/core/BattleStore.js` 購読 + `sound_fx.js`）。サーバー変更不要。

#### P1-2 イニシアチブの手動調整（G5）
- **提案**: GM限定イベント（例: `request_reorder_timeline`）でタイムラインの並べ替え・特定キャラの順序固定を可能にする。UIは既存タイムライン（`battle/components/Timeline.js`）へのドラッグ&ドロップまたは上下ボタン。
- **効果**: 割り込み・遅延行動・演出上の順序変更などGM裁量の進行が可能になる。
- **影響範囲**: `manager/battle/select_resolve_state.py`、`events/battle/common_routes.py`、`Timeline.js`。

#### P1-3 限定undo（1手巻き戻し）（G4）
- **提案**: 最小構成として「HP/MP/FP・状態異常のGM/プレイヤー変更操作の直近N件を履歴に積み、GMが逆操作で戻せる」操作履歴方式。戦闘フェーズ全体のスナップショット復元は複雑度が高いため未決定事項（§7）とする。
- **効果**: ダメージ入力ミス・誤操作のたびに全リセットする現状の運用負荷を解消。04残課題「GM操作ログの見える化」と履歴データを共用できる。
- **影響範囲**: `manager/room_manager.py`（ステータス増減系）、`events/socket_char.py` / `socket_items.py`、GM向けUI。

### P2 — プレイの快適性

#### P2-1 キーボードショートカット（G7）
- **提案**: 最小セット — 宣言確定（Enter）、解決フェーズ送り（Space/→）、マップズームリセット、チャット欄フォーカス（/）。入力中は無効化するガード必須。
- **影響範囲**: フロントのみ（`DeclarePanel.js`、`ResolveFlowPanel.js`、`visual_controls.js`）。

#### P2-2 ダークモード（G8）
- **提案**: 色を CSS 変数へ段階的に集約し、`prefers-color-scheme: dark` ＋手動トグル（localStorage）を提供。まず戦闘画面・ログ・モーダルの主要面から。
- **影響範囲**: `static/styles.css` と `static/css/` 全般。機能変更なし・見た目のみ。

#### P2-3 スキル・用語横断検索の復活（G9）
- **提案**: 死にコードの `tab_skill_search.js` を、ドックの📚（図鑑）隣に「スキル検索」モーダルとして再接続する。復活させない判断なら削除して `CLASSIC_SCRIPTS` からも外す（二択を議論で確定）。
- **影響範囲**: `static/js/tab_skill_search.js`、`static/js/action_dock.js`、`scripts/build_frontend.mjs`。

#### P2-4 アクセシビリティ最低限対応（G11）
- **提案**: ドックアイコン（`static/4_visual_battle.html:5-21`）と主要操作ボタンへ `aria-label` 付与。P2-1のキーボード操作と合わせて操作性を底上げ。

### P3 — 大型テーマ（本書では候補提示のみ、着手時に別計画へ切り出す）

| テーマ | 概要 | 主な論点 |
|---|---|---|
| 観戦者ロール（G12） | `RoomMember.role` に `spectator` を追加し読み取り専用入室 | secret/gmOnly情報の秘匿設計、UI の操作封鎖範囲 |
| 並行戦闘（G13） | `battle_id` のルーム固定を解除し複数エンカウント同時進行 | 状態構造の大改修。費用対効果を要検討 |
| シナリオ/キャンペーン管理（G14) | シーンメモ・ハンドアウト・セッションをまたぐ進行管理 | ルーム＝状態コンテナという現設計との整合 |
| BGM/効果音同期（G15） | GMが指定した音源URLの再生指示を同期配信 | 音源の権利・ホスティング、自動再生制限 |
| VTT拡張 | フォグ・ピン/メモ・複数マップ切替 | 探索モードの位置づけ再定義 |

### 併記 — 技術的負債の整理（プレイ体験を間接支援）（G16）

- 未使用JSの削除: `static/js/wide_match_functions.js`、`static/js/wide_match_dock.js`、`static/js/battle/utils/DomUtils_backup.js`。
- ルート直下の開発残骸の整理: `battle_state.json`、`saved_rooms.json`、`error.log`、`manager/temp_logic_draft.py`、`temp_animation.css`、`test_results.txt`。
- `manager/game_logic.py` の巨大関数分割は計画書29として **2026-07-07 に実装完了**（`manager/battle/effect_handlers/` へ分割、B01 追補参照）。残る行数超過ファイルは `manager/utils.py` と `events/battle/common_routes.py` の2件（別計画）。

## 5. 実装段階（Phase 分割案）

| Phase | 内容 | 依存 |
|---|---|---|
| Phase 1 | P0-2 サーバーダイス → P0-3 保存信頼性 → P0-1 ログエクスポート/検索 | なし（相互独立、この順を推奨） |
| Phase 2 | P1-1 通知 ＋ P2-1 ショートカット（どちらもフロント完結） | なし |
| Phase 3 | P1-2 イニシアチブ手動調整 → P1-3 限定undo | P1-3 は §7 の方式決定が前提 |
| Phase 4 | P2-2 ダークモード、P2-3 検索復活、P2-4 aria | なし |
| Phase 5 | 負債整理（未使用JS削除・残骸整理） | 単独PRで随時可 |
| （別計画） | P3 の各テーマ | 着手判断後に個別計画書を新規作成 |

## 6. 推奨PR分割

1. サーバーサイドダイス（events/socket_main.py + フロント除去 + テスト）
2. 保存リトライ＋節目フラッシュ（room_manager.py + テスト）
3. ログエクスポートAPI＋ログ検索UI
4. 手番通知（フロントのみ）
5. キーボードショートカット（フロントのみ）
6. イニシアチブ手動調整（サーバー＋Timeline UI）
7. 限定undo（方式決定後）
8. ダークモード（CSS変数化を先行PRに分けてもよい）
9. スキル検索の復活 or 削除
10. 死にコード・残骸整理

※ 各PRで JS/CSS を触る場合は `npm run build` 必須（AGENTS.md）。

## 7. 未決定事項

| 論点 | 選択肢 | 備考 |
|---|---|---|
| ログの長期保全方式 | (1) エクスポートのみで対応（500件維持） / (2) 切り捨て前に別テーブルへアーカイブ / (3) 上限引き上げ | (2)はDBスキーマ追加・Render容量に影響。まず(1)で様子見が低リスク |
| undo の範囲 | (1) ステータス変更の逆操作のみ / (2) ラウンド開始時スナップショット復元も追加 | (2)は召喚・バフ・戦闘メモリの整合が難しい |
| サーバーダイス移行時の互換 | 旧クライアント表示の互換維持が必要か | ログフォーマットを踏襲すれば互換問題は小さい見込み |
| スキル検索 | 復活 or 削除 | 復活なら図鑑UIとの統合も検討 |
| ダークモードの実装粒度 | 全画面一括 / 主要画面から段階導入 | CSS変数化の作業量に依存 |
| P3 テーマの着手要否 | 観戦ロール・並行戦闘・シナリオ管理・BGM・VTT拡張 | 利用実態（プレイ人数・セッション形態）を踏まえて判断 |
| 04残課題との統合 | GM操作ログ見える化を P1-3 に吸収するか | 吸収する場合は 04 を更新 |

## 8. 決定事項ログ

（一問一答の議論後に追記する。`manuals/planning_process.md` 参照）

| 日付 | 論点 | 決定 | 根拠 |
|---|---|---|---|
| | | | |

## 9. 受け入れ条件

- **Phase 1**: `/roll` の出目がサーバー生成であること（クライアント改竄不能）。保存失敗時にリトライログが出ること。GMがログをファイル保存でき、ログ履歴モーダルで文字列検索できること。
- **Phase 2**: タブ非アクティブ中に自分の宣言待ちになるとタイトル点滅（＋許可時は通知）が出ること。主要操作がキーボードで完結すること（入力欄フォーカス中は発火しない）。
- **Phase 3**: GMがタイムラインの順序を変更でき、変更が全参加者に同期されること。ステータス誤操作を全リセットなしで1手戻せること。
- **Phase 4**: ダークモード切替で主要画面のコントラストが確保されること。スキル検索の方針（復活/削除）が実装に反映されバンドルが整合すること。
- 共通: `pytest -q` 通過、`npm run build` 実行済み、`python scripts/check_text_encoding.py` / `check_mojibake_markers.py` 通過。
