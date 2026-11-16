# ルームと戦闘の夜色と金の試作

リポジトリのルートで実行します。撮影には Python の Playwright と Chrome が必要です。

1. `npm run build` で本体のバンドルを作ります。
2. `python app.py --db _local/agent_db/gemtrpg.db` で確認用のアプリを起動します。確認用 DB が空ならマスターデータを JSON キャッシュから取り込みます。
3. 別の端末で `python scripts/ui_room_night_proto/shots.py` を実行します。ローカルのアプリの API を使い、確認専用のアカウントとルームを作って撮影します。
4. `node scripts/ui_room_night_proto/build.mjs` を実行し、`_local/ui_room_night_proto/index.html` を開きます。画像を押すと原寸で表示されます。

撮影スクリプトは現行の画面と、`night.css` を適用した同じ画面を撮ります。戦闘結果はアプリの宣言・解決を通して生成します。FP は盤面の現行表示に合わせ、丸い札で比較します。右下の知らせは配置と読みやすさを確認するための試作です。比較のため成功と誤りを同時に表示しています。

待機列の置き換え前後を撮る場合は、各バージョンの本体で `shots.py --queue-only <出力先>` を実行します。確認後はアプリを停止し、確認専用 DB と比較済みの写真を片付けます。
