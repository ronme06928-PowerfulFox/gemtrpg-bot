# 00 残タスク一覧（planned/ ダイジェスト）

**作成日**: 2026-07-07（最終更新: 2026-07-08 — 計画30/31/32/33/34を追加。31・33は実装完了・削除済み。未計画項目ゼロ）
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
- `tests/test_python_module_size_guard.py` の `LEGACY_FILE_CEILINGS` に残る行数超過ファイルは1つ:
  - `events/battle/common_routes.py`（1531行）→ **計画書34** で計画済み
  → 34を完了すれば例外リストが空になる。

---

## タスク早見表

| 元計画 | タスク | 優先度感 | ひとことメモ |
|---|---|---|---|
| 28 | P0-2 サーバーサイドダイスロール | 高 | `/roll` `/sroll` の改竄可能性を解消。最も基本的な信頼性課題 |
| 28 | P0-3 保存信頼性の強化 | 高 | デバウンス保存の失敗リトライ＋節目フラッシュ |
| 28 | P0-1 セッションログのエクスポート/検索 | 高 | 500件切り捨て問題の実害緩和 |
| 04 | アイテム在庫不足の回帰テスト | 中 | 個数0での使用/没収の挙動確認テスト追加のみ |
| 28 | P1-1 手番・宣言待ち通知 | 中 | フロントのみで完結（タブタイトル点滅/Notification/SE） |
| 28 | P1-2 イニシアチブの手動調整 | 中 | GM限定でタイムライン並べ替え |
| 28 / 04 | P1-3 限定undo（操作履歴） | 中 | 04の「GM操作ログ見える化」と統合判断が必要（§7参照） |
| 28 | P2-1 キーボードショートカット | 低〜中 | フロントのみ |
| 28 | P2-2 ダークモード | 低〜中 | CSS変数化が前提 |
| 28 | P2-3 スキル検索の復活/削除 | 低 | 死にコード`tab_skill_search.js`の扱いを決める二択 |
| 28 | P2-4 aria-label 対応 | 低 | ドックアイコン中心 |
| 28 | P3 大型テーマ（観戦ロール/並行戦闘/シナリオ管理/BGM/VTT拡張） | 未定 | 着手判断のみ。個別計画は未作成 |
| 28 | 技術的負債整理（死にコード・残骸ファイル削除） | 低 | 単独PRで随時可 |
| 12 | 逆襲: 被ダメターン限定の与ダメ増加 | 未着手 | 加害者反応（被弾反応パッシブ）は実装済み。残るのは戦闘メモリ方式 |
| 13 | 気合い（次攻撃1回2.5倍） | 未着手 | 基盤はあるが専用バフ`Bu-Charge`が未実装 |
| 16 | 増援機能 | 未着手 | データ構造のみ設計済み。UI・投入処理は全て未実装 |
| 24 | キャラ駒の枠画像デザイン | 未着手（画像待ち） | 設計確定済み。PNG画像の用意が最初のボトルネック |
| 30 | バランス検証シミュレータ | 中 | 実エンジンで低/中/高ロールの撃破ターンを自動検証。§7の一問一答が未実施 |
| 31 | ~~スキルデータlint・相場自動集計~~ | — | **実装完了・計画書削除済み**。正本は `C01_JSON_Definition_Master.md` §12 |
| 32 | 戦闘UI一本化（旧テキスト戦闘の廃止） | 中 | 移設2群（ログ入口/キャラJSON読込）が要注意。§7未実施。28のG16死にコード分を吸収 |
| 33 | ~~`manager/utils.py` 分割~~ | — | **実装完了・計画書削除済み**。正本は `B01_Skill_Logic_Core.md` 追補 |
| 34 | `events/battle/common_routes.py` 分割 | 低〜中 | リダイレクト系(約180行)をphase_flow型で抽出。intentハンドラ本体は隔離ロードテスト契約により移動不可 |

---

## 計画書ごとの詳細サマリ

### 28_TRPG_Play_Experience_Improvement_Plan.md（アプリ全体スキャン起点・議論前のたたき台）

P0〜P3の改善提案16項目（G1〜G16のギャップに対応）。**§7未決定事項が7件あり、実装前に一問一答での確定が必要**:
ログ長期保全方式 / undoの範囲 / サーバーダイス移行時の互換 / スキル検索の去就 /
ダークモードの粒度 / P3着手要否 / 04残課題との統合。

推奨実装順（Phase1〜5、独立度高い順）:
1. サーバーダイス → 保存信頼性 → ログエクスポート/検索
2. 手番通知 + キーボードショートカット（フロントのみ、並行可）
3. イニシアチブ手動調整 → 限定undo（§7方式決定が前提）
4. ダークモード / スキル検索 / aria
5. 負債整理（随時）

### 04_TRPG_Session_Improvement_Feasibility_Plan.md（残課題のみ）

大半は解消済み（GM操作系・認可回帰テスト・debug_apply_buffの露出管理）。
残るのは2件のみ:
- アイテム在庫不足の回帰テスト追加
- GM操作ログ見える化 → 28のP1-3と統合するか要判断

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

### 32_Battle_UI_Unification_Plan.md（戦闘UI一本化）

旧テキスト戦闘（3_battlefield.html＋tab_battlefield.js）を廃止。**ビジュアル画面が
旧ファイルに依存するのは2群のみ**（ログ入口 `logToBattleLog`＝visual_socketがwrapするので
ロード順注意／キャラJSON読込 `parseCharacterJsonToCharacterData`）。これを移設すれば
残りは削除可能。死にファイル3点＋no-opイベント（request_wide_match）の掃除も含む。
`tab_skill_search.js` の去就は28 P2-3の決定に従う。

### ~~33_Utils_Module_Split_Plan.md~~ → 実装完了・削除済み（正本: `B01_Skill_Logic_Core.md` 追補）

`apply_buff`（約370行、buff_id別分岐の塊）と付随ヘルパ3つを `manager/buff_apply.py` へ移設。
utils.pyは1510→1105行、`LEGACY_FILE_CEILINGS`から削除済み。循環回避はbuff_apply側から
manager.utilsを遅延importする方式（既存流儀と一致）。出身系グループ（`test_origin_bonuses.py`
がmonkeypatch依存）はスコープ外として明確に確認済み、Phase 2（スタック資源移設）も
目的達成に不要と判断し実施しなかった。全既存テスト無修正で通過（643 passed, 2 skipped）。

### 34_Common_Routes_Split_Plan.md（events/battle/common_routes.py 分割）

1531行→目標1400前後。**intentハンドラ9本は importlib 隔離ロードテスト
（test_intent_authorization_routes.py 等）の契約により物理移動不可**。パッケージ内で確立済みの
phase_flow型（ctx注入＋薄いラッパを common_routes に残す）で、リダイレクト系実体（852-1031、
約180行）を `redirect_flow.py` へ抽出するのが第1手。32（UI一本化）を先にやると
wide宣言ハンドラ削除分だけ楽になる。33・34完了で LEGACY_FILE_CEILINGS が空になる。

### 24_TokenFrame_Image_Design_Plan.md（キャラ駒枠画像）

設計確定済み（JS/CSS実装方針・座標仕様・生成AIプロンプト例まで記載済み）。
**ボトルネックは画像アセットの用意**（`ally_frame.png` / `enemy_frame.png`、160×160px、
中央116×116px透過）。画像が揃えばPhase1〜4はすぐ着手可能。

---

## 次に着手するなら

1. **すぐ実装できる（設計議論不要〜最小）**: 13（気合い）、24（画像用意後）
2. **§7の一問一答から始める**: 28（プレイ体験改善）、30（シミュレータ）、32（UI一本化）、34（common_routes分割）
3. **戦闘メモリ設計が要る**: 12（逆襲）
4. **費用対効果順の私見**: 32 → 34（32の後が楽）→ 30
5. **実施順の依存**: 32 → 34 の順が有利（wide宣言ハンドラ削除分だけ34が軽くなる）
