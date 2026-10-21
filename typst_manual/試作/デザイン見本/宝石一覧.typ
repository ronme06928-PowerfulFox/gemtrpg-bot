// Build: typst compile --root typst_manual typst_manual/試作/デザイン見本/宝石一覧.typ output/pdf/46_gem_catalog.pdf
// 計画46・デザイン見本。章や編に割り当てる候補の宝石を、塗り・線画・小さな目印の3通りで並べる。
#import "book_theme.typ": stones, gem-shape, ink, muted
#set page(paper: "a4", flipped: true, margin: 14mm)
#set text(font: "Noto Sans JP", size: 9pt, fill: ink)
#text(size: 18pt, weight: "bold")[宝石マークの候補]
#h(4mm) #text(fill: muted)[上段：塗り（基本ルールブック）　中段：線画（操作ガイド）　下段：見出しの目印の大きさ]
#v(3mm)
#let keys = stones.keys()
#let half = 6
#for row in keys.chunks(half) {
  let pad = range(half - row.len()).map(_ => [])
  grid(columns: (1fr,) * half, column-gutter: 3mm, row-gutter: 2.5mm, align: center + bottom,
    ..row.map(k => gem-shape(k, 24mm, stones.at(k).main)), ..pad,
    ..row.map(k => gem-shape(k, 11mm, stones.at(k).main, wire: true)), ..pad,
    ..row.map(k => [#gem-shape(k, 5mm, stones.at(k).main)#h(1.5mm)#text(size: 10pt, weight: "bold", fill: stones.at(k).main, stones.at(k).name)]), ..pad,
  )
  v(5mm)
}
