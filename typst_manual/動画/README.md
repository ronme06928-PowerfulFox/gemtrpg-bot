# 説明動画の制作

## 現在の段階

「1ラウンドの流れ」のM1（環境と部品）とM2（第1枚・第3枚の試作）が完了しました。
正本は [計画53](../../manuals/planned/53_Explainer_Video_Plan.md) の§4（画面構成）と§6（台本）です。
依頼での「計画51」は、番号の重複解消により「計画53」へ読み替えます。
M2の試作を見て確認する段階です。M3の残り6枚とローカル実機比較は未着手です。

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

- `parts/`：共通テーマから部品を書き出すTypstソース。
- `01_1ラウンドの流れ/figs/`：デッキ内に埋め込むSVG。
- `01_1ラウンドの流れ/`：`deck.html`・`narration.md`・`app_mock.css`・`deck.css`・`timeline.json` と `themes/gemuria/` を置きます。
- `scripts/verify-m2.mjs`：台本の一致、未加工ロゴ、数値・バー・字幕のブラウザ検証。
- `_local/m1-smoke/`：M1の雛形と埋め込み確認用。説明動画の原稿には含めません。
- 各デッキの `out/`：ビルドしたHTML・PDF・確認用PNG。Gitの管理対象外です。

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

## 雛形・チェック・書き出し

以下はリポジトリのルートから実行するM1の確認手順です。
`npm run new` は空でないフォルダに書かないため、初回だけ実行します。
確認用の台本はegatariの雛形のもので、正式な台本の代用にはしません。

```powershell
$egatariDir = 'C:/Users/yharu/tools/egatari-studio'
$smokeDir = Join-Path (Get-Location) 'typst_manual/動画/_local/m1-smoke'
npm --prefix $egatariDir run new -- $smokeDir --theme default --title 'M1 環境と部品の確認'
npm --prefix $egatariDir run check -- "$smokeDir/deck.html"
npm --prefix $egatariDir run build -- "$smokeDir/deck.html"
npm --prefix $egatariDir run sheet -- $smokeDir
```

正式なデッキも、上のコマンドにデッキの絶対パスを渡します。字幕は組み立てたHTMLに `?captions=1` を付けて確認します。
PDFが必要なら `node C:/Users/yharu/tools/egatari-studio/tools/pdf.mjs <組み立てたHTML> <出力PDF>` を使います。
ビルドした配布物はコミットせずDiscordで配布します。pushは行いません。

## 後続段階での確認

- `themes/gemuria/` と未加工のロゴを配置済みです。`--base` はルビーの `#ad2840` です。
- `EGATARI_THEMES` によるテーマ共有は動作確認済みです。配置の決定は下記のM2記録を参照してください。
- U1：HPはアプリの緑と本の赤を保ち、どちらにも「HP」を添えました。文字で対応を追えるため、この案を維持することを提案します。
- U2：「ナギ 勝利（攻撃側勝利）」を仮の見出しとし、M3でローカル実機と照合します。
- U3：第2枚にアプリの層を置かない案を維持することを提案します。試作2枚では盤面の情報量が多く、4段階の流れ図には全面を使う方が読みやすいと考えます。第2枚そのものはM3で作ります。
- 各段階の検証結果は計画53にも反映します。

## M1の検証結果（2026-10-24）

- Node v24.13.1、Typst 0.15.0で確認しました。
- 雛形5枚：`npm run check` は終了コード0、エラー0・警告0です。
- 確認用の6枚目に8点の `{{FIG:…}}` を追加し、書き出し前は `not found: ruby-fill.svg` で失敗することを確認しました。
  書き出した8点を確認用デッキの `figs/` にコピーすると、終了コード0、エラー0・警告0になりました。
- `npm run build` と `npm run sheet -- <確認用デッキ> --tiles --cols 3` は成功しました。
  `out/sheet.png` と `out/sheet-tiles/06.png` で、ルビーの光沢・線画・ダイスの1〜6の目に欠けがないことを確認しました。
- 正式な第1枚・第3枚と字幕、ローカルの戦闘画面との比較はM2以降です。
- M1で公式docsと実際の挙動に違いは見つかりませんでした。`{{FIG:…}}` のサイズ指定と作業フォルダ内への配置はdocsどおりです。
- TypstのSVG出力には末尾改行がないため、上の書き出し手順でLFを1つ付けます。図の内容は変更しません。
- 音声なしの自動再生は、台本の字数から段階の長さを決めません。既定のholdは1.2秒です。
  M2以降で字幕を読む時間を確認し、`timeline.json` のholdで調整します。字幕の既定速度7字/秒だけでは、動画全体の長さは決まりません。
- `EGATARI_THEMES` による共有はM2で試します。M1ではテーマやロゴをまだ追加していません。

## M2のビルドと確認

リポジトリのルートから実行します。アプリ側の `npm run build` は実行しません。

```powershell
$egatariDir = 'C:/Users/yharu/tools/egatari-studio'
$deckDir = Join-Path (Get-Location) 'typst_manual/動画/01_1ラウンドの流れ'
npm --prefix $egatariDir run check -- "$deckDir/deck.html"
npm --prefix $egatariDir run build -- "$deckDir/deck.html"
node typst_manual/動画/scripts/verify-m2.mjs $egatariDir
npm --prefix $egatariDir run sheet -- $deckDir --tiles --cols 2 --width 960
```

`out/deck.html` をブラウザで開き、URLの末尾に `?captions=1` を付けます。
Sキーでも字幕を切り替えられます。Aキーで自動再生、左右キーで段階を送ります。
`?mode=video&captions=1` は、音声がない場合にその段階の字幕全文を見せます。通常モードは文のまとまりごとに送ります。
確認用PNGは `out/sheet.png`、字幕付きは `out/captions-*.png` です。

### M2の検証結果（2026-10-24）

- 試作は第1枚「1ラウンドの流れ」と第3枚「戦闘開始時の状態」だけです。スライドidは今後も変えません。
- 台本は計画53§6と文字単位で一致します。見出しにidだけを追加しました。ロゴは元のPNGとSHA-256が一致します。
- 数値は第4章と一致し、アプリの層は現在値だけ、本の層はHP/MPの現在値／最大値を表示しています。
- 盤面・駒は1.7倍です。画像なしの駒の頭文字は、教材ではバーと文字の箱が重ならないよう上へ寄せました。タイムラインは描いていません。
- 品質チェックは終了コード0、エラー0・警告1です。警告は第3枚の段階0に台本がないことです。正本が `[1]` から始まるため、入場の1.2秒は無言で表示し、台本は変更していません。
- 台本・ロゴ・数値・バーの割合・字幕と図の重なり・字幕の欠け・ブラウザの実行エラーを `verify-m2.mjs` で検証しました。
- 全段階の読む時間を、台本の空白とmarkを除いた文字数÷7＋2秒で設定しました。試作2枚は計63秒です。
- `sheet` の最終段階と字幕付きPNGを目視しました。ローカル実機との比較はM3です。
- HTMLの図は `.plot` の中に置くと図の文字サイズ下限24pxが適用されます。通常のdivだけでは本文扱いとなり27pxが必要です。公式docsの「図は24px」の具体的な適用条件として確認しました。

### テーマの共有

`_local/m2-shared-theme/` にテーマを持たない同じ原稿を置き、次の環境変数でビルドできることを確認しました。

```powershell
$env:EGATARI_THEMES = Join-Path (Get-Location) 'typst_manual/動画/01_1ラウンドの流れ/themes'
```

この状態で別デッキをビルドすると、`gemuria` の色とロゴが埋め込まれ、デッキ内テーマでの出力とSHA-256が一致しました。
設定は確認用プロセスだけに適用し、ユーザー環境には保存していません。
共有は可能ですが、今回の原稿は指定どおりデッキ内 `themes/gemuria/` に置きます。
将来の動画でもこのthemesフォルダを環境変数で参照できます。外部テーマだけを使うデッキを移動する場合は、テーマも渡すか `--portable` で含めます。
