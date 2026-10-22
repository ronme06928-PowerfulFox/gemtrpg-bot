// Build: typst compile --root typst_manual typst_manual/全体マニュアル/main.typ typst_manual/全体マニュアル/main.pdf
#import "../manual_theme.typ": book-conf, book-cover, publication-toc
#import "../publication_info.typ": publications
#set document(title: "ジェムリアTRPG " + publications.book.title + "・" + publications.book.edition)
#show: book-conf
#show heading.where(level: 3): set heading(bookmarked: false)

#book-cover()
#publication-toc()

#include "00_この本の使い方.typ"
#include "01_ジェムリアで遊ぶ.typ"
#include "02_キャラクターを作る.typ"
#include "03_探索と判定.typ"
#include "04_戦闘の基本.typ"
#include "05_戦闘の裁定.typ"
#include "06_状態異常と特殊効果.typ"
#include "07_セッションの終わりと成長.typ"
#include "90_巻末.typ"

#import "../publication_endmatter.typ": publication-endmatter
#publication-endmatter("book")
