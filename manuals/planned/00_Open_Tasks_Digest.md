# 00 残タスク一覧（planned/ ダイジェスト）

**作成日**: 2026-07-07（最終更新: 2026-07-10 — 計画28 Phase 1を実装し、正本をF01へ統合）
**位置づけ**: `manuals/planned/` 配下の各計画書に散っている未完了タスクを1本にまとめた索引。
使用量が厳しい時などに、個別ファイルを開かずここだけ見て次の一手を判断するためのもの。
**このファイルは要約であり正本ではない。** 実装時は必ず該当する個別計画書（04/12/13/16/24/28）を読むこと。
各計画書の内容が変わったら、このダイジェストも合わせて更新する。

---

## 状態スナップショット（2026-07-07 時点）

- `manager/game_logic.py` の分割（旧計画29）は**実装完了**。`process_skill_effects` は
  `manager/battle/effect_handlers/` へ分割済み（正本: `B01_Skill_Logic_Core.md` 追補）。
- `manager/utils.py` の分割（計画書33）も**実装完了**。`apply_buff` は
  `manager/buff_apply.py` へ分割済み（正本: `B01_Skill_Logic_Core.md` 追補）。utils.py は
  1510→1105行、`LEGACY_FILE_CEILINGS` から削除済み。
- `events/battle/common_routes.py` の分割（計画書34）も**実装完了**。リダイレクト処理は
  `events/battle/redirect_flow.py` へ分割済み（正本: `B03_SelectResolve_Spec.md` 追補）。
  1533→1380行、`LEGACY_FILE_CEILINGS` から削除済み。
  **`tests/test_python_module_size_guard.py` の `LEGACY_FILE_CEILINGS` は現在空**
  （29・33・34の完了によりモジュールサイズガードの例外がゼロになった）。

---

## タスク早見表

| 元計画 | タスク | 優先度感 | ひとことメモ |
|---|---|---|---|
| 28 | ~~P0-3 保存信頼性の強化~~ | — | **実装完了**。正本は `F01_Operations_Manual.md` Part 7 |
| 28 | ~~P0-1 セッションログの別テーブルアーカイブ＋エクスポート/検索~~ | — | **実装完了**。正本は `F01_Operations_Manual.md` Part 7 |
| 28 | P0-2 サーバーダイスの回帰テスト・仕様反映 | 中 | `/roll` `/sroll` のサーバー処理は実装済み。逆戻り防止と正本化が残る |
| 04 | アイテム在庫不足の回帰テスト | 中 | 個数0での使用/没収の挙動確認テスト追加のみ |
| 28 | P1-1 手番・宣言待ち通知 | 中 | フロントのみで完結（タブタイトル点滅/Notification/SE） |
| 28 | P1-2 イニシアチブの手動調整 | 中 | GM限定でタイムライン並べ替え |
| 28 / 04 | P1-3 限定undo（操作履歴） | 中 | 04の「GM操作ログ見える化」を吸収して操作履歴基盤を一本化 |
| 28 | P2-1 キーボードショートカット | 低〜中 | フロントのみ |
| 28 | ~~P1-4 キャラクターJSON追加導線の再設計~~ | — | **実装完了**。正本は `E02_UI_Component_Specs.md` Part 5 |
| 28 | P2-2 ダークモード | 低〜中 | 主要画面から段階導入 |
| 28 | P2-3 可視性制御付きスキル検索の復活 | 低〜中 | 敵専用スキルは非GM検索対象外。現在フィールド上で公開閲覧可能な敵スキルは検索可能。UIは現行アプリに合わせて再設計 |
| 28 | P2-4 aria-label 対応 | 低 | ドックアイコン中心 |
| 28 | P3 大型テーマ（観戦ロール/並行戦闘/シナリオ管理/BGM/VTT拡張） | 保留 | 今回は着手せず、必要時に個別計画へ切り出す |
| 28 | 技術的負債整理（死にコード・残骸ファイル削除） | 低 | 単独PRで随時可 |
| 12 | 逆襲: 被ダメターン限定の与ダメ増加 | 未着手 | 加害者反応（被弾反応パッシブ）は実装済み。残るのは戦闘メモリ方式 |
| 13 | 気合い（次攻撃1回2.5倍） | 未着手 | 基盤はあるが専用バフ`Bu-Charge`が未実装 |
| 16 | 増援機能 | 未着手 | データ構造のみ設計済み。UI・投入処理は全て未実装 |
| 24 | キャラ駒の枠画像デザイン | 未着手（画像待ち） | 設計確定済み。PNG画像の用意が最初のボトルネック |
| 30 | バランス検証シミュレータ | 中 | 実エンジンで低/中/高ロールの撃破ターンを自動検証。§7の一問一答が未実施 |
| 35 | ホロウダンジョン（ハクスラ） | 未着手（たたき台） | 浅層1〜50Fの階層制ハクスラ。battle_only基盤流用。§10の一問一答が未実施 |
| 31 | ~~スキルデータlint・相場自動集計~~ | — | **実装完了・計画書削除済み**。正本は `C01_JSON_Definition_Master.md` §12 |
| 32 | ~~戦闘UI一本化（旧テキスト戦闘の廃止）~~ | — | **実装完了・計画書削除済み**。正本は `E01_Visual_Battle_Architecture.md` 追補 |
| 33 | ~~`manager/utils.py` 分割~~ | — | **実装完了・計画書削除済み**。正本は `B01_Skill_Logic_Core.md` 追補 |
| 34 | ~~`events/battle/common_routes.py` 分割~~ | — | **実装完了・計画書削除済み**。正本は `B03_SelectResolve_Spec.md` 追補 |

---

## 計画書ごとの詳細サマリ

### 28_TRPG_Play_Experience_Improvement_Plan.md（決定済み・実装前整理）

TRPGプレイ体験改善を、目的、対象範囲、現状整理、決定済み方針、実装フェーズ、受け入れ条件に再整理済み。
Phase 1（保存信頼性、ログ別テーブルアーカイブ、GMログエクスポート、ログ履歴検索）は2026-07-10に実装完了し、
正本を `manuals/implemented/F01_Operations_Manual.md` Part 7へ統合済み。
2026-07-08の再調査で、
`/roll` `/sroll` のサーバーダイス化、旧テキスト戦闘/旧wide match系JS削除、
utils/common_routes分割完了を反映済み。ログ長期保全方式は
**別テーブルアーカイブ**で決定済み。2026-07-10に残る論点も決定済み:
04残課題は限定undoへ吸収 / undoはステータス変更の逆操作のみ / サーバーダイス仕様はA01+F01へ正本化 /
スキル検索は可視性制御付きで復活し、UIは現行アプリの雰囲気に合わせて再設計 /
キャラクターJSON追加は味方/敵選択から始まる2段階導線へ再設計し、ローカルJSONファイル読込を追加済み。GM専用デバッグ生成は各追加画面で人数選択可能 /
ダークモードは主要画面から段階導入 / P3は今回は保留。

推奨実装順（Phase1〜5、独立度高い順）:
1. サーバーダイスの回帰テスト・仕様反映（実装済み挙動の固定）
2. 手番通知 + キーボードショートカット（フロントのみ、並行可）
3. イニシアチブ手動調整 → 操作履歴ベースの限定undo
4. 主要画面ダークモード / 可視性制御付きスキル検索 / aria
5. 残骸ファイル整理（随時）

### 04_TRPG_Session_Improvement_Feasibility_Plan.md（残課題のみ）

大半は解消済み（GM操作系・認可回帰テスト・debug_apply_buffの露出管理）。
04単体で残る実装作業はアイテム在庫不足の回帰テスト追加のみ。
GM操作ログ見える化は28のP1-3へ吸収済み方針で、操作履歴ベースの限定undoと同じ基盤で扱う。

### 12_Retaliation_Plan.md（逆襲）

加害者への追加ダメージ（被弾反応パッシブ）は実装済み（C02仕様）。
未実装は「被ダメしたターンのみ自分の与ダメが増える」条件参照のみ。
推奨: 専用バフ方式（方式B）で先に実装。戦闘メモリ（`damage_taken_this_round`等）を
HPを減らす**全経路**（core/duel_solver/wide_solver/skill_effects/追撃/反射/被弾反応自体）に
仕込む必要があり、ここが最も壊れやすい。

### 13_Charge_Kiai_Plan.md（気合い）

完全未実装。新規バフ`Bu-Charge`（`plugins/buffs/charge.py`）＋気合いスキル定義の2点が要作業。
「次のダメージスキル1回だけ2.5倍、非ダメージでは消費しない、`expire_round`で1R後失効」という
仕様は確定済みなので、設計議論は不要ですぐ実装に入れる。

### 16_Reinforcement_Feature_Separate_Plan.md（増援）

データ構造案のみ（`reinforcements[]` / `timing` / `condition` / `members` / `once`）。
UI・戦闘中投入処理・マイグレーション・E2Eは明示的に未実装。
後続フェーズ: データ構造→敵編成UI→ステージUI→ラウンド開始時投入処理→ログ/E2E の5段階。

### 30_Battle_Balance_Simulator_Plan.md（バランス検証シミュレータ）

実戦闘エンジン（Select/Resolve）をFlaskなしのpytestハーネスで回し、低/中/高ロール別の
決着ラウンド・詰み・勝敗を自動集計する。ヘッドレス駆動は既存smoke testで実証済み、
敵AIは自動化済みで**味方AIの薄いラッパと roll_dice 差し替えが主な新規実装**。
乱数は roll_dice 系と random 直呼び（AI選択）の2系統がある点に注意。

### 35_Hollow_Dungeon_Plan.md（ホロウダンジョン・たたき台）

世界設定『アヌッサ・ホロウ』を題材にした階層制ハクスラ（浅層1〜50F、51F以降はフレーバー封鎖）。
battle_only（PvE）基盤・バフプラグイン・grant_item を流用し、新規は「ラン状態（`hollow`キー）」
「重み付き抽選」「ホロウ専用敵マスター」「遺物マスター」「階層スケーリング」「進行UI」。
マスターデータは**Google Sheetsを正**としgspreadで取り込む（既存 `data_manager.py` の認証基盤を流用、
JSONはキャッシュ）。Sheetsへの書き戻しも実現可能と確認済みでPhase 7に分離。
敵はホロウ専用マスター新設（プリセットへのタグ付け方式は不採用）、実体化はプリセット互換形式で既存コード流用。
遺物はラン中のみ有効な special_buffs で表現し、ラン終了で消滅（設定準拠）。

2026-07-10の議論で追加決定: 進行はGMレスのプレイヤー主導（ホロウ用ホストがGM専用操作を代行、
他プレイヤーは非拘束の推薦ピンで意思表示）／全滅は常に1Fから再挑戦（チェックポイント再開はしない）／
遺物は既定でパーティ全体対象、対象を絞る場合はconditional条件かslot:N（編成順）で指定／精鋭はバフ積みを
基本に階層帯（Tierのサブ帯域）が進むと精鋭セット自体が別データへ切り替わる方式／ホロウ専用スプレッドシート
を新規作成中（既存スキルシートとは分離）。

さらに追加決定: **ホストはルームオーナーが既定値**。オーナー（現ホスト）が退室（membership失効）したら
`RoomMember.joined_at`昇順で次の在室メンバーへ自動継承し、いつでも別ユーザーへ明示的に譲渡も可能
（ルーム設定的なUIから）。ホスト不在時はGMが常に代行可（OR条件の権限判定）。
**パーティ編成画面を新設**（味方キャラ一覧とパーティ一覧`party.order`を分離、並べ替え可能）。
これはホロウ専用ではなく**通常のTRPGルームでも使える汎用機能**として設計し、味方NPCはパーティ一覧に
含めないだけで排除を表現する（新規`is_npc`フラグは必須としない）。ホロウはラン開始時に`party.order`を
`hollow.run.party_order`へスナップショットしてslot:N遺物の基準にする。
この汎用機能のためPhase 0（パーティ/ホスト基盤）を新設。

さらに追加決定: **ホスト明示的譲渡は現ホストとGM/オーナーのみ可**（早い者勝ちの自称は不可）。
**パーティ画面は通常ルームのドック（`action_dock.js`）に常設ボタンを置く**汎用機能とし、パーティ一覧の
各キャラ行から既存のアイテム使用・キャラ詳細表示への導線を追加する（既存モーダルの再利用のみ、
再実装しない。既存ドックアイコンは残し統合・撤去は今回はしない）。

さらに追加決定: **推薦ピンの対象範囲**は初期実装（Phase 5）を降りる/撤退中心に絞る。遺物選択（誰が取るか等）
への拡大は方向性として採用するが、詳細は遺物運用の仕様が固まるPhase 3〜4着手時に再検討。
**パーティ行のショートカットはアイテム使用・キャラ詳細表示の2つに限定**（簡易ステータス編集はGM操作のため対象外）。

Phase 0〜7（パーティ/ホスト基盤→データ基盤→進行コア→報酬→イベント階→UI→バランス→書き戻し）。
§10の一問一答（撤退時の持ち帰り・精鋭セット切替間隔・is_npcフラグ要否・遺物選択への推薦ピン拡大の詳細ほか10論点）が未実施。

### ~~31_Skill_Data_Lint_Market_Rate_Plan.md~~ → 実装完了・削除済み（正本: `C01_JSON_Definition_Master.md` §12）

`scripts/skill_catalog_tool.py` に `lint` / `build-market-rate` サブコマンドを実装。Phase 1〜4すべて完了:
- `lint`: strict正規化＋skill_constraints参照整合（ERROR、現行133件で0件）に加え、
  確定基準からの相場逸脱（WARN: power_stage/cost/state_value/acquire_cost/action_economy）を検出。
- `build-market-rate`: F02の`<!-- BEGIN/END:market-rate -->`マーカー区間を自動再集計・上書き
  （キャッシュmtime由来の日付で冪等）。
- `manager/data_manager.py::update_all_data()` にfail-closedフック接続済み
  （lint ERRORがあれば`--update`自体を失敗させる）。
- `.github/workflows/skill-smoke.yml` に lint と `build-market-rate --check` を追加済み。
- 回帰テスト4ファイル（lint/warn/market_rate/data_manager_lint_hook、計21ケース）。

実装中に手動集計の見落とし2件（取得0帯の欠落／状態異常表へのFP・MP・HP混入）と、
WIN timingのAPPLY_STATEを誤検知していたstate_value判定の設計欠陥を発見・修正した。

### ~~32_Battle_UI_Unification_Plan.md~~ → 実装完了・削除済み（正本: `E01_Visual_Battle_Architecture.md` 追補）

旧テキスト戦闘（3_battlefield.html＋tab_battlefield.js）を廃止。共有2群（ログ入口
`logToBattleLog`／キャラJSON読込`parseCharacterJsonToCharacterData`）を
`static/js/common/log_core.js`・`char_json.js`へ移設し、旧タブ本体・死にファイル3点
（wide_match_functions.js/wide_match_dock.js/DomUtils_backup.js）・no-opイベント
（`request_wide_match`とその唯一の呼び出し元`openVisualWideMatchModal`）を削除。
バンドルサイズ818.1KB→766.9KB（約51KB削減）。

Phase 4実装時に当初の想定を修正: `declare_skill`サーバハンドラは`tests/test_match_integraton.py`
が直接呼び出す実テストが存在すると判明し、「テスト無修正で全通過」を優先して**削除しなかった**
（フロント視点では死にコードだが、サーバー単体としては検証済みの契約）。
`request_declare_wide_skill_users`はテスト・呼び出し元ともにゼロを確認し決定どおり削除。
`tab_skill_search.js`は28の議論に委ね現状維持。全643テスト無修正で通過、preview実機確認済み。

### ~~33_Utils_Module_Split_Plan.md~~ → 実装完了・削除済み（正本: `B01_Skill_Logic_Core.md` 追補）

`apply_buff`（約370行、buff_id別分岐の塊）と付随ヘルパ3つを `manager/buff_apply.py` へ移設。
utils.pyは1510→1105行、`LEGACY_FILE_CEILINGS`から削除済み。循環回避はbuff_apply側から
manager.utilsを遅延importする方式（既存流儀と一致）。出身系グループ（`test_origin_bonuses.py`
がmonkeypatch依存）はスコープ外として明確に確認済み、Phase 2（スタック資源移設）も
目的達成に不要と判断し実施しなかった。全既存テスト無修正で通過（643 passed, 2 skipped）。

### ~~34_Common_Routes_Split_Plan.md~~ → 実装完了・削除済み（正本: `B03_SelectResolve_Spec.md` 追補）

リダイレクト系実体（`clear_redirect_state`/`append_redirect_record`/`cancel_redirect_by_no_redirect`/
`try_apply_redirect`/`recalculate_redirect_state`、約180行）を`events/battle/redirect_flow.py`へ
phase_flow型（依存を関数注入）で抽出。common_routes.py側は`_recalculate_redirect_state`等
3関数をテスト契約維持のため元シグネチャのまま薄いラッパーとして残した。

§7の「未登録ハンドラ2本」論点で**想定外の既存バグを発見**: `on_request_switch_battle_mode`
（PvE/PvP切替）と`on_request_ai_suggest_skill`（AIスキル提案）は死にコードではなく、
現行ビジュアルUI（visual_ui.js/visual_panel.js）から実際にemitされる生きた機能だったが、
`@socketio.on(...)`デコレータが欠落しておりサーバー側が常に無反応だった。デコレータを追加して
修復し、回帰テスト5件を追加（`tests/test_switch_mode_and_ai_suggest_routes.py`）。

common_routes.py 1533→1380行。29・33・34完了により`LEGACY_FILE_CEILINGS`が空になった
（モジュールサイズガードの例外ゼロ）。全648テスト無修正で通過。

### 24_TokenFrame_Image_Design_Plan.md（キャラ駒枠画像）

設計確定済み（JS/CSS実装方針・座標仕様・生成AIプロンプト例まで記載済み）。
**ボトルネックは画像アセットの用意**（`ally_frame.png` / `enemy_frame.png`、160×160px、
中央116×116px透過）。画像が揃えばPhase1〜4はすぐ着手可能。

---

## 次に着手するなら

1. **すぐ実装できる（設計議論不要〜最小）**: 13（気合い）、24（画像用意後）
2. **一問一答から始める**: 28（プレイ体験改善）、30（シミュレータ）、35（ホロウダンジョン §10）
3. **戦闘メモリ設計が要る**: 12（逆襲）
4. 31・32・33・34は実装完了。残る計画書は04・12・13・16・24・28・30・35の8本。
