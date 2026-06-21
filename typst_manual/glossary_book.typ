// glossary_book.typ — 別冊「用語辞典」/ アプリのデータ定義から自動生成
// このファイルを「組版する本体」として書き出すと、用語辞典PDFができる。
#import "manual_theme.typ": *
#set document(title: "ジェムリアTRPG 用語辞典")
#show: manual-conf

// 同じフォルダにある JSON を読む（用語が増えたらこのファイルを上書きするだけ）
#let glossary = json("glossary_catalog_cache.json")

#let nl(s) = s.split("\n").join(linebreak())          // JSON内の改行を反映
#let name_of(id) = if id in glossary { glossary.at(id).display_name } else { id }

// カテゴリの表示順と色（存在しないカテゴリは自動でスキップ）
#let category_order = ("ルール", "タイミング", "スキルタグ", "状態異常", "効果", "デバフ", "バフ")
#let cat_color(c) = (
  "状態異常": rgb(150, 0, 0),
  "効果": rgb(0, 110, 0),
  "デバフ": rgb(120, 60, 0),
  "バフ": rgb(0, 80, 160),
).at(c, default: luma(60%))

#let term_card(t) = block(width: 100%, breakable: false,
  inset: (x: 10pt, y: 8pt), radius: 6pt, stroke: 0.9pt + luma(60%), fill: luma(98%))[
  #grid(columns: (1fr, auto), column-gutter: 6pt, align: (left + horizon, right + horizon),
    text(size: 13pt, weight: "bold")[#t.display_name],
    text(size: 8.5pt, fill: cat_color(t.category))[#t.term_id ・ #t.category])
  #v(4pt)
  #nl(t.long)
  #if t.flavor != "" {
    v(5pt)
    block(width: 100%, fill: luma(95%), inset: (x: 8pt, y: 5pt), radius: 4pt)[
      #text(size: 9.5pt, style: "italic", fill: luma(30%))[#nl(t.flavor)]]
  }
  #if t.links.len() > 0 {
    v(5pt)
    text(size: 9pt, fill: rgb(0, 102, 204))[関連: #t.links.map(name_of).join("　/　")]
  }
]

#align(center)[#text(size: 22pt, weight: "bold")[ジェムリアTRPG　用語辞典]]
#v(0.5em)
#align(center)[#text(size: 10pt, fill: luma(40%))[ダイスボットアプリのデータ定義から自動生成]]
#v(1.5em)

#for cat in category_order [
  == #cat
  #for (id, t) in glossary.pairs() {
    if t.is_enabled and t.category == cat { term_card(t); v(6pt) }
  }
]
