# ルール本・出版物の管理

## Gitで管理するもの

- 各冊子のTypst原稿、共通テーマ、原稿内で描く図、編集方針。原稿の書き方は[書き方の手引き](WRITING_GUIDE.md)に従う。
- 本のPDF。`全体マニュアル/main.typ`・`main.pdf`は第0〜7章と巻末を統合した基本ルールブックの刊行前の確認版（54頁）。第8章は保留。旧本文・旧PDFは`全体マニュアル/旧版/旧ルール本.typ`・`旧ルール本.pdf`に保持する。
- レビュー用に作成した試作PDF（`../output/pdf/46_*.pdf`）。操作ガイドは `操作ガイド/main.typ`・`main.pdf`（37頁）、レビュー用は `../output/pdf/46_operation_guide.pdf`。

## ローカルだけで管理するもの

素材画像、画面キャプチャ、採用前の候補、PDFを画像にした表示確認用ファイルは `_local/` に保存する。このディレクトリ全体を `.gitignore` で除外する。

```text
typst_manual/
  README.md
  全体マニュアル/          章原稿・統合入口・刊行前の確認版PDF（Git管理）
    旧版/                  旧ルール本.typ・旧ルール本.pdf（Git管理）
  試作/                    図解などの試作原稿（Git管理）
  操作ガイド/              セッション操作ガイドの原稿（Git管理）
  _local/                  以下はすべてローカル専用
    materials/             イラスト・背景・加工済み素材
      <冊子名>/
    screenshots/           アプリ画面のキャプチャ
      <冊子名>/
    previews/              PDFの表示確認画像
      <試作名・冊子名>/
    work/                  加工途中・生成途中のファイル
      <試作名・冊子名>/
output/pdf/                レビュー用の試作PDF（Git管理）
```

新しい環境では必要なローカルディレクトリを作成する。空フォルダや素材そのものはGitから復元されない。

原稿でローカル素材を使う場合は、各冊子のREADMEに参照先の相対パス、用途、入手元・利用条件を記録する。素材は別途コピーまたはバックアップから戻す。ローカル素材が必要な本は、Gitの取得だけでは再生成できない。

アプリ本体の `static/` にある画像はこの方針の対象外。拡張子で画像を一括除外せず、書籍用ローカルディレクトリの範囲で除外する。すでにGit管理されている素材を移す際は、参照箇所と追跡状態を確認する。

PDF確認ツールが `tmp/pdfs/` に出力する場合もGit対象外とする。残しておきたい確認画像は `_local/previews/<試作名・冊子名>/` にまとめる。

2026-10-21：冊子全体の空白調整を完了（基本本65→53頁、操作ガイド37→35頁）。本文サイズ・余白・段落設定はC案のまま。全88頁と章別レビュー8本を確認し、組版警告0件。原因・改ページの削除・残る余白は[台帳§19.34](../manuals/planned/46_Publication_Source_Inventory.md#1934-冊子全体の空白調整2026-10-21)。

2026-10-22：戦闘裁定5件を反映（D06・D17、攻撃対防御／回避の同値、合算参加側のコスト・勝利FP、個別同速候補）。基本本53頁・操作ガイド35頁を維持。2冊と章別レビュー8本は組版警告0件。全件1204 passed / 2 skipped。反映箇所・修正前の失敗・残るGM確認は[台帳§19.35](../manuals/planned/46_Publication_Source_Inventory.md#1935-戦闘裁定5件の反映2026-10-22)。

2026-10-22（読みやすさ・版CとD39）：2冊の全章に用語・式・核心の強調、例外・作例・関連参照の整理を適用。第5章の再回避／強硬攻撃の節と勝敗／不発の表を分割し、D39を反映。基本本53→53頁・操作ガイド35→36頁、全件1214 passed / 2 skipped、組版警告0件。全89頁を画像で確認。変更点・確認中の文の保持・残る余白は[台帳§19.36](../manuals/planned/46_Publication_Source_Inventory.md#1936-版cの読みやすさとd392026-10-22)。

2026-10-22（段階6）：段階6の刊行準備を完了。基本本54頁・操作ガイド37頁（第1版・刊行前の確認版）。版情報・奥付・改訂履歴・Discord配布案内を整備し、冊子内参照72か所を追加リンク化。全91頁、2層しおり、リンク、フォントと警告を検査。受け入れ条件と残件は台帳§19.37。段階7の読者通読・発行日決定・公開は未実施。第8章は保留。アプリ変更・pushなし。 新しい2冊はジェムリアのDiscordサーバーでPDFを配布します。発行日は段階7で決めます。過去の日付の頁数・状態は当時の記録です。

## 刊行情報と再生成

新しい2冊の配布場所はジェムリアのDiscordサーバーです。PDFにはURLを載せません。現在は「第1版・刊行前の確認版」です。書名・版・確認日・改訂履歴は `publication_info.typ` で管理し、公開時には同ファイルの `release-date` を設定します。これだけで表紙・柱・奥付の2冊分が切り替わり、発行日が表示されます。各冊子の版は独立して更新でき、関連冊子の版も追従します。履歴は版ごとに、変更したルール・操作と節名を数行で記録します。

### 組版環境・フォント

検証環境は **Typst 0.15.0 (3ae52774)**。本文・余白・段落は版Cを維持します。使用フォントは次のとおりです。

| フォント | 用途 | 必要なファイル |
| --- | --- | --- |
| Noto Sans JP | 2冊の本文・見出し・柱 | `NotoSansJP-VF.ttf`（可変） |
| Noto Serif JP | 基本本表紙の標章・副題 | `NotoSerifJP-VF.ttf`（可変） |
| DejaVu Sans Mono | 操作ガイドの英字装飾・図番号・頁番号 | Typst 0.15.0内蔵（通常・太字） |
| Segoe UI Emoji | 操作ガイドの🏠・📦・🎒など | `seguiemj.ttf`（Windowsのフォント） |
| Segoe UI Symbol | 操作ガイドの記号 | `seguisym.ttf`（Windowsのフォント） |

Windowsのフォントを利用可能な環境で、外部フォント4ファイルを `typst_manual/_local/fonts/` に用意します。フォントそのものはGit管理・Discord配布に含めません。別PCでも同じフォントファイルとTypst版を使い、システムの自動代替を避けるため次のコマンドで組版します（リポジトリ直下から実行）。PDFの日時・文書IDによるバイト列の差はあり得ます。

```powershell
typst compile --ignore-system-fonts --font-path typst_manual/_local/fonts --root typst_manual typst_manual/全体マニュアル/main.typ typst_manual/全体マニュアル/main.pdf
typst compile --ignore-system-fonts --font-path typst_manual/_local/fonts --root typst_manual typst_manual/操作ガイド/main.typ typst_manual/操作ガイド/main.pdf
```

検証に使用した外部フォントのSHA-256（同名の別版を見分けるため）：

```text
NotoSansJP-VF.ttf  5113756f8a3b5d01b2211025e267c50121e3b36f465b7bbaf3cdaf4c3430bfd0
NotoSerifJP-VF.ttf b7e0d299a21bd2009eff27aca5e9508c75ab494de222f96bd0bbe355a8d8ced5
seguiemj.ttf       451df9bb5546055af625ff86aa72695df43e8e170b4c6c1316fe44e9c7a22f7c
seguisym.ttf       a4a35dcc62cd30e1a6c97b695ecef83e59d2b149e3af834f6a49f11851d56b37
```

組版時の標準エラー出力が空であることを確認します。検査にはPopplerの `pdftoppm`（例：`pdftoppm -png -scale-to 1500 入力.pdf 出力接頭辞`）と、Pythonのpypdf・pdfplumber・Pillowを使いました。文字コード検査は `python scripts/check_text_encoding.py`、`python scripts/check_mojibake_markers.py --include-manuals`、`git diff --check` です。
