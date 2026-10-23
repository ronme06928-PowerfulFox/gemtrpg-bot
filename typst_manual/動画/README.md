# 説明動画の制作

## 現在の段階

「1ラウンドの流れ」のM1（環境と部品）が完了しました。
正本は [計画53](../../manuals/planned/53_Explainer_Video_Plan.md) の§4（画面構成）と§6（台本）です。
依頼での「計画51」は、番号の重複解消により「計画53」へ読み替えます。
M2の試作2枚、M3の残り6枚は未着手です。

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
- `01_1ラウンドの流れ/`：今後、正式な `deck.html`・`narration.md`・`app_mock.css` とテーマを置きます。
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

- M2で `themes/gemuria/` と未加工のロゴを配置します。`--base` はルビーの `#ad2840` です。
- `EGATARI_THEMES` によるテーマ共有は未検証です。検証するまではデッキ内のテーマ配置を前提にします。
- U1：HPはアプリの緑と本の赤を保ち、どちらにも「HP」を添えます。試作で読みやすさを確認します。
- U2：「ナギ 勝利（攻撃側勝利）」を仮の見出しとし、M3でローカル実機と照合します。
- U3：第2枚にアプリの層を置かない案を維持します。M1では試作の所見は出しません。
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
