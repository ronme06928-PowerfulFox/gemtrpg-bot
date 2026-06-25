# 26 Render/ローカル分離後のアカウント・ルーム権限改善計画

**作成日**: 2026-06-14  
**精査日**: 2026-06-19  
**コード突合**: 2026-06-21（3.2の主張を実コードで全件検証。整合性・順序を見直し）  
**種別**: planned  
**状態**: 実装前の設計確定中
**前提**: Tailscale公開は廃止し、ローカル環境とRender環境は別DB・別ユーザー・別ルームとして扱う。

---

## 1. 目的

Render公開運用に耐えるアカウント認証、セッション、復旧、ルーム参加、ルーム別権限を段階的に導入する。

この計画の完了条件は「画面上でログインできる」ことではない。サーバー側で認証主体と権限を一意に判定し、未参加者・一般参加者・GM・owner・アプリ管理者の境界をHTTPとSocket.IOの両方で強制できることを完了条件とする。

---

## 2. 確定済みの基本方針

- ローカル起動はローカル検証用とし、ローカルSQLiteだけを使用する。
- Render環境は公開・常設用とし、Render PostgreSQLだけを使用する。
- ローカルとRenderのユーザー、ルーム、権限、画像レジストリを共有しない。
- Tailscale、Funnel、Serve、GemDiceBot_Launch、外部Neon共有DB運用は対象外とする。
- パスワード、復旧コード、参加コード、ワンタイムコード、GM PINは平文保存しない。
- アプリ管理権限とルーム内権限を分離する。
- ルーム権限はアカウント単位ではなく、ルームごとのmembershipから判定する。
- 管理者8桁コードは緊急管理用に限定して残し、日常的なGM認証には使わない。
- フロントエンドから送られた `username`、`attribute`、`role` は権限判定の根拠にしない。

---

## 3. 2026-06-19 現状監査

### 3.1 すでに存在する土台

| 項目 | 現状 | 評価 |
|---|---|---|
| ローカルDB分離 | 非Renderでは `DATABASE_URL` を無視し、`sqlite:///gemtrpg.db` を使う | 方針どおり。ただし自動テストがない |
| ユーザーID | `User.id` とFlask sessionにUUIDを保持 | 継続利用できる |
| ルーム作成者 | `Room.owner_id` を保存 | membership導入時の移行元にできる |
| アプリ管理者 | `User.is_app_admin` が存在 | ルームロールと分離して継続利用できる |
| 復旧情報 | 復旧コードとブラウザ用トークンはハッシュ保存 | 原型は利用できるが、寿命・複数端末・失効設計が不足 |
| GM PIN | `Room.gm_pin_hash` をハッシュ保存 | 移行期間の互換手段として利用できる |
| CORS/SECRET_KEY | 本番必須化済み | Cookie設定とCSRF/Origin対策は追加が必要 |

### 3.2 実装前に解消すべき問題

| 重要度 | 問題 | 実装への影響 |
|---|---|---|
| P0 | Renderで `DATABASE_URL` がない場合、SQLiteへフォールバックする | Render上で別の空DBが起動し、分離保証ではなくデータ消失に見える事故になる |
| P0 | `/api/entry` は名前だけで新規アカウントを作成・再利用する | 公開環境の本人確認にならず、名前の衝突・なりすましを防げない |
| P0 | `session_required` は `session['username']` の存在だけを見る | 削除済みユーザー、失効済みセッション、認証バージョン変更を検知できない |
| P0 | `/load_room` はログイン済みなら全ルーム状態を返す | 未参加者にログ、キャラクター、画像URL等が漏れる |
| P0 | `/save_room` はログイン済みユーザーからルーム全状態を受け取る | 任意ルームの全状態を上書きできる。原則廃止対象 |
| P0 | Socketイベントの一部がpayloadの `room`、`username` を前提にする | 別ルーム操作・なりすましを共通境界で防げていない |
| P0 | ルームmembershipテーブルが存在しない | 「参加済み」「owner/gm/player」を永続的に判定できない |
| P0 | 復旧コードに有効期限・試行回数制限・使用時失効がない | 公開環境での総当たりと長期漏えいに弱い |
| P0 | `get_session_user` が呼ばれるたびブラウザ復旧トークンを再発行する | 多端末利用、通常ログアウト、トークン失効の意味が不安定になる |
| P0 | 通常ログアウト後も自動復旧を行う設計だと直後に再ログインする | 「通常ログアウト」と「トークンを残す」がそのままでは両立しない |
| P0 | 管理ユーザー一覧・詳細は一般ログインユーザーも取得できる | 公開運用ではUUID、最終ログイン、所有情報の開示範囲が広すぎる |
| P1 | `ImageRegistry.uploader` と一部キャラクター所有情報がユーザー名基準 | 名前変更・同名ユーザー・UUID移行で所有権が曖昧になる |
| P1 | 起動時migrationがエラーをログに出して継続する | 必須列の追加に失敗してもアプリが起動し、実行時障害になる |
| P1 | `static/mobile/` が共通API（`/api/entry`・`/create_room`・`/load_room`・`/list_rooms`・`/api/get_session_user`）を直接利用 | 共通APIを安全化するとモバイル版が壊れる。現状のまま公開もできない |

#### 2026-06-21 コード突合での補強（記述より深刻・追記すべき事実）

- **Socket `join_room` は `session['username']` すら検証していない**（`events/socket_main.py`）。payloadの `room`/`username`/`role` だけで入室でき、`is_user_management_admin` なら自動GM昇格する。8.3の前提は「現状はSocketにsession認証が存在しない」である。
- **Cookieセキュリティ設定が現状ゼロ**。`configure_app()` に `SESSION_COOKIE_SECURE`/`SAMESITE` 設定がなくFlaskデフォルト依存。7.1のCookie項は「追加」ではなく「新規実装」。
- **`recovery_code_issued_at` カラムは存在するが検証コードで未使用**。復旧コードの期限化は新カラム不要、既存カラムの活用で済む（6.1/7.3に反映）。
- **`get_session_user` / `/api/entry` が毎回 `issue_recovery=True` でトークンを再発行**している（`app.py`）。このため**クライアント保存済みの端末トークンは常に陳腐化**しており、現状のままでは「既存ユーザーの移行アンカー」として信頼できない（3.2のP0「再発行」と4・Phase 2・Q26-003に直結する移行リスク）。
- **room state内の所有者情報が二重持ち**：各キャラの `owner_id`（UUID）と別途 `character_owners` 辞書（`manager/room_manager.py`）。Phase 1のplayer membership backfillではどちらを正本にするか決める必要がある。

結論: パスワード画面から着手してはいけない。最初にDB接続、認証主体、セッション、共通認可境界を固定する。さらに**トークン再発行の停止は移行アンカー保全のためPhase 0で先に行う**（4・Phase 0・Phase 2参照）。

---

## 4. 設計上の不変条件

実装方式を選ぶ際も、以下は変更しない。

1. 認証済みユーザーの正本は `session['user_id']` とDB上の `User` である。
2. `username` は表示名であり、認証・所有権・認可のキーにしない。
3. ルーム内権限の正本はDB上のmembershipであり、Flask sessionの `attribute` を正本にしない。
4. Socket接続時に認証し、各イベントではSIDが対象ルームへ参加済みかを共通ヘルパーで検証する。
5. owner/gm/playerの変更・剥奪は、再ログインを待たず既存Socketへ反映する。
6. 未参加者向けルームカードと参加者向けルーム状態は別DTO・別認可経路にする。
7. 短い秘密値は、値のハッシュ、期限、試行上限、失効日時をセットで管理する。
8. 認証失敗レスポンスでは、アカウントの存在有無を判別できる文言を返さない。
9. パスワード、コード、トークン、マスターキーをログ・監査payload・Socket broadcastへ出さない。
10. 既存データ移行はexpand → backfill → cutover → contractの順に行い、単一デプロイで破壊的変更しない。

---

## 5. 対象範囲

### 5.1 対象

- Render/ローカルDB選択と起動時検証
- Cookie sessionと認証済みユーザー解決
- アカウント作成、パスワード設定、パスワードログイン
- 通常ログアウト、完全ログアウト、信頼済み端末トークン
- 既存復旧コードの移行と失効
- 管理者発行のワンタイム・パスワード再設定コード
- app admin、room owner、room gm、room playerの認可
- ルームmembership、参加コード、公開ロビーDTO
- ルーム情報表示・編集
- HTTP/Socket.IO双方の認可テスト
- デスクトップUIと、共通API変更の影響を受けるモバイル版の扱い

### 5.2 対象外

- メール送信によるパスワードリセット
- OAuth、Googleログイン、Discordログイン
- ローカルとRender間のアカウント・ルーム同期
- Tailscale/Neon関連機能の復活
- 複数Render worker対応。現行のworker=1前提は維持する
- 戦闘ルールやスキル仕様の変更

---

## 6. 実装詳細: 推奨データモデル

名称は実装時に微調整してよいが、責務を1列へ詰め込まない。

### 6.1 User拡張

```text
User
  id: UUID文字列（既存）
  name: 表示名（既存、重複可）
  login_name_normalized: ログイン識別子の正規化値（候補、unique）
  password_hash: nullable。既存ユーザー移行中のみnullを許可
  password_changed_at: nullable
  auth_version: integer、default 1
  is_app_admin: boolean（既存）
  last_login: datetime（既存）
```

`auth_version` はパスワード再設定や「全端末からログアウト」で増加させる。sessionにも同値を持たせ、差異があれば認証を失効させる。

### 6.2 TrustedDeviceToken

ブラウザ復旧トークンを `User.recovery_token_hash` 1個で管理せず、端末単位の行へ分離する。

```text
TrustedDeviceToken
  id
  user_id
  selector: unique、公開側識別子
  token_hash: secret部分のハッシュ
  created_at
  last_used_at
  expires_at
  revoked_at
```

- localStorageには `selector + secret` を保存する。
- DBにはsecret平文を保存しない。
- 通常ログアウトは行を失効せず、自動復旧停止フラグをブラウザ側に残す。
- 完全ログアウトは現在のtoken行を失効し、localStorageも削除する。
- 「全端末からログアウト」は全token行を失効し、`auth_version` を増加させる。

### 6.3 OneTimeLoginCode

管理者発行コードはUser列へ直接置かず、発行履歴を独立管理する。

```text
OneTimeLoginCode
  id
  user_id
  code_hash
  created_by_user_id
  created_at
  expires_at
  used_at
  revoked_at
  failed_attempts
```

- 同一ユーザーへの新規発行時は未使用旧コードを失効する。
- 使用判定と `used_at` 更新は同一トランザクションで行う。
- コード認証後は通常sessionを即時発行せず、パスワード設定専用の短命grantを発行する。
- grantではルーム・画像・管理APIを利用できない。パスワード設定完了後に通常sessionへ昇格する。

### 6.4 RoomMembership

```text
RoomMembership
  room_id
  user_id
  role: owner | gm | player
  joined_at
  updated_at
  revoked_at
  updated_by_user_id
```

- `(room_id, user_id)` は有効membershipについて一意にする。
- Room作成とowner membership作成は同一トランザクションにする。
- `Room.owner_id` は移行期間中維持する。owner変更時はmembershipと同一トランザクションで更新する。
- 最後のowner削除は禁止し、先にowner移譲を要求する。

### 6.5 Room拡張

```text
Room
  description
  lobby_visibility: hidden | listed | closed
  recruitment_status
  join_code_hash
  join_code_rotated_at
```

- `hidden`: 未参加者の一覧に出さない。
- `listed`: 安全なカードだけ表示し、参加コード入力を許可する。
- `closed`: 一覧表示の可否は未決定。少なくとも新規membership作成を拒否する。
- 参加コードとGM PINは別の秘密値として扱い、同じ列・同じ用途に流用しない。

---

## 7. 認証・セッション仕様

### 7.1 Cookie

- Render: `SESSION_COOKIE_SECURE=True`
- 全環境: `SESSION_COOKIE_HTTPONLY=True`
- 原則: `SESSION_COOKIE_SAMESITE='Lax'`
- sessionには `user_id`、`auth_version`、認証時刻、必要最小限の状態だけを置く。
- ログイン、復旧、ワンタイムコード交換の直前に `session.clear()` し、古いルーム権限を持ち越さない。
- 認証済みAPIは毎回Userの存在と `auth_version` を確認する共通デコレータを使う。
- **移行期の遷移**: 共通デコレータ導入時、`auth_version` 未保持の既存sessionが存在する。これを「v1とみなして継続」か「即時失効させて再ログイン要求」かを決定し、決定事項ログへ記録する（即時失効を選ぶ場合、導入デプロイ時に全ログイン中ユーザーがログアウトされる点を許容前提とする）。
- 状態変更APIはJSONのみを受け、許可Origin検証またはCSRF tokenを共通適用する。
- **前提確認（未項目）**: RenderでフロントとバックエンドAPI/Socketが**同一オリジンで配信されるか**を確定する。同一オリジンなら `SAMESITE='Lax'` とCookie認証でSocket connectが成立する。別オリジン構成なら `SameSite=Lax` ではSocket connect時にCookieが送られず、認証方式の再検討が必要（Q26として起こす）。

### 7.2 パスワード

- `werkzeug.security.generate_password_hash()` / `check_password_hash()` を使用する。
- パスワードはtrim・Unicode正規化しない。入力された文字列をそのまま照合する。
- 最小長と最大長を定義する。推奨初期値は10〜128文字。
- ログイン識別子はNFKC + casefold等で正規化した別列に保存し、SQLite/PostgreSQLのcollation差へ依存しない。
- 存在しないアカウントでもダミーハッシュ照合を行い、存在確認の時間差を小さくする。
- 連続失敗へレート制限を入れる。ロックアウト値と解除手段は未決事項で確定する。

### 7.3 復旧コード

- 既存復旧コードは「既存ユーザーが初回パスワードを設定する移行手段」として期限付きで残す。期限管理は**未使用の既存 `recovery_code_issued_at` カラムを活用**し、新カラム追加を避ける。
- 新しい通常アカウントの恒久的なログイン手段にはしない。
- 使用成功時はコードを失効し、パスワード設定専用grantへ交換する。
- コード再発行は現在のパスワード再確認、または管理者のワンタイムコード経由にする。

### 7.4 ログアウト

通常ログアウトと完全ログアウトを次のように区別する。

| 操作 | Flask session | 現端末token | 自動復旧 | 他端末 |
|---|---|---|---|---|
| 通常ログアウト | `session.clear()` | 保持 | 明示操作まで停止 | 維持 |
| 完全ログアウト | `session.clear()` | serverで失効しlocalStorage削除 | 不可 | 維持 |
| 全端末ログアウト | `session.clear()` | 全件失効 | 不可 | `auth_version` 不一致で失効 |

通常ログアウト後のログイン画面には「この端末の保存済みアカウントで続ける」を明示表示し、ページロードだけで即時再ログインしない。

---

## 8. ルーム権限仕様

### 8.1 ロール

| ロール | 主な権限 |
|---|---|
| app admin | ユーザー管理、緊急対応。全ルームGMを自動付与しない |
| owner | ルーム削除、owner移譲、gm付与/解除、参加コード再発行、ルーム設定編集 |
| gm | GM向け戦闘操作、ルーム説明・募集状態編集。owner移譲とルーム削除は不可 |
| player | 参加者向け状態閲覧、自分のキャラクター操作、チャット |
| non-member | 安全なロビーカード閲覧と参加コード送信のみ |

緊急管理用8桁コードを使う場合も、暗黙に `session['attribute']='GM'` としない。明示的な管理操作または監査可能な一時昇格フローに限定する。

### 8.2 HTTP境界

| API | 必要権限 | 返却/更新範囲 |
|---|---|---|
| `/api/get_session_user` | 認証済み | 自分の安全なプロフィールのみ |
| `/api/admin/users` | app admin | 管理用ユーザー一覧 |
| `/api/admin/user_details` | app admin | 対象ユーザーの管理情報 |
| `/list_rooms` | 認証済み | non-memberには安全なカード、memberには自分のroleを追加 |
| `/load_room` | 有効membership | 参加者向けルーム状態 |
| `/save_room` | 原則廃止 | クライアントからの全状態上書きを許可しない |
| `/api/get_room_users` | 有効membership | 参加者一覧。必要最小限の表示情報のみ |
| ルーム設定更新 | owner/gm | 許可フィールドだけ個別更新 |
| ルーム削除 | owner | 再認証または明示確認を要求 |

`/list_rooms` の未参加者向けDTOに、`owner_id`、参加者一覧、GM情報、ログ、キャラクター、画像URL、参加コードを含めない。

### 8.3 Socket.IO境界

- `connect` では有効な認証sessionを要求する。匿名接続を継続する場合も認証前イベントを明示的に限定する。
- `join_room` はpayloadのユーザー名・roleを無視し、sessionのuser_idとDB membershipから参加可否・roleを解決する。
- 各イベントで `request.sid` がpayloadのroomへ参加済みか検証する。
- チャット投稿者名はサーバー側のユーザー情報から設定する。
- GM専用イベントは共通 `require_room_role(room, {'owner', 'gm'})` を通す。
- role剥奪時は該当user_idのSIDキャッシュを更新し、必要ならroomからleaveさせる。
- HTTPとSocketで別々の権限ロジックを複製せず、`manager/room_access.py` 相当へ集約する。

---

## 9. 実装フェーズ

### Phase 0: 分離保証とセキュリティ基盤

目的: 新機能を載せる前に、誤DB接続・失効不能session・既存の無認可経路を固定する。

実装内容:

- Renderでは `DATABASE_URL` 未設定または非PostgreSQLなら起動失敗させる。
- ローカルでは環境変数 `DATABASE_URL` を無視するテストを追加する。
- Cookie属性（`SECURE`/`HTTPONLY`/`SAMESITE`）を新規設定する（現状未設定）。
- 認証済みUser解決と `auth_version` 検証を共通デコレータへ集約する。移行期は `auth_version` 未保持の既存sessionの扱い（v1扱いか即時失効か）を7.1の決定どおり適用する。
- **`get_session_user`／`/api/entry` の毎回トークン再発行を停止する**。再発行を止めないと既存ユーザーの端末トークンが陳腐化し続け、Phase 2の移行アンカーが成立しないため、Phase 0で先に止める。
- 管理ユーザー一覧・詳細をapp admin限定にする。
- `/save_room` は本Phaseで**無害化**する（全状態上書きを拒否、必要なら個別更新APIへ置換）。物理削除はPhase 8で行う。事前にデスクトップ側の呼び出し元を棚卸しする。
- HTTP/Socketのroom参加確認ヘルパー（`manager/room_access.py` 相当）を先に追加する。**membership不在のPhase 0では `Room.owner_id` とroom state内の所有者情報による暫定判定**で始め、インターフェースを固定する。Phase 5でmembership正本へ無改変で差し替える。
- 代表的な読み書き経路（`/load_room`・`/save_room`・主要Socketイベント）へ拒否テストを入れる。
- 失敗した必須DB migrationで起動を継続しない（現状はエラー継続のfail-safe）。**fail-fast切替の前に、Renderプロダクションのバックアップに対して現行スキーマでdry-runし、潜在的な失敗が無いことを確認する**。

完了ゲート:

- Phase 0が通るまでパスワードUIを追加しない。
- 非参加者が既存API/Socketを直接叩いてルーム状態を読めない・変更できない。
- トークン再発行が停止し、既存の端末トークンが安定して照合できる。

実装進捗（2026-06-21・PR-26-01 第1弾）:

- [x] Render `DATABASE_URL` 未設定/非PostgreSQLで起動失敗（`app._get_database_uri`）。`tests/test_database_environment_guard.py`。
- [x] Cookie属性 `HTTPONLY`/`SAMESITE=Lax`/`SECURE`(本番のみ) を設定（`configure_app`）。
- [x] `session_required` がUserの実在を確認（削除済みユーザーを401で失効、`session.clear()`）。`get_session_user` も削除済みユーザーを復活させない。
- [x] トークン毎回再発行の停止（`upsert_user` は未発行時のみ発行）。`tests/test_user_recovery.py` を新仕様へ更新。
- [x] 管理ユーザー一覧・詳細をapp admin限定（`_require_app_admin`、403）。
- [x] 認証境界テスト `tests/test_phase0_auth_boundary.py`（全合格、回帰なし）。
- [ ] `auth_version` の本格適用は専用列の追加が必要なため、スキーマ拡張（Phase 1）と同時に行う。Q26-015の決定（未保持sessionは即時失効）を適用する。
- [ ] migration fail-fast化は、Renderプロダクションのバックアップへのdry-run確認後に実施する。

実装進捗（2026-06-22・PR-26-01 第2弾）:

- [x] `manager/room_access.py` 暫定ヘルパーを新設（`owner_id`／`user_sids`在室／キャラ所有による判定。Phase 5でmembership正本へ無改変差し替え予定。`resolve_room_role`/`user_can_access_room`/`is_sid_in_room`/`is_user_in_room` を公開）。
- [x] `/save_room` を所有権ベース認可に（owner か在室参加者のみ。非参加者は403）。デスクトップの `tab_battlefield.js`・`visual_ui.js` は在室中のみ呼ぶため非破壊。mobileは `/save_room` 未使用。
- [x] Socket `connect` を未認証拒否、`join_room` を認証必須化＋payloadのusername/role不信頼（sessionから採る）。
- [x] `request_chat`／`request_log`／`request_select_resolve_sync` に SID-room 紐付け検証を追加し、別ルームへの覗き見・書き込みを遮断。チャット/ログ投稿者名はサーバー側の在室情報から確定。
- [x] テスト追加 `tests/test_room_access.py`／`test_room_access_http.py`／`test_room_access_socket.py`（全合格、回帰なし）。
- [x] **`/load_room` を参加者ゲートに**（2026-06-22・Q26-012決定後）：`enter_room` 成功を `session['entered_rooms']` に記録し、`/load_room` は入室済みか owner/参加者のみ200、非参加者は403。PC版は `enter_room → load_room` の順で呼ぶため非破壊。
- [x] **`/mobile` 停止**（モバイル版開発停止の方針）：`/mobile` とモバイルアセットの直接読み出しを404で停止（`serve_mobile_index`／`serve_static_files`）。`tests/test_mobile_suspended.py`。
- [ ] 残りのSocketイベント（battle/char/items/exploration）の全面棚卸しはPhase 5で実施。

別件（Phase 0と無関係・既存の赤）: `tests/test_python_module_size_guard.py` が `manager/game_logic.py` の1500行超過で失敗中。本計画の変更前から赤であり、分割またはLEGACY_FILE_CEILINGS登録で別途解消する。

### Phase 1: スキーマexpandと既存データbackfill

目的: 現行コードと互換なnullable列・新規テーブルを先行導入する。

実装内容:

- User拡張、TrustedDeviceToken、OneTimeLoginCode、RoomMembership、Room拡張を追加する。
- 既存 `Room.owner_id` からowner membershipを作る。
- room state中のキャラクター所有者からplayer membership候補をbackfillする。**正本はキャラ単位の `owner_id`（UUID）とし、`character_owners` 辞書は補助参照に限定する**（二重持ちのため、不一致時はdry-runへ出す）。
- owner不在・重複表示名・不明な所有者をdry-runレポートへ出す。
- migrationはPostgreSQL/SQLiteの双方でidempotentにする。

完了ゲート:

- 同じmigrationを2回実行しても壊れない。
- 途中失敗時にどのrevisionまで適用されたか判定できる。
- 旧コードでも新スキーマ上で起動できる。

実装進捗（2026-06-22・PR-26-02 第1弾）:

- [x] User拡張（`login_name_normalized`(unique index)／`password_hash`／`password_changed_at`／`auth_version` default 1）、Room拡張（`description`／`lobby_visibility` default hidden／`recruitment_status`／`join_code_hash`／`join_code_rotated_at`）を `models.py` に追加。
- [x] 新テーブル `TrustedDeviceToken`／`OneTimeLoginCode` を追加（FKは `ondelete=CASCADE`／`SET NULL`）。
- [x] `manager/db_migration.py` を idempotent に拡張（旧スキーマへ列追加・再実行安全・unique index は IF NOT EXISTS）。
- [x] expand とマイグレーション冪等性のテスト `tests/test_phase1_schema_expand.py`（旧スキーマ→列追加→2回実行・新テーブル利用・旧コード互換）。
- [x] **`RoomMember`（既存 `room_members` 採用）**（2026-06-22・本番スキーマ確認後）：本番列(id/room_id/user_id/role/joined_at/granted_by_user_id)をコードに取り込み、`updated_at`/`revoked_at` を追加。有効membership(revoked_at IS NULL)の (room_id,user_id) 部分一意インデックスを張る。`db_migration` を冪等拡張。`tests/test_room_membership.py`。
- [x] **owner/player backfill と dry-run**（`manager/membership_backfill.py`／`scripts/backfill_memberships.py`）：owner_id とキャラ所有者(UUID)から冪等にmembership作成、既存行はスキップ。dry-runで owner不在・重複表示名・所有者不明キャラ・作成見込みを集計。`tests/test_membership_backfill.py`。
  - 運用: 本番では `python scripts/backfill_memberships.py`（dry-run）で集計確認 → `--apply` で実行。起動時自動実行はしない。
  - 注: ローカル `gemtrpg.db` の旧データはキャラ `owner_id` が表示名（非UUID）のため dry-run で「所有者不明」に分類される。本番でも同様の旧データはbackfill対象外として記録される。

本番 `room_members` 確認用SQL（Neon SQLコンソール / Render shell で実行）:

```sql
-- 列定義
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'room_members' ORDER BY ordinal_position;
-- 制約（PK/FK/UNIQUE）
SELECT tc.constraint_type, tc.constraint_name, kcu.column_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
WHERE tc.table_name = 'room_members' ORDER BY tc.constraint_type, kcu.column_name;
-- 行数
SELECT count(*) AS row_count FROM room_members;
```

### Phase 2: パスワード設定・通常ログイン

目的: 名前だけのセッション開始から、本人確認できるアカウント認証へ移行する。

実装内容:

- 新規登録、既存ユーザーの初回パスワード設定、通常ログインAPIを分離する。
- `/api/entry` に新規作成・名前変更・ログインの3責務を持たせない。
- 表示名変更は専用の認証済みAPIへ分離する。
- login_nameの正規化、一意性、パスワードポリシー、失敗制限を実装する。
- 既存復旧コードまたは有効な端末tokenから初回パスワード設定へ進める。
- Renderで名前だけのログインを無効化する。

実装進捗（2026-06-22・PR-26-03）:

- [x] ロジック層 `manager/account_auth.py`（login_name正規化 NFKC+casefold・一意、パスワードポリシー10-128・trim/正規化しない・werkzeugハッシュ、`set_password`/`auth_version`増加）＋ `manager/auth_rate_limit.py`（in-memory、password/コード別上限）。`tests/test_account_auth.py`。
- [x] 新規API: `POST /api/register`（login_name+password）、`/api/login`（レート制限＋汎用エラー＋ダミー照合で存在判別防止）、`/api/set_password`（recover後セッションで既存ユーザー初回移行）、`/api/change_display_name`（表示名分離）。`tests/test_account_auth_routes.py`。
- [x] **auth_version 本格適用（Q26-015 / Phase 0残）**：セッションへ `auth_version` を載せ、`session_required`／`get_session_user` で不一致・未保持を失効。entry/recover も auth_version を載せる。`bump_auth_version` で全端末失効が可能に。
- [x] `/api/entry` に名前だけログイン無効化フラグ `ACCOUNT_DISABLE_NAME_ONLY_LOGIN`（既定off）を追加。cutover時にON。
- [ ] **Renderで名前だけログイン無効化の実施**と**UI連携**はPhase 7（ログイン画面）で行う。それまで `/api/entry` は従来どおり動作（旧導線維持）。
- 注: auth_version 適用により、デプロイ時に既存ログイン中セッション（auth_version未保持）は一度失効する（Q26-015の決定どおり）。クライアントは保存済み端末トークンで自動再認証される。

### Phase 3: ログアウトと信頼済み端末

目的: session失効と端末token失効の意味を明確にする。

実装内容:

- `POST /api/logout` に `mode: session | device | all` を持たせるか、用途別endpointへ分ける。
- 通常ログアウト後の自動復旧を抑止する。
- 完全ログアウトはtokenをserver側でも失効する。
- UIはロビーまたはユーザー設定に置き、確認ダイアログを必須にする。
- ルーム内ヘッダーへ常設しない。

実装進捗（2026-06-22・PR-26-04）:

- [x] `manager/device_token.py`：TrustedDeviceToken の発行/照合/失効/全失効（selector+secret、secretはハッシュ保存、既定30日=Q26-005、last_used_at更新）。`tests/test_device_token.py`。
- [x] `POST /api/logout` mode=session|device|all：
  - session=Flask session破棄のみ（端末トークン保持）
  - device=現端末トークン失効＋旧 `recovery_token_hash` 無効化
  - all=全端末トークン失効＋`auth_version`増加（全セッション失効）
  - `tests/test_logout_tokens.py`（device/all失効・別セッション失効を検証）。
- [ ] **クライアント移行（localStorage selector+secret・通常ログアウト後の自動復旧抑止・確認ダイアログ・配置）はPhase 7**。現状は旧 `recovery_token_hash` 方式も併存し、device/allログアウトで無効化される。

### Phase 4: 管理者ワンタイムコードとパスワード再設定

目的: パスワードを忘れた利用者を、平文パスワード共有なしで復旧する。

実装内容:

- app adminだけがユーザー単位でコード発行・再発行・失効できる。
- コード実値は発行直後の一度だけ表示する。
- 有効期限、失敗上限、一回使用、旧コード失効を実装する。
- 使用後はパスワード設定専用grantへ交換し、通常機能へは入れない。
- パスワード設定完了時に全端末tokenを失効し、`auth_version` を増加させる。
- 発行者、対象、発行・使用・失効時刻を監査する。コード値は監査しない。

実装進捗（2026-06-22・PR-26-05）:

- [x] `manager/one_time_code.py`：発行（10文字/15分/旧コード失効=Q26-007）・照合consume（一回使用）・失敗上限5で失効・全失効。コードはハッシュ保存、実値は発行時のみ返す。
- [x] `POST /api/admin/issue_login_code`（app admin限定・監査ログ。コード値はログに出さない）。
- [x] `POST /api/redeem_login_code`：コード使用→**パスワード設定専用grant**発行（レート制限・汎用エラー）。grantは `session_required` を通らずルーム/管理APIに入れない。
- [x] `set_account_password` を grant 対応に拡張：grant経路では設定完了時に `auth_version` 増加＋全端末トークン失効→通常sessionへ昇格。
- [x] 監査はモデル列（created_by_user_id/created_at/used_at/revoked_at）＋ログで担保。`tests/test_one_time_login_code.py`（フルリセットフロー含む）。
- [ ] 管理者UI（発行ボタン・コード一度表示）とユーザー向け再設定画面はPhase 7。

### Phase 5: ルームmembershipとサーバー認可の全面適用

目的: owner/gm/playerを永続化し、全ルーム操作へ同じ認可規則を適用する。

実装内容:

- Room作成者へowner membershipを作る。
- ownerがgm付与・解除、owner移譲、player除名を行えるAPIを追加する。
- Phase 0で固定した `manager/room_access.py` の判定根拠を、暫定の `owner_id`/room state所有者からmembership正本へ**インターフェース無改変で差し替える**。
- 現行 `session['attribute']` と `user_sids[].attribute` を権限の正本から外す。
- HTTPルートと全Socketイベントを棚卸しし、participant/GM/owner要件を一覧化して適用する。
- app adminの自動GM化を廃止する。
- 既存GM PINは移行期間のmembership取得手段に限定し、期限後に廃止する。

実装進捗（2026-06-22・PR-26-06/07）:

- [x] Room作成者へowner membership（`create_room` 同一トランザクション）。
- [x] owner専用メンバー管理API（grant_gm/revoke_gm/transfer_owner/remove_member）。`tests/test_room_member_routes.py`。
- [x] `room_access` の判定根拠を **RoomMember 正本**へ差し替え（インターフェース不変、membership無しのみ移行期フォールバック）。`tests/test_room_membership_authz.py`。
- [x] **app adminの自動GM化を廃止**（`join_room`）。
- [x] GM PIN は GM membership の取得手段に（`join_room` で gm membership を付与）。
- [x] **権限の正本を membership に**。`session['attribute']`／`user_sids[].attribute` は正本ではなく、**join時にmembershipから導出・role変更時に同期されるサーバー側の派生キャッシュ**とする（クライアントから偽装不可）。

設計判断（attribute の扱い）: socketイベントは引き続きサーバー側 `user_sids[].attribute` を読むが、その値は membership から導出・同期される。これにより worker=1/eventlet で毎イベントDB再解決のコストを避けつつ、正本は membership に一本化する。`room_access.sid_has_room_role(sid, room, GM_ROLES)` を用意済みで、毎回DB再解決が必要なイベントは個別に切替できる。

全Socketイベント棚卸し（94イベント、`grep '@socketio.on(' events/`）:

- 参加者（在室）必須: チャット/ログ/同期系（`request_chat`/`request_log`/`request_select_resolve_sync` は SID-room 検証済み=Phase 0第2弾）。
- GM相当(owner/gm)必須: `request_gm_*`（apply_buff/remove_buff/apply_state/grant_item/adjust_item）、`request_new_round`/`request_end_round`/`request_reset_battle`/`request_force_end_match`/`request_add_debug_character`、`request_*_preset_*`／`request_bo_*`（戦闘設定・プリセット系）、背景/立ち絵/トークン更新系。現状はサーバー側 attribute(=membership派生) で `!= 'GM'` 判定済み。
- キャラ所有者 or GM: `declare_skill`/`request_use_item`/`request_move_*`/`request_delete_character` 等は `is_authorized_for_character` で判定済み。

- [ ] **残（cutover・実機スモークと同時に実施）**: 上記 GM系イベントの判定を、派生 attribute から `sid_has_room_role` の**毎回membership再解決**へ全面切替する。挙動を変える最大の箇所のため、ローカル起動スモーク（entry→入室→GM操作→保存）で確認しながら行う。PR-26-07 のcutover手順に対応。

### Phase 6: 参加コードと安全な公開ロビー

目的: 未参加者に内部状態を出さず、コード成功後だけmembershipを作る。

実装内容:

- hidden/listed/closedの表示・参加規則を確定して実装する。
- 未参加者向けroom card DTOを専用に作る。
- 参加コード成功とplayer membership作成を同一トランザクションにする。
- 参加コードの再発行、失効、試行制限を追加する。
- 既存memberはコード再入力なしで再入室できる。
- ルーム一覧から `owner_id` 等の内部識別子を除外する。

### Phase 7: ログイン・ユーザー設定・ルーム情報UI

目的: 安全化済みAPIを、迷わない導線で利用できるようにする。

実装内容:

- 通常ログインを主導線にする。
- 新規登録、既存ユーザー移行、コード復旧を補助導線へ分ける。
- パスワード欄をユーザー設定へ常時表示せず、専用モーダルで現在のパスワードを再確認する。
- ルーム情報に説明、募集状態、種別、参加コード管理を表示する。
- 参加コード実値の表示範囲と、owner/gmの編集範囲を分離する。
- `static/js/`・`static/css/` を編集後に `npm run build` を実行し、`static/dist/*` をコミットする。

### Phase 8: 旧方式contractと公開前監査

目的: 移行用経路を閉じ、旧フィールド・旧APIが裏口として残らないようにする。

実装内容:

- 名前だけの `/api/entry`、再利用可能な復旧コード、旧token列を停止する。
- GM PIN互換期間を終える場合は、関連UI・API・列を段階的に削除する。
- `session['attribute']` 依存を検索し、認可用途が0件であることを確認する。
- 未使用の `/save_room` を削除する。
- mobile版を更新できていない場合は、公開導線と `/mobile` を明示的に停止する。
- 公開前の認証・認可・情報漏えいチェックリストを実施する。

---

## 10. 推奨PR分割

| PR | 対応Phase | 内容 | 単独ロールバック |
|---|---|---|---|
| PR-26-01 | Phase 0 | DB分離fail-closed、Cookie新規設定、認証User解決、トークン再発行停止、`/save_room`無害化、暫定認可ヘルパー、既存P0認可修正 | 可 |
| PR-26-02 | Phase 1 | nullable列・新規テーブル・idempotent migration・backfill dry-run | 可。旧コード互換を維持 |
| PR-26-03 | Phase 2 | 新規登録、初回設定、パスワードログインAPIとテスト | feature flagまたは旧導線維持で可 |
| PR-26-04 | Phase 3 | ログアウト、端末token、全端末失効 | 可 |
| PR-26-05 | Phase 4 | 管理者ワンタイムコード、再設定grant、監査 | 可 |
| PR-26-06 | Phase 5（前半） | RoomMembership backfillと認可ヘルパーのmembership差し替え | read-only照合段階なら可 |
| PR-26-07 | Phase 5（後半） | HTTP/Socketのmembership強制、app admin自動GM廃止 | cutover手順が必要 |
| PR-26-08 | Phase 6 | 参加コード、公開ロビーDTO、visibility | 可 |
| PR-26-09 | Phase 7 | デスクトップUI、必要なmobile対応、frontend build | API互換期間中なら可 |
| PR-26-10 | Phase 8 | 旧API/旧列/旧GM PIN経路・`/save_room`物理削除のcontract | 原則ロールバック不可。バックアップ必須 |

認証、membership、公開ロビーを1PRへまとめない。DB変更、サーバー認可、UIを分け、各段階で拒否テストを通す。

---

## 11. 移行・ロールバック方針

1. Render DBの手動バックアップを取得する。
2. 新規テーブルとnullable列だけを追加する。
3. dry-runで既存ユーザー重複、owner不在ルーム、キャラクター所有者不明を集計する。
4. owner/player membershipをbackfillする。
5. 新旧の認可結果をログ比較するshadow modeを短期間設ける。秘密値・ルーム内容はログに出さない。
6. 認可をmembershipへcutoverする。
7. owner不在ルームはfail-closedでhidden/closedにし、app adminが所有者を割り当てる。
8. 安定確認後に旧ログイン・旧復旧・旧GM PIN経路を停止する。
9. contract migrationは別デプロイとし、直前バックアップを再取得する。

ロールバック時に新規テーブルを即削除しない。旧コードが未知の列・テーブルを無視できるexpand設計を維持する。

---

## 12. テスト計画

### 12.1 DB・起動

- ローカルで `DATABASE_URL` が設定されていてもSQLiteを選ぶ。
- Render判定時に `DATABASE_URL` がなければ起動失敗する。
- Render判定時にSQLite URLを拒否する。
- migrationの初回・再実行・途中失敗をテストする。

### 12.2 認証

- 新規登録、重複login_name、正常/異常パスワードをテストする。
- login_nameの大文字小文字・Unicode正規化差をテストする。
- 削除ユーザー、`auth_version` 不一致、期限切れsessionを拒否する。
- ログイン成功時に旧sessionのルーム権限が残らない。
- エラーメッセージからアカウント存在有無を判別できない。
- パスワード・コード・tokenがレスポンスやログへ不要に残らない。

### 12.3 ログアウト・token

- 通常ログアウト後にsession APIが401を返し、自動復旧しない。
- 保存済み端末アカウントの明示操作では復帰できる。
- 完全ログアウト後は同じtokenを再利用できない。
- 全端末ログアウト後は既存sessionと全tokenが使えない。
- 2端末のtokenが互いを意図せず失効しない。

### 12.4 ワンタイムコード

- DBにはコード実値がない。
- 期限切れ、使用済み、失敗上限超過、再発行前コードを拒否する。
- 同時使用でも成功は1回だけになる。
- reset grantでルームAPI・画像API・管理APIへ入れない。
- パスワード設定完了後に他sessionが失効する。

### 12.5 ルーム認可

- non-memberはroom cardだけ取得でき、`/load_room` を403にする。
- playerは他roomへアクセスできない。
- playerはGM/owner操作を実行できない。
- gm権限は別roomへ漏れない。
- app adminであるだけでは任意roomのGM操作ができない。
- owner移譲後、旧ownerはowner専用操作を実行できない。
- role剥奪済みSocketが次のイベントを実行できない。
- payloadのusername/role/room改変で権限を上げられない。
- 未参加者向けDTOにログ、参加者、キャラクター、画像URL、owner_id、参加コードがない。

### 12.6 回帰

- 既存のルーム作成、通常入室、戦闘専用ルーム、画像、キャラクター所有権、戦闘操作を確認する。
- `pytest -q`
- `python scripts/check_text_encoding.py`
- `python scripts/check_mojibake_markers.py`
- フロント変更時は `npm run build` と主要JSの構文確認を行う。
- デスクトップのログイン→ルーム参加→再読み込み→ログアウトを実ブラウザで確認する。
- mobileを維持する決定なら同じ認証・参加シナリオをmobileでも確認する。

---

## 13. 主な対象ファイル

### 既存

- `app.py`: 設定、route登録、旧認証・room APIの分離
- `models.py`: User/Room拡張、新規モデル
- `manager/user_manager.py`: 既存ユーザー・復旧処理の移行
- `manager/auth.py`: 既存GM PIN互換。アカウント認証を混在させない
- `manager/db_migration.py`: revision管理、必須migration失敗時のfail-fast
- `manager/room_manager.py`: username基準の権限依存をuser_id/membershipへ移行
- `events/socket_main.py`: 認証済みjoin、payload不信頼化
- `events/socket_*.py`, `events/battle/*.py`: 共通room認可の適用
- `static/index.html`, `static/js/main.js`, `static/js/modals.js`, `static/js/user_management.js`
- `static/mobile/`: 維持または一時停止の決定後に対応
- `RENDER_SETUP.md`: 必須環境変数、Cookie、migration、ロールバック手順

### 新規候補

- `manager/account_auth.py`: パスワード、session、端末token、reset grant
- `manager/room_access.py`: membershipとHTTP/Socket共通認可
- `manager/auth_rate_limit.py`: 認証・短いコードの試行制限
- `tests/test_account_auth.py`
- `tests/test_logout_tokens.py`
- `tests/test_one_time_login_code.py`
- `tests/test_room_membership.py`
- `tests/test_room_access_http.py`
- `tests/test_room_access_socket.py`
- `tests/test_database_environment_guard.py`

新規ロジックを `app.py` へ積み増さない。`app.py` はroute登録と薄い入出力変換に留める。

---

## 14. 受け入れ条件

- Renderとローカルが誤って同じDBを見る経路がない。
- RenderがDB設定不備のままSQLiteで起動しない。
- 名前だけでは既存アカウントへ入れない。
- パスワード、復旧コード、ワンタイムコード、参加コード、端末token、GM PINが平文保存されない。
- 通常/完全/全端末ログアウトの差がテストとUI文言で一致する。
- 未参加者はルーム内部状態をHTTP/Socketのどちらからも取得・変更できない。
- room roleは別roomへ漏れず、app adminとroom gmが混同されない。
- コード失敗制限、期限、一回使用がサーバー側で強制される。
- 既存ルームのowner移行結果とowner不在ルームの扱いが記録される。
- デスクトップ版とmobile版の公開可否が曖昧なままデプロイされない。
- 全pytest、文字コード、文字化け、frontend buildの該当チェックが通る。
- rollback手順とDBバックアップ確認なしにcontract migrationを実施しない。

---

## 15. 決定事項ログ

| 日付 | 論点 | 決定 | 根拠 |
|---|---|---|---|
| 2026-06-14 | 環境分離 | ローカルとRenderはDB・ユーザー・ルームを共有しない | 検証環境と公開環境の誤操作・情報混在を防ぐため |
| 2026-06-14 | 公開方式 | Tailscale/Funnel/Serve/Neon共有DBを計画対象外とする | Render主軸へ運用を一本化するため |
| 2026-06-14 | アカウント改善 | ログアウト、パスワード、管理者ワンタイムコードを段階導入する | 公開運用で復旧コードだけに依存しないため |
| 2026-06-14 | ルーム権限 | owner/gm/playerをルーム単位で扱う | GM権限の他ルームへの漏出を防ぐため |
| 2026-06-19 | 精査結果 | UI実装より前に、DB fail-closed、認証主体、session、HTTP/Socket認可境界をPhase 0で固定する | 現行の無認可経路へ新しいログインUIだけを載せても公開安全性が上がらないため |
| 2026-06-21 | コード突合 | 3.2の現状診断は実コードと全件一致を確認。トークン再発行停止をPhase 0へ前倒し、認可ヘルパーは暫定(owner_id)→membership差し替えの二段構え、Phase↔PR対応を明記 | 既存ユーザーの移行アンカー(端末token)が再発行で陳腐化し続けており、停止しないとPhase 2が成立しないため |
| 2026-06-21 | Q26-015 | 共通デコレータ導入時、auth_version未保持の既存sessionは**即時失効**させ再ログインを要求する（導入デプロイ時の全ログアウトを許容） | 移行期の判定を単純化し、失効不能sessionを残さないため |
| 2026-06-21 | Q26-014 | フロント/API/Socketは**同一オリジン**（Flask+WhiteNoiseが単一Web Serviceで全配信、JSは相対パス/`io(origin)`で接続）。`SameSite=Lax`+Cookie認証でSocket connectを成立させる | コードで実証（app.py・main.js・Procfile）。別オリジン用の代替認証は不要 |
| 2026-06-22 | Q26-012 | **モバイル版は開発を一時停止し、PC Web版中心で開発する（アプリ全体の方針）。`/mobile` 導線は404で停止** | mobileの同時安全化が負担になり、PC版に集中するため。これにより `/load_room` を参加者ゲート化できる |
| 2026-06-22 | membership方針 | **本番Neonの既存 `room_members` を会員名簿の正本として採用**（新テーブルを作らない）。列: id/room_id/user_id/role/joined_at/granted_by_user_id + 追加 updated_at/revoked_at | 本番スキーマ確認の結果、計画の RoomMembership とほぼ一致するクリーンな構造で、コードに取り込めばスキーマの正をコード側へ寄せられるため（[[project_room_members_external_table]] の助言どおり） |
| 2026-06-22 | 実機スモーク | Phase 0-5 をローカル起動して実機確認、**全項目合格**。entry/register/login/logout・auth_version失効・create_room→owner membership・load_room参加者ゲート(非メンバー403)・owner専用grant_gm(非owner403)・Socket認証あり接続&join_room成功&**認証なし接続拒否** を確認 | auth_version・membership・Socket認可は稼働中アプリ挙動を変えるため、main合流前の起動スモークが必要だった。結果は良好 |

---

## 16. 未決定事項と議論順

上から順に一問一答で決める。前の決定が後続のデータモデル・UIへ影響する。

| 番号 | 論点 | 推奨案 | 未決定のまま着手できない範囲 |
|---|---|---|---|
| Q26-001 | ログイン識別子と表示名を分けるか | 一意のlogin_nameと重複可の表示名を分ける | User migration、登録、ログインUI |
| Q26-002 | 新規アカウントを自己登録にするか | Renderでも自己登録可。ただし一意ID+パスワード必須 | 初回利用画面、荒らし対策 |
| Q26-003 | 既存ユーザーの初回移行方法 | 復旧コード/端末tokenで本人確認後、login_nameとパスワードを設定 | 旧 `/api/entry` 停止時期 |
| Q26-004 | 通常ログアウトで端末tokenを残すか | 残すが自動復旧を停止し、明示ボタンでのみ再利用 | logout API/UI |
| Q26-005 | 端末tokenの有効期限 | 30日を初期値とし、利用時延長の有無を決める | TrustedDeviceToken仕様 |
| Q26-006 | パスワード/コードの失敗制限 | passwordと各コードに別上限を設ける | 公開前セキュリティ試験 |
| Q26-007 | ワンタイムコードの形式・期限 | 読み間違えにくい10文字、15分、5回失敗で失効 | 管理者UI、コードモデル |
| Q26-008 | 既存owner不在ルーム | hiddenかつ参加停止にし、app adminがowner割当 | membership cutover |
| Q26-009 | listed/closedの表示差 | closedはカード表示するが新規参加不可 | 公開ロビーDTO/UI |
| Q26-010 | 参加コードの閲覧者 | ownerのみ実値閲覧/再発行、gmは募集状態編集まで | ルーム情報UI |
| Q26-011 | app adminの緊急ルーム操作 | 明示的な一時昇格+監査を要求 | master key、管理API |
| Q26-012 | `static/mobile/` の扱い | **【確定 2026-06-22】モバイル版は開発を一時停止し、PC Web版中心で開発する。`/mobile` 導線は停止** | Phase 2以降の公開 / `/load_room` ゲート |
| Q26-013 | 画像所有者のUUID移行 | 新規アップロードからUUID化し、旧画像は段階backfill | 名前変更・削除の整合性 |
| Q26-014 | Renderのフロント/API・Socketのオリジン構成 | **【確定 2026-06-21・コードで実証】同一オリジン**。`SameSite=Lax`+Cookie認証を採用 | Phase 0のCookie設定、Socket connect認証(8.3) |
| Q26-015 | 共通デコレータ導入時の既存session(auth_version未保持)の扱い | **【確定 2026-06-21】即時失効させ再ログイン要求（導入時の全ログアウトを許容）** | Phase 0のauth_version検証 |

着手順の補足: 上記のうち**Q26-014（オリジン）とトークン再発行停止はPhase 0の前提**であり、Phase 2の移行成立に直結するため最優先で確定する。Q26-001（login_name分離）はUser migration全体の前提として従来どおり先行する。

すべてを実装開始前に決める必要はない。ただし各行の「着手できない範囲」へ進む前に決定事項ログへ記録する。

---

## 17. 実装開始前チェックリスト

- [ ] Q26-001〜Q26-004、およびQ26-014（オリジン構成）・Q26-015（auth_version遷移）を決定事項ログへ記録した。
- [ ] Phase 0の拒否テスト一覧を先に作成した。
- [ ] `/save_room` のデスクトップ側呼び出し元を棚卸しした（mobileは未使用を確認済み）。
- [ ] トークン再発行停止による既存ユーザーへの影響を確認した。
- [ ] 全HTTP routeとSocket eventの必要role一覧を作成した。
- [ ] 既存DBの重複表示名、owner不在ルーム、所有者不明キャラクターをdry-run集計した。
- [ ] Render DBバックアップとrollback担当を確認した。
- [ ] mobileを同時対応するか、一時停止するか決定した。
- [ ] frontend変更を含むPRで `npm run build` を実行する手順を明記した。
