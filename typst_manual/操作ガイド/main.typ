// セッション操作ガイド（計画46・4D〜4Fで制作中）
// Build: typst compile --root typst_manual typst_manual/操作ガイド/main.typ output/pdf/46_operation_guide.pdf
#import "../manual_theme.typ": publication-conf

#show: publication-conf.with(footer-label: "ジェムリアTRPG / セッション操作ガイド・作業版")

#page(header: none, footer: none)[
  #v(60mm)
  #text(size: 12pt, fill: rgb("647080"))[ジェムリアTRPG]
  #v(4mm)
  #text(size: 30pt, weight: "bold")[セッション操作ガイド]
  #v(6mm)
  #text(size: 12pt)[共通編・プレイヤー編・GM編]
  #v(1fr)
  #text(size: 9pt, fill: rgb("647080"))[作業版。本文は制作中で、内容は確定していません。]
]

#outline(title: "目次", depth: 2)

#include "00_この本の使い方.typ"
#include "01_始める前に.typ"
#include "02_キャラクターを用意する.typ"
#include "03_画面を読む.typ"
#include "04_探索と戦闘を操作する.typ"
#include "05_セッションの後.typ"
#include "06_GM_卓を準備する.typ"
#include "07_GM_当日を進める.typ"
#include "08_GM_介入と復旧.typ"
#include "09_GM_素材を作る.typ"
#include "90_困ったときの索引.typ"
