# 説明動画の制作

## 現在の動画

計画54のS1として、[共通の動きの7部品](common/README.md)と確認用デッキを追加しました。確認用HTML・MP4・PNGは `_local/s1-components/out/`（Git管理外）。「1ラウンドの流れ」のv2本編はS2で制作します。以下のR3とr3-v2は制作記録として残します。

「1ラウンドの流れ」のR3修正版を制作・検証しました。本文7場面と共通クレジット1枚、27段階、タイムライン162.85秒です。実MP4の測定値は下記の検証結果を参照してください。
味方はR1の男冒険者（HP100・MP10・FP0）、敵は人狼型シュラーカー（HP30・MP6・FP0）。HP・MPは満タンから始めます。
冥鳴ひまりの声を19段階に入れ、採用済みのSE＋6dBを重ねます。BGMはありません。

[計画54](../../manuals/planned/54_Explainer_Video_Series_Plan.md)が共通部品と今後の制作の正本です。[計画53](../../manuals/planned/53_Explainer_Video_Plan.md)はR3までの制作記録と、引き継ぐ声・SE等の決定を保持します。
[確認済み台本](01_1ラウンドの流れ/narration.md)と[画面との対応](01_1ラウンドの流れ/storyboard-r2.md)を使います。
旧M1〜M3の記録は[F01 Part 14](../../manuals/implemented/F01_Operations_Manual.md#explainer-videos)、声・SE比較は[R1](01_1ラウンドの流れ_R1/README.md)へ残しています。
計画53のF01への統合時期は計画54§9 Q7で扱います。
R3は公開せず記録として残し、共通部品を使うv2本編の制作はS2で行います。
2026-10-26の修正：「基本の一太刀」を「きほんのひとたち」と読み、速度値・最終威力が確定した時に、味方・敵それぞれ1回だけアプリ既存のダイス音を鳴らします。途中のロール音と確定tickをまとめ、ダイス周りの音を8回から4回へ減らしました。締めはラウンド終了時の処理後、次のラウンドが始まり戦闘が続く説明へ変更しています。

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
- 同デッキの `components/round-video/index.js`：全場面を(k,t)と音声cueから描く部品。独自タイマー・乱数・CSSアニメーションは使いません。
- 同デッキの `voice/config.json`：固定版・声・読み・話速等。`voice/events.json`：SEと必要な余韻。`timeline.json` は声の長さから再生成します。
- `common/`：動画間で共用するクレジットの生成関数・CSS・作品名と発行元。タイトルと使用素材は各デッキの `credits.json`。
- `scripts/prepare-r2.mjs`：共通クレジットをデッキ内へ配置し、全編の声とSEを生成します。
- 同スクリプトはアプリの `static/audio/dice-roll.mp3` を読み取り、`sfx/imported/` へコピーします。この素材コピーはGit管理外です。出典・動画利用条件は[SEの記録](01_1ラウンドの流れ/sfx/README.md)を参照してください。
- `scripts/prepare-voice.mjs`：R1とR2が使う音声生成処理。WAV処理は `r1-audio.mjs` を共有します。
- `scripts/verify-r2.mjs`：全編の数値・巻き戻し・字幕・音声・ロゴ・効果枠・クレジット・自動再生をブラウザで確認します。
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

## 全編の音声生成・ビルド・確認

最初に別のPowerShellで固定版VOICEVOX ENGINEを起動します。エディターや外部サービスは使いません。

```powershell
& C:/Users/yharu/tools/voicevox-engine-0.26.0/windows-cpu/run.exe --host 127.0.0.1 --port 50021 --no-use_gpu --cpu_num_threads 4 --disable_mutable_api --output_log_utf8
```

リポジトリのルートから実行します。アプリ本体のビルドは不要です。

```powershell
$egatariDir = 'C:/Users/yharu/tools/egatari-studio'
$deckDir = Join-Path (Get-Location) 'typst_manual/動画/01_1ラウンドの流れ'
$ffmpegDir = 'C:/Users/yharu/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.1-full_build/bin'
$env:PATH = "$ffmpegDir;$env:PATH"
$videoTemp = Join-Path (Get-Location) 'typst_manual/動画/_local/media-temp'
New-Item -ItemType Directory -Force -Path $videoTemp | Out-Null
$env:TEMP = $videoTemp
$env:TMP = $videoTemp
node --test typst_manual/動画/scripts/test-r1-audio.mjs typst_manual/動画/scripts/test-credits.mjs
node typst_manual/動画/scripts/prepare-r2.mjs $egatariDir
npm --prefix $egatariDir run build -- "$deckDir/deck.html" --embed-audio
Copy-Item -LiteralPath "$deckDir/out/deck.html" -Destination "$deckDir/out/deck-r3-v2.html"
npm --prefix $egatariDir run check -- "$deckDir/deck.html"
node typst_manual/動画/scripts/verify-r2.mjs $egatariDir
npm --prefix $egatariDir run sheet -- $deckDir --tiles --cols 2 --width 640
node "$egatariDir/render/render.mjs" "$deckDir/out/deck-r3-v2.html" --out "$deckDir/out/r3-v2" --full --fps 24 --scale 1 --captions
```

- `out/deck.html`：オフライン再生する単一HTML。`?captions=1`で開き、Aキーで声付き自動再生、Sキーで字幕、左右キーで段階を送ります。
- `out/deck-r3-v2.html`、`out/r3-v2/full.mp4`：修正版の単一HTMLと字幕付きMP4。1280×720・24fps。末尾はナレーション終了後の共通クレジット5秒。旧メッセージの再生キャッシュと区別できる名前にします。
- `out/sheet.png`、`out/sheet-tiles/`：各枚の最終状態。動きと途中の効果枠はMP4、`out/effect.png`等はブラウザ検証で確認します。
- `out/audio-report-plus6.json`：声の識別・各段階の長さ・cue・SE時刻・合成後ピーク。
- 台本・声・設定のhashが同じ原音は再利用します。読みと締めの修正で原音4本を更新し、残り17本はキャッシュを使用しました。ダイス音の差し替えでは原音21本すべてを再利用しています。
- 音声とモデルは区別し、配布するのは通常の `--embed-audio` HTMLとMP4です。編集用 `--portable` は配布に使いません。

旧SE専用の `prepare-media.mjs`、旧作例の2部品と `verify-deck.mjs` はR2で削除しました。
VOICEVOX音声を消す古い生成経路は使わず、egatariのsynth.pyとも併用しません。

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
