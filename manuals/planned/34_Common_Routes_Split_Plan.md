# 34 events/battle/common_routes.py 分割計画

**作成日**: 2026-07-08
**位置づけ**: `events/battle/common_routes.py`（1531行、`LEGACY_FILE_CEILINGS` に1540でピン留め）を1500行制限内へ分割し、例外リストから外す計画。Socket.IO ハンドラモジュールのため、計画書29/33の「ファサード再export」ではなく、**このパッケージで既に確立している「ctx注入＋薄いラッパ」方式（phase_flow型）**を踏襲する。議論前のたたき台。

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

- 現状1531行 → 目標は**マージン込みで1400行前後**（最低32行の削減では再超過しやすい）。
- **第1手: リダイレクト系（852-1031、約180行）を `redirect_flow.py` へ**（phase_flow 型の ctx 注入）。
  - `_recalculate_redirect_state` は隔離ロードテストの patch 対象 → **薄いラッパ名を common_routes に残す**。
  - `_try_apply_redirect` / `_cancel_redirect_by_no_redirect` / `_append_redirect_record` / `_clear_redirect_state` は内部呼び出しのみで移動しやすいが、ハンドラから module global 参照されている場合はラッパを残す（実装時に参照元を確認）。
- **第2手（必要時）: mass コスト消費＋認可（438-599、約160行）を実体移設**。`_consume_mass_costs_on_resolve_start` / `_authorize_intent_slot_control` ともラッパ名を残す。
- 第1手だけで 1531−180+ラッパ数十行 ≈ 1380行前後となる見込み。第2手は行数推移を見て判断。
- サブモジュールは common_routes を import しない（依存注入で渡す）— 既存3例と同じ。

## 5. 実装段階

| Phase | 内容 | 完了条件 |
|---|---|---|
| 0 | ベースライン確認（`pytest -q` 全通過）＋未登録ハンドラ2本の登録経路精査 | 精査結果を §8 決定事項ログへ記録 |
| 1 | `redirect_flow.py` 新設、リダイレクト実体の移設＋ラッパ設置 | テスト無修正で全通過（特に隔離ロード系2テスト）、行数確認 |
| 2（必要時） | mass コスト消費・認可の実体移設 | 同上、common_routes が1500行未満（目標1400前後） |
| 3 | `LEGACY_FILE_CEILINGS` から common_routes を削除、構成追補（B03 or E01 系）、本計画書を削除 | サイズガード・全テスト・エンコーディングチェック通過 |

## 6. 推奨PR分割

1. Phase 0＋1（リダイレクト移設）
2. Phase 2（コスト・認可移設、必要時）
3. Phase 3（サイズガード更新・ドキュメント）

※ 計画書32（UI一本化）Phase 4 が `request_declare_wide_skill_users` ハンドラを削除する場合、着手順によっては行数前提が変わる。**32→34 の順で実施するなら Phase 2 が不要になる可能性がある**。

## 7. 未決定事項

| 論点 | 選択肢 | 備考 |
|---|---|---|
| 抽出範囲 | (1) リダイレクトのみ / (2) リダイレクト＋コスト・認可 | (1)でも1500は下回るがマージンが薄め。行数実測で判断 |
| 32との実施順 | 32が先（wide宣言ハンドラ削除後に34） / 34が先 | 32が先なら34の作業量が減る |
| 未登録ハンドラ2本 | 死にコードとして削除 / 別経路登録を確認して維持 | `on_request_switch_battle_mode` は探索モード切替（socket_exploration側に類似イベントあり）の可能性。要精査 |
| 新モジュールの粒度 | redirect_flow.py 1本 / intent_costs.py も分ける | 既存3サブモジュールの粒度（170〜370行）に合わせる |
| ドキュメント追補先 | B03（Select/Resolve仕様） / E01（アーキテクチャ） | イベント層の構成図をどちらに置くか |

## 8. 決定事項ログ

（一問一答の議論後に追記する）

| 日付 | 論点 | 決定 | 根拠 |
|---|---|---|---|
| | | | |

## 9. 受け入れ条件

- `events/battle/common_routes.py` が1500行未満になり、`LEGACY_FILE_CEILINGS` から削除されている（**これで例外リストが空になる**）。
- 全既存テストが**無修正**で通過。特に:
  - `test_intent_authorization_routes.py` / `test_pve_enemy_target_fallback_routes.py`（importlib 隔離ロード＋ヘルパ monkeypatch）
  - `test_battle_only_round_routes.py` / `test_socket_room_auth.py`（通常 import＋属性 patch）
- Socket.IO イベントの登録一覧が分割前後で同一（二重登録・登録漏れなし）。
- 新設サブモジュールは common_routes を import しない（循環なし）。
- エンコーディング/文字化けチェック通過。
