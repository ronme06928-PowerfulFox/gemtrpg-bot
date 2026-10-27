# 説明動画の制作

## 現在の動画

計画54 S2-2の「1ラウンドの流れ」v2を、承認済みの12カットと共通の7部品で制作・検証しました。[絵コンテ](01_1ラウンドの流れ/storyboard-v2.md)・[追加2文の承認記録](01_1ラウンドの流れ/narration-v2-proposal.md)・[台本](01_1ラウンドの流れ/narration.md)が対応します。

確認用の単一HTMLは `out/deck-v2-opening.html`、字幕付きMP4は `out/v2-opening/full.mp4`、各カットのPNGは `out/v2-review/`（いずれも01_1ラウンドの流れ/内、Git管理外）。正本は[計画54](../../manuals/planned/54_Explainer_Video_Series_Plan.md)。通し確認後までF01への統合と計画53の完了処理は行いません。

味方HP100・MP10・FP0、敵HP30・MP6・FP0から始め、使用コストなしの基本の一太刀を使います。冥鳴ひまり／VOICEVOX 0.26.0、SE＋6dB、ダイス確定音4回、共通クレジット5秒を引き継ぎます。背景は採用済みの遺跡を全面coverで表示します。

R1は比較記録として変更せず、旧r3-v2のHTML・MP4も保存します。旧本編専用のround-video、deck.css、battle_scenes.cssと生成・検証経路はv2へ置き換えました。R3の原稿はローカルGitの0f96e35以前に残っています。[計画53](../../manuals/planned/53_Explainer_Video_Plan.md)と[旧絵コンテ](01_1ラウンドの流れ/storyboard-r2.md)は当時の記録です。

## 版と環境


- Windows 11、Node 22以上、Typst 0.15、Microsoft Edgeを使います。
- Pythonが必要なときは `C:/Users/yharu/anaconda3/python.exe` を使います。
- egatari-studioはアプリのリポジトリの外に置き、タグ `v0.4.5` に固定します。
  タグのコミットは `c73221161b9761edafa21abb56f3f589fade3b5a` です。
- [公式README（v0.4.5）](https://github.com/egatari/egatari-studio/blob/v0.4.5/README.ja.md) と
  [リファレンス（v0.4.5）](https://github.com/egatari/egatari-studio/blob/v0.4.5/docs/reference.ja.md) を参照します。

PowerShellで初回だけ実行します。

```powershell
git clone --branch v0.4.5 --depth 1 https://github.com/egatari/egatari-studio.git C:/Users/yharu/tools/egatari-studio
npm --prefix C:/Users/yharu/tools/egatari-studio ci
```

`git clone` は注釈付きタグを経由してdetached HEADにします。タグのコミットを使うため、そのままにします。
アプリ本体の `package.json`・依存関係・`static/` は変更しません。

## 置き場所

- `parts/assets.typ`：本の宝石・ダイスを書き出すTypstソース。
- `01_1ラウンドの流れ/`：全編のHTML・台本・CSS・テーマ・画像・SVG・SE・声の設定。
- 同デッキの `components/round-cut/index.js`：カットごとの(k,t)と音声cueを共通部品へ配線します。独自タイマー・乱数・CSSアニメーションは使いません。
- 同デッキの `voice/config.json`：固定版・声・読み・話速等。`voice/events.json`：SEと必要な余韻。`timeline.json` は声の長さから再生成します。
- `common/`：動画間で共用するクレジットの生成関数・CSS・作品名と発行元。タイトルと使用素材は各デッキの `credits.json`。
- `scripts/prepare-round-v2.mjs`：共通クレジットをデッキ内へ配置し、全編の声とSEを生成します。
- 同スクリプトはアプリの `static/audio/dice-roll.mp3` を読み取り、`sfx/imported/` へコピーします。この素材コピーはGit管理外です。出典・動画利用条件は[SEの記録](01_1ラウンドの流れ/sfx/README.md)を参照してください。
- `scripts/prepare-voice.mjs`：R1とv2が使う音声生成処理。WAV処理は `r1-audio.mjs` を共有します。
- `scripts/verify-round-v2.mjs`：全編の数値・巻き戻し・字幕・音声・ロゴ・効果枠・クレジット・自動再生をブラウザで確認します。
- `out/`：単一HTML・PNG・MP4。`audio/`：生成WAVとmanifest。`voice/cache/`：原音WAVとVOICEVOX query。これらの生成物はGit管理外です。
- `_local/`：ローカル確認用。共通クレジット単体の見本は[専用手順](common/README.md)で再生成します。

## 部品の書き出し


リポジトリのルートから実行します。`manual_theme.typ` の `gem-shape` と `die` を直接呼びます。
ルビーの色も `gems.at("4")` から取得し、輪郭やダイスの目を描き直しません。
SVGはegatariの作業フォルダ内に置きます。作業フォルダの外への参照はegatariに拒否されます。

```powershell
$videoDir = Join-Path (Get-Location) 'typst_manual/動画'
$figDir = Join-Path $videoDir '01_1ラウンドの流れ/figs'
New-Item -ItemType Directory -Force -Path $figDir | Out-Null
$videoAssets = @('ruby-fill', 'ruby-wire', 'die-1', 'die-2', 'die-3', 'die-4', 'die-5', 'die-6')
foreach ($videoAsset in $videoAssets) {
  typst compile --root . --format svg --input "asset=$videoAsset" "$videoDir/parts/assets.typ" "$figDir/$videoAsset.svg"
  if ($LASTEXITCODE -ne 0) { throw "SVG export failed: $videoAsset" }
  $svgPath = Join-Path $figDir "$videoAsset.svg"
  $svgText = [System.IO.File]::ReadAllText($svgPath, [System.Text.Encoding]::UTF8)
  [System.IO.File]::WriteAllText($svgPath, $svgText.TrimEnd() + "`n", [System.Text.UTF8Encoding]::new($false))
}
```

HTMLでは `{{FIG:ruby-fill}}` のように埋め込みます。図のコンテナに `aria-label` を付け、
幅と高さをCSSで指定します（egatariは埋め込み時にSVGのwidth・heightを外します）。

## 雛形の初回確認

リポジトリのルートから実行します。`new` は空でないフォルダに書かないため、初回だけ使います。

```powershell
$egatariDir = 'C:/Users/yharu/tools/egatari-studio'
$smokeDir = Join-Path (Get-Location) 'typst_manual/動画/_local/m1-smoke'
npm --prefix $egatariDir run new -- $smokeDir --theme default --title 'M1 環境と部品の確認'
npm --prefix $egatariDir run check -- "$smokeDir/deck.html"
```

## S2-2の音声生成・ビルド・確認

固定版VOICEVOX ENGINEを別のPowerShellで起動します。

```powershell
& C:/Users/yharu/tools/voicevox-engine-0.26.0/windows-cpu/run.exe --host 127.0.0.1 --port 50021 --no-use_gpu --cpu_num_threads 4 --disable_mutable_api --output_log_utf8
```

リポジトリのルートから実行します。

```powershell
$egatariDir = 'C:/Users/yharu/tools/egatari-studio'
$deckDir = Join-Path (Get-Location) 'typst_manual/動画/01_1ラウンドの流れ'
$ffmpegDir = 'C:/Users/yharu/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.1-full_build/bin'
$env:PATH = "$ffmpegDir;$env:PATH"
$videoTemp = Join-Path (Get-Location) 'typst_manual/動画/_local/media-temp'
New-Item -ItemType Directory -Force -Path $videoTemp | Out-Null
$env:TEMP = $videoTemp
$env:TMP = $videoTemp
node --test typst_manual/動画/scripts/test-r1-audio.mjs typst_manual/動画/scripts/test-credits.mjs typst_manual/動画/scripts/test-round-v2.mjs typst_manual/動画/scripts/test-opening.mjs
node typst_manual/動画/scripts/prepare-round-v2.mjs $egatariDir --voice
npm --prefix $egatariDir run build -- "$deckDir/deck.html" --embed-audio
Copy-Item -LiteralPath "$deckDir/out/deck.html" -Destination "$deckDir/out/deck-v2-opening.html"
npm --prefix $egatariDir run check -- "$deckDir/deck.html"
node typst_manual/動画/scripts/verify-round-v2.mjs $egatariDir
npm --prefix $egatariDir run sheet -- $deckDir --tiles --cols 3 --width 426
node "$egatariDir/render/render.mjs" "$deckDir/out/deck-v2-opening.html" --out "$deckDir/out/v2-opening" --full --fps 24 --scale 1 --captions
node typst_manual/動画/scripts/verify-round-v2-video.mjs
```

- HTMLは通信不要。Aキーで声付き自動再生、Sキーで字幕、左右で段階移動。クレジットは声の終了後5秒です。配布には通常の `--embed-audio` を使い、編集用portableは使いません。
- 生成入力の共通部品・motion.css・背景画像はprepareが写し、Git管理から除外します。共通部品を直接直し、写しを手編集しません。12カット固有の配線だけがcomponents/round-cutにあります。
- 原音のhashは声の識別・読み上げ文・音声設定から作ります。S2-2初版ではC02の同期用5原音とC11追加2文を生成し、20原音は再利用。今回の冒頭改訂はスロット説明だけ1原音を生成し、残り26原音を再利用しました。タイトル用チャイムはPCM合成です。
- 初回の内訳は `out/s2-voice-first-generation.json`、通常の音声・cue・SE・ピークは `out/audio-report-plus6.json`。古い台本の流用や欠損音声の無音置換は行いません。
- `out/v2-review/browser-report.json` は途中・巻き戻し・オフライン音声・コントラストの検証記録、`out/v2-opening/video-report.json` は実MP4の測定記録です。
- 静止絵コンテの221秒は見積もりでした。実際の声からタイムラインを作り、尺合わせの静止は足しません。

## S2-2初版の検証結果（2026-10-27、冒頭改訂前）

- 実MP4は174.398209秒（2分54.398秒）、4185フレーム、1280×720・24fps、H.264＋AAC。全編デコードを通過し、最大ピーク-7.5dBFS。末尾5秒は120フレームの共通クレジットです。
- npm run checkはエラー0・警告12（無言の入場段階11か所とクレジットのみ）。非表示の長すぎる見出しをR-titleが検出する負例も確認しました。ユニットテスト6件、S1の65時刻の回帰検査も通過。
- 巻き戻し78状態のDOMが一致し、途中8か所のPNGは画素一致。本文27px・図24px以上、行動済みのコントラスト12.63:1。声・字幕・数値・段階・GM・SEの同期点と作例のルールを照合しました。
- 単一HTMLの22音声を全デコードし、通信を遮断して再生を確認。外部アセット参照・個人のファイルパスはなく、ロゴ・立ち絵のPNGは元のSHA-256と一致します。
- 今回は--onlyで3群を並列生成し、正規rendererの--fullで全34入力と最終／中間PNGを再照合して連結しました。部分生成の終了コード2は未選択クリップが未生成であるという通知で、最終timeline.out.jsonはcomplete=true。上の通常の一括手順でも再生成できます。
- 実MP4の12か所のフレーム変化と、締め・最後のクレジットを確認。詳細はout/v2/video-report.json、画像は同フォルダのmotion-*.png・ending-caption.png・credits-end.pngです。ユーザーの通し確認を待ち、F01統合と計画53の完了処理は保留します。

## 冒頭改訂（2026-10-27）

スロットの語りをユーザー指定の2文へ差し替え、冒頭は2.6秒のタイトルカード＋自作3音チャイムを表示します。声は冥鳴ひまりのまま、C02[2]だけ生成し、ほか21段階の26原音はキャッシュを使いました。本文の見出しは非表示を維持します。

common/opening.mjs・opening.cssが共通の題名とSEを作り、C01の段階0へ配置します。タイトル中は語りを入れず、段階1から盤面と既存の冒頭の語りに切り替えます。最初のフレームと巻き戻しで同じタイトルへ戻ります。SEの由来はsfx/README.md。

確認HTMLはout/deck-v2-opening.html、MP4はout/v2-opening/full.mp4、冒頭とスロット説明だけの見本は同フォルダのopening-and-slots.mp4、タイトルPNGはopening.png。旧out/deck-v2.html・out/v2/full.mp4は比較用に保存します。声の生成記録はout/voice-opening-revision.json。

改訂版の実MP4は179.648209秒・4311フレーム・1280×720/24fps。全編デコードを通過し、最大ピーク-7.5dBFS、タイトルSEの実MP4内ピーク-19dBFS、最後は5秒です。冒頭から声への自動再生・78状態の巻き戻し・23音声のオフライン再生を確認。品質エラー0・警告12、単体テスト8件通過。タイトル・新説明の字幕・末尾は実MP4から抽出して確認しました。

## テーマの共有


`_local/m2-shared-theme/` にテーマを持たない同じ原稿を置き、次の環境変数でビルドできることを確認しました。

```powershell
$env:EGATARI_THEMES = Join-Path (Get-Location) 'typst_manual/動画/01_1ラウンドの流れ/themes'
```

この状態で別デッキをビルドすると、`gemuria` の色とロゴが埋め込まれ、デッキ内テーマでの出力とSHA-256が一致しました。
設定は確認用プロセスだけに適用し、ユーザー環境には保存していません。
共有は可能ですが、今回の原稿は指定どおりデッキ内 `themes/gemuria/` に置きます。
将来の動画でもこのthemesフォルダを環境変数で参照できます。外部テーマだけを使うデッキを移動する場合は、テーマも渡すか `--portable` で含めます。

## 検証結果（2026-10-26、R3修正版）

- checkはエラー0・警告8。本文7枚の短い入場段階0と、無言のクレジット段階に口述原稿がない警告です。19の音声段階にはすべて声があります。
- テスト5件通過。実ブラウザでHP100・MP10、敵HP30→21、味方FP0→1→3、敵FP0→2、両者の行動済み、巻き戻しを確認しました。
- 赤枠をタイミングから効果全体へ広げ、カードが両者のFPへ重ならないことを確認しました。画像とロゴは元PNGと一致します。
- 音声段階の先頭・中間・末尾で字幕の欠けと盤面との重なりを検証し、全19本の埋め込みAACをデコードしました。自動再生で実際に再生位置が進むことも確認しました。
- `talk`・`lecture`・`video`で表示できる共通クレジットを採用。字幕OFFでも文字が残り、0・2.5・4.99秒の画面が一致します。
- v0.4.5では最初のスライドの段階0のアニメーション長が0になるため、表紙の読み上げを段階1から始めます。各音声段階は字幕の途中切替も含めて全長を描き、後半を静止画像で埋めません。
- 実MP4はH.264＋AAC、1280×720・24fps・3903フレーム、162.648秒です。全編のデコード検査を通過し、最大ピークは-7.5dBFSでクリップなし。`out/r3-v2/video-report.json`へ測定値を保存しました。段階ごとのフレーム丸めを含み、タイムラインとの差は0.202秒です。
- 実動画から取り出した `out/r3-ending-caption.png`、`out/r3-credit-frame.png` で締めの字幕とクレジットを確認しました。矢印・赤枠・FPは全編ブラウザ検証でも確認しています。
- R3ではVOICEVOX queryのモーラ列で、スキル名を含む3か所の「ヒトタチ」を確認しました。アプリ既存音とデッキ内コピーのSHA-256一致、速度・威力で各2回のダイス音が結果の確定時にだけ鳴り、別の確定tickを重ねないことを検証します。Springin’ Sound Stockの出典を追加した4行のクレジットも画面内に収まります。
- Anacondaのffmpeg 4.2.2は `-fps_mode` に非対応です。上記手順で9.0.1をプロセス内だけ優先します。AAC圧縮キャッシュのrenameが制限される場合はTEMP/TMPを上記のローカル作業領域へ置きます。

コミット前に実行します。

```powershell
& C:/Users/yharu/anaconda3/python.exe scripts/check_text_encoding.py
& C:/Users/yharu/anaconda3/python.exe scripts/check_mojibake_markers.py
```
