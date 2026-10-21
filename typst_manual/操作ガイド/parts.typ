// 操作ガイドの章ファイルで共通に使う部品。
#import "../manual_theme.typ" as theme
#let publication-header = theme.publication-header
#let callout = theme.guide-callout

// 本文と索引の参照先は、リンクと実際のページ番号を併記する。
#let guide-ref(target, body) = context link(target)[#body（#counter(page).at(target).first()ページ）]

// 章扉・図番号は本番の共通テーマで管理する。
#let chapter = theme.guide-chapter
#let fig = theme.guide-fig

// 症状と確かめることの表（各章末の「困ったとき」）。
#let trouble(..rows) = context block(breakable: false)[#table(
  columns: (38%, 62%), inset: (x: 6pt, y: 5pt), stroke: 0.6pt + rgb("dce3e8"),
  publication-header(theme.guide-current-mark().part, guide: true, [*症状*], [*確かめること*]),
  ..rows.pos().flatten(),
)]

// 簡略図の部品（試作「1ラウンドの流れ」と同じ見た目）
#let blue = rgb("246589")
#let red = rgb("a9493e")
#let muted = rgb("647080")
#let line-c = rgb("c9d2d9")
#let at(x, y, body) = place(top + left, dx: x, dy: y, body)
#let arrow(w: 10mm, color: blue) = box(width: w, height: 6mm)[
  #place(left + horizon, line(length: w - 2mm, stroke: 1.5pt + color))
  #place(right + horizon, text(fill: color, size: 15pt)[▶])
]
#let tag(body, color: blue) = box(fill: color.lighten(90%), radius: 3pt, inset: (x: 6pt, y: 3pt), text(fill: color, size: 9pt, weight: "bold", body))
#let button(body, active: false, color: blue) = box(
  fill: if active { color } else { white },
  stroke: 0.8pt + color, radius: 3pt, inset: (x: 5pt, y: 3pt),
  text(size: 9pt, weight: "bold", fill: if active { white } else { color }, body),
)
#let screen(w, h, title, body) = box(width: w, height: h, fill: white, stroke: 0.8pt + line-c, radius: 3pt)[
  #at(3mm, 2mm, text(size: 8.5pt, weight: "bold", fill: muted, title))
  #body
]
#let field(w, body) = box(width: w, stroke: 0.6pt + line-c, radius: 2pt, inset: 3pt, text(size: 8.5pt, fill: muted, body))
#let piece(name, color) = circle(radius: 6mm, inset: 0pt, fill: color.lighten(90%), stroke: 1.2pt + color)[#align(center + horizon, text(size: 10pt, weight: "bold", fill: color, name))]
