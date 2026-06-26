// theme.typ — ジェムリアTRPG プロジェクト文書 共通テーマ（Typst）
//
// 使い方:
//   #import "../lib/theme.typ": *
//   #show: doc-conf.with(
//     title: "ドキュメント名",
//     subtitle: "サブタイトル（任意）",
//     meta: (("版", "2026-06-26"), ("対象", "運用担当")),
//   )
//
// 提供する補助:
//   note/warn-box/rule-box/def-box/ex-box/steps/terms-table/hr/kbd
//
// 新しいTypst文書は本テーマを import して統一感を保つこと（README参照）。

#let running_chapter = state("running_chapter", [ ])

#let hr() = line(length: 100%, stroke: 0.8pt + luma(75%))

// インライン強調（コマンド・キー入力など）
#let kbd(body) = box(
  inset: (x: 4pt, y: 1pt), radius: 3pt, fill: luma(94%), stroke: 0.5pt + luma(75%),
)[#raw(body)]

#let _box(body, title: none, kind: "rule") = {
  let (stroke_col, fill_col, label) = (
    if kind == "warn" { (rgb(190, 80, 60), rgb(252, 244, 242), "注意") }
    else if kind == "def" { (luma(60%), luma(96%), "定義") }
    else if kind == "ex"  { (luma(60%), luma(96%), "例") }
    else { (luma(55%), luma(97%), "ポイント") }
  )
  let head = if title != none { title } else { label }
  block(width: 100%, inset: (x: 10pt, y: 8pt), radius: 6pt, stroke: 0.9pt + stroke_col, fill: fill_col)[
    #stack(spacing: 4pt, [*#head*], body)
  ]
}
#let rule-box(body, title: none) = _box(body, title: title, kind: "rule")
#let warn-box(body, title: none) = _box(body, title: title, kind: "warn")
#let def-box(body, title: none)  = _box(body, title: title, kind: "def")
#let ex-box(body, title: none)   = _box(body, title: title, kind: "ex")
#let note(body) = warn-box(body, title: "注記")

#let steps(body, title: "手順") = block(
  width: 100%, inset: (x: 10pt, y: 8pt), radius: 6pt, stroke: 0.9pt + luma(55%), fill: luma(97%))[
  #stack(spacing: 4pt, [*#title*], body)
]

#let terms-table(items) = {
  let cells = ()
  for pair in items { cells.push([*#pair.at(0)*]); cells.push([#pair.at(1)]) }
  block(width: 100%, inset: (x: 10pt, y: 8pt), radius: 6pt, stroke: 0.8pt + luma(70%), fill: luma(98%))[
    #table(columns: (33%, 67%), inset: (x: 6pt, y: 5pt), stroke: 0.6pt + luma(82%),
      table.header(table.cell(fill: luma(94%))[*項目*], table.cell(fill: luma(94%))[*説明*]),
      ..cells)
  ]
}

// 文書テンプレート本体。title/subtitle/meta を受けて表紙ブロックと共通設定を適用する。
#let doc-conf(title: "", subtitle: none, meta: (), doc) = {
  set page(paper: "a4", margin: (top: 22mm, bottom: 22mm, left: 20mm, right: 20mm),
    header: context align(right, text(size: 9pt, fill: luma(20%))[#running_chapter.get()]),
    footer: context align(center, text(size: 9pt, fill: luma(20%))[#counter(page).display()]))
  set text(font: ("Noto Serif CJK JP", "Noto Sans CJK JP"), size: 11pt, lang: "ja")
  set par(leading: 0.68em, justify: false, spacing: 0.6em)
  set list(tight: false, spacing: 0.5em, indent: 1em)
  set heading(numbering: "1.1.1", outlined: true)
  show link: it => text(fill: rgb(0, 102, 204))[#underline(stroke: 0.6pt + rgb(0, 102, 204))[#it]]
  show heading.where(level: 1): it => { running_chapter.update(it.body); it }
  show heading.where(level: 1): set text(size: 17pt, weight: "bold")
  show heading.where(level: 2): set text(size: 13.5pt, weight: "bold")
  show heading.where(level: 3): set text(size: 11.5pt, weight: "bold")

  // 表紙ブロック
  block(width: 100%, inset: (x: 0pt, y: 0pt))[
    #text(size: 22pt, weight: "bold")[#title]
    #if subtitle != none [ \ #text(size: 13pt, fill: luma(35%))[#subtitle] ]
  ]
  if meta.len() > 0 {
    v(6pt)
    block(inset: (x: 10pt, y: 8pt), radius: 6pt, fill: luma(96%), stroke: 0.6pt + luma(80%))[
      #table(columns: (auto, 1fr), inset: (x: 6pt, y: 3pt), stroke: none,
        ..meta.map(p => ([*#p.at(0)*], [#p.at(1)])).flatten())
    ]
  }
  v(4pt)
  hr()
  v(6pt)
  doc
}
