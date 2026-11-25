# Tier・固定階の編集画面の試作

`node scripts/hollow_tier_proto/build.mjs` を実行し、`_local/hollow_tier_proto/index.html` をブラウザーで開く。

「階」のタブと一覧から資源を開く。右下で「遭遇表」「イベント」「階の地図」の A・B を個別に切り替える。入力値は切り替え後も保持され、「保存」は開いている間だけ反映する。

遭遇表の割合は通常・精鋭ごとの合計を、イベントの割合は5種類の合計を基準にする。合計が0なら「—」を表示する。地図は未保存の階範囲にも追従する。固定階の印は Tier 範囲と独立し、固定階のある階は範囲外でも抜けに数えない。

`node scripts/hollow_tier_proto/check.mjs --shots` で Chrome と Python の Playwright を使い、操作・コントラスト・表示幅を確認して撮影する。確認画像は `_local/hollow_tier_proto/` に出力する。

本物の画面は、隔離 DB の写しを `_local/agent_db/gemtrpg.db` に用意し、`python -m scripts.hollow_tier_proto.check_app --app-python .venv/Scripts/python.exe` で確認する。確認画像は `_local/pr35_4_shots/` に出力する。
