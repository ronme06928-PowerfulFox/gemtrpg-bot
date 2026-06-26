# manuals/typst — プロジェクト文書の Typst 置き場

プロジェクトの仕様・計画・運用手順を **PDF 化する Typst ソース**を管理するディレクトリ。
MD の正本（`manuals/implemented/`・`planned/`・`operations/`）に対する「整形済みPDF版」を作る。

## ディレクトリ構成

```
manuals/typst/
  README.md                  このファイル
  lib/
    theme.typ                共有テーマ（全文書で import する）
  build/                     コンパイル出力(PDF)。gitignore（コミットしない）
  operations_runbook.typ     運用手順書（MD正本: manuals/operations/account_system_deploy_runbook.md）
  json_definition_manual.typ JSON定義マニュアル（旧式・共有テーマ未使用。移行は任意）
  AI_PROMPT_JSON_MANUAL.md    他AIチャットに投げる再生成プロンプト
```

> 用語辞典の「別冊」（アプリのデータから自動生成する本）は別系統で、リポジトリ直下の
> `typst_manual/`（`glossary_book.typ` + 専用テーマ + データキャッシュ）に置いている。
> あちらはデータ生成物と密結合の自己完結ユニットなので、本ディレクトリとは分離している。

## 新しい Typst 文書の追加手順

1. `manuals/typst/<name>.typ` を作成し、先頭で共有テーマを import する。

   ```typst
   #import "lib/theme.typ": *

   #show: doc-conf.with(
     title: "ドキュメント名",
     subtitle: "サブタイトル（任意）",
     meta: (("版", "2026-06-26"), ("対象", "..."), ("MD正本", "manuals/.../xxx.md")),
   )

   = 見出し
   本文...
   ```

2. 利用できる補助（`lib/theme.typ`）:
   - `doc-conf(title:, subtitle:, meta:, doc)` … テンプレート本体（表紙＋共通設定）
   - `note(body)` / `warn-box(body, title:)` / `rule-box` / `def-box` / `ex-box`
   - `steps(body, title:)` … 手順ブロック
   - `terms-table(items)` … 用語表（`items` は `(("項目","説明"), ...)`）
   - `kbd("text")` … コマンド/キー入力のインライン強調
   - `hr()` … 区切り線

3. ビルド（PDFは `build/` へ。`build/` は gitignore）:

   ```bash
   typst compile manuals/typst/<name>.typ manuals/typst/build/<name>.pdf
   ```

## 運用ルール

- **MD が正本**。Typst は整形版。内容を変えたらまず対応する MD を更新し、Typst に反映する。
- 新規文書は必ず `lib/theme.typ` を import して体裁を統一する。
- `build/*.pdf` はコミットしない（ソースから再生成できる）。
- 日本語フォントは `Noto Serif/Sans CJK JP` を指定。未インストール環境ではフォント警告が出るが
  フォールバックで生成される（内容に影響なし）。

## 既存資産メモ

- `json_definition_manual.typ`: スキル/バフJSON統合マニュアルの雛形。共有テーマ化前の旧式。
  正本 `manuals/implemented/C01_JSON_Definition_Master.md` を更新したら差分反映する。
  時間があれば `lib/theme.typ` へ移行してよい。
