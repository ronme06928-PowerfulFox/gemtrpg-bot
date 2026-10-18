// 操作ガイドの章ファイルで共通に使う部品。

// 制作中の節に置く枠。出典と執筆前の確認事項を示し、本文としては扱わない。
#let unwritten(source: none, check: none) = block(
  width: 100%, inset: (x: 10pt, y: 8pt), radius: 4pt,
  stroke: (paint: rgb("9aa6b2"), thickness: 0.8pt, dash: "dashed"),
  fill: rgb("f4f6f8"),
)[
  #set text(size: 9pt, fill: rgb("647080"))
  #set par(spacing: 0.8em)
  *未執筆*
  #if source != none [\ 出典：#source]
  #if check != none [\ 確認すること：#check]
]

// 章の始まり。前の章から改ページする。
#let chapter(title) = {
  pagebreak(weak: true)
  heading(level: 1, title)
}
