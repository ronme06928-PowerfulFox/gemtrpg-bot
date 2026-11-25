# ホロウデータと淵の夜

`node scripts/hollow_data_proto/build.mjs` で生成した `_local/hollow_data_proto/index.html` をブラウザーで開く。メインメニューの「ホロウデータ」からユニット・Tierへ進み、右下の「A 青緑」「B 紫」「夜色と金と比較」で配色を切り替える。ユニット管理の「その他」から、セッション用ユニットの複製も試せる。変更はページを開いている間だけ保持する。

共通部品はアプリの CSS を読み込む。淵の夜の値と等級の色は `themes.css`、試作固有の配置は `page.css` に置く。対比値はブラウザーで両案のテーマ変数から計算する。作品の背景には既存の「暗い遺跡洞窟」を使う。

`node scripts/hollow_data_proto/check.mjs` で操作と配色を検査し、同じフォルダに1280pxと680pxの確認画像を出す。撮り直しは同名の画像を上書きする。検査は Python の Playwright と Chrome を使う。

実アプリの検査は `_local/agent_db/gemtrpg.db` に DB の写しを用意し、Playwright が入った Python で `python scripts/hollow_data_proto/check_app.py` を実行する。アプリの依存が別の環境にあるときは `--app-python .venv/Scripts/python.exe` を付ける。検査は `app.py --db` で確認用アプリを起動し、区分・保存・複製・未保存確認と主な文字・枠の対比を確かめ、`_local/pr35_2_shots/` に1280pxの写真を出す。検査で作るユーザーと資源は写しに保存される。
