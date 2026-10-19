// manual_theme.typ — ジェムリアTRPG マニュアル共通テーマ
// 使い方:  #import "manual_theme.typ": *   →  #show: manual-conf

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

// 計画46・4CのC案（2026-10-18採用）。本文・図の文字は縮小しない。
#let publication-figure(n, caption, body) = block(
  breakable: false, above: 3mm, below: 3mm,
)[
  #rect(fill: rgb("f7f9fa"), stroke: 0.5pt + rgb("dce3e8"), radius: 4pt,
    inset: (x: 0pt, y: 3mm), body)
  #v(1mm)
  #text(size: 9pt, fill: rgb("647080"))[図#n　#caption]
]

#let publication-conf(doc, header-label: none, footer-label: none) = {
  set page(paper: "a4", binding: left,
    margin: (inside: 24mm, outside: 20mm, top: 23mm, bottom: 23mm),
    // 柱は、そのページで始まる章、なければ直前の章を示す。
    // ヘッダーは本文より先に評価されるため、stateではなく見出しを検索する。
    header: context text(size: 8pt, fill: rgb("647080"))[
      #if header-label != none { header-label } else {
        let chapters = query(heading.where(level: 1))
        let starting = chapters.filter(h => h.location().page() == here().page())
        let started = chapters.filter(h => h.location().page() < here().page())
        if starting.len() > 0 { starting.first().body }
        else if started.len() > 0 { started.last().body }
      }
    ],
    footer: context align(right, text(size: 8pt, fill: rgb("647080"))[
      #if footer-label != none [#footer-label　]#counter(page).display()
    ]))
  set text(font: "Noto Sans JP", size: 11pt, lang: "ja", fill: rgb("253345"))
  set par(leading: 0.65em, spacing: 1.4em)
  set heading(numbering: none, outlined: true)
  show heading.where(level: 1): set text(size: 23pt)
  show heading.where(level: 2): set text(size: 14pt, fill: rgb("246589"))
  show heading.where(level: 2): set block(above: 3.5mm, below: 1.5mm)
  // 目次・しおりの見出し文字列には装飾を含めない。
  show heading.where(level: 2): it => block(sticky: true, grid(
    columns: (1.8mm, 1fr), column-gutter: 2.2mm, align: horizon,
    circle(radius: 0.9mm, fill: rgb("246589"), stroke: none),
    it.body,
  ))
  show link: it => text(fill: rgb("246589"))[#underline(stroke: 0.6pt + rgb("246589"))[#it]]
  doc
}

#let manual-conf = publication-conf
