# セッション操作ガイド（原稿）

計画46・4Dで制作中のセッション操作ガイドの原稿。書き方は[書き方の手引き](../WRITING_GUIDE.md)、紙面は共通テーマ `../manual_theme.typ` の `publication-conf`（C案）に従う。進め方は[統合作業計画](../../manuals/planned/46_Publication_Execution_Plan.md)§11、章ごとの状態と確認事項は[出典・不足台帳](../../manuals/planned/46_Publication_Source_Inventory.md)§16。

```powershell
typst compile --root typst_manual typst_manual/操作ガイド/main.typ output/pdf/46_operation_guide.pdf
```

| ファイル | 内容 |
| --- | --- |
| `main.typ` | 表紙・目次・章の読み込み |
| `parts.typ` | 章で共通に使う部品（章の開始、未執筆の枠） |
| `00_この本の使い方.typ` | 冊子の使い方・読む順番 |
| `01_始める前に.typ` | 共通編 |
| `02_`〜`05_` | プレイヤー編 PL 1〜4 |
| `90_困ったときの索引.typ` | 巻末の症状索引 |

GM編の章は4Fで追加する。レビュー用のPDFは `output/pdf/46_operation_guide.pdf`、刊行版の `main.pdf` は段階6で作る。表示確認画像は `../_local/previews/46_operation_guide/` に保存する。
