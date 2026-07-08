# 34 events/battle/common_routes.py 分割計画

**作成日**: 2026-07-08（一問一答議論完了: 2026-07-08）
**位置づけ**: `events/battle/common_routes.py`（1531行、`LEGACY_FILE_CEILINGS` に1540でピン留め）を1500行制限内へ分割し、例外リストから外す計画。Socket.IO ハンドラモジュールのため、計画書29/33の「ファサード再export」ではなく、**このパッケージで既に確立している「ctx注入＋薄いラッパ」方式（phase_flow型）**を踏襲する。`planning_process.md` の一問一答による方針決定が完了し、実装着手可能な状態（未登録ハンドラ2本のバグ修正は調査中に発見・別途修復済み）。

---

## 1. 目的

- `events/battle/common_routes.py` を1500行未満にし、モジュールサイズガードの例外を最後の1件まで解消する（33と合わせて例外ゼロへ）。
- リダイレクト処理・コスト消費・認可などの実体ロジックをテーマ別サブモジュールへ移し、intent フローの見通しを改善する。
- **挙動変更は一切行わない**。既存テストは無修正で全通過が条件。

## 2. 現状分析（2026-07-08 調査）

### 2.1 登録の仕組み

- `app.py:171` の `import events.battle` → `events/battle/__init__.py` が `duel_routes` / `wide_routes` / `common_routes` を副作用importし、`@socketio.on` デコレータがモジュール読み込み時に登録される。明示的な register 関数は無い。
- **新サブモジュールを route ファイルにする場合は `__init__.py` へ import 追加が必要**。逆に、同一イベント名の `@socketio.on` を新旧2ファイルに残すと**二重登録・二重発火**する。

### 2.2 行数の偏り（計1531行）

| ブロック | 行スパン | 概算 | 備考 |
|---|---|---:|---|
| import・ローカルヘルパ・送受信ログ | 1-110 | 110 | `_require_in_room` / `_log_battle_recv` 等 |
| 進行・GM・モーダル・wide ハンドラ | 112-367 | 255 | 100行超なし |
| 委譲ラッパ群（既分割分） | 369-436, 600-780 | 210 | intent_targets / pve_intents / phase_flow への薄いラッパ |
| **mass コスト消費＋intent認可（実体）** | 438-599 | **160** | `_consume_mass_costs_on_resolve_start`(78) / `_authorize_intent_slot_control`(78) |
| **リダイレクト系（実体・最大の残ブロック）** | 852-1031 | **180** | `_try_apply_redirect`(75) / `_recalculate_redirect_state` ほか |
| intent フローハンドラ群 | 1032-1531 | 500 | `battle_intent_commit`(83) 等9本。**物理移動は不可**（§2.3） |

### 2.3 テスト契約（最重要制約）

- `tests/test_intent_authorization_routes.py` と `test_pve_enemy_target_fallback_routes.py` は **`importlib.util.spec_from_file_location` で common_routes.py 単体を隔離ロード**し、`getattr(routes, handler_name)` でハンドラを呼び、`_recalculate_redirect_state` / `_refresh_resolve_ready` / `_validate_and_normalize_target` / `evaluate_skill_access` 等を**モジュール属性として monkeypatch** する。
- → **intent ハンドラ本体と、テストが patch する全ヘルパ名は common_routes の名前空間に残す必要があり、ハンドラはそれらを module global 参照で呼び続ける必要がある**（ローカル束縛にすると patch が効かなくなる）。intent ハンドラの別ファイルへの物理移動は不可。
- 通常 import 系テスト（`test_battle_only_round_routes.py` / `test_socket_room_auth.py` / `test_grant_skill_system.py` / `test_target_scope_aliases.py`）も `on_request_end_round` / `_normalize_target_by_skill` 等を common_routes 属性として参照・patch する。

### 2.4 確立済みの分割パターン（手本）

このパッケージには既に3つのサブモジュール分割前例があり、いずれも「**サブモジュールは common_routes を import しない（循環なし）。依存は ctx dict / 関数引数で注入。common_routes 側に薄いラッパ名を残して monkeypatch 契約を維持**」という同型:

- `events/battle/phase_flow.py`（176行）— `_phase_flow_context()` が毎回 module globals から ctx を組み立てて渡す
- `events/battle/pve_intents.py`（237行）— `get_room_state_fn=` 等の関数注入
- `events/battle/intent_targets.py`（373行）— 呼び出し時に `all_skill_data` 等を同期してから委譲

### 2.5 その他の発見

- `on_request_switch_battle_mode`（:335）と `on_request_ai_suggest_skill`（:352）には **`@socketio.on` が付いていない**（このファイルからは未登録）。死にコードか別経路登録かの精査が必要（§7）。
- モジュールレベルの可変状態は `logger` のみ。共有キャッシュは無く、分割で状態管理を新設する必要はない。
- `request_declare_wide_skill_users` ハンドラは**計画書32（戦闘UI一本化）で削除候補**。32を先に実施すればその分も行数が減る。

## 3. 対象範囲

### 触るもの
- `events/battle/common_routes.py`（実体ロジックの抽出元。ラッパ名は残す）
- 新規: `events/battle/redirect_flow.py`（リダイレクト系の実体）
- 新規（必要時）: `events/battle/intent_costs.py` 等（mass コスト消費・認可の実体）
- 完了時: `tests/test_python_module_size_guard.py`（common_routes の ceiling 削除）

### 触らないもの（禁止事項）
- intent フローハンドラ9本の物理配置（common_routes に残す）
- テストが monkeypatch する全ヘルパの**名前と module global 参照経路**
- Socket.IO イベント名・ペイロード・emit 内容
- 既存サブモジュール（intent_targets / pve_intents / phase_flow）の構造
- `events/battle/__init__.py` の登録順序（新規 route ファイルを作らない限り変更不要）

## 4. 設計方針

- 現状約1533行（32のバグ修正で+2行）→ 目標は**マージン込みで1400行前後**。
- **リダイレクト系（852-1031、約180行）を `redirect_flow.py` へ**（phase_flow 型の ctx 注入）。コスト・認可の抽出は決定事項ログのとおり今回は行わない（§8）。
  - `_recalculate_redirect_state` は隔離ロードテストの patch 対象 → **薄いラッパ名を common_routes に残す**。
  - `_try_apply_redirect` / `_cancel_redirect_by_no_redirect` / `_append_redirect_record` / `_clear_redirect_state` は内部呼び出しのみで移動しやすいが、ハンドラから module global 参照されている場合はラッパを残す（実装時に参照元を確認）。
- リダイレクト系抽出で 1533−180+ラッパ数十行 ≈ 1380行前後となる見込み。
- サブモジュールは common_routes を import しない（依存注入で渡す）— 既存3例と同じ。

## 5. 実装段階

| Phase | 内容 | 完了条件 |
|---|---|---|
| 0 ✅ | ベースライン確認＋未登録ハンドラ2本の登録経路精査 | 完了。死にコードではなく既存バグと判明し修復済み（§8） |
| 1 | `redirect_flow.py` 新設、リダイレクト実体の移設＋ラッパ設置 | テスト無修正で全通過（特に隔離ロード系2テスト）、行数確認 |
| 2 | `LEGACY_FILE_CEILINGS` から common_routes を削除、B03へ構成追補、本計画書を削除 | サイズガード・全テスト・エンコーディングチェック通過 |

## 6. 推奨PR分割

1. Phase 0（バグ修正、実施済み）
2. Phase 1（リダイレクト移設）
3. Phase 2（サイズガード更新・ドキュメント）

## 7. 未決定事項

（2026-07-08 の一問一答議論により全て確定。§8 決定事項ログ参照）

## 8. 決定事項ログ

| 日付 | 論点 | 決定 | 根拠 |
|---|---|---|---|
| 2026-07-08 | 未登録ハンドラ2本 | **死にコードではなく既存バグと判明。`@socketio.on(...)`を追加して修復した**（削除しなかった） | 調査の結果、`request_switch_battle_mode`（visual_ui.js:707）と`request_ai_suggest_skill`（visual_panel.js:479）は現行ビジュアルUIから実際にemitされている生きた機能だが、デコレータ欠落でサーバー側が無反応になっていた。回帰テスト5件を追加（`tests/test_switch_mode_and_ai_suggest_routes.py`）、pytest 648 passed で確認済み |
| 2026-07-08 | 抽出範囲 | **リダイレクト系のみ**（約180行を`redirect_flow.py`へ） | 目標達成に十分な余裕（1380行前後の見込み）。「小さく安全に検証できる変更」の原則を優先。コスト・認可の抽出は必要になった時点で第2弾として着手 |
| 2026-07-08 | 新モジュールの粒度 | **redirect_flow.py 1本のみ**（intent_costs.pyは今回作らない） | 抽出範囲をリダイレクト系のみに決めたことに伴い自動的に確定 |
| 2026-07-08 | ドキュメント追補先 | **B03（Select/Resolve確定仕様書）** | リダイレクト処理はSelect/Resolveのゲームルール仕様の一部（no_redirectタグ等と直接関連）。E01は画面・UI構造寄りのため不採用 |

## 9. 受け入れ条件

- `events/battle/common_routes.py` が1500行未満になり、`LEGACY_FILE_CEILINGS` から削除されている（**これで例外リストが空になる**）。
- 全既存テストが**無修正**で通過。特に:
  - `test_intent_authorization_routes.py` / `test_pve_enemy_target_fallback_routes.py`（importlib 隔離ロード＋ヘルパ monkeypatch）
  - `test_battle_only_round_routes.py` / `test_socket_room_auth.py`（通常 import＋属性 patch）
- Socket.IO イベントの登録一覧が分割前後で同一（二重登録・登録漏れなし）。
- 新設サブモジュールは common_routes を import しない（循環なし）。
- エンコーディング/文字化けチェック通過。
