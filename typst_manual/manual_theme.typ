// manual_theme.typ — ジェムリアTRPG マニュアル共通テーマ
// 使い方:  #import "manual_theme.typ": *   →  #show: manual-conf

#let running_chapter = state("running_chapter", [ ])

#let hr() = line(length: 100%, stroke: 0.8pt + luma(75%))

#let box(body, title: none, kind: "rule") = {
  let (stroke_col, fill_col, label) = (
    if kind == "warn" { (luma(55%), luma(93%), "注意") }
    else if kind == "def" { (luma(60%), luma(96%), "定義") }
    else if kind == "ex"  { (luma(60%), luma(96%), "例") }
    else { (luma(55%), luma(97%), "ルール") }
  )
  let head = if title != none { title } else { label }
  block(inset: (x: 10pt, y: 8pt), radius: 6pt, stroke: 0.9pt + stroke_col, fill: fill_col)[
    #stack(spacing: 4pt, [*#head*], body)
  ]
}
#let rule_box(body, title: none) = box(body, title: title, kind: "rule")
#let warn_box(body, title: none) = box(body, title: title, kind: "warn")
#let def_box(body, title: none)  = box(body, title: title, kind: "def")
#let ex_box(body, title: none)   = box(body, title: title, kind: "ex")
#let note(body) = warn_box(body, title: "注記")

#let steps(body, title: "手順") = block(
  inset: (x: 10pt, y: 8pt), radius: 6pt, stroke: 0.9pt + luma(55%), fill: luma(97%))[
  #stack(spacing: 4pt, [*#title*], body)
]

#let terms_table(items) = {
  let cells = ()
  for pair in items { cells.push([*#pair.at(0)*]); cells.push([#pair.at(1)]) }
  block(inset: (x: 10pt, y: 8pt), radius: 6pt, stroke: 0.8pt + luma(70%), fill: luma(98%))[
    #table(columns: (33%, 67%), inset: (x: 6pt, y: 5pt), stroke: 0.6pt + luma(82%),
      table.header(table.cell(fill: luma(94%))[*用語*], table.cell(fill: luma(94%))[*説明*]),
      ..cells)
  ]
}

// テンプレート本体（set/show をまとめて適用する関数）
#let manual-conf(doc) = {
  set page(paper: "a4", margin: (top: 22mm, bottom: 22mm, left: 20mm, right: 20mm),
    header: context align(right, text(size: 9pt, fill: luma(20%))[#running_chapter.get()]),
    footer: context align(center, text(size: 9pt, fill: luma(20%))[#counter(page).display()]))
  set text(font: ("Noto Serif CJK JP", "Noto Sans CJK JP"), size: 12pt, lang: "ja")
  set par(leading: 0.68em, justify: false, spacing: 0.6em)
  set list(tight: false, spacing: 0.5em, indent: 1em)
  set heading(numbering: "1.1.1", outlined: true)
  show link: it => text(fill: rgb(0, 102, 204))[#underline(stroke: 0.6pt + rgb(0, 102, 204))[#it]]
  show heading.where(level: 1): it => { running_chapter.update(it.body); it }
  doc
}
