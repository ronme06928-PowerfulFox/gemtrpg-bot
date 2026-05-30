# 25 アプリ改善 実装マニュアル

**更新日**: 2026-05-20  
**種別**: planned  
**対象**: 現行アプリ実装の安定化、権限強化、戦闘ルール修正、テスト基盤整備、保守性改善

---

## 1. 目的

本書は、現行アプリ精査で見つかった改善点を、実装時に追跡しやすい作業単位へ分解した実装マニュアルである。

各改善項目には特別番号を付与し、issue、ブランチ名、コミット、PR、テスト名で参照できるようにする。

---

## 2. 特別番号ルール

形式:

```text
IMP-25-P{優先度}-{領域}-{連番}
```

例:

```text
IMP-25-P0-RULE-001
```

優先度:

| 優先度 | 意味 |
|---|---|
| `P0` | 先に直さないと安全性・主要機能・テスト信頼性に影響する |
| `P1` | 次に直すべき保守性・運用安定性の課題 |
| `P2` | 中期的に品質を上げる改善 |

領域:

| 領域 | 対象 |
|---|---|
| `AUTH` | 認証、権限、CORS、セッション |
| `SEC` | XSS、アップロード、安全なDOM描画 |
| `RULE` | 戦闘ルール、スキル判定、Select/Resolve |
| `TEST` | pytest、e2e、テスト順序依存 |
| `ARCH` | モジュール分割、起動構造、依存整理 |
| `FE` | フロントエンド状態管理、Socket.IO、UI構造 |
| `DATA` | DBモデル、画像API、データ整合性 |

---

## 3. 実装フェーズ

### Phase 0: 主要不具合と安全性の固定

目的: 戦闘ルールの明確な不具合、GM権限、XSSを先に潰す。

#### IMP-25-P0-RULE-001: スキル分類の日本語キー対応

**対象**

- `manager/battle/skill_rules.py`
- `manager/battle/resolve_match_runtime.py`
- `manager/battle/fp_summary.py`
- `tests/test_non_damage_skill.py`
- `tests/test_skill_target_tags.py`

**現状**

`_resolve_skill_category()` が `category` 中心の判定になっており、JSON定義側の `分類: 回避`、`分類: 防御` を攻撃扱いにするケースがある。

**実装内容**

- `分類`、`カテゴリ`、`category`、`type` を同一の分類入力として扱う。
- 競合時の優先順位は `分類` > `カテゴリ` > `category` > `type` とする。
- `回避`、`防御`、`攻撃`、`補助` を role 判定へ正規化する。
- 防御・回避スキルが非ダメージ処理になることを保証する。
- 防御・回避が攻撃に勝利した場合のFP付与条件を再確認する。

**受け入れ条件**

- `pytest -q tests/test_non_damage_skill.py`
- `pytest -q tests/test_skill_target_tags.py`
- 防御・回避スキルで一方的にHPが減らない。
- clash win FP が防御・回避側勝利で期待どおり付与される。

#### IMP-25-P0-RULE-002: 日本語ターゲットタグの範囲推定対応

**対象**

- `manager/battle/skill_rules.py`
- `tests/test_select_resolve_smoke.py`

**現状**

`同陣営指定` タグが ally target として推定されず、味方対象ペアが敵対解決や clash 形成に流れる可能性がある。

**実装内容**

- `同陣営指定`、`味方指定` を ally scope として扱う。
- `敵指定`、`敵陣営指定` が必要な場合は enemy scope として明示する。
- 既存の英語タグ `ally_target`、`enemy_target` との互換性を維持する。
- 日本語タグと英語タグが競合した場合は、日本語タグを優先する。

**受け入れ条件**

- `pytest -q tests/test_select_resolve_smoke.py::test_case30c_ally_target_pair_does_not_form_clash`
- 味方対象スキルが clash を形成しない。

#### IMP-25-P0-AUTH-001: GM権限を自己申告から切り離す

**対象**

- `app.py`
- `events/socket_main.py`
- `events/battle/common_routes.py`
- GM専用API、GM専用Socketイベント

**現状**

クライアントが `attribute=GM` を送るだけでGM扱いになり得る。GM限定操作の前提として弱い。

**実装内容**

- ルーム作成時に、GMが `4桁数字` のGM PINを手入力する。
- 入室時は `プレイヤーとして入室` / `GMとして入室` を選択する。
- GMとして入室する場合のみ、GM PIN入力欄を表示する。
- 入力値がルームのGM PIN、または環境変数 `GM_MASTER_KEY` の `8桁数字` と一致した場合だけGM入室を許可する。
- `GM_MASTER_KEY` が未設定の場合、マスターキー機能は無効にする。
- GM PINは平文保存せず、`Room.gm_pin_hash` のようなハッシュ列へ保存する。
- PIN照合には `werkzeug.security.check_password_hash()` を使う。
- マスターキー照合には `secrets.compare_digest()` を使う。
- 既存の「自分でGM/ユーザー属性を選ぶ」ロビー機能は廃止対象にする。
- PIN不一致時はプレイヤー入室へフォールバックせず、明示的にエラーにする。
- `request_update_user_info` で一般ユーザーがGMへ昇格できないようにする。
- GM専用イベントは共通ヘルパーで `is_current_user_gm(room_name)` を通す。
- `debug_apply_buff` など状態変更イベントにもGM権限チェックを追加する。
- クライアントから送られた `attribute=GM` は信用せず、サーバー側の照合結果だけで `session['attribute'] = 'GM'` を設定する。
- ロビー上のユーザー管理は誰でも開ける。ユーザー一覧/詳細は閲覧可能にし、削除/譲渡などの破壊的操作は別途権限を要求する。
- ユーザー管理の操作権限は、ルームGM権限とは別のアプリ管理権限として扱う。
- ユーザー管理の削除/譲渡は、アプリ管理権限を持つユーザー、またはその場で8桁マスターキーを入力した操作だけ許可する。
- マスターキー入力により、特定ユーザーへアプリ管理権限を半永続的に付与/解除できるようにする。
- ルームからロビーへ戻る際は、ルームGM状態を解除し、ロビー上ではプレイヤー状態に戻す。
- ルーム一覧の削除ボタンは全員に表示する。ただし削除実行時には、そのルームの4桁GM PINまたは8桁マスターキーを必須にする。

**受け入れ条件**

- 非GMユーザーがクライアント改変だけでGM操作を実行できない。
- 既存のGM操作は、正規のGM入室手順では引き続き動く。
- ルーム作成時、4桁数字以外のGM PINは拒否される。
- GM入室時、ルームGM PIN一致または `GM_MASTER_KEY` 一致でのみGMになる。
- `GM_MASTER_KEY` は8桁数字以外なら無効扱い、または起動時警告にする。
- ロビーでは、プレイヤー状態でもユーザー管理を開ける。
- ルームGMとして入室後にロビーへ戻っても、ユーザー管理の削除/譲渡はアプリ管理権限またはマスターキーなしでは実行できない。
- マスターキーで指定ユーザーへアプリ管理権限を付与/解除できる。
- ルーム削除は、セッション属性やオーナー状態だけでは成功せず、GM PINまたはマスターキー一致を必要とする。
- GM権限チェックの単体テスト、またはSocketイベントテストを追加する。

#### IMP-25-P0-AUTH-002: SECRET_KEYとCORS設定の環境変数化

**対象**

- `app.py`
- `RENDER_SETUP.md`
- `.env.example` が存在する場合は同ファイル

**現状**

`SECRET_KEY` が固定値で、Socket.IO CORS が `*` になっている。

**実装内容**

- `SECRET_KEY` は環境変数から読む。
- 本番環境で未設定なら起動失敗させる。
- `CORS_ORIGINS` を環境変数で指定できるようにする。
- `CORS_ORIGINS` が未設定の場合は、ローカル開発時のみ `localhost` / `127.0.0.1` 系を許可する。
- 本番環境では `SECRET_KEY` と `CORS_ORIGINS` を必須にする。
- ローカル開発時のみ、未設定の `SECRET_KEY` に開発用値を使える。

**受け入れ条件**

- 本番相当設定で固定 `SECRET_KEY` が使われない。
- 許可していないOriginからのSocket接続が拒否される。

#### IMP-25-P0-SEC-001: チャット/ログのXSS対策

**対象**

- `events/socket_main.py`
- `manager/room_manager.py`
- `static/js/tab_battlefield.js`
- `static/js/visual/visual_ui.js`
- その他 `innerHTML` でユーザー入力を描画する箇所

**現状**

チャット本文、ユーザー名、エラーメッセージなどが `innerHTML` に入る箇所がある。

**実装内容**

- チャット本文とユーザー名は `textContent` で描画する。
- 装飾が必要なログは、テキストノードと要素生成で組み立てる。
- ユーザー入力のチャット本文にはHTML装飾を許可しない。
- システムログの装飾は、アプリ側で生成したDOM構造だけに限定する。
- 戦闘ログとVisualログは、システムログのみ `<br>`, `<strong>`, `<b>` と安全なHTML実体参照を限定復元する。
- チャット本文は引き続き完全テキスト表示にする。

**実装状況**

- 2026-05-26: `static/js/tab_battlefield.js` と `static/js/visual/visual_ui.js` で、システムログの限定リッチ表示と `-&gt;` 表示崩れの復元を実装済み。

**受け入れ条件**

- `<img onerror=...>` や `<script>` をチャット投稿しても実行されない。
- 通常ログの表示崩れがない。

---

### Phase 1: テスト基盤の信頼性回復

目的: 変更前後の安全確認を機械的にできる状態へ戻す。

#### IMP-25-P1-TEST-001: モジュールサイズガードの対象整理

**対象**

- `tests/test_python_module_size_guard.py`
- `.gitignore`
- `manuals/module_size_policy.md`

**現状**

未追跡の `.claude/worktrees` がサイズガード対象に入り、実体コード以外で失敗する。また複数の現行ファイルが既存上限を超過している。

**実装内容**

- `.claude/` をテスト対象外、かつ必要なら `.gitignore` 対象にする。
- 既存巨大ファイルの上限を現状値へ追認するか、分割タスクへ接続する。
- 新規コードは `1500` 行制限を維持する。

**受け入れ条件**

- `pytest -q tests/test_python_module_size_guard.py`
- サイズ上限の例外がマニュアルとテストで一致している。

#### IMP-25-P1-TEST-002: e2eテストの通常pytest混入防止

**対象**

- `tests/e2e/test_browser.py`
- `pytest.ini`

**現状**

通常の `pytest` でブラウザe2eが走り、ChromeDriver取得のネットワーク失敗で落ちる。

**実装内容**

- `test_browser.py` に `pytest.mark.e2e` 相当のゲートを追加する。
- 通常の `pytest` ではe2eを実行しない。
- `RUN_E2E=1` など明示時のみ、手動確認に近い低頻度テストとして実行する。
- ChromeDriverの自動ダウンロードは通常テスト経路から排除する。
- WebDriverは既存ローカルドライバ、または利用者が事前に用意したブラウザ環境を優先する。
- UIセレクタが現行画面と合っているか確認する。

**受け入れ条件**

- 通常の `pytest` でe2eが走らない。
- `RUN_E2E=1` 指定時のみブラウザテストが実行される。

#### IMP-25-P1-TEST-003: テスト順序依存の切り分け

**対象**

- `tests/test_apply_buff_per_n.py`
- `tests/test_condition_status_stack_sum.py`
- `tests/test_pb10_preview.py`
- 関連する fixture、グローバルキャッシュ、モンキーパッチ

**現状**

個別実行では通るが、フルスイートで失敗するテストがある。共有状態、キャッシュ、monkeypatchの戻し漏れが疑わしい。

**実装内容**

- 失敗テストを `pytest-randomly` 相当の順序変更で再現する。
- グローバル辞書、キャッシュ、設定値、Skillデータの初期化fixtureを明示する。
- monkeypatch対象をテスト単位で閉じる。

**受け入れ条件**

- `pytest -q --ignore=.claude`
- 同一テストを順序変更しても結果が変わらない。

---

### Phase 2: アーキテクチャと保守性の改善

目的: 今後の機能追加で巨大ファイルへ追記し続けない構造にする。

#### IMP-25-P1-ARCH-001: 戦闘Socketルートの分割

**対象**

- `events/socket_battle_only.py`
- `events/battle/common_routes.py`
- `events/battle/`

**現状**

Socketイベント、権限、入力正規化、戦闘状態更新が大きなファイルに集中している。

**実装内容**

- GM操作、プレイヤー宣言、デバッグ操作、状態同期を別モジュールへ分離する。
- 各イベントは入力検証、権限チェック、ドメイン処理呼び出しの順に揃える。
- 既存イベント名は維持し、外部互換性を壊さない。

**受け入れ条件**

- 既存Socketイベント名が変わらない。
- 分割後の各新規Pythonファイルが `1500` 行以下。
- 関連pytestが通る。

**実装状況**

- 2026-05-25: 完了。
- 主な分離先:
  - `events/battle/intent_targets.py`
  - `events/battle/pve_intents.py`
  - `events/battle/phase_flow.py`
  - `events/battle_only/catalog_state.py`
  - `events/battle_only/runtime_builders.py`
- `events/battle/common_routes.py` と `events/socket_battle_only.py` は `1500` 行以下に縮小済み。

#### IMP-25-P1-ARCH-002: `manager/game_logic.py` と `manager/utils.py` の責務分割

**対象**

- `manager/game_logic.py`
- `manager/utils.py`
- `manager/battle/`

**現状**

スキル効果、バフ、状態、ユーティリティが大きなファイルへ集まり、局所変更の影響範囲が読みづらい。

**実装内容**

- スキル効果処理、状態参照、バフ計算、表示用整形を分離候補にする。
- まず純粋関数に近い処理から移動する。
- 移動前後で import 経路を薄い互換レイヤーで保つ。

**受け入れ条件**

- 既存テストが通る。
- 旧importを使う既存コードが壊れない。
- 新規追加は分割後モジュール側へ行う。

**実装状況**

- 2026-05-26: 完了。
- 主な分離先:
  - `manager/battle/condition_eval.py`
  - `manager/battle/buff_power.py`
  - `manager/battle/skill_effect_helpers.py`
  - `manager/battle/power_preview.py`
  - `manager/battle/damage_multiplier.py`
  - `manager/battle/lifecycle_effects.py`
  - `manager/battle/dice_command.py`
- `manager/game_logic.py` と `manager/utils.py` はどちらも `1500` 行以下に縮小済み。
- `tests/test_python_module_size_guard.py` のレガシー例外は空になった。

#### IMP-25-P1-ARCH-003: Flask app factory 化

**調査状況**: 実装前調査済み（2026-05-31）

**実装状況**: 第5段階まで完了（2026-05-31）

**対象**

- `app.py`
- `manager/db_migration.py`
- テスト初期化コード
- `manager/data_manager.py`
- `scripts/check_schema.py`
- `scripts/migrate_visibility.py`
- `scripts/register_default_images.py`
- `Procfile`

**現状**

当初はimport時または起動時にDB作成、マイグレーション、初期データ読み込みが走っていた。2026-05-31時点で起動処理は `create_app()` / `run_startup_tasks()` / `wsgi.py` に分離済み。

詳細:

- `app.py` は `create_app()` でFlask appを生成する。
- `WhiteNoise`、`cloudinary.config()`、`CORS`、`Compress`、`db.init_app()`、`socketio.init_app()` は `init_extensions()` に集約済み。
- DB migration、`db.create_all()`、buff plugin discovery、初期データ読み込みは `run_startup_tasks()` に集約済み。
- Socketイベント登録は `register_socket_handlers()` に集約済み。
- HTTPルートは `register_http_routes()` に集約済みで、`@app.route` / `@app.after_request` 直書きは残っていない。
- Render/Gunicornは当初 `Procfile` で `app:app` を参照していたが、2026-05-31に `wsgi:app` へ切り替え済み。
- `manager/data_manager.py`、`scripts/check_schema.py`、`scripts/migrate_visibility.py`、`scripts/register_default_images.py` が `from app import app` に依存している。

問題:

- 通常の `from app import app` 互換は維持しているため、互換入口ではstartup副作用が残る。
- テストやWSGI入口では `GEMTRPG_SKIP_IMPORT_STARTUP` / `GEMTRPG_DISABLE_DEFAULT_APP` / `GEMTRPG_SKIP_WSGI_STARTUP` により副作用を抑制できる。
- `manager/data_manager.py` と一部 `scripts/*.py` の `from app import app` 依存は、追加の仕上げ候補として残っている。

**実装内容**

- `create_app(config=None)` を用意する。
- DB初期化とマイグレーションは明示的な起動手順へ分ける。
- テストはテスト用configでappを作る。
- `register_http_routes(app)` を用意し、HTTPルート登録をfactoryから呼べる形へ移す。
- `register_socket_handlers()` を用意し、Socketイベントモジュールimportを一箇所へ集約する。
- `run_startup_tasks(app)` を用意し、migration、`db.create_all()`、buff plugin discovery、キャッシュ/初期データ読み込みを明示的に実行する。
- 本番入口は段階的に `wsgi.py` へ移し、`Procfile` は最終的に `wsgi:app` を参照する。
- 既存スクリプトの `from app import app` は、必要に応じて `from app import create_app` または `from wsgi import app` へ置き換える。

推奨する段階移行:

1. **起動処理の関数化**
   - `configure_app(app, config=None)`、`init_extensions(app, cors_origins)`、`run_startup_tasks(app)` を作る。
   - この段階では `app = create_app(run_startup=True)` を残し、外部入口を壊さない。
   - 2026-05-31: 完了。`create_app(config=None, run_startup=True, register_sockets=True, register_routes=True)`、`configure_app()`、`init_extensions()`、`run_startup_tasks()`、`register_socket_handlers()` を追加済み。
   - 既存互換のため、通常起動では `app = create_app(...)` を維持し、import時startup副作用は本番互換として残している。
2. **HTTPルート登録の分離**
   - `@app.route` 直書きを `register_http_routes(app)` に寄せる。
   - ルート関数の中身は極力変更せず、登録形だけを変える。
   - 2026-05-31: 前半として静的配信系のみ着手。`/`、`/mobile`、`/<path:filename>`、`after_request` キャッシュヘッダを `register_http_routes(app)` 経由へ移した。
   - 2026-05-31: 中盤として軽いデータ取得GET APIを移行。`/get_skill`、`/api/get_skill_metadata`、`/api/get_skill_data`、`/api/get_item_data`、`/api/get_radiance_data`、`/api/get_passive_data`、`/api/get_buff_data`、`/api/get_glossary_data` を `register_http_routes(app)` 経由へ移した。
   - 2026-05-31: 後半として画像系APIを移行。`/api/upload_image`、`/api/images`、`/api/images/<image_id>`、`/api/local_images` を `register_http_routes(app)` 経由へ移した。
   - 2026-05-31: 認証/セッション系APIを移行。`/api/entry`、`/api/recover_user`、`/api/recover_from_local_token`、`/api/regenerate_recovery_code`、`/api/enter_room`、`/api/leave_room_context`、`/api/get_session_user` を `register_http_routes(app)` 経由へ移した。
   - 2026-05-31: ルーム系APIを移行。`/list_rooms`、`/load_room`、`/create_room`、`/delete_room`、`/save_room`、`/api/get_room_users` を `register_http_routes(app)` 経由へ移した。
   - 2026-05-31: 管理系APIと監査POSTを移行。`/api/admin/user_details`、`/api/admin/users`、`/api/admin/delete_user`、`/api/admin/transfer`、`/api/admin/set_user_management_admin`、`/api/json_nl_builder_audit` を `register_http_routes(app)` 経由へ移した。
   - 2026-05-31: 完了。`app.py` 内の `@app.route` / `@app.after_request` 直書きは残っていない。
3. **Socket登録の明示化**
   - `import events...` を `register_socket_handlers()` に移す。
   - 1プロセス1回だけ登録される前提を守る。
   - 2026-05-31: 第一段階として `register_socket_handlers()` に集約済み。イベント内部ロジックの整理は行っていない。
4. **テスト用factoryの導入**
   - `create_app(config={...}, run_startup=False, register_sockets=False)` のように、テストでDB初期化やSocket登録を抑制できる入口を用意する。
   - APIテストは `sqlite:///:memory:` を使う。
   - 2026-05-31: 完了。`create_app(..., run_startup=False, register_sockets=False)` でHTTPルート登録済みのFlask appを作れるようにした。
   - 2026-05-31: `register_routes` 引数を追加し、特殊な検証ではHTTPルート登録自体も切り替えられるようにした。
   - 2026-05-31: `get_local_images()` はグローバル `app.root_path` ではなく `current_app.root_path` を使うようにし、factoryで作った別appからも正しいrootを参照する。
   - 2026-05-31: テスト時は `GEMTRPG_SKIP_IMPORT_STARTUP=1` により、`from app import create_app` でDB migration/初期データ読み込みが走らないようにできる。通常の `from app import app` 互換は維持する。
   - 2026-05-31: `tests/test_app_factory.py` を追加し、startupなしfactoryでも主要HTTPルートと総ルート数34が維持されることを確認する。
5. **本番入口の切り替え**
   - `wsgi.py` に `app = create_app(run_startup=True, register_sockets=True)` を置く。
   - `Procfile` を `web: gunicorn -c gunicorn_config.py wsgi:app` へ変更する。
   - 2026-05-31: 完了。`wsgi.py` を追加し、`Procfile` を `wsgi:app` へ切り替えた。
   - 2026-05-31: `wsgi.py` は `GEMTRPG_DISABLE_DEFAULT_APP=1` を設定してから `create_app()` をimportし、互換用のグローバルapp作成を避ける。
   - 2026-05-31: 検証用に `GEMTRPG_SKIP_WSGI_STARTUP=1` を用意し、WSGI入口のルート登録をDB startupなしで確認できるようにした。本番では未設定のためstartupは実行される。

最初に触るべきファイル:

1. `app.py`: factory、設定、起動処理、HTTP登録の分離。
2. `wsgi.py`: 本番入口を新設。
3. `manager/data_manager.py`: `from app import app` の除去または遅延化。
4. `scripts/*.py`: `from app import app` 依存の置換。
5. `tests/`: factory利用のAPIテストを追加。

初回実装で避けること:

- HTTPルートの業務ロジックを同時に大きく書き換えない。
- Socketイベントの内部ロジックを同時に整理しない。
- DB migration方式をAlembic等へ一気に置き換えない。
- Procfile変更を、ローカル起動確認前に単独で先行しない。

**受け入れ条件**

- テストが不要な本番DBへ触れない。
- importだけでDB副作用が発生しない。
- Render/Gunicorn用の入口が明示され、既存の本番起動手順が保たれる。
- `python app.py` によるローカル起動が維持される。
- `create_app(..., run_startup=False)` でDB migrationや初期データ読み込みを抑制できる。
- Socketイベントが未登録または二重登録にならない。
- `pytest -q --ignore=.claude` が通る。

第一段階の確認結果:

- `python -m py_compile app.py`: OK
- `python -c "import app; print(len(app.app.url_map._rules))"`: 34 routes
- `pytest -q tests/test_image_visibility.py tests/test_image_upload_validation.py tests/test_room_model_defaults.py`: 11 passed
- `pytest -q --ignore=.claude`: 403 passed, 2 skipped

第二段階前半の確認結果:

- `python -m py_compile app.py`: OK
- `python -c "import app; print(len(app.app.url_map._rules))"`: 34 routes
- `pytest -q tests/test_image_visibility.py tests/test_image_upload_validation.py tests/test_room_model_defaults.py`: 11 passed
- `pytest -q --ignore=.claude`: 403 passed, 2 skipped

第二段階中盤の確認結果:

- `python -m py_compile app.py`: OK
- `python -c "import app; print(len(app.app.url_map._rules))"`: 34 routes
- `pytest -q tests/test_skill_catalog_smoke.py tests/test_image_visibility.py tests/test_image_upload_validation.py tests/test_room_model_defaults.py`: 16 passed
- `pytest -q --ignore=.claude`: 403 passed, 2 skipped

第二段階後半の確認結果:

- `python -m py_compile app.py`: OK
- `python -c "import app; print(len(app.app.url_map._rules))"`: 34 routes
- `pytest -q tests/test_image_visibility.py tests/test_image_upload_validation.py tests/test_room_model_defaults.py`: 11 passed
- `pytest -q --ignore=.claude`: 403 passed, 2 skipped

第二段階 認証/セッション系移行後の確認結果:

- `python -m py_compile app.py`: OK
- `python -c "import app; print(len(app.app.url_map._rules))"`: 34 routes
- `pytest -q tests/test_user_recovery.py tests/test_image_visibility.py tests/test_image_upload_validation.py tests/test_room_model_defaults.py`: 15 passed
- `pytest -q --ignore=.claude`: 403 passed, 2 skipped

第二段階 ルーム系移行後の確認結果:

- `python -m py_compile app.py`: OK
- `python -c "import app; print(len(app.app.url_map._rules))"`: 34 routes
- `pytest -q tests/test_battle_only_room_bootstrap.py tests/test_room_preset_apply.py tests/test_user_recovery.py tests/test_room_model_defaults.py`: 17 passed
- `pytest -q --ignore=.claude`: 403 passed, 2 skipped

第二段階完了後の確認結果:

- `rg -n "@app\\.route|@app\\.after_request" app.py`: no matches
- `python -m py_compile app.py`: OK
- `python -c "import app; print(len(app.app.url_map._rules))"`: 34 routes
- `pytest -q --ignore=.claude`: 403 passed, 2 skipped

第三段階 factoryテスト入口導入後の確認結果:

- `python -m py_compile app.py`: OK
- `python -c "import os; os.environ['GEMTRPG_SKIP_IMPORT_STARTUP']='1'; import app; print(len(app.app.url_map._rules))"`: 34 routes
- `pytest -q tests/test_app_factory.py tests/test_battle_multiplier_relation.py`: 4 passed
- `pytest -q tests/test_app_factory.py tests/test_user_recovery.py tests/test_image_visibility.py tests/test_image_upload_validation.py tests/test_room_model_defaults.py`: 16 passed
- `pytest -q --ignore=.claude`: 404 passed, 2 skipped
- `python scripts/check_text_encoding.py`: OK
- `python scripts/check_mojibake_markers.py`: OK

第五段階 本番入口切り替え後の確認結果:

- `python -m py_compile app.py wsgi.py`: OK
- `python -c "import os; os.environ['GEMTRPG_SKIP_WSGI_STARTUP']='1'; import wsgi; print(len(wsgi.app.url_map._rules))"`: 34 routes
- `python -c "import os; os.environ['GEMTRPG_SKIP_IMPORT_STARTUP']='1'; import app; print(app.app is not None, len(app.app.url_map._rules))"`: `True 34`
- `Procfile`: `web: gunicorn -c gunicorn_config.py wsgi:app`

#### IMP-25-P1-FE-001: フロント状態管理とSocket境界の一本化

**実装状況**: 着手中（2026-05-31）

**対象**

- `static/js/main.js`
- `static/js/battle/index.js`
- `static/js/battle/SocketClient.js`
- `static/js/battle/BattleStore.js`
- `static/js/visual/`

**現状**

`BattleStore`、`SocketClient`、`EventBus` がある一方で、従来の `window.*`、直接 `socket.on`、直接DOM更新が残っている。

**実装内容**

- 新規イベント購読は `SocketClient` 経由に限定する。
- 共有状態は `BattleStore` または明示したストアへ集約する。
- `window.*` 公開は互換用の最小セットに減らす。
- 旧ハンドラと新ハンドラの二重処理を棚卸しする。

段階移行:

1. **Socket購読境界の追加**
   - `SocketClient` に外部UI向けの購読APIを追加する。
   - 既存の直接 `socket.on` は、まずVisual Battle内の購読から `SocketClient` 経由へ寄せる。
   - 2026-05-31: 着手。`SocketClient.on()` / `SocketClient.off()` を追加した。
   - 2026-05-31: `visual_socket.js` に `registerSocketHandler()` を追加し、同ファイル内のイベント購読はこの境界経由へ置き換えた。`SocketClient` が利用できない初期化順では既存の `socket.on` にフォールバックする。
   - 2026-05-31: `main.js` に `registerAppSocketHandler()` を追加し、`state_updated`、`new_log`、`user_info_updated`、`user_list_updated` は `SocketClient.on()` 優先で購読するようにした。`connect` / `disconnect` はSocketIO初期化ライフサイクルのため直接購読を維持する。
2. **状態更新の重複棚卸し**
   - `state_updated`、`battle_state_updated`、`battle_phase_changed` など、Store更新と画面更新が重なりやすいイベントを一覧化する。
   - 画面更新だけを残す箇所と、Store更新へ寄せる箇所を分ける。
   - 2026-05-31: `SocketClient` がStore更新とEventBus発火を担当し、`visual_socket.js` は既存画面更新・ログ遅延制御・レガシー描画互換を担当する境界として整理を開始した。
   - 2026-05-31: `visual_socket.js` 内にあった2本目の `state_updated` 購読（ターン変更フラグ更新のみ）を主ハンドラへ統合し、重複購読を削除した。
   - 2026-05-31: `tab_battlefield.js` の `state_updated` と、戦闘専用参加者モーダルの一時購読を `SocketClient.on()` / `SocketClient.off()` 優先へ寄せた。
   - 2026-05-31: `state_updated` の直接購読は `SocketClient` 本体に限定した。`main.js`、`visual_socket.js`、`tab_battlefield.js`、`battle_only_participant_modal.js` は共通境界経由。
   - 2026-05-31: `skill_declaration_result`、プリセット系イベント、広域マッチ差分イベントも `SocketClient.on(..., { replace: true })` 優先へ寄せた。既存の `off -> on` による置換動作はフォールバックでも維持する。
3. **window公開の縮小**
   - 既存HTML/旧JSが参照している公開APIを確認し、互換が必要なものだけ残す。

**受け入れ条件**

- 同じSocketイベントに対する重複UI更新がない。
- 新規UIコードが直接 `window.socket` に依存しない。

第一段階 Socket購読境界追加後の確認結果:

- `node --check static/js/battle/core/SocketClient.js`: OK
- `node --check static/js/visual/visual_socket.js`: OK
- `node --check static/js/main.js`: OK
- `node --check static/js/tab_battlefield.js`: OK
- `node --check static/js/modals/battle_only_participant_modal.js`: OK
- `node --check static/js/modals.js`: OK
- `node --check static/js/wide_match_synced.js`: OK
- `node --check static/js/battle/index.js`: OK
- `node --check static/js/visual/visual_main.js`: OK
- `rg -n "socket\\.on\\(|socket\\.off\\(" static/js/visual/visual_socket.js`: `registerSocketHandler()` 内のフォールバックのみ
- `rg -n "socket\\.on\\('state_updated'|socketRef\\.on\\('state_updated'" static/js`: `SocketClient.js` の中核購読のみ
- `pytest -q --ignore=.claude`: 404 passed, 2 skipped
- `python scripts/check_text_encoding.py`: OK
- `python scripts/check_mojibake_markers.py`: OK

---

### Phase 3: 運用・データ・依存の安定化

目的: 公開運用や長期保守で事故になりやすい箇所を整える。

#### IMP-25-P2-SEC-001: 画像アップロードの検証強化

**実装状況**: 実装済み（2026-05-30）

**対象**

- `app.py`
- `manager/image_upload_validation.py`
- `tests/test_image_upload_validation.py`

**現状**

アップロードファイルのサイズ、拡張子、content-type検証が弱い。

**実装内容**

- `MAX_CONTENT_LENGTH` を設定する。
- 許可拡張子とMIMEタイプを限定する。
- Cloudinary送信前にファイル種別を検証する。
- ファイルシグネチャを確認し、拡張子/MIMEと内容が一致しない画像を拒否する。
- PNG/JPEG/GIF/WebPのみ許可し、SVGなどの能動的コンテンツになりやすい形式は許可しない。
- エラー時はCloudinary送信前に400で拒否する。

**受け入れ条件**

- 許可外ファイルがアップロードできない。
- サイズ超過が明示的に拒否される。

#### IMP-25-P2-DATA-001: SQLAlchemyモデルのデフォルト値修正

**実装状況**: 実装済み（2026-05-30）

**対象**

- `models.py`

**現状**

`Room.data = db.Column(db.JSON, default={})` が mutable default になっている。

**実装内容**

- `Room.data` が `default=dict` を使う状態であることを確認済み。
- 退行防止として `tests/test_room_model_defaults.py` を追加する。
- 既存データ移行が不要か確認する。

**受け入れ条件**

- 新規Room間で `data` が共有されない。
- モデル関連テストが通る。

#### IMP-25-P2-DATA-002: GM専用画像の取得仕様整理

**実装状況**: 実装済み（2026-05-30）

**対象**

- `app.py`
- `manager/image_manager.py`
- `tests/test_image_visibility.py`

**現状**

画像削除APIではGM判定を使うが、画像一覧APIではGM判定を渡していない。

**実装内容**

- GMはGM専用画像を一覧取得できる仕様か確認する。
- 仕様どおりに `get_images(..., is_gm=...)` を呼ぶ。
- プレイヤーからGM専用画像が見えないことを保証する。
- 非GM状態では、アップロード者本人であっても `visibility=gm` の画像を一覧表示しない。
- アップロード時の `visibility=gm` は、サーバー側でGM状態のときだけ保存する。

**受け入れ条件**

- GMとプレイヤーで画像一覧の見え方が仕様どおり分かれる。

#### IMP-25-P2-ARCH-001: 依存バージョン固定方針の導入

**対象**

- `requirements.txt`
- 必要に応じて `requirements-dev.txt`

**現状**

多くの依存が未固定で、環境差分による破損を検知しづらい。

**実装内容**

- 本番依存と開発依存を分ける。
- 本番依存は `requirements.txt` で主要依存をバージョン固定する。
- 開発/テスト依存は `requirements-dev.txt` に分離する。
- いきなり厳密ロックへ移行せず、まず主要依存の固定で再現性を上げる。
- CIまたはローカルセットアップ手順に反映する。

**受け入れ条件**

- 新規環境で再現可能に依存をインストールできる。

---

## 3.5 当面の実施順方針

ARCH-001/ARCH-002完了後は、P1の残タスクへ直行せず、P2のうち負担が軽く影響範囲を限定しやすい項目を先に処理する。

優先するP2項目:

1. `IMP-25-P2-DATA-001`: SQLAlchemyモデルの mutable default 修正
2. `IMP-25-P2-SEC-001`: 画像アップロード検証強化
3. `IMP-25-P2-DATA-002`: GM専用画像の取得仕様整理

意図:

- P1の `ARCH-003` / `FE-001` は影響範囲が広いため、着手前に小さな安全性改善を先に片付ける。
- P2の軽量タスクでデータ・アップロード・秘匿画像まわりの事故リスクを下げる。
- 小さな変更でテストと運用手順を安定させてから、P1の大きな構造変更へ戻る。

P2軽量タスク完了後、P1へ戻る順番:

1. `IMP-25-P1-ARCH-003`: Flask app factory 化
2. `IMP-25-P1-FE-001`: フロント状態管理とSocket境界の整理

---

## 4. 推奨PR分割

| PR | 含める番号 | 目的 |
|---|---|---|
| PR-25-01 | `IMP-25-P0-RULE-001`, `IMP-25-P0-RULE-002` | 戦闘ルールの明確な不具合修正 |
| PR-25-02 | `IMP-25-P0-AUTH-001`, `IMP-25-P0-AUTH-002` | GM権限と接続設定の安全化 |
| PR-25-03 | `IMP-25-P0-SEC-001` | ログ/チャットXSS対策 |
| PR-25-04 | `IMP-25-P1-TEST-001`, `IMP-25-P1-TEST-002`, `IMP-25-P1-TEST-003` | テスト基盤の信頼性回復 |
| PR-25-05 | `IMP-25-P1-ARCH-001`, `IMP-25-P1-ARCH-002` | 巨大Pythonモジュール分割 |
| PR-25-06 | `IMP-25-P1-FE-001` | フロント状態管理の整理 |
| PR-25-07 | `IMP-25-P2-*` | 運用・データ・依存の安定化 |

---

## 5. 実装前チェックリスト

- [ ] 対象番号をPR本文、コミットメッセージ、テスト名のいずれかに含める。
- [ ] 既存の日本語キー、英語キー、旧JSON定義の互換性を確認する。
- [ ] Socketイベント名を変更しない。
- [ ] GM権限を扱う変更では、非GMの拒否テストを追加する。
- [ ] GM PINは4桁数字、マスターキーは8桁数字として検証する。
- [ ] GM PINを平文でDB、ログ、Socket payload、画面再表示に残さない。
- [ ] `innerHTML` を使う場合は、入力元が信頼済みか、サニタイズ済みかを明記する。
- [ ] 巨大ファイルへ追記する場合は、分割できない理由をPRに書く。

---

## 6. 完了条件

最低完了条件:

- `IMP-25-P0-*` がすべて完了している。
- 通常pytestでネットワーク依存e2eが走らない。
- `python scripts/check_text_encoding.py` が通る。
- `python scripts/check_mojibake_markers.py` が通る。

推奨完了条件:

- `pytest -q --ignore=.claude` が通る。
- `pytest -q tests/test_python_module_size_guard.py` が通る。
- 新規コードが `manuals/module_size_policy.md` に違反しない。

---

## 7. 未決事項

現時点で、P0実装前に必ず決めるべき未決事項はない。

実装前または実装中に確認するとよい任意事項:

| 番号 | 内容 | 決めること |
|---|---|---|
| `DEC-25-007` | GM PIN失敗制限 | 連続失敗時にルーム単位で短時間ロックするか、ログ記録のみにするか |
| `DEC-25-008` | ルーム作成UI文言 | GM PINを「GM PIN」「GMキー」「GMパス」のどれで表示するか |
| `DEC-25-009` | DB移行方式 | `Room.gm_pin_hash` 追加を起動時軽量migrationにするか、明示migrationにするか |

---

## 8. 決定事項ログ

| 日付 | 番号 | 決定 | 根拠 |
|---|---|---|---|
| 2026-05-20 | `IMP-25` | 改善項目は `IMP-25-P{優先度}-{領域}-{連番}` で管理する | 実装、テスト、PRで追跡しやすくするため |
| 2026-05-20 | `DEC-25-001` | GM認証方式は、ルーム作成時にGMが手入力する4桁GM PINと、環境変数 `GM_MASTER_KEY` の8桁マスターキーを併用する | 軽量な卓運用を維持しつつ、クライアント自己申告のGM昇格を廃止するため |
| 2026-05-20 | `DEC-25-002` | ユーザー入力のチャット本文は完全テキスト表示にし、HTML装飾を許可しない | XSS対策を単純で維持しやすくするため |
| 2026-05-20 | `DEC-25-003` | e2eは通常pytestから分離し、`RUN_E2E=1` など明示時のみ低頻度で実行する | 通常テストをブラウザ環境やネットワーク取得に依存させないため |
| 2026-05-20 | `DEC-25-004` | 依存固定は、まず本番依存の主要バージョン固定と開発依存の分離で進める | 厳密ロックの運用負荷を避けつつ、環境再現性を上げるため |
| 2026-05-20 | `DEC-25-005` | `SECRET_KEY` と `CORS_ORIGINS` は本番環境で必須、ローカル開発時のみ未設定時の緩和を許可する | ローカルの扱いやすさと公開環境の安全性を両立するため |
| 2026-05-20 | `DEC-25-006` | スキル定義キーは日本語キー優先で正規化する。優先順位は `分類` > `カテゴリ` > `category` > `type` とする | 既存データが日本語定義中心であり、既存JSONの意味を保つため |
| 2026-05-30 | `DEC-25-010` | ARCH-001/ARCH-002完了後は、P2の軽量タスクを先に処理してからP1の大規模構造変更へ戻る | `ARCH-003` と `FE-001` は影響範囲が広いため、小さな安全性改善を先に片付けてリスクを下げるため |
| 2026-05-31 | `DEC-25-011` | `ARCH-003` は一括リライトではなく、起動処理の関数化、HTTPルート登録分離、Socket登録明示化、テスト用factory、本番入口切替の順に段階移行する | `app.py` import時副作用、`@app.route` 直書き、Socket import副作用、`app:app` 本番入口が同時に絡むため、単発変更ではRender起動と通常テストの両方に影響が大きいため |
