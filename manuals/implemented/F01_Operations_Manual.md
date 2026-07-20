<!-- 旧: 14 / 16 / 21 を統合 (2026-05-09) -->

# 運用マニュアル

**最終更新日**: 2026-07-11
**系統**: F — 運用
**統合元**: 14_GM_Buff_Item_Operations_Spec / 16_Manual_Update_Protocol / 21_Render_Deploy_Operations / 26_Account_Auth_Plan

---

## 本書の構成

1. GMバフ・アイテム操作仕様（旧14）
2. マニュアル更新プロトコルと機能改善ロードマップ（旧16）
3. Renderデプロイ運用手順（旧21）
4. GM PIN / アプリ管理者権限運用
5. Socketイベント在室認証パターン（旧Plan 27）
6. **アカウント認証・ルーム権限システム仕様（旧Plan 26）**
7. **保存信頼性・ログ長期保全仕様（Plan 28 Phase 1）**
8. **サーバーダイス仕様（Plan 28 Phase 1.5）**

---

# Part 1: GMバフ・アイテム操作仕様

**最終更新日**: 2026-05-02
**対象バージョン**: Current
**関連フェーズ**: Phase A（認可強化）/ Phase B（GM API）/ Phase C（GM UI）

## 1. 本書の目的

セッション進行中に GM が行う以下の操作について、実装済み仕様を一箇所に固定する。

- 任意キャラクターへのバフ/デバフ付与
- 任意キャラクターからのバフ/デバフ解除
- 任意キャラクターのアイテム個数増減（付与/没収）
- 既存イベントの認可強化（所有者 or GM）

## 2. 実装済み範囲

## 2.1 Phase A: 認可強化

- `request_state_update`
  更新対象キャラに対して `所有者 or GM` のサーバー側チェックを実施。
- `request_use_item`
  `payload.user_id` で指定されたキャラに対して `所有者 or GM` を必須化。

## 2.2 Phase B: GM API

- `request_gm_apply_buff`
- `request_gm_remove_buff`
- `request_gm_adjust_item`

いずれもサーバー側でルームGMとして認証済みの `attribute == "GM"` を必須とし、反映後は状態同期を行う。
`attribute == "GM"` は、ルームGM PIN、マスターキー、またはアプリ管理者のGM入室によってサーバー側で付与されたものだけを信用する。

## 2.3 Phase C: GM UI

`static/js/action_dock.js` のクイック編集に GM 専用パネルを実装。

- バフ付与フォーム（`buff_id`, `lasting`, `delay`, `count`）
- バフ解除フォーム（付与済み一覧から選択）
- アイテム増減フォーム（`item_id`, `delta`）

加えて、バフ付与フォーム上部に各入力値の意味を表示するヘルプ行を追加済み。

## 3. GM UI 入力ルール（確定）

## 3.1 バフ付与欄の意味

- `buff_id`: `Bu-xx` 形式のID（必須）
- `lasting`: 効果が継続するラウンド数
- `delay`: 効果が有効化されるまでの待機ラウンド数
- `count`: スタック数/使用回数系バフ向けの任意値

## 3.2 解除欄

- 現在 `special_buffs` に存在するエントリから選択して解除する。
- 解除要求は `buff_id` のみ送る（Phase3仕様）。

## 3.3 アイテム増減欄

- `delta > 0`: 付与
- `delta < 0`: 没収
- `delta == 0`: 不正入力として拒否

## 4. API仕様（運用視点）

## 4.1 `request_gm_apply_buff`

入力:

- `room`
- `target_id`
- `buff_id`（必須）
- `lasting`（省略時はサーバー側既定）
- `delay`（省略時はサーバー側既定）
- `count`（任意）

動作:

- `buff_id` から名称解決して付与する。
- `buff_name` 単独指定は受理しない（エラー）。
- 付与後は `broadcast_state_update` で同期。

## 4.2 `request_gm_remove_buff`

入力:

- `room`
- `target_id`
- `buff_id`（必須）

動作:

- `buff_id` が一致するエントリのみ解除対象とする。
- `buff_name` ベース解除は行わない。

## 4.3 `request_gm_adjust_item`

入力:

- `room`
- `target_id`
- `item_id`
- `delta`

動作:

- 正負で増減を分岐（付与/没収）。
- 在庫不足など失敗時はエラーを返して反映しない。

## 5. `buff_name` で動的バフは使えるか

結論: **使えない（Phase3）**。
2026-05-02 以降、`buff_name` 単独指定は受理しない。
バフ付与/解除は `buff_id` 指定が必須。

運用上の注意:

- 一部のシステム特殊処理は `buff_id` 依存で分岐するため、常に `buff_id` を指定すること。
- `count` の意味はバフごとに異なるため、汎用UIでは「任意の追加値」として扱う。

## 6. 既存マニュアルとの関係

- 操作全体の導線は `A02_GM_Creator_Manual.md` を正とする。
- データ定義の詳細は `C01_JSON_Definition_Master.md` を正とする。
- 本書は「GM運用時のバフ/アイテム操作」に限定した確定仕様。

---

# Part 1-B: GM PIN / アプリ管理者権限運用

**最終更新日**: 2026-07-20
**対象**: ルームGM認証、マスターキー、ユーザー管理権限、Render環境変数

## 1. 権限の分離

| 権限 | 範囲 | 主な用途 |
|---|---|---|
| ルームロール（owner/gm/player） | 入室中の特定ルーム | 戦闘進行、代理操作、GM専用Socket/API |
| アプリ管理者権限（`is_app_admin`） | アプリ全体 | ユーザー管理、全ルームへの入室、ルームのowner相当操作 |

通常ユーザーのルームロールはDB上のメンバーシップ（`room_members`テーブル）が正本。アプリ管理者は、実際の`Room.owner_id`やmembershipを書き換えず、権限判定時だけ全ルームの仮想ownerとして扱う。非公開・募集締切ルームもロビーに表示され、参加コードやGM PINなしでGM相当として入室できる。ルーム設定、参加コード、メンバー管理、owner移譲、削除もowner相当で実行できる。

## 2. ルームGM PIN

- ルーム作成時、4桁数字のGM PINを必須入力する。
- GM PINは平文保存せず、ハッシュとして `rooms.gm_pin_hash` に保存する。
- プレイヤーとして入室する場合、PIN入力は不要。
- GMとして入室する場合（または gm membership 取得のため）、4桁GM PINまたは8桁マスターキーを入力する。
- GM PINは参加コードとは別の秘密値であり、用途を混用しない。

## 3. マスターキー

マスターキーは8桁数字で、環境変数 `GM_MASTER_KEY` から読み込む。

用途:

- 任意ルームへのGM入室（GM PIN代替）
- 最初のアプリ管理者を `/api/admin/set_user_management_admin` で付与する（初回セットアップ）
- ルーム削除
- アプリ管理者権限の付与/解除

未設定、または8桁数字以外の場合、マスターキー機能は無効として扱う。

## 4. ユーザー管理

- ユーザー管理画面の一覧/詳細は **アプリ管理者のみ** 閲覧できる。
- 削除/所有権譲渡はアプリ管理者のみ実行できる。
- パスワードリセット用ワンタイムコード発行はアプリ管理者のみ実行できる（`POST /api/admin/issue_login_code`）。
- 管理者権限は `users.is_app_admin` に保存され、半永続的に保持される。
- ルームGMロールはユーザー管理操作の根拠にしない。
- ユーザー情報変更モーダルには、8桁マスターキーを入力して自分自身へユーザー管理権限を付与する導線を表示する。キーは保存せず、`POST /api/admin/set_user_management_admin` の検証にのみ使う。

## 5. Render環境変数

Renderでは、以下を環境変数として設定する。

| 変数 | 要否 | 内容 |
|---|---|---|
| `SECRET_KEY` | 必須 | Flaskセッション署名用。GMマスターキーとは別。 |
| `DATABASE_URL` | 必須 | PostgreSQL URL。未設定/非PGは起動失敗（fail-fast）。 |
| `CORS_ORIGINS` | 必須 | 許可Origin。例: `https://gemtrpg-diceapp.onrender.com` |
| `CLOUDINARY_CLOUD_NAME` / `CLOUDINARY_API_KEY` / `CLOUDINARY_API_SECRET` | 必須 | 画像アップロード |
| `GM_MASTER_KEY` | 任意 | 8桁数字のマスターキー。未設定ならマスターキー無効。 |
| `ACCOUNT_DISABLE_NAME_ONLY_LOGIN` | 推奨 | `1` で名前だけログイン（旧 `/api/entry`）を無効化。本番では必ず `1`。 |

`CORS_ORIGINS` はOriginだけを指定し、末尾スラッシュは付けない。フロントとAPI/Socketは同一オリジンで配信（Flask+WhiteNoise）。`SameSite=Lax` + Cookie認証でSocket connectが成立する。

---

# Part 1-C: 画像アップロード運用

**最終更新日**: 2026-05-30  
**対象**: 画像ピッカー、`/api/upload_image`、Cloudinary連携、画像レジストリ

## 1. 基本方針

画像アップロードは、サーバー側で検証したうえでCloudinaryへ送信する。クライアント側の `accept="image/*"` は補助扱いであり、許可判定の正本にはしない。

Cloudinaryへ送信する前に、次をすべて満たす必要がある。

| 項目 | 許可内容 |
|---|---|
| サイズ | 10MB以下 |
| 拡張子 | `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` |
| MIMEタイプ | `image/png`, `image/jpeg`, `image/gif`, `image/webp` |
| ファイル内容 | 先頭シグネチャがMIMEタイプと一致すること |

SVGは許可しない。ブラウザ上で能動的コンテンツを含みうるため、通常の立ち絵・背景画像用途ではPNG/JPEG/GIF/WebPへ変換してから使う。

## 2. 利用手順

1. 画像ピッカーを開く。
2. 「新規アップロード」から画像ファイルを選択する。
3. 必要に応じて画像名を設定する。
4. アップロードを実行する。
5. 成功後、画像一覧に登録された画像を選択する。

背景画像として使う場合も、同じ検証を通過した画像だけが登録される。

## 2.1 公開範囲

画像の公開範囲は `public` と `gm` の2種類。

| 公開範囲 | 表示対象 | 用途 |
|---|---|---|
| `public` | 通常プレイヤーとGM | 一般の立ち絵、背景、共有素材 |
| `gm` | GMとして入室中のユーザーのみ | 敵立ち絵、秘匿NPC、事前準備用の背景 |

GM専用画像は、アップロード者本人であってもプレイヤー状態では一覧に表示されない。ルームGM PIN、マスターキー、またはアプリ管理者権限でGMとして入室している場合だけ、画像一覧に表示される。

アップロード時に `visibility=gm` が送られても、サーバー側でGM状態でなければ `public` として登録する。公開範囲の最終判定はクライアントではなくサーバー側で行う。

## 3. エラー時の確認

アップロードに失敗した場合は、次の順番で確認する。

1. ファイルサイズが10MBを超えていないか。
2. 拡張子が `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` のいずれかか。
3. ファイルの実体と拡張子が一致しているか。
4. SVG、PDF、テキスト、拡張子だけ画像に変えたファイルを送っていないか。
5. Cloudinary環境変数が本番環境で正しく設定されているか。

サーバー側検証で拒否された場合はHTTP 400を返し、Cloudinaryへは送信しない。Cloudinary側または通信で失敗した場合は、Cloudinary送信後のエラーとして扱う。

## 4. 実装上の確認箇所

- アップロード入口: `app.py` の `/api/upload_image`
- 検証ロジック: `manager/image_upload_validation.py`
- 登録処理: `manager/image_manager.py` の `register_image`
- 公開範囲フィルタ: `manager/image_manager.py` の `get_images`
- DBモデル: `models.py` の `ImageRegistry`
- 回帰テスト: `tests/test_image_upload_validation.py`
- GM専用画像の回帰テスト: `tests/test_image_visibility.py`

機能改修時は、最低限 `pytest -q tests/test_image_upload_validation.py tests/test_image_visibility.py` を実行する。アップロード仕様を変える場合は、許可拡張子、MIMEタイプ、サイズ上限、シグネチャ検証、GM専用画像の表示境界テストも同時に更新する。

## 5. Render / 本番運用

Renderでは、画像アップロード機能の利用にCloudinaryの環境変数が必要になる。

| 環境変数 | 内容 |
|---|---|
| `CLOUDINARY_CLOUD_NAME` | Cloudinaryのクラウド名 |
| `CLOUDINARY_API_KEY` | Cloudinary APIキー |
| `CLOUDINARY_API_SECRET` | Cloudinary APIシークレット |

これらが未設定の場合、画像検証を通過してもCloudinary送信で失敗する。公開環境で画像アップロードを使う場合は、デプロイ前にRenderのEnvironmentで3項目を確認する。

---

# Part 2: マニュアル更新プロトコルと機能改善ロードマップ

最終更新: 2026-04-05
対象: 実装運用（Current）

---

## 0. 目的

この資料は次の2点を同時に満たすための運用ガイドです。

- 追加要素が増えても「大マニュアルがすぐ古くなる」問題を防ぐ
- 機能改修時に、仕様・テスト・運用手順を同時更新する

---

## 1. 現状課題（要約）

- 仕様の主語が複数（コード、テスト、manuals）に分散している
- JSON定義の許容範囲がドキュメントより実装側で先行しやすい
- 大きい統合マニュアルほど差分更新が重く、更新漏れが起きやすい

---

## 2. 推奨ドキュメント構成

運用は「3層構造」に分ける。

1. 導線層（利用者向け）
2. 仕様層（実装ルール）
3. 変更層（差分履歴）

具体案:

- 導線層: `01`, `02`, `10` を中心に「操作方法」だけを維持
- 仕様層: `09`, `14`, `15` を中心に「機械的ルール」を維持
- 変更層: 追加で `manuals/changes/` を作り、日付単位で差分記録

---

## 3. 更新ルール（Definition of Done）

機能追加・仕様変更の完了条件を固定する。

必須3点:

- コード更新
- テスト更新
- マニュアル更新

最低限更新すべきファイル:

- スキル/バフJSON仕様に触れた場合: `C01_JSON_Definition_Master.md`
- Select/Resolve挙動に触れた場合: `B03_SelectResolve_Spec.md`
- GM操作導線に触れた場合: `A02_GM_Creator_Manual.md`

---

## 4. 変更時の実務フロー（推奨）

1. 仕様変更を先に1行で宣言する
2. コードを変更する
3. 先にテストを通す
4. `15` に「何が増えたか」を追記する
5. `manuals/changes/YYYY-MM-DD_*.md` を1本追加する

`changes` ファイルの最小テンプレート:

```md
# 2026-04-05: target_scope alias update

## Added
- target_scope に same_team/opposing_team の正規化を追加

## Changed
- 同陣営対象スキルは redirect 対象外に統一

## Tests
- tests/test_target_scope_aliases.py
- tests/test_skill_target_tags.py
```

---

## 5. 機能改善提案（優先度順）

### P1: JSON定義バリデータAPI + UI

- 目的: 編集中に即時で定義ミスを検知
- 内容: `skills/buffs/radiance/passive/items/summon` の lint をAPI化
- 効果: テスト実行前にエラー原因を可視化

### P1: カタログ参照整合チェックの拡張

- 目的: `buff_id`, `skill_id`, `summon_template_id` の参照切れを防止
- 内容: 既存 `test_skill_catalog_smoke.py` を基点に他カタログにも横展開
- 効果: 運用データ更新時の事故率低下

### P2: 差分ベースのマニュアル自動生成

- 目的: 大マニュアル更新の手作業を削減
- 内容: キャッシュJSONから「キー一覧」「effect type一覧」を自動抽出して下書き生成
- 効果: 仕様書の鮮度維持

### P2: スキル/バフ定義プレビュー画面

- 目的: JSON更新の確認コスト削減
- 内容: `timing`, `target_scope`, `effects` を可視化し、実行順も表示
- 効果: 実装担当以外でもレビューしやすい

### P3: 変更影響マップ

- 目的: 変更時に関連章を漏れなく更新
- 内容: 「このeffect typeを触ると更新すべき manual/test 一覧」を自動提示
- 効果: 更新漏れ防止

---

## 6. マニュアル要約の作り方（実戦向け）

大マニュアル更新時は「全文書き換え」ではなく、章ごとの責務を固定する。

- 章A: 目的（何ができるか）
- 章B: 入力（何を設定するか）
- 章C: 実行（どう処理されるか）
- 章D: 検証（どのテストで担保するか）

この4点だけを各章に揃えると、追加要素があっても追記位置が明確になる。

---

## 7. 今回の着地点

このプロトコルに合わせて、JSON定義の大元として以下を新設済み。

- `manuals/implemented/C01_JSON_Definition_Master.md`

次アクション候補:

1. `manuals/changes/` の新設
2. `tests/` にカタログ横断lintの追加
3. JSONバリデータAPIの実装

---

# Part 3: Renderデプロイ運用手順

最終更新: 2026-05-02
状態: 実装済み・本番反映済み

---

## 1. デプロイ前に固定すべき条件
1. `schema=skill_json_rule_v2`
2. `APPLY_BUFF/REMOVE_BUFF` は `buff_id` 必須
3. 自然言語入力では `的中時` を使用（`中時/命中時` 禁止）

---

## 2. 事前チェック
1. `skills_cache.json` バックアップ
2. `buff_catalog_cache.json` バックアップ
3. `battle_only_presets_cache.json` バックアップ
4. 直前安定コミットSHAの記録

---

## 3. 反映後スモーク
1. 宣言→確定が正常
2. `的中時` 付与系が正常
3. `buff_id` 付与/解除が正常
4. 特記（条件補正）が正常
5. 自然言語ビルダーが整形表示/1行コピーで動作

---

## 4. 監視
1. `logs/json_rule_v2_audit.jsonl` の failure 件数
2. battle_error の急増有無
3. 主要フロー（宣言/解決/ラウンド終了）

---

## 5. ロールバック条件
1. 宣言確定不能の再現
2. 特記解釈失敗の多発
3. `buff_id` 参照不整合で進行不可

---

## 6. ロールバック最小手順
1. 直前安定コミットへ戻す
2. Render再デプロイ
3. `/api/get_skill_data` と宣言フローを再確認

---

# Part 4: Socket イベント在室認証パターン（Plan 27 より統合・2026-06-28）

## 1. 原則

全 Socket ハンドラは、ペイロードの `room` に対して SID が在室済みかを検証する。
クロスルーム操作（在室していないルームへの書き込み/読み取り）は不可能にする。

## 2. 基本パターン

```python
from manager.room_access import is_sid_in_room

@socketio.on('any_event')
def handle_any_event(data):
    room = data.get('room')
    if not room:
        return
    if not is_sid_in_room(request.sid, room):
        emit('error', {'message': 'Not in this room'}, to=request.sid)
        return
    # 既存処理
```

## 3. GM 権限が必要なイベントの検証順序

在室チェック → GM 権限チェック の順で行う。GM 権限は `get_user_info_from_sid` 経由で membership から取得。

```python
if not is_sid_in_room(request.sid, room):
    emit('error', {'message': 'Not in this room'}, to=request.sid)
    return
user_info = get_user_info_from_sid(request.sid)
if user_info.get('attribute') != 'GM':
    emit('error', {'message': 'GM only'}, to=request.sid)
    return
```

## 4. キャラクター操作の検証順序

在室チェック → キャラ所有者チェック（`is_authorized_for_character`）の順。

## 5. 適用済みファイル（2026-06-28 実機スモーク確認済み）

| ファイル | 適用 |
|---|---|
| `events/socket_main.py` | ✅ |
| `events/socket_room_presets.py` | ✅ `_require_room_participant()` ヘルパー |
| `events/socket_battle_only.py` | ✅ |
| `events/socket_exploration.py` | ✅ |
| `events/battle/common_routes.py` | ✅ |
| `events/battle/duel_routes.py` | ✅ |
| `events/battle/wide_routes.py` | ✅ |
| `events/socket_char.py` | ✅ |
| `events/socket_items.py` | ✅ |

---

# Part 5: アプリ安全性・アーキテクチャ確定方針（Plan 25 より統合・2026-06-28）

*P0 実装確認済み（2026-05-31）。以下は確定した設計方針。*

| 決定 | 内容 |
|---|---|
| GM 認証方式 | ルーム作成時に GM が手入力する 4 桁 GM PIN と環境変数 `GM_MASTER_KEY`（8桁）を併用。クライアント自己申告の GM 昇格を廃止。 |
| チャット本文 | 完全テキスト表示のみ。HTML 装飾不可（XSS 対策を単純で維持しやすくするため）。 |
| 本番環境変数 | `SECRET_KEY` と `CORS_ORIGINS` は本番環境で必須。ローカル開発時のみ未設定時の緩和を許可。 |
| スキル定義キー優先順位 | `分類` > `カテゴリ` > `category` > `type`（既存 JSON の意味を保つため。B01 §10 / C01 §9 参照）。 |
| e2e テスト分離 | 通常 pytest はネットワーク依存 e2e を走らせない。`RUN_E2E=1` など明示時のみ実行。 |
| `app.py` 段階移行方針 | 一括リライトではなく、起動処理関数化 → HTTP ルート登録分離 → Socket 登録明示化 → テスト用 factory → 本番入口切替の順で段階移行する。 |

---

# Part 6: アカウント認証・ルーム権限 システム仕様（Plan 26 より統合・2026-06-28）

## 1. 設計不変条件

実装方式を選んでも変更しない原則。

1. 認証済みユーザーの正本は `session['user_id']` とDB上の `User`。
2. `username`（表示名）は認証・所有権・認可のキーにしない。
3. ルーム内権限の正本は `room_members` テーブルのmembership。Flask sessionの `attribute` を正本にしない。
4. Socket接続時に認証し、各イベントではSIDが対象ルームへ参加済みかを共通ヘルパーで検証する。
5. owner/gm/playerの変更・剥奪は、再ログインを待たず既存Socketへ反映する。
6. 未参加者向けロビーカードと参加者向けルーム状態は別DTO・別認可経路にする。
7. 短い秘密値は、値のハッシュ、期限、試行上限、失効日時をセットで管理する。
8. 認証失敗レスポンスでは、アカウントの存在有無を判別できる文言を返さない。
9. パスワード、コード、トークン、マスターキーをログ・監査payload・Socket broadcastへ出さない。
10. 既存データ移行はexpand → backfill → cutover → contractの順に行い、単一デプロイで破壊的変更しない。

## 2. データモデル概要

### User 拡張列

| 列 | 型 | 用途 |
|---|---|---|
| `login_name_normalized` | VARCHAR(100) unique | ログイン識別子（NFKC+casefold正規化）。表示名とは別。 |
| `password_hash` | VARCHAR(255) | werkzeugハッシュ。新規アカウントのみ必須。 |
| `auth_version` | INTEGER default 1 | パスワード再設定/全端末ログアウトで増加。sessionに同値を持たせ不一致で失効。 |
| `is_app_admin` | BOOLEAN | アプリ全体の管理者フラグ。ルームロールとは別。 |

### TrustedDeviceToken（端末トークン）

- `selector`（公開側識別子）+ `token_hash`（secret部分のハッシュ）の2列構成。
- localStorageには `selector + secret` を保存。DBにはsecret平文を保存しない。
- 通常ログアウトは行を失効させず自動復旧を停止。完全ログアウトは行を失効しlocalStorage削除。全端末ログアウトは全行失効＋`auth_version` 増加。

### OneTimeLoginCode（ワンタイムコード）

- app adminがユーザー単位で発行（`POST /api/admin/issue_login_code`）。
- ハッシュ保存。コード実値は発行時の一度だけ返す。
- 10文字・15分有効・5回失敗で失効。使用したコードはその場で失効（一回使用）。
- 使用後はパスワード設定専用grantへ交換し、設定完了後に通常sessionへ昇格する。

### RoomMember

- `(room_id, user_id)` の有効membership（`revoked_at IS NULL`）は一意。
- `role`: `owner` | `gm` | `player`。
- ルーム作成と owner membership 作成は同一トランザクション。
- 最後の owner 削除は禁止（先に owner 移譲を要求）。

### Room 拡張列

| 列 | 型 | 用途 |
|---|---|---|
| `lobby_visibility` | VARCHAR(20) | `hidden` / `listed` / `closed` |
| `join_code_hash` | VARCHAR(255) | 参加コードのハッシュ。GM PINとは別の秘密値。 |
| `description` | TEXT | ロビーカードに表示するルーム説明 |
| `recruitment_status` | VARCHAR(20) | 募集状態（owner/gmが編集可） |

## 3. 認証・セッション仕様

### Cookie設定

| 設定 | 値 |
|---|---|
| `SESSION_COOKIE_HTTPONLY` | True（全環境） |
| `SESSION_COOKIE_SAMESITE` | `Lax`（全環境） |
| `SESSION_COOKIE_SECURE` | True（Render本番のみ） |

sessionには `user_id`、`auth_version`、必要最小限の状態だけを置く。ログイン直前に `session.clear()` して古いルーム権限を持ち越さない。

### パスワード

- `werkzeug.security` でハッシュ化・照合。
- 最小10文字・最大128文字。trim/Unicode正規化しない（入力文字列をそのまま照合）。
- login_nameはNFKC+casefoldで正規化した別列に保存し、SQLiteとPostgreSQLのcollation差に依存しない。
- 連続失敗にはインメモリレート制限あり（worker=1のため再起動でリセット）。

### ログアウト（`POST /api/logout`）

| mode | Flask session | 現端末token | `auth_version` |
|---|---|---|---|
| `session` | clear | 保持 | 変化なし |
| `device` | clear | 失効 | 変化なし |
| `all` | clear | 全件失効 | 増加（他sessionも失効） |

## 4. HTTP認可境界

| API | 必要権限 |
|---|---|
| `/api/get_session_user` | 認証済み |
| `/api/admin/users` / `/api/admin/user_details` | app admin のみ |
| `/list_rooms` | 認証済み（非memberには安全なロビーカードのみ） |
| `/load_room` | 有効membership（`room_members`）または入室済みsession |
| `/save_room` | 有効membership（owner/在室参加者）。全状態上書きは将来廃止予定 |
| ルーム設定更新 | owner=全項目 / gm=募集状態のみ |
| ルーム削除 | owner のみ |

未参加者向けロビーカードに `owner_id`・参加者一覧・ログ・キャラクター・画像URL・参加コードを含めない。

## 5. Socket.IO認可境界

- `connect` では有効な認証sessionを要求する。
- `join_room` はpayloadの username/role を無視し、sessionの `user_id` とDB membershipから役割を解決する。
- 各イベントで `is_sid_in_room(request.sid, room)` で在室を検証する（`manager/room_access.py`）。
- GM判定は `get_user_info_from_sid` を単一チョークポイントとし、`attribute` を毎回 membership から再解決する。
- role剥奪時は次のイベントから即時反映（再接続不要）。
- HTTPとSocketで別々の権限ロジックを複製せず `manager/room_access.py` に集約する。

## 6. 環境分離方針

- ローカル環境: `DATABASE_URL` を無視し `sqlite:///gemtrpg.db` を使用。
- Render本番: `DATABASE_URL` 未設定または非PostgreSQLなら **起動失敗（fail-fast）**。
- ローカルとRenderのユーザー・ルーム・権限・画像レジストリは共有しない。
- DBマイグレーション（`manager/db_migration.py`）は冪等設計。列追加失敗時は `RuntimeError` を raise して起動を中断する。

---

# Part 7: 保存信頼性・ログ長期保全仕様（Plan 28 Phase 1 より統合・2026-07-10）

## 1. 保存信頼性

ルーム状態の正本はメモリ上の `active_room_states`。DBは永続化先として扱い、通常保存は既存どおりデバウンスして書き込みを集約する。

追加仕様:

- デバウンス保存が失敗した場合、対象ルームがDB上に残っていれば1回だけ再試行する。
- 再試行しても失敗した場合はエラーログを残し、次のユーザー操作で再度ダーティ化されるのを待つ。
- 削除済みルームは再試行対象にしない。これにより、削除後の遅延保存でルームが復活する事故を防ぐ。
- `flush_room_state_now(room_name)` により、重要イベント直後に保留保存を即時フラッシュできる。

即時フラッシュ対象:

- ラウンド開始
- ラウンド終了
- 戦闘リセット
- 強制マッチ終了
- 戦闘モード切替
- 探索/戦闘パート切替
- 戦闘専用モードの自動リセット/自動次ラウンド開始

## 2. ログ長期保全

ルーム状態内の `logs` は従来どおり最新500件を通常表示用に保持する。ただし500件を超えて切り捨てる前に、古いログを `room_log_archives` テーブルへ保存する。

`room_log_archives` の主な列:

| 列 | 用途 |
|---|---|
| `room_id` / `room_name` | 対象ルーム |
| `log_id` | ルーム内ログ連番 |
| `timestamp_ms` | クライアント/サーバーログ時刻（ms） |
| `log_type` | `chat` / `system` / `match` / `state-change` など |
| `user_name` | ログ投稿者 |
| `secret` | 秘匿ログかどうか |
| `message` | 表示本文 |
| `payload` | 元ログ辞書 |
| `archived_at` | アーカイブ保存時刻 |

アーカイブ保存に失敗した場合、メモリ上のログ切り捨ては行わない。ログ喪失を避けるため、状態サイズ増加より記録保全を優先する。

`broadcast_log` を通る通常ログに加え、Select/Resolve解決トレースが直接 `state["logs"]` に追加する経路でも同じアーカイブ付き切り詰めを使う。

## 3. ログエクスポート

GMは次のAPIでルームログをエクスポートできる。

```text
GET /api/room/export_logs?room_name=<room>&format=json
GET /api/room/export_logs?room_name=<room>&format=text
```

認可:

- 有効なルームロールが `owner` または `gm` のユーザーのみ実行可能。
- `player` は403。

出力:

- `json`: `gem_dicebot_room_logs.v1` スキーマで、アーカイブログと現行 `state["logs"]` を時刻/連番順に統合して返す。
- `text`: 1ログ1行のプレーンテキストとして返す。
- レスポンスは `Content-Disposition: attachment` を付け、ブラウザ保存できる。

## 4. ログ履歴検索UI

ビジュアル戦闘画面の「履歴」ボタンは、ログ履歴モーダルを開く。

実装済み機能:

- 表示中の `battleState.logs` を対象にフリーワード検索できる。
- 種別フィルタ（全て、チャット、システム、戦闘、状態変更）を選べる。
- GMにはJSON/TXTエクスポートボタンを表示する。
- エクスポートボタンはログ履歴モーダル右上の「JSON保存」「TXT保存」として表示する。
- エクスポートはサーバーAPIを使うため、500件を超えてアーカイブされたログも含まれる。

## 5. 回帰テスト

主な検証:

- `tests/test_room_log_archive.py`
  - 500件超過ログが切り捨て前にアーカイブされる。
  - GM以外はログエクスポートできない。
  - エクスポートにアーカイブ済みログと現行ログが時系列で含まれる。
  - 保存失敗時に1回再試行される。
  - 削除済みルームをデバウンス保存で再作成しない。
- `tests/test_phase1_schema_expand.py`
  - `room_log_archives` テーブルが新規環境で利用できる。

---

# Part 8: サーバーダイス仕様（Plan 28 Phase 1.5 より統合・2026-07-11）

## 1. 目的

チャット欄からの `/roll` `/sroll` は、クライアント側で出目や投稿者名を作らず、Socketイベント `request_chat` を受けたサーバー側で処理する。
これにより、ログに残るダイス結果、投稿者名、秘匿フラグの正本をサーバーへ寄せる。

## 2. 入力仕様

対象イベント:

- `request_chat`
- 実装箇所: `events/socket_main.py::handle_chat`

コマンド判定:

- 投稿本文の先頭にある独立トークン `roll` / `/roll` / `sroll` / `/sroll` だけをコマンドとして扱う。
- コマンド以外の通常チャットでも、従来互換として本文に `XdY` 形式のダイス式があればサーバーでロールする。
- 1投稿に複数のコマンドを書いても分割実行しない。先頭コマンドを1回だけ解釈し、残りは1つの式または投稿本文として扱う。

公開範囲:

- `/roll` / `roll`: 常に通常公開ログ。クライアントpayloadに `secret: true` が含まれていても採用しない。
- `/sroll` / `sroll`: 常に秘匿ログ。
- コマンドなし通常チャットの `secret` は既存互換としてpayload値に従う。

投稿者名:

- `payload.user` は信用しない。
- `user_sids[request.sid].username` を投稿者名として使う。
- 在室していないSIDから別ルームへ送られた `request_chat` は無視する。

## 3. 出力仕様

ダイス式が実行された場合、`manager.dice_roller.roll_dice()` の結果を用いて次の形式で `broadcast_log` する。

```text
<式> → <details> = <total>
```

例:

```text
2d6+3 → (4+5)+3 = 12
```

ログ種別は `chat`。公開/秘匿は上記のコマンド仕様に従う。

## 4. 不正入力・境界条件

- コマンド後にダイス式がないが文字列が残る場合、コマンドだけを除いた本文を通常チャットとして送信する。
- コマンドだけで本文が空になる場合、ログは送信しない。
- ダイス式は `\d+d\d+` を含む場合にロール対象とする。
- 先頭コマンド以外に後続の `/roll` `/sroll` が含まれても、追加コマンドとしては実行しない。

## 5. 回帰テスト

主な検証:

- `tests/test_room_access_socket.py`
  - 非在室SIDから別ルームへのチャットを無視する。
  - チャット投稿者名はpayloadではなくサーバー側在室情報から確定する。
  - `/roll` はサーバーで `roll_dice()` を呼び、通常公開ログとして記録する。
  - `/roll` はpayloadの `secret` 値に影響されない。
  - `/sroll` はサーバーで `roll_dice()` を呼び、秘匿ログとして記録する。
  - ダイス式なし/不正な式は通常チャットまたは無視として扱う。
  - 複数コマンド混在時に分割実行しない。

# Part 9: アカウント紐づけキャラクター管理仕様（Plan 36 より統合・2026-07-12）

## 1. 目的

キャラクターは従来 `Room.data['characters']` にのみ存在しルームに従属していた（ルームをまたいだ再利用は手動JSON持ち回りのみ）。
本機能は、アカウント（`User`）に紐づく「持ちキャラ」を独立して保存・管理し、複数ルームへの投入とシナリオ後の成長を可能にする。
キャラ作成ツール（`CharaCreator/GEMDICEBOT_CharaCreator.html`）は最小統合方針（既存UIをそのまま配信し、保存/読込ボタンのみ追加）で本体へ組み込む。

## 2. データモデル

`models.py::OwnedCharacter`（`owned_characters`テーブル）:

| カラム | 内容 |
|---|---|
| `id` | UUID文字列主キー（`owned_<uuid4().hex>`） |
| `user_id` | 所有者（`users.id` FK） |
| `name` | 表示用。`data.name`のコピー |
| `data` | キャラJSON本体（CharaCreator出力の`data`部をそのまま格納。スキーマの細分化はしない） |
| `exp_total` | 蓄積経験値。**キャラ作成時点の経験＋シナリオ経験（＋出身7ボーナス）で初期化**され、以後は成果反映（Part 9-4）でのみ加算される |
| `growth_log` | 成長履歴 `[{date, kind, ...}, ...]`。`kind`は`reflect_session_results`（成果反映）または`growth`（成長画面） |
| `created_at` / `updated_at` / `deleted_at` | 論理削除（`RoomMember`と同じ流儀） |

`Room.data`と同じJSON列パターンを踏襲する。**重要な実装上の注意**: JSON列の内容を部分更新する場合、`dict(character.data)`のような浅いコピーでは`params`等のネスト辞書要素が元オブジェクトと共有されたままになる。これを場で書き換えてから再代入すると、SQLAlchemyの変更検知が「コミット前後で差分なし」と誤判定し、UPDATE文が発行されないままコミット後に値が元へ戻る。ネストした辞書・リストの要素は必ずコピーしてから変更すること（`routes/owned_characters.py::grow_owned_character`参照）。

## 3. CRUD API（`routes/owned_characters.py`）

すべて `session_required`（要ログイン）。所有者本人のみ参照・変更できる（`user_id`一致・`deleted_at IS NULL`で絞り込み、他人のキャラは404）。

| メソッド | パス | 内容 |
|---|---|---|
| GET | `/api/owned_characters` | 自分の持ちキャラ一覧。各要素に`used_exp`/`remaining_exp`/`skill_exp_budget`を付与（後述） |
| GET | `/api/owned_characters/<id>` | 単体取得 |
| POST | `/api/owned_characters` | 新規保存。1アカウントあたり20体のソフト上限（`OWNED_CHARACTER_LIMIT`） |
| PUT | `/api/owned_characters/<id>` | 上書き保存（CharaCreatorからの再編集）。`exp_total`は変更しない |
| DELETE | `/api/owned_characters/<id>` | 論理削除 |
| POST | `/api/owned_characters/<id>/growth` | 軽量成長画面からのスキル追加・パラメータ上昇（Part 9-5） |

## 4. ルーム投入とセッション成果の反映

### 投入（Phase 3）

- クライアントは`GET /api/owned_characters`で取得した`data`を`{kind:"character", data:{...}}`へ包み、既存の`parseCharacterJsonToCharacterData`でルーム用キャラへ正規化した上で、`request_add_character`に**`ownedCharacterId`を追加**して送信する（`static/js/common/char_json.js::loadCharacterFromJSON`のoptions引数）。
- サーバー側（`events/socket_char.py::handle_add_character` → `_resolve_owned_character_tag`）は、session の `user_id` と `OwnedCharacter.user_id` が一致する場合のみ `char_data['owned_character_id']` をスタンプする。不一致・存在しないIDは**静かに無視**（キャラ追加自体は成功させ、タグだけ付けない）。これにより、他人の持ちキャラへ成果を誤って書き戻す事故を防ぐ。
- 投入はコピーであり、ルーム内キャラを書き換えても持ちキャラ本体（DB上の`OwnedCharacter.data`）には一切影響しない。

### 成果反映（Phase 4）: `request_reflect_session_results`

`events/socket_char.py::handle_reflect_session_results`。payload: `{room, char_id, exp_gain, items: {item_id: qty, ...}}`。

- **対象**: ルーム内キャラに`owned_character_id`があるもののみ（JSON貼り付け由来の従来キャラはスキップ、`reflect_session_results_result`イベントで`skipped:true, reason:'not_owned_character'`を返す）。
- **実行権限**: キャラ所有者本人（`char.owner_id == session.user_id`）または GM。それ以外は`error`イベントで拒否。
- **冪等性**: `char['flags']['results_reflected']`が既に立っている場合はスキップ（`reason:'already_reflected'`）。1キャラ・1回のみ反映する。
- **ホロウ除外**: `state.get('play_mode') == 'hollow'`の場合、アイテムは反映対象外とし経験値のみ反映する（計画35「ホロウ内で完結の原則」。ホロウ側の`play_mode='hollow'`実装前でも、この判定は`state.play_mode`未設定時は通常ルーム扱いになるため副作用なく先行実装できている）。
- 成功時は`owned.exp_total`に`exp_gain`を加算し、`items`（ホロウでない場合のみ）を`owned.data['inventory']`へマージ、`owned.growth_log`に`kind:'reflect_session_results'`のエントリを追加してコミットする。

## 5. 軽量成長画面とコスト計算（Phase 5）

### CharaCreatorのコスト計算式のPython移植

`routes/owned_characters.py`に、CharaCreator（`GEMDICEBOT_CharaCreator.html::calculateStats()`）の予算計算をそのまま移植した関数群を持つ。

- `compute_exp_limit(data)`: `経験`＋`シナリオ経験`パラメータの合計（出身7＝ラグラゼシス非都市部のみ+1）。**キャラ作成時の`exp_total`初期値**として使う。
- `compute_used_exp(data)`: `data.commands`から`【スキルID 表示名】`パターンでスキルIDを抽出し（正規表現はCharaCreatorの`restoreFromCommands()`と同一）、スキルマスター（`extensions.all_skill_data`）の`取得コスト`フィールドを合算する。出身6（ラグラゼシス都市部）のみ、魔法カテゴリ（IDが`Ms`/`Mb`/`Mp`で始まる）スキルの先頭コスト1点分を割引く。
- `compute_param_growth_spent(growth_log)`: 成長画面でのパラメータ上昇に使った経験値の累計。パラメータ上昇は`commands`に現れないため、`growth_log`の`kind=='growth'`エントリの`param_increases`を合算して求める。
- `used_exp`（API応答）= `compute_used_exp(data)` + `compute_param_growth_spent(growth_log)`。`remaining_exp` = `exp_total - used_exp`。
- `skill_exp_budget`（API応答）= `exp_total - compute_param_growth_spent(growth_log)`。CharaCreator側の`costMax`（経験欄）に渡すべき値であり、**`remaining_exp`をそのまま渡してはいけない**（CharaCreator自身が「現在選択中のスキル」のコストを含めて上限判定するため、`remaining_exp`を渡すと既存スキルのコストを二重に差し引いてしまう）。

### `POST /api/owned_characters/<id>/growth`

payload: `{add_skill_ids: [...], add_radiance_ids: [...], param_increases: {"筋力": 1, ...}}`。

- スキル追加のコストは、追加前後の`compute_used_exp`の差分として算出する（`all_skill_data`の`チャットパレット`フィールドをそのまま`commands`へ追記するため、CharaCreatorが生成する行と同一形式になる）。
- パラメータ上昇は house rule として1ポイントあたり経験値1消費（CharaCreator自体には無い、成長画面固有のルール）。現行UI（`owned_characters_modal.js`）はこの入力欄を提供していないが、API自体は互換性のため残している。
- 消費合計が残り経験値を超える場合は400を返し、`data`・`growth_log`とも変更しない。
- 成功時は`data.params`の対象ラベルを更新（無ければ新規追加）し、`growth_log`に`kind:'growth'`のエントリを追加する。`exp_total`自体は変更しない（消費すれば`remaining_exp`が自動的に減るだけ、という設計）。

### 輝化スキルの成長（`add_radiance_ids`、通過点予算）

CharaCreatorの「通過点」（`data.params`の`通過点`ラベル、CharaCreator側フィールド名`radiance-points`）を、輝化スキル習得専用の予算として扱う。経験値予算（`exp_total`/`remaining_exp`）とは完全に独立しており、互いを侵食しない。

- `compute_radiance_limit(data)`: `通過点`パラメータの値をそのまま輝化予算の上限とする。
- `compute_radiance_used(data, radiance_skills)`: `data.SPassive`配列（輝化スキルIDと特殊パッシブIDが混在する）のうち、輝化スキル辞書（`manager.radiance.loader.radiance_loader.load_skills()`、`/api/get_radiance_data`と同一データ）に存在するIDだけコスト（`cost`フィールド）を合算する。パッシブ側のIDは輝化辞書に存在しないため自然に0コスト扱いとなり、成長エンドポイントの対象から除外される（特殊パッシブの習得は現状もCharaCreator側の再編集でのみ可能）。
- API応答に`radiance_limit`（通過点の総量）・`radiance_used`（消費済み）・`radiance_remaining`（残り）を追加する。
- `add_radiance_ids`で指定したIDは、未知ID・既に`SPassive`にある重複IDのいずれも400エラーで拒否する（`data`・`growth_log`とも変更しない）。コスト合計が`radiance_remaining`を超える場合も同様に400で拒否する。
- 成功時は`add_radiance_ids`を`data.SPassive`へ追記し（`commands`は変更しない）、`growth_log`のエントリに`added_radiance_ids`・`radiance_cost`を記録する。

### CharaCreator再編集時の予算連動

`?owned_id=<id>`付きで`/chara_creator`を開くと、`loadOwnedCharacterFromAccount()`が`GET /api/owned_characters/<id>`を取得し、フォームへ復元した上で`p-exp`欄を`skill_exp_budget`で上書きする（`p-exp-scenario`は0）。これにより、CharaCreator上の「上限」表示が持ちキャラの実際の残り予算と一致した状態で再編集できる。

## 6. 回帰テスト

- `tests/test_owned_characters_api.py`: CRUD・所有者以外からの隔離・論理削除・保存上限。
- `tests/test_chara_creator_route.py`: `/chara_creator`配信ルート。
- `tests/test_add_character_owned_character.py`: 投入時の`owned_character_id`タグ付け・他人のIDの無視・投入コピーの独立性。
- `tests/test_reflect_session_results.py`: 所有者/GMによる反映・非所有者非GMの拒否・二重反映防止・`owned_character_id`なしのスキップ・ホロウルームでのアイテム除外。
- `tests/test_owned_character_growth.py`: `compute_exp_limit`/`compute_used_exp`の同値性（出身6/7エッジケース含む）・成長エンドポイントの予算超過拒否・複数回呼び出しでの累積・`skill_exp_budget`の算出・輝化スキル成長（通過点予算内での習得成功・予算超過拒否・未知ID拒否・重複ID拒否・経験値予算との独立性・`growth_log`記録）。
