# 共通クレジット

動画のナレーションを終えた後、最後に5秒表示する1枚です。R2-1の配置見本を作成しました。本編への接続は確認後のR2-2で行います。

## 管理するもの

- `credits.json`：作品名「ジェムリアTRPG」と発行元「創作ゆる大地」。表記は `typst_manual/publication_info.typ` を参照します。本の発行日は動画へ転記しません。
- `credits.mjs`：共通HTMLの生成関数。動画タイトルと使用素材の一覧を引数に渡します。表示文字をエスケープします。
- `credits.css`：1280×720、BIZ UDPゴシック、本文27px・タイトル46pxの配置。
- 各動画の `credits.json`：動画タイトル、使用音声・素材の一覧。今回の設定は `01_1ラウンドの流れ/credits.json` です。別動画へ流用する際は使う素材に合わせて更新します。

ロゴは `typst_manual/assets/gemuria_logo.png` の全画像をそのまま使います。加工・切り抜きは行いません。
egatariは作業フォルダ外を読み込まないため、生成時にHTML・CSS・ロゴ・テーマを作業フォルダ内へ配置します。

## 見本の生成と確認

リポジトリのルートからPowerShellで実行します。egatariは外部のv0.4.5を使います。

```powershell
$creditsEgPlugin = 'C:/Users/yharu/tools/egatari-studio'
$creditsPreview = Join-Path (Get-Location) 'typst_manual/動画/_local/credits-preview'
node --test typst_manual/動画/scripts/test-credits.mjs
node typst_manual/動画/scripts/prepare-credits-preview.mjs
npm --prefix $creditsEgPlugin run build -- "$creditsPreview/deck.html"
npm --prefix $creditsEgPlugin run check -- "$creditsPreview/deck.html"
node typst_manual/動画/scripts/verify-credits.mjs $creditsEgPlugin
npm --prefix $creditsEgPlugin run sheet -- $creditsPreview --tiles --cols 1 --width 1280
```

出力は `_local/credits-preview/out/` の `deck.html`、`credits-0.png`、`sheet.png` です。PNGはブラウザ検証で生成します。
生成物はGit管理外です。元の全編デッキ・R1・音声manifestは書き換えません。

5秒のMP4も確認する場合は、ffmpegをPATHへ通し、続けて実行します。

```powershell
node "$creditsEgPlugin/render/render.mjs" "$creditsPreview/out/deck.html" --out "$creditsPreview/out/motion" --full --fps 24 --scale 1
```

## 確認結果（2026-10-25）

- テスト2件通過。タイトルや素材を差し替えられ、使っていない素材名を残しません。
- egatari check：エラー0・警告1。口述原稿なしの警告は、無言の最終スライドに対するものです。
- `talk`・`lecture`・`video` モードで文字の大きさ・欠け・配置を検証しました。字幕がなくてもクレジットを表示します。
- 0秒・2.5秒・4.99秒のPNGが一致し、静止表示を確認しました。元PNGと配置したロゴのSHA-256も一致しました。
- MP4の映像は24fps・120フレーム、5秒。AACの末尾を含むファイル全体は5.023秒です。
- v0.4.5は `.body` が既定の本文領域を右にはみ出すとR-fitエラーにします。本文コンテナを左右44pxの内側へ置いて解消しました。最終checkの警告は前述の無言表示だけです。

表示する情報量が増える場合は、文字を縮める前に5秒で読める量かを確認します。
