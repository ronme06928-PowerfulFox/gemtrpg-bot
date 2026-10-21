// Build: typst compile --root typst_manual typst_manual/全体マニュアル/main.typ typst_manual/全体マニュアル/main.pdf
#import "../manual_theme.typ": publication-conf
#set document(title: "ジェムリアTRPG 基本ルールブック・作業版")
#show: publication-conf.with(footer-label: "ジェムリアTRPG / 基本ルールブック・作業版")
#show heading.where(level: 1): it => { pagebreak(weak: true); it }
#show heading.where(level: 3): set heading(bookmarked: false)

#page(header: none, footer: none)[
  #v(60mm)
  #text(size: 12pt, fill: rgb("647080"))[ジェムリアTRPG]
  #v(4mm)
  #text(size: 12pt)[The Ray, from Perfect Gemstone]
  #v(6mm)
  #text(size: 30pt, weight: "bold")[基本ルールブック]
  #v(1fr)
  #text(size: 9pt, fill: rgb("647080"))[作業版。本文は制作中で、内容は確定していません。]
]

#outline(title: "目次", depth: 2)

#include "00_この本の使い方.typ"
#include "01_ジェムリアで遊ぶ.typ"
#include "02_キャラクターを作る.typ"
#include "03_探索と判定.typ"
#include "04_戦闘の基本.typ"
#include "05_戦闘の裁定.typ"
#include "06_状態異常と特殊効果.typ"
#include "07_セッションの終わりと成長.typ"
#include "90_巻末.typ"
