// 2冊で同じ項目・版情報を使う奥付。
#import "publication_info.typ": *
#import "manual_theme.typ": book-chapter, guide-chapter

#let publication-endmatter(key) = {
  let info = publications.at(key)
  if key == "book" {
    book-chapter("A", "巻末", [奥付], [], target: <publication-colophon>)
  } else {
    guide-chapter("index", "END", [奥付], [], target: <publication-colophon>)
  }
  [*#info.title*]
  parbreak()
  publication-status(key)
  parbreak()
  if publication-date != none { [発行日：#publication-date]; parbreak() }
  [発行元：#publisher]
  parbreak()
  distribution
  parbreak()
  if info.app-checked != none {
    [確認したアプリの日付：#info.app-checked]
    parbreak()
  }
  heading(level: 2, [関連冊子])
  for other in ("book", "guide") {
    let related = publications.at(other)
    [#related.title　#related.edition]
    parbreak()
  }
  [#heading(level: 2, [改訂履歴]) <publication-history>]
  for item in info.history {
    [#item.edition：#item.summary]
    parbreak()
  }
}
