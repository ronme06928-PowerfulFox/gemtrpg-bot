// 操作ガイドの章ファイルで共通に使う部品。
#import "../manual_theme.typ": publication-figure

// 本文と索引の参照先は、リンクと実際のページ番号を併記する。
#let guide-ref(target, body) = context link(target)[#body（#counter(page).at(target).first()ページ）]

// 章は自然に続け、巻頭・共通編・PL編・GM編・索引の入口で改ページする。
#let chapter(title) = {
  if title in ([この本の使い方], [共通　始める前に], [PL 1　キャラクターを用意する], [GM 1　卓を準備する], [困ったときの索引]) { pagebreak(weak: true) }
  heading(level: 1, title)
}

// 図の番号は本全体の通し番号にする。
#let fig-counter = counter("guide-figure")
#let fig(caption, body) = {
  fig-counter.step()
  context publication-figure(fig-counter.display(), caption, body)
}

// 症状と確かめることの表（各章末の「困ったとき」）。
#let trouble(..rows) = block(breakable: false)[#table(
  columns: (38%, 62%), inset: (x: 6pt, y: 5pt), stroke: 0.6pt + rgb("dce3e8"),
  table.header(table.cell(fill: rgb("eef1f3"))[*症状*], table.cell(fill: rgb("eef1f3"))[*確かめること*]),
  ..rows.pos().flatten(),
)]

// 簡略図の部品（試作「1ラウンドを操作する流れ」と同じ見た目）
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
