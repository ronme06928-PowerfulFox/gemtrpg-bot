// 2冊で同じ項目・版情報を使う奥付。章扉・柱・つまみを付けない、シンプルな1ページにする。
#import "publication_info.typ": *
#import "manual_theme.typ": ink, muted

#let publication-endmatter(key) = {
  let info = publications.at(key)
  let item(label, body) = grid(columns: (30mm, 1fr), column-gutter: 3mm, text(fill: muted, label), body)
  page(header: none, background: none)[
    // 目次は章の目印と見出しを対で数えるため、目印だけを置き、章扉は描かない。
    #if key == "book" {
      [#metadata((key: "A", num: "巻末", title: [奥付])) <chapter-mark>]
    } else {
      [#metadata((part: "index", code: "END", title: [奥付])) <guide-mark>]
    }
    #show heading.where(level: 1): it => block(above: 3mm, below: 3mm, text(size: 13pt, weight: "bold", fill: ink, it.body))
    #show heading.where(level: 2): it => block(above: 4mm, below: 2mm, text(size: 10pt, weight: "bold", fill: ink, it.body))
    #set text(size: 10pt)
    #set par(spacing: 1.2em)
    #v(1fr)
    #line(length: 100%, stroke: 0.6pt + ink)
    #[#heading(level: 1)[奥付] <publication-colophon>]
    #text(size: 12pt, weight: "bold", info.title)
    #v(1mm)
    #item([版], publication-status(key))
    #if publication-date != none { item([発行日], publication-date) }
    #item([発行元], publisher)
    #item([配布], distribution)
    #if info.app-checked != none { item([確認したアプリ], info.app-checked) }
    #heading(level: 2)[関連冊子]
    #for other in ("book", "guide") {
      let related = publications.at(other)
      [#related.title　#related.edition]
      linebreak()
    }
    #[#heading(level: 2)[改訂履歴] <publication-history>]
    #for entry in info.history {
      [#entry.edition：#entry.summary]
      linebreak()
    }
    #line(length: 100%, stroke: 0.6pt + ink)
  ]
}
