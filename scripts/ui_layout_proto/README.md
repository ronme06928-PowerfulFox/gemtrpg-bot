# 管理画面と配色の比較

`node scripts/ui_layout_proto/build.mjs` で `_local/ui_layout_proto/index.html` を生成し、ブラウザーで開く。

- メインメニューの上段は「セッション」（ルーム一覧）と「ダンジョン」（準備中）。中段はマイキャラクターと使い方、下段はユニット管理とマスターデータ。右上からアカウントを開く。管理画面では一覧・入力の復帰、差分の比較・承認と次の案件への移動を試せる。
- 右下で制作者・GM・一般、13px／16px、宝石A／宝石Bを変更する。見た目は `manuals/projects/app_foundation/ui/ui_template.html` の「紙と金・控えめ」。承認の流れを見るには制作者の「アプリ管理者」をオンにする。ルーム外のGMは公開データを閲覧できる。
- 宝石Aは分類ごとの色を優先し、宝石Bは近い用途を同系統にまとめる。本文色と操作色は共通で、分類の違いは印と淡い面に出す。
- キャッシュを元に、承認案件・制作者限定データ・ルーム一覧の比較用データを用意する。保存と承認は試作を開いている間の状態に反映する。

`node scripts/ui_layout_proto/check.mjs` で Chrome の操作とコントラストを検査する（Python の Playwright が必要）。

## 本物のマスターデータの画面で試す

`node scripts/catalog_preview/pr19/build.mjs` のあとに `node scripts/ui_layout_proto/build-real.mjs` を実行し、`_local/ui_layout_proto/master_real.html` を開く（大きいので `local-outputs` のサーバー経由で `http://127.0.0.1:8765/ui_layout_proto/master_real.html`）。本物の管理画面のコードを偽物のサーバーで動かし、`real_skin.css` で「紙と金・控えめ」を上書きする。左下で今の見た目と切り替える。
