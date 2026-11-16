# 計画65：戦闘専用ルームの廃止

作成日: 2026-11-16
状態: 方針決定済み。実装詳細まで記載。着手可（§8 の未決定事項は PR65-2 だけに関わる）。

## 1. 目的

使われていない戦闘専用ルーム（`play_mode == "battle_only"`）を、画面・サーバー・資料から取り除く。ルームは通常ルームだけにする。

- 自由に戦闘だけ遊びたい人は、通常ルームを作って自分が GM になればよい（2026-11-16 ユーザー）。
- 戦闘専用ルームは計画61のユニット管理・待機列より前に作られた経路で、下書き・すぐ始める窓・戦績などを独自に持つ。通常ルームには、待機列と登場（D01 Part 5）、戦闘突入・戦闘終結と戦績（A02 §2.2・§2.4）がそろった。
- ホロウダンジョン（計画35）は、戦闘専用ルームではなく通常ルームを土台に作り直す。GM なしで戦闘を進めるための特別扱いは、ここで一度消し、ホロウの「ホスト」の権限として作り直す（§3）。

## 2. 対象範囲

### 消すもの

| 区分 | 対象 |
|---|---|
| ルームの作成 | ルーム一覧の「戦闘専用ルーム作成」、`/create_room` の `play_mode`、ルーム札の「戦闘専用」 |
| Socket | `events/socket_battle_only.py`（907行、`request_bo_*` の全イベント） |
| 下書き・戦績 | `events/battle_only/catalog_state.py`（469行）、`manager/battle_only_record_state.py`（60行）、ルーム状態の `battle_only` の項目 |
| 配置 | `manager/preset_deployment.py` の戦闘専用の組み立て（`_battle_only_defaults`・`_validate_battle_only_candidate`・`_build_battle_only_candidate`、`target_mode` の分岐）、待機列の「下書きへ反映」 |
| 画面 | `static/js/modals/battle_only_draft_modal.js`・`battle_only_quick_start_modal.js`・`battle_only_participant_modal.js`（計2,152行）、`visual_ui.js` の戦闘専用パネル、`static/4_visual_battle.html` の「戦闘専用」ボタン |
| GM なしで進めるための特別扱い | §3 の8か所 |
| テスト | 戦闘専用だけを確かめるファイル（§5.5） |
| 資料 | D01 Part 2・Part 5 §3、A02 §2.6 ほか（§5.6） |

### 移すもの（消さない）

| 対象 | 移し先 | 理由 |
|---|---|---|
| 全滅による勝敗の判定（`resolve_auto_runtime._bo_estimate_battle_result`。`catalog_state._estimate_battle_result` は同じ処理の重複） | `manager/battle/battle_result.py` の `estimate_battle_result(state)`（1つにまとめる） | シミュレーター（F03）が使う。ホロウでも使う |
| 味方・敵の自動配置（`manager/battle_only_runtime.py` の `_bo_assign_auto_positions` 以下の位置計算） | `manager/sim/positions.py` | シミュレーターだけが使う |
| `events/battle_only/catalog_access_context.py` の `catalog_request_context` | `events/preset_deployment_access.py` | 通常ルームの待機列（`events/socket_preset_deployment.py`）が使う |

### 触らないもの

- 通常ルームの挙動（待機列と登場、戦闘突入・終結、戦績、R開始・R終了、PvE の切り替え、解決表示の進行役）。§3 の分岐を消しても、通常ルーム側の条件（GM 限定・所有者の確認）はそのまま残る。
- ユニット管理（ユニット・編成・ステージ）の項目と画面。ステージの味方編成は待機列の登場で使えるので残す。
- シミュレーター CLI の使い方と結果（F03）。
- 動画用に固めた解決パネルの写し（`typst_manual/動画/01_1ラウンドの流れ/components/resolve-panel/`・`out/`）。撮った時点の写しなので直さない。

## 3. GM なしで進めるための特別扱い（消す・ホロウで作り直す）

戦闘専用ルームでは、次の操作を GM でなくても行えた。消したあと、計画35でホロウの「ホスト（＋GM の代行）」の権限として作り直すときの参考に残す。コードは git の履歴（このPRの直前）から参照できる。

| # | 場所 | 戦闘専用での挙動 | 通常ルーム |
|---|---|---|---|
| 1 | `events/battle/common_routes.py` `on_request_end_round` | PL もラウンド終了できる。解決表示の再生中は終了させない | GM のみ |
| 2 | 同 `on_request_reset_battle` | PL もリセットできる | GM のみ |
| 3 | 同 解決開始（1266行付近） | PL も解決を開始できる | GM のみ |
| 4 | 同 `_get_battle_only_intent_control_policy` と宣言の権限（656行付近） | 宣言できる人を「全員が全キャラ分（`all`）」と「開始した人と GM（`starter_only`）」で切り替える | 所有者・GM |
| 5 | 同 `_start_resolve_presentation_for_request` と `events/battle/resolve_presentation_routes.py` | 解決表示の進行役は戦闘を始めた人。進行役が部屋にいなければ PL も引き継げる | Resolve を始めた GM。引き継ぎは GM のみ |
| 6 | `manager/battle/common_manager.py` `move_token_logic`、`events/socket_char.py` の移動・削除・駒の大きさ | 誰でも他人の駒を動かせる・消せる・大きさを変えられる | 所有者・GM |
| 7 | `manager/battle/resolve_auto_runtime.py` `_maybe_finalize_battle_only_result`・`_auto_reset_battle_only_field` | 全滅で勝敗を自動で決め、解決表示の後に盤面を自動でリセットする | GM が戦闘終結で結果を選ぶ |
| 8 | `manager/battle/resolve_auto_single_phase.py` `_try_auto_advance_battle_only_round`、`common_routes._complete_round_after_resolve` | 解決表示の後、ラウンド終了と次のラウンド開始を自動で行う | GM が R開始を押す |

## 4. 段階とPR

| PR | 内容 | 前提 |
|---|---|---|
| PR65-1 | サーバー・画面・テスト・仕様書（`manuals/implemented/` ほか、刊行物を除く）から戦闘専用ルームを消す。§2 の「移すもの」を移す | なし |
| PR65-2 | 刊行物（操作ガイド第1章・第7章と PDF、計画46の台帳）から戦闘専用ルームを外す | PR65-1。§8 の論点1 |

PR65-1 は1回で出す。サーバーだけ先に消すと、画面のボタンが反応しなくなるため。

## 5. 実装詳細（PR65-1）

AGENTS.md の順（資料 → テスト → 実装 → 不要コード・資料の確認）で進める。

### 5.1 ルームの種類を通常だけにする

- `routes/room.py` `create_room`：`play_mode` を受け取らない。新しいルームの状態は `play_mode: "normal"` 固定。`battle_only` の初期値を作らない。
- `manager/room_manager.py`：`_default_battle_only_state`・`_ensure_battle_only_defaults` を消す。ルーム状態を読むとき、`play_mode` を `"normal"` にし、`battle_only` の項目があれば消す（既存の戦闘専用ルームは通常ルームとして開ける。戦績は使われていないので捨てる）。
- `manager/data_manager.py`・`manager/room_access.py`：一覧の `play_mode` の判定と `battle_only_stage_id` を消す。一覧の札（`play_mode`）は返さなくてよい。
- 起動時の移行（`manager/db_migration.py` の既存の流れに足す）：保存済みの全ルームから `battle_only` の項目を消し、`play_mode` を `"normal"` にする。同じファイルの `_remap_room_drafts` の `battle_only` の付け替えは消す。

### 5.2 戦闘専用の経路を消す

- `app.py` の `import events.socket_battle_only` を消し、`events/socket_battle_only.py`・`events/battle_only/catalog_state.py`・`events/battle_only/__init__.py`・`manager/battle_only_record_state.py`・`manager/battle_only_runtime.py` を消す（§2 の「移すもの」を先に移す）。
- `manager/battle/common_manager.py`：`finalize_in_progress_records` の import と、`battle_only` の戦績を閉じる処理を消す。
- `manager/preset_deployment.py`：戦闘専用の組み立てを消す。`build_deployment_candidate`・`preview_deployment`・`apply_deployment` は通常ルームの組み立てだけにする。
- `events/socket_preset_deployment.py`：`_validate_target_mode` と `target_mode` を消す。import を `events/preset_deployment_access.py` に替える。
- `manager/units/repository.py` `room_references`：`battle_only` の下書きの参照の数え上げを消す（`references` の結果からルームの行がなくなる）。
- `manager/field_effects.py` `_extract_rules_from_state`：`battle_only` の項目を読まない。有効・無効はルーム状態の `stage_field_effect_profile` の有無だけで決める（通常ルームの挙動は変わらない。今も `battle_only` の項目は既定で有効）。
- `manager/battle/combat_session.py`・`events/battle/combat_session_routes.py`：`_is_battle_only` と、戦闘専用ルームを除外する分岐を消す。

### 5.3 §3 の特別扱いを消す

§3 の1〜8を消し、通常ルームの条件だけを残す。`common_routes.py`（1,471行）は分岐と `_is_battle_only_mode` 関数が消えるので短くなる。`_complete_round_after_resolve` は通常ルームの処理（`process_full_round_end` と保存）だけにする。

画面側：
- `static/js/main.js`：「戦闘専用ルーム作成」ボタン、`createRoomByMode` の戦闘専用の分岐、ルーム札の「戦闘専用」を消す。
- `static/js/visual/visual_ui.js`：戦闘専用パネルと `battle_only` の判定を消す。
- `static/js/visual/visual_controls.js`・`visual_combat_session.js`・`battle/components/ResolveFlowPanel.js`：`battle_only` の判定を消し、通常ルームの経路だけにする。
- `static/js/modals/preset_deployment_browser.js`：`battleOnly` の分岐（「下書きへ反映」、味方編成の置き換え、`request_bo_start_battle`）を消す。
- `static/4_visual_battle.html`：「戦闘専用」ボタンを消す。
- 3つのモーダルのファイルを消し、`scripts/build_frontend.mjs` の `CLASSIC_SCRIPTS` から外す。CSS に戦闘専用だけの規則があれば消す。
- `npm run build` を実行し、`static/dist/*` をコミットする。

### 5.4 シミュレーター

- `manager/sim/preset_loader.py`：ルーム状態を `play_mode: "normal"`・`battle_mode: "pve"` で作る。`battle_only` の項目（`simulator`・`selected_stage_id`・`field_effect_profile`）は使っているか確かめ、ステージの効果はルーム状態の `stage_field_effect_profile` に置く。自動配置は `manager/sim/positions.py` から呼ぶ。
- `manager/sim/battle_runner.py`：`resolve_auto_runtime._bo_estimate_battle_result` を `manager/battle/battle_result.estimate_battle_result` に替える。
- `tests/sim/test_simulate_battle.py` が同じ結果で通ること（乱数の種を固定した試合の結果を変えない）。

### 5.5 テスト

| 扱い | ファイル |
|---|---|
| 消す | `test_battle_only_catalog.py`、`test_battle_only_room_bootstrap.py`、`test_battle_only_round_routes.py`、`test_battle_only_auto_result.py`、`test_battle_only_frontend_flow_contract.py` |
| 戦闘専用の場合を消し、通常ルームの場合を残す | `test_preset_deployment.py`、`test_preset_deployment_socket.py`、`test_reset_summon_cleanup.py`、`test_resolve_presentation.py`、`test_units.py`、`test_unit_workspace.py`、`test_socket_room_auth.py`、`test_token_move_differential.py`、`test_select_resolve_smoke.py`、`test_combat_session_room_create.py`、`test_combat_session_phase0.py`、`test_combat_session_frontend.py`、`test_stage_field_effects_runtime.py`、`test_reflect_radiance_results.py`、`test_persistence_process_recovery.py`、`test_immediate_round_limit.py`、`tests/e2e/test_room_preset_apply_e2e.py`、`tests/sim/test_simulate_battle.py` |
| 足す | ルームの作成で `play_mode` を送っても通常ルームになる。`battle_only` の項目と `play_mode: "battle_only"` を持つ保存済みのルームが、読み込みと起動時の移行で通常ルームになる。§3 の1〜3・6が、PL では拒否される（通常ルームの既存のテストで足りていれば足さない）。`estimate_battle_result` の4つの結果 |

全件テストの後、`grep -rnE "battle_only|request_bo_|_bo_" --include=*.py --include=*.js .`（`tests`・`static/dist`・`.venv`・`typst_manual`・`.claude` を除く）で残りがないことを確かめる。

### 5.6 資料（刊行物を除く）

| 文書 | 直すこと |
|---|---|
| `implemented/D01_Play_Mode_Specs.md` | Part 2 を消す。Part 5 §3 を消す。Part 7 を通常ルームだけの記述にする。本書の構成の表を直す |
| `implemented/A02_GM_Creator_Manual.md` | §2.6 を消し、ルーム作成・権限の表・トラブルの表の戦闘専用の記述を消す |
| `implemented/A01_Player_Manual.md` | 付録A「共有された戦闘専用プリセット」が今も正しいか確かめ、戦闘専用ルームの記述を消す |
| `implemented/E02_UI_Component_Specs.md` | Part 11 §1・§6 の戦闘専用の記述を消す |
| `implemented/B03_SelectResolve_Spec.md`・`E01_Visual_Battle_Architecture.md`・`B01_Skill_Logic_Core.md`・`C01_JSON_Definition_Master.md`・`F01_Operations_Manual.md` | 戦闘専用ルームとの比較の記述を通常ルームだけにする |
| `implemented/F03_Battle_Balance_Simulator_CLI.md` | 共有する部品を `manager/sim/positions.py`・`manager/battle/battle_result.py` に直す |
| `START_HERE.md`・`README.md` | 戦闘専用の案内を消す |
| `projects/app_foundation/` の `backlog.md`・`repository_inventory.md`・`repository_structure.md`・`repository_release.md`・`ui/ui_foundation_plan.md`、`projects/master_database/README.md`、`module_size_policy.md` | 戦闘専用ルームの記述を消すか、廃止済みと書く |
| `planned/12`・`16`・`45`・`60` | 戦闘専用ルームを前提にした記述を通常ルームに直す |
| `planned/35_Hollow_Dungeon_Plan.md` | 計画35の書き直し（別作業）で扱う。ここでは触らない |
| `ui_design_decision_log.md` | 過去の決定の記録なので本文は直さない。末尾に「計画65で戦闘専用ルームを廃止」と1行足す |
| `planned/00_Open_Tasks_Digest.md` | 計画65の行を足し、完了時に更新する |

## 6. 実装詳細（PR65-2）

- `typst_manual/操作ガイド/01_始める前に.typ`（2か所）と `07_GM_当日を進める.typ`（4か所）から戦闘専用ルームの記述を消し、PDF を作り直す。
- `planned/46_Publication_Source_Inventory.md`・`46_Manual_Restructuring_Plan.md`・`46_Publication_Execution_Plan.md` の戦闘専用の項目を、廃止済みとして閉じる。
- 計画46の作業中の変更と重ならないよう、計画46の流れの中で行う。

## 7. 決定事項ログ

| 日付 | 論点 | 決定 | 根拠 |
|---|---|---|---|
| 2026-11-16 | 戦闘専用ルームの扱い | **廃止する。ルームは通常ルームだけにする** | 使われていない。戦闘だけ遊びたい人は通常ルームを作って GM になればよい（ユーザー） |
| 2026-11-16 | 廃止の時期 | **ホロウを待たずに今消す** | 使われていないので、GM なしで戦える部屋が一時的になくなっても困らない（ユーザー） |
| 2026-11-16 | GM なしで進めるための特別扱い | **一緒に消す。計画35でホストの権限として作り直す。消す前の挙動は§3に残す** | 使う部屋がない処理を残すと、誰も通らないコードになる |
| 2026-11-16 | 全滅の判定・自動配置 | **全滅の判定は `manager/battle/battle_result.py`、自動配置は `manager/sim/positions.py` へ移して残す** | シミュレーターが使う。全滅の判定はホロウでも使う |
| 2026-11-16 | 既存の戦闘専用ルーム | **通常ルームとして開けるようにし、`battle_only` の項目と戦績は捨てる** | 使われていない。後方互換は持たない（AGENTS.md） |

## 8. 未決定事項

| # | 論点 | 影響 |
|---|---|---|
| 1 | 刊行物（操作ガイド）を直す時期。刊行の前に PR65-2 を入れるか、刊行後の改訂にするか | PR65-2 の時期だけ。PR65-1 には関わらない |

## 9. 受け入れ条件

1. ルーム一覧に「戦闘専用ルーム作成」がなく、作れるルームは通常ルームだけ。
2. `play_mode: "battle_only"` と `battle_only` の項目を持つ保存済みのルームが、起動後に通常ルームとして開け、待機列・登場・戦闘突入・終結が動く。
3. 通常ルームの §3 の操作の権限が、PR の前と変わらない（PL はラウンド終了・リセット・解決の開始・他人の駒の操作ができない）。
4. シミュレーターのテストが同じ結果で通る。
5. `pytest -q` が全件通る。`npm run build` の成果物がコミットされている。
6. コードに `battle_only`・`request_bo_`・`_bo_` が残っていない（§5.5 の確認）。
7. `manuals/implemented/` ほか（刊行物を除く）に、戦闘専用ルームを今ある機能として書いた記述が残っていない。
