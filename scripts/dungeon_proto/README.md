# ダンジョン入口の試作

`node scripts/dungeon_proto/build.mjs` を実行し、`_local/dungeon_proto/index.html` をブラウザーで開く。メインメニューの「ダンジョン」から移動する。

右下で「部屋」の行／札、「入口」の控えめ／見出し、「一覧」の参加中／空を個別に切り替える。「新しく作る」と「参加コードで入る」は表示中の一覧に部屋を加える。試作用の参加コードは `GEM-1423`。ほかのコードでは入力欄の下にエラーが出る。

`node scripts/dungeon_proto/check.mjs --shots` で Chrome と Python の Playwright を使い、操作・コントラスト・表示幅を確認して撮影する。画像は `_local/dungeon_proto/` に出力する。

本物の画面は隔離 DB の写しを `_local/agent_db/gemtrpg.db` に置き、`python -m scripts.dungeon_proto.check_app --app-python .venv/Scripts/python.exe` で確認する。画像は `_local/pr35_5_shots/` に出力する。
