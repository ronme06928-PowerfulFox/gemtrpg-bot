# PostgreSQL手元バックアップ

作成日: 2026-11-01。課題: `OPS-BACKUP-MANUAL`。現在のNeonの履歴復元6時間とは別に、セッション後・更新前のDBをPCへ保管する。

## 方式と対象

標準の `pg_dump` によるcustom形式の論理バックアップを使う。NeonのConnection poolingをオフにした直接接続を使用する。[Neon公式手順](https://neon.com/docs/manage/backup-pg-dump)と[PostgreSQL pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html)を参照。

- CLIは `scripts/backup_postgres.py`。アプリ・`.env`・現役SQLiteを読み込まず、専用の接続情報だけで動く。
- 接続URLは端末で非表示入力する。自動実行の検討用に専用環境変数 `GEMDICE_BACKUP_DATABASE_URL` も使えるが、引数やログには載せない。
- DB接続パスワードは一時的なpgpassファイルへ書き、終了時に削除する。子プロセスへ接続URL全体や `PGPASSWORD` を渡さない。外部接続はTLSを必須とする。
- `pg_dump`は読取専用接続で取得し、元DBの書換えや復元は行わない。バックアップはDBにコミット済みの状態を含み、保存待ち中のメモリ状態は含まない。
- 所有者・メンバー権限・持ちキャラ・ログ等のアプリDBテーブルを含む。PostgreSQLのクラスタ全体のロール・接続設定、Cloudinaryの画像実体、ソースは対象外。

## 保存と検査の契約

保存先はGit除外の `_local/backups/postgres/`。成功した1回分ごとに日時とランダムIDのフォルダを作り、`database.dump` と `manifest.json` を保管する。既存バックアップの上書き・自動削除は行わない。

1. 取得中は新しい日時フォルダへ保存し、未完了マーカーを置く。
2. `pg_restore --list` でアプリの主要テーブルを確認する。
3. 接続先を指定しない `pg_restore --file=-` の出力を破棄し、アーカイブ全体が読み出せることを検査する。DBへ復元しない。[pg_restoreの動作](https://www.postgresql.org/docs/18/app-pgrestore.html)を参照。
4. サイズ・SHA-256・日時・ツールの版をmanifestへ保存してから、未完了マーカーを除去して確定する。Windowsで検査直後のフォルダ移動が拒否される場合にも備え、フォルダ名は変更しない。接続URL・DB接続パスワードはmanifestに書かない。
5. 失敗・タイムアウトでは成功扱いにせず、その回の未完了ファイルと一時認証情報を片付ける。既存の成功済みバックアップは変更しない。

アーカイブ読込検査は、実DBへ復元した検証とは区別する。実際の復元試験は、同梱の結合テストで作る使い捨てのローカルPostgreSQLに限る。本番への復元コマンドはCLIに設けない。

## 初回準備と実行

PostgreSQLクライアントは、PATH上、`--pg-bin`で指定したフォルダ、または `_local/tools/postgresql/bin/` から探す。`pg_dump` と `pg_restore` のメジャー版をそろえ、サーバーより古いpg_dumpは使わない。配布元は[PostgreSQL公式のWindows案内](https://www.postgresql.org/download/windows/)から案内されるEDBのバイナリを使用する。

普段は `scripts/backup_postgres.cmd` をダブルクリックする。端末が開き、接続情報を非表示入力して1回分を保存する。接続URLの入力前にツールの配置を確認したい場合は、リポジトリ直下で次を実行する。

```powershell
python scripts/backup_postgres.py doctor
python scripts/backup_postgres.py backup
```

Neonの `GemDiceBot` → `production` → Connectを開き、Connection poolingをオフにした、`postgresql://`から始まるURL部分だけを端末の非表示入力へ貼り付ける。`psql`コマンドや外側の引用符は含めない。チャットには送らない。SQL EditorやRestore、Create、Upgradeは使用しない。

既存バックアップの再検査:

```powershell
python scripts/backup_postgres.py verify "_local/backups/postgres/<保管フォルダ>"
```

DBバックアップにはアプリのユーザーデータが入るため、Git・公開フォルダ・共有先には置かない。`_local/backups/` は使い捨て出力ではなく保管原本であり、確認画像等の片付けでは削除しない。接続情報を保存しなくても、作成したDBバックアップ自体の保管は必要である。

## 自動の控え（2026-11-17）

決めたこと（論点と根拠）は[自動化比較の決定事項](../projects/app_foundation/backup_automation_options.md#決定事項2026-11-17マスターデータベースプロジェクトの今後の順番2)。この PC の Windows タスクが毎日12時に `backup --auto` を動かし、その時刻に PC が止まっていたら次の起動時に取る。

### 仕組み

- 接続 URL は、手動の控えと同じ直接接続 URL（Connection pooling をオフにしたもの）。Windows の資格情報マネージャー（汎用資格情報 `GemDiceBot/backup-database-url`）に置き、`backup --auto` がそこから読む。環境変数 `GEMDICE_BACKUP_DATABASE_URL` があればそちらを先に使う。URL はタスクの引数・ログ・manifest に載せない。
- 取得と検査は手動と同じ。manifest に `trigger`（`auto` か `manual`）を書く。それ以前の控え（`trigger` なし）は手動として扱う。
- 自動で取れたあと、古い自動の控えを消す：直近7日は日ごとに最新の1つ、その前の12週の間は週（ISO 週）ごとに最新の1つを残し、それより古い自動の控えは消す。消すのは `trigger: auto` で、未完了の印が無く、中身が `database.dump` と `manifest.json` だけのフォルダに限る。手動の控えと未完了のフォルダは消さない。
- 結果は `_local/backups/postgres/auto.log` に1行ずつ残す（日時・成否・理由。接続情報は書かない）。失敗したときは Windows の通知（PowerShell の通知）を出す。タスクは `pythonw.exe` で動かすので、黒い窓は出ない。
- `python scripts/backup_postgres.py status` で、最後に取れた控えの日時と種類、`auto.log` の最後の行を出す。最後に取れた控えが2日（48時間）より古いと注意を出し、終了コード1を返す。

### 初回の準備（ユーザーが行う。接続情報はチャット・資料に載せない）

1. PC で `python scripts/backup_postgres.py store-credential` を実行し、手動の控えと同じ直接接続 URL を非表示入力へ貼り付ける。資格情報マネージャーに保存される（形式だけを確かめ、接続はしない）。
2. `python scripts/backup_postgres.py backup --auto` を1回手で動かし、成功することを確かめる。
3. PowerShell で `scriptsegister_backup_task.ps1` を実行し、タスク `GemDiceBot DB backup` を登録する（Python の場所が違うときは `-Python <pythonw.exe のパス>`）。登録はこのユーザーがログオンしているときだけ動く形で、管理者権限は要らない。
4. 翌日以降に `status` で、自動で取れていることを確かめる。

2026-11-17：ユーザーが手順1〜3を済ませた。手で動かした自動の控え（`20261117_032214_92ef40bf7db6`）は成功し、タスクは毎日12時・起動時の取り戻しありで登録された。

URL を変えたとき（パスワードの再発行など）は手順1をやり直す。タスクをやめるときは `Unregister-ScheduledTask -TaskName "GemDiceBot DB backup"`。

## 検証と残る手順

2026-11-01: 接続情報の非表示・pooler/TLS拒否・失敗時の原本保護・途中ファイルの除去・改変検出を確認した。PostgreSQL 18.6を使った取得・検査・別DB復元・認証失敗・破損検出を含め、関連テスト28件が成功（16.77秒）。アプリの10テーブルを対象とし、ルームJSON・所有者・権限・持ちキャラ・保管ログの一致を確認した。目次とハッシュが通る破損アーカイブも読込検査で拒否した。本番データ・接続情報は使用していない。

結合テストは `tests/test_backup_postgres_integration.py`。`RUN_POSTGRES_BACKUP_INTEGRATION=1` のときだけ、127.0.0.1に一時PostgreSQLを起動し、合成データの取得・別DB復元・壊れたアーカイブの拒否・認証失敗を検証する。Windowsサービスには登録せず、終了時にテスト用プロセスを停止する。ループバックの隔離検証に限り `sslmode=disable` を許可する。本番Neonへの外部接続ではTLS必須のままとする。

このPCには公式Windows案内から辿ったEDB PostgreSQL 18.6のbin/lib/shareを `_local/tools/postgresql/` に配置した。配布元・ZIPのSHA-256は同フォルダの `provenance.json` に記録した。Windowsサービス登録・システムPATHの変更は行っていない。`doctor` はpg_dump/pg_restoreとも18.6でreadyを返す。

2026-11-01 00:48 JST: ユーザーがPCの非表示入力で初回取得に成功した。保管先は `_local/backups/postgres/20261101_004844_5fab5819fd23/`。52,204 bytes、publicの11テーブルを含む。作成後の `verify` でもサイズ・SHA-256・アーカイブ全体の読込検査が成功した。この取得分を実DBへ復元する試験は未実施。接続URL・パスワードはチャット・資料へ受け取っていない。Renderの実接続先との最終照合は別途残る。

ダブルクリック起動ができない場合は、Windowsキー＋Rで `cmd` を起動し、このPCでは次を実行できた。

```bat
"C:/Users/yharu/anaconda3/python.exe" "C:/Users/yharu/Desktop/TRPG/Gem_DiceBotTool/scripts/backup_postgres.py" backup
```

手動での初回保管は完了し、[自動化比較](../projects/app_foundation/backup_automation_options.md)も作成済み。2026-11-17 に PC の Windows タスクでの自動化を決め、上の「自動の控え」を作った。外部保管先・有料契約は採らない（必要になったら決める）。
