# 宣言の応答計測

対象: アプリ基盤プロジェクト `PERF-BASELINE`。宣言のpreview/commitの往復、サーバー内、Store通知と宣言パネルの同期更新、描画機会までの待ちを分ける。計画58の演出・SE・文字・色は変更しない。

## 操作

計測対応を含む同じ版のフロントエンドとサーバーを使用する。DevToolsのConsoleで次を実行する。

```javascript
GemDicePerf.start()
```

通常の画面から宣言の選択・確定を数回行い、結果を見る。

```javascript
GemDicePerf.report()
GemDicePerf.stop()
```

`clear()` は保留と結果を消す。`start()` は保留と以前の結果を消して新しく計測し、`stop()` は保留を破棄して確定済みの結果を残す。再読み込みすると無効へ戻る。操作の自動実行や記録の外部送信は行わない。計測のために本番へ反映する場合も、commit / pushのユーザー指示が必要。

## 結果の読み方

- `rtt_ms`: 送信からACK受信。クライアントの単調時計で測る。
- `server_ms`: サーバーの受信ハンドラ内経過時間。認証や計算・配信構築/送信を含み、ACKの送信は含まない。
- `remaining_rtt_ms`: RTTからserver_msを引いた残り。ネットワークだけでなくサーバー到着前の待ち・Socket処理・クライアント側待ちなどを含む。
- `send_to_state_ms`: 送信から同じ要求IDの戦闘状態受信まで。
- `store_dispatch_ms`: コアの受信ハンドラでStore更新・同期購読処理を終えるまで。
- `declare_panel_ms`: その同期処理内でDeclarePanelのrenderに費やした合計。
- `receive_to_frame_ms`: 受信から2回のRAFまで。描画機会の目安。タブ非表示・RAF未提供・期限切れは数値を捏造せず状態を記録する。
- `stages_ms`: サーバーのredirect、ready、state deliveryの各区間。区間外の時間もあるため合計がserver_msと一致するとは限らない。

未対応サーバー・拒否・期限切れは `complete` の標本へ混ぜない。接続方式を併記し、初回・通常・多キャラ、多スロット、タブ表示状態をそろえる。サーバーとPCの時計の絶対値を引き算しない。

通常時は無効。有効時は要求ID・ACK・時刻採取・RAFの負荷が加わる。計測結果だけで元の動作と完全に同じ負荷とは扱わない。実装仕様は[B03](../implemented/B03_SelectResolve_Spec.md#宣言の任意計測)、[E01](../implemented/E01_Visual_Battle_Architecture.md#宣言の応答計測)を正とする。

## ブラウザーでの部品確認

`tests/support/intent_performance_browser.mjs` は合成状態と模擬通信だけを使う、宣言パネル・Store・2回のRAFの確認用fixture。アプリサーバーや本番へは接続しない。ここで見える往復とserver_msは模擬条件であり、本番の実測には使わない。fixtureをesbuildでブラウザー向けにまとめ、確認用HTMLと既存のCSSを一時配置して、127.0.0.1の専用サーバーで開く。確認後は一時サーバーとHTML/JSを片付け、再生成用fixtureを保持する。

## 2026-11-01の検証結果

- IDの形式・無効時の従来動作、拒否・例外、スレッド/greenlet間の分離、実Socket.IOのACKと通知、認可の保持を確認した。
- フロントはACK/状態の到着順、無関係なID、非表示タブ、期限切れ、停止、上限、未対応ACK、実SocketClient/Store/DeclarePanelの接続をNodeで検証した。
- 全体テストでギャラリーのタイマーなし実行が1件失敗した。無効時のコンストラクタがタイマーを要求しないよう遅延参照へ修正後、ギャラリーを含む関連29件と全件 `1452 passed / 5 skipped`（205.81秒）が成功し、終了時の保存待ち0件を確認した。スキップ5件には明示有効化する使い捨てPostgreSQL検証3件を含む。その検証はバックアップ整備時に別途実施済み。
- `npm run build` が成功し、配信バンドルとindex.htmlを更新した。battleのハッシュは `e748257ce2c1`。通常のapp JS/CSSバンドルは変更なし。
- 実ブラウザでギャラリーの描画と、合成データの宣言パネルでpreview/commitを確認した。両方 `complete`、保留0件、両方のRAFを `observed` と記録した。通信はfixtureの模擬処理であり、server_msも固定0なので、所要時間を本番・実サーバーの評価には使わない。
- 確認用HTTPサーバーとタブを停止し、一時HTML/JSを削除した。fixtureと最新検証結果 `_local/performance/intent_measurement_validation.json` は保持した。本番・契約・既存バックアップを変更していない。

残る確認: 実アプリを通る通常回線・多キャラ条件での計測、Render/eventletの時間、描画機会と実表示の対応。本番へ出す場合は `main` のcommit/pushがRender反映となるため、[AGENTS.md](../../AGENTS.md)の明示指示を受けてから行う。
