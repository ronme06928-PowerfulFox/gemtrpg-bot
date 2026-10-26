# 動画の共通部品

## S1：共通の動き（計画54）

2026-10-27、承認済みの7部品を制作。既存本編とr3-v2の成果物は変更しない。確認用は `_local/s1-components/`（Git管理外）。本編の台本・声・SEの再制作はS2で行う。

| 部品 | 定義と使用例 | 段階・動き |
| --- | --- | --- |
| 段階表示 | [phase](components/phase/README.md) | ラウンド開始→選択フェーズ→解決フェーズ→ラウンド終了の現在地を光らせる |
| ダイス | [dice](components/dice/README.md) | 1段階2.4秒。速度は確定値がスロットへ移り、威力はダイスが式の出目へ入り、=直後に合計 |
| 一撃とHP | [impact-hp](components/impact-hp/README.md) | 1段階2.4秒。一撃の到着後にHP30→21、−9が浮かぶ。動画の説明用 |
| FPの丸 | [fp](components/fp/README.md) | 勝利と効果の2段階。光と理由札を添えて0→1→3 |
| 効果文の枠 | [effect-frame](components/effect-frame/README.md) | 2段階。r3-v2と同じ3.5秒のタイミング枠、次の段階の0.7秒で全文へ拡張 |
| 背景 | [background](components/background/README.md) | 初期表示から採用した青空の遺跡を全面に表示。0.8秒で明るさを整える |
| GMの吹き出し | [gm-bubble](components/gm-bubble/README.md) | 1段階0.6秒。オパール色 `#a8457f` のGMの札と案内。吹き出しのGM：は外す |

### 組み込み方

1. 必要な `components/<名前>/` をデッキ内の `components/` へコピーし、`motion.css` を読み込む。クラスの色はこのCSSのテーマ変数で割り当てる。
2. 各 `demo.html` は使用例の断片。確認デッキ全体は `scripts/prepare-s1.mjs` が組み立てる。部品の子に表示要素を置き、必要な数値は直下のJSONから渡す。`data-from` と `steps` で本編の段階へ割り当てる。部品は(k,t)から毎回表示を復元し、Infinityはその段階の最終状態。
3. 駒の形・HP/MPバー・FPは既存本編の `app_mock.css` を読み取りコピーする。原典は `static/js/visual/visual_map.js` と `static/css/modules/visual_map.css`。ダイスの行き先のスロットも同じ丸・配色。矢印色は `visual_arrows.js` のマッチ色 `#ffb020`。一撃を含む動きは教材の説明であり、計画52の将来演出の再現ではない。
4. 立ち絵と本から書き出した `figs/die-1.svg`〜`die-6.svg` は既存本編からコピーする。背景は [素材記録](assets/README.md) のPNG。これらをすべてデッキ内へ置く。作業フォルダ外の素材参照はしない。
5. 本文27px・図24px以上。図の領域には `.plot` を付ける。GMと字幕を分ける（確認用の字幕予約帯はy=624〜696）。GMの札の形式と色はユーザー決定済み。S2で使用する吹き出しの文言は絵コンテの提案を確認する。

ダイスの `value` は生の出目ではなく補正を含む確定値。S2-1で計画53の数値にそろえ、速度4+2=6、敵3+1=4、威力4+2+3=9／敵4+1+1=6を使う。S1の速度5+1=6の見本は修正した。威力の例は最後の1d3の出目3を転がし、既に出た2と基礎4へ加える。出目3の位置へダイス自体を入れ、合計9を=の直後に出す。スロット／式の配置は今回の2駒の作例に限定する。

### 確認デッキの再生成

リポジトリのルートからPowerShellで実行する。外部egatariはv0.4.5固定。

```powershell
$s1Engine = 'C:/Users/yharu/tools/egatari-studio'
$s1Preview = Join-Path (Get-Location) 'typst_manual/動画/_local/s1-components'
node typst_manual/動画/scripts/prepare-s1.mjs
npm --prefix $s1Engine run build -- "$s1Preview/deck.html"
npm --prefix $s1Engine run check -- "$s1Preview/deck.html"
node typst_manual/動画/scripts/verify-s1.mjs $s1Engine
$s1Ffmpeg = 'C:/Users/yharu/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.1-full_build/bin'
$env:PATH = "$s1Ffmpeg;$env:PATH"
node "$s1Engine/render/render.mjs" "$s1Preview/out/deck.html" --out "$s1Preview/out/motion" --full --fps 24 --scale 1
node typst_manual/動画/scripts/verify-s1-video.mjs
```

`out/deck.html` は8場面の確認用デッキ、`out/motion/full.mp4` は全体。音声なし。各部品のPNGは `phase-0.6.png`、`dice-slot-0.6.png`／`dice-power-0.6.png`、`impact-hp-1.2.png`、`fp-0.6.png`／`fp-k2-end.png`、`effect-end.png`／`effect-full.png`、`background-end.png`、`gm-end.png`。同じ場所に時刻別のPNGと検証JSONを出す。

### 背景と格子の実アプリ比較

通常は `.claude/launch.json` の `gemtrpg` を起動し、次を実行する。新しいブラウザコンテキストと新規の専用テストアカウントを使い、ルーム・チャット・参加コードを取得しない。背景はブラウザメモリ内の表示用状態へ渡し、Socket保存しない。

```powershell
node typst_manual/動画/scripts/verify-s1-grid.mjs $s1Engine
```

今回の環境ではlocalhostへのTCP接続がタイムアウトした。そのため次の代替で実施した。`.claude/launch.json` の同じPython環境と `app.py` を使い、Flask `test_client` が実ルートの応答をブラウザへ渡す。アプリの配布済みHTML・CSS・JSと `renderVisualMap` をそのまま実行する。ライブHTTP接続による比較とは区別する。

```powershell
node typst_manual/動画/scripts/verify-s1-grid.mjs $s1Engine --wsgi
```

結果は `out/app-grid-before.png`、`out/app-grid-background.png`、`out/app-grid-removed.png` と `out/grid-report.json`。

- 初期表示は90px格子。背景指定はCSSのグラデーションを画像URL1枚で置き換え、`contain / no-repeat / center` になる。画像の上にアプリの格子線は出ない。
- 採用後の動画部品は `object-fit:cover` で盤面を満たし、格子と左右の地色を出さない。既定の `object-position:center 65%` は空・階段・駒の足元を残す切り取り。カット側で `--battle-background-position` を指定して位置を調整できる。段階0・途中・最終・巻き戻しを通して画像を見せる。
- アプリの2250px正方形盤面はcontain表示のままで、画像上下に地色が残る。実アプリ画面を使うカットでは、画像の範囲内に収まるよう表示倍率と撮影範囲を調整する。背景を外しても `backgroundSize/Repeat/Position` が残り初期の90px格子に戻らない点も比較時に確認した。アプリ本体は変更していない。
- 石床の目地は距離のマス目ではない。2026-10-27、正面向き・青空の遺跡画像をユーザーが採用した。斜め通路の案や水彩調の案は採用していない。

### S1の検証結果

S1検証結果（2026-10-27）：egatari checkはエラー0・警告0。13段階・65時刻の往復でDOMの状態が一致し、PNG差は赤枠の角の最大2画素（微小なアンチエイリアス差）。実MP4は1280×720・24fps・784フレーム・32.684626秒で、全編デコードと13段階の実フレーム変化を確認した。文字コード検査2本とPythonモジュール行数ガードも通過。S1の測定JSONは `seek-report.json`・`video-report.json`・`grid-report.json` に残す。

S2-1で修正した部品も同じ検証と実MP4を通過。式中の出目と合計の分離、白い斬撃、正式な段階名、駒の絵の右側に出る−9、オパール色のGMの札を確認しました。[絵コンテ案](../01_1ラウンドの流れ/storyboard-v2.md)と[台本変更案](../01_1ラウンドの流れ/narration-v2-proposal.md)は承認待ちです。絵コンテでは `.v2-slide h2` とページ番号を非表示にしても品質チェックを通過し、長すぎる非表示見出しの負例はR-titleで失敗しました。再生成と検証は絵コンテ案の手順を参照してください。

## 共通クレジット

動画のナレーションを終えた後、最後に5秒表示する1枚です。R2-1の配置見本を作成しました。本編への接続は確認後のR2-2で行います。

## 管理するもの

- `credits.json`：作品名「ジェムリアTRPG」と発行元「創作ゆる大地」。表記は `typst_manual/publication_info.typ` を参照します。本の発行日は動画へ転記しません。
- `credits.mjs`：共通HTMLの生成関数。動画タイトルと使用素材の一覧を引数に渡します。表示文字をエスケープします。
- `credits.css`：1280×720、BIZ UDPゴシック、本文27px・タイトル46pxの配置。
- 各動画の `credits.json`：動画タイトル、使用音声・素材の一覧。今回の設定は `01_1ラウンドの流れ/credits.json` です。別動画へ流用する際は使う素材に合わせて更新します。

ロゴは `typst_manual/assets/gemuria_logo.png` の全画像をそのまま使います。加工・切り抜きは行いません。
2026-10-26、アプリ既存のダイス音を使うため、今回の動画設定へ `ダイス音：Springin’ Sound Stock` を追加しました。発行元・音声・効果音・ダイス音の4行も、文字27pxのまま5秒の最終スライドへ収めます。
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
