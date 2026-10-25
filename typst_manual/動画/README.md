# 説明動画の制作

## 完成した動画

「1ラウンドの流れ」はM1〜M3まで完了しました。8枚・37段階、字幕付き約3分42秒、読み上げなし・効果音付きです。
盤面を主役にし、宣言からマッチ成立、威力、HP減少、勝利FP、終了時FPへ順に動かします。
仕様・参照元と台本の正本は [F01 Part 14](../../manuals/implemented/F01_Operations_Manual.md#explainer-videos) です。
M1〜M3の制作仕様はF01へ統合済みです。後続の題材はまだ制作していません。

2026-10-25追記：作例の抽象化、SEの強調、VOICEVOX冥鳴ひまりの試用について、
[計画53を改訂計画として再作成](../../manuals/planned/53_Explainer_Video_Plan.md)しました。
レビューと言い回しの相談を経て、[R1の短い試作](01_1ラウンドの流れ_R1/README.md)を作成しました。
冥鳴ひまりの声とSE従来音量／＋6dBを、約52秒の3場面で比較できます。
試聴後、SEは＋6dB版を採用しました。今後は動画タイトル・作品名・発行元・使用音声や素材をまとめた共通の最終スライドを5秒表示します。
次は全編の台本案と共通クレジットの見本を作るR2-1です。具体的な段階と未決定事項は計画53を参照してください。
以下は基準版の手順です。新しい全編と共通スライドはまだ反映していません。

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

- `parts/assets.typ`：本のテーマからSVGを書き出すソース。
- `01_1ラウンドの流れ/`：deck.html、narration.md、timeline.json、deck.css、app_mock.css、battle_scenes.css。
- 同デッキの `components/round-scene/`：表紙とHP/MP/FPの紹介。`components/battle-sequence/`：流れ図から次ラウンドまでの動き。
- 同デッキの `images/`：人狼型シュラーカー。`sfx/`：CC0効果音6種・出典・キュー表。
- `scripts/prepare-media.mjs`：段階の長さと効果音トラックを生成。`audio/steps/`と`audio/manifest.json`は生成物として無視します。
- 同デッキの `figs/`：埋め込むSVG。`themes/gemuria/`：テーマと未加工のロゴ。
- `scripts/verify-deck.mjs`：台本の一致、未加工ロゴ、数値・バー・字幕・動き・巻き戻しのブラウザ検証。
- `_local/`：環境確認やローカル実機比較用。Git管理対象外です。
- 同デッキの `out/`：HTML・PDF・確認用PNG・MP4。Git管理対象外です。

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

## 正式デッキのビルドと確認

リポジトリのルートから実行します。アプリ側の `npm run build` は実行しません。

```powershell
$egatariDir = 'C:/Users/yharu/tools/egatari-studio'
$deckDir = Join-Path (Get-Location) 'typst_manual/動画/01_1ラウンドの流れ'
$ffmpegDir = 'C:/Users/yharu/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.1-full_build/bin'
$env:PATH = "$ffmpegDir;$env:PATH"
# 圧縮用キャッシュをこのプロセスの作業領域に限定します。
$videoTemp = Join-Path (Get-Location) 'typst_manual/動画/_local/media-temp'
New-Item -ItemType Directory -Force -Path $videoTemp | Out-Null
$env:TEMP = $videoTemp
$env:TMP = $videoTemp
node typst_manual/動画/scripts/prepare-media.mjs $egatariDir
npm --prefix $egatariDir run check -- "$deckDir/deck.html"
npm --prefix $egatariDir run build -- "$deckDir/deck.html" --embed-audio
node typst_manual/動画/scripts/verify-deck.mjs $egatariDir
npm --prefix $egatariDir run sheet -- $deckDir --tiles --cols 4 --width 640
```

`out/deck.html` をブラウザで開き、`?captions=1` を付けます。Sキーで字幕、Aキーで自動再生、左右キーで段階を送れます。
`?mode=video&captions=1` は無音の段階で字幕全文を見せます。効果音付きの10段階も、改訂した台本は標準の1まとまりに収まります。Aキーの自動再生中に効果音が鳴ります。手送り・seekでは鳴りません。
品質チェックはエラー0・警告7。第2〜8枚の段階0に台本がない警告です。段階1から字幕を出します。
入場段階は1.2秒、台本のある段階は空白とmarkを除いた字数÷7＋1秒、最短4秒です。動きのある段階はその長さも確保します。prepare-media.mjsがtimeline.jsonへhold・durを書き、効果音のlead・pad_afterを0にします。

PDFが必要なら次で書き出します。

```powershell
node C:/Users/yharu/tools/egatari-studio/tools/pdf.mjs "$deckDir/out/deck.html" "$deckDir/out/deck.pdf"
```

確認用PNGは `out/sheet.png`、各枚は `out/sheet-tiles/`、字幕付きの途中段階は `out/captions-*.png` です。
sheetは最終段階のみです。矢印の描画や数値変化はMP4で確認します。

## テーマの共有


`_local/m2-shared-theme/` にテーマを持たない同じ原稿を置き、次の環境変数でビルドできることを確認しました。

```powershell
$env:EGATARI_THEMES = Join-Path (Get-Location) 'typst_manual/動画/01_1ラウンドの流れ/themes'
```

この状態で別デッキをビルドすると、`gemuria` の色とロゴが埋め込まれ、デッキ内テーマでの出力とSHA-256が一致しました。
設定は確認用プロセスだけに適用し、ユーザー環境には保存していません。
共有は可能ですが、今回の原稿は指定どおりデッキ内 `themes/gemuria/` に置きます。
将来の動画でもこのthemesフォルダを環境変数で参照できます。外部テーマだけを使うデッキを移動する場合は、テーマも渡すか `--portable` で含めます。

## 動画の書き出し


このPCではAnacondaのffmpeg 4.2.2がPATHで先に選ばれ、egatariの `-fps_mode` に対応していませんでした。
ffmpeg 9.0.1をコマンドのプロセス内だけで優先します。ユーザー環境のPATHは変更しません。

```powershell
$ffmpegDir = 'C:/Users/yharu/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.1-full_build/bin'
$env:PATH = "$ffmpegDir;$env:PATH"
$deckDir = Join-Path (Get-Location) 'typst_manual/動画/01_1ラウンドの流れ'
node C:/Users/yharu/tools/egatari-studio/render/render.mjs "$deckDir/out/deck.html" --out "$deckDir/out/motion" --full --fps 24 --scale 1 --captions
```

出力は `out/motion/full.mp4`（約3分42秒・1280×720・24fps）、各段階は `clip_0000.mp4`〜`clip_0036.mp4` です。
読み上げとBGMはありません。効果音を10段階・13回に配置しました。ビルドした配布物はコミットせずDiscordで配布します。pushは行いません。

## 検証結果（2026-10-25改訂）

- 雛形checkとSVG8点の埋め込み確認はエラー0・警告0。正式デッキのcheckはエラー0・警告7です。
- 台本8枚は、ユーザーの改稿依頼を受けて2026-10-25に短く書き直しました。F01の改訂台本と文字単位で一致します。ロゴは元PNGとSHA-256が一致します。
- 全段階の字幕の欠け・図との重なり、数値、バー割合、マッチ成立前後、HP/FPの変化、巻き戻し、ブラウザの実行エラーをverify-deck.mjsで確認しました。
- 動きはegatariの段階・時刻から決まり、独自タイマーを使いません。同時刻へ戻した画面は全画素で1階調以内に一致します（画像を含む合成レイヤーの丸め差だけを許容）。
- ローカル127.0.0.1:5000のテスト専用アカウントとルームで、固定作例の状態を実アプリ部品へ渡して比較しました。駒、バー、FP、宣言パネルの手順・案内文、威力表示、勝敗見出しと色を照合しました。同じ出目を振った通し戦闘の検証ではありません。ルームは終了後に削除しています。
- U1：HPの色は各層のまま、必ず「HP」を添えます。U2：実機どおり「ナギ 勝利 (攻撃側勝利)」を採用しました。U3：第2枚は盤面なしの流れ図です。
- 図の24px下限は.plot内で適用されます。通常divは本文27px扱いです。宣言パネルだけは実機に合わせ明朝です。
- 音声なしの既定holdは1.2秒で、台本の字数から自動算出されません。timeline.jsonで明示しています。
- SVGのサイズ指定・作業フォルダ内配置・テーマ共有は公式docsどおりでした。v0.4.5の機能とdocsの矛盾は見つかりませんでした。

### 改訂で確認したこと

- 作例の外の加速・減速、宣言の選び直し、同じスロットでの再攻撃を否定する補足を外しました。数値、計算、使用コスト、処理順は第4章どおりです。
- 敵は人狼型シュラーカーの未加工PNGを使い、全身をバーの上に収めます。名前・能力値は説明用の「敵」のまま。ナギの立ち絵は保留です。
- 効果音は[選定表](01_1ラウンドの流れ/sfx/README.md)を参照。`out/sfx-samples.wav`で6種を表の順に2秒ごとに聴けます。
- ブラウザで埋め込み音声10本をデコードし、音量・開始時刻・長さを検証しました。Aキーの自動再生で実際に再生位置が進むことも確認しています。
- v0.4.5の動画レンダラーは、動きが終わった後を最終画像で埋めます。音付き段階の字幕は全10段階とも最初と最後の文面が同じ1まとまりに収まることを検証しました。外部のegatari本体は変更しません。
- Windowsの制限された一時フォルダでAAC圧縮キャッシュのrenameがEPERMになりました。上記のTEMP/TMP設定で回避しました。設定は実行プロセスだけに適用します。

コミット前は、指定のPythonで次を実行します。

```powershell
& C:/Users/yharu/anaconda3/python.exe scripts/check_text_encoding.py
& C:/Users/yharu/anaconda3/python.exe scripts/check_mojibake_markers.py
```
