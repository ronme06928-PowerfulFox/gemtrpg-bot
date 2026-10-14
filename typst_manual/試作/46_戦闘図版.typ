// 図解試作の6図を本文組版用に分離。数値の変更時は元の図解も照合する。
#import "46_戦闘図解.typ": at, token, slot, arrow, tag, blue, red, gold, muted

#let diagram1 = box(width: 174mm, height: 41mm, [
  #at(9mm, 0mm, token("ナギ", blue, "110/129", "9/12", "1"))
  #at(115mm, 0mm, token("敵", red, "30/30", "6/6", "0"))
  #at(64mm, 3mm, box(width: 42mm)[#align(center)[#tag([ROUND 1])#v(3mm)#text(size: 10pt)[今回は1人1行動]#v(1mm)#text(size: 8pt, fill: muted)[追加効果・状態異常なし]]])
  #at(17mm, 35mm, text(size: 8pt, fill: muted)[HP・MPは 現在値 / 最大値])
  #at(65mm, 31mm, text(size: 8.5pt)[ナギは前の場面でHPとMPを消費しています。])
])

#let diagram2 = box(width: 174mm, height: 41mm, [
  #at(1mm, 0mm, text(size: 9pt)[ナギ　出目4 ＋ 速度補正2])
  #at(99mm, 0mm, text(size: 9pt)[敵　出目3 ＋ 速度補正1])
  #at(1mm, 7mm, slot("ナギのスロット", "6", blue))
  #at(99mm, 7mm, slot("敵のスロット", "4", red))
  #at(61mm, 10mm, arrow(w: 30mm))
  #at(64mm, 17mm, text(size: 8pt, fill: muted)[速い順に処理])
  #at(1mm, 27mm, tag([出身ボーナス　ナギのFP 1 → 2], color: gold))
  #at(103mm, 27mm, text(size: 8.5pt)[ラティウム：50%でFP＋1\ 今回はFPを1得たものとします。])
])

#let diagram3 = box(width: 174mm, height: 41mm, [
  #at(1mm, 2mm, slot("ナギのスロット", "6", blue))
  #at(115mm, 2mm, slot("敵のスロット", "4", red))
  #at(59mm, 3mm, arrow(w: 51mm, color: blue))
  #at(59mm, 10mm, arrow(w: 51mm, color: red, reverse: true))
  #at(1mm, 20mm, tag([基本の一太刀 / 消費なし]))
  #at(115mm, 20mm, tag([基本の一太刀 / 消費なし], color: red))
  #at(64mm, 21mm, text(size: 13pt, weight: "bold")[マッチ])
  #at(30mm, 33mm, text(size: 9pt)[今回は互いに「基本の一太刀」で攻撃します。])
])

#let diagram4 = box(width: 174mm, height: 41mm, [
  #at(1mm, 0mm, tag([ナギ / 基本の一太刀]))
  #at(109mm, 0mm, tag([敵 / 基本の一太刀], color: red))
  #at(1mm, 10mm, text(size: 10pt)[4 ＋ 1d2 ＋ 1d3])
  #at(109mm, 10mm, text(size: 10pt)[4 ＋ 1d2 ＋ 1d2])
  #at(1mm, 18mm, text(size: 12pt)[4 ＋ #box(stroke: blue, inset: 4pt, radius: 3pt)[2] ＋ #box(stroke: blue, inset: 4pt, radius: 3pt)[3]])
  #at(109mm, 18mm, text(size: 12pt)[4 ＋ #box(stroke: red, inset: 4pt, radius: 3pt)[1] ＋ #box(stroke: red, inset: 4pt, radius: 3pt)[1]])
  #at(65mm, 12mm, text(size: 27pt, weight: "bold")[#text(fill: blue)[9] > #text(fill: red)[6]])
  #at(68mm, 27mm, tag([ナギの勝利]))
])

#let diagram5 = box(width: 174mm, height: 41mm, [
  #at(1mm, 0mm, token("ナギ", blue, "110/129", "9/12", "2 → 3"))
  #at(121mm, 0mm, token("敵", red, "21/30", "6/6", "0"))
  #at(58mm, 2mm, text(size: 17pt, weight: "bold", fill: red)[9ダメージ])
  #at(56mm, 11mm, arrow(w: 60mm, color: red))
  #at(64mm, 20mm, text(size: 14pt, weight: "bold")[HP 30 → 21])
  #at(1mm, 32mm, text(size: 8.5pt)[攻撃同士の勝利でFP＋1])
  #at(110mm, 32mm, text(size: 8.5pt)[このマッチで両者の行動が終了])
])

#let diagram6 = box(width: 174mm, height: 41mm, [
  #at(1mm, 0mm, tag([基本の一太刀：終了時にFP＋2], color: gold))
  #at(1mm, 11mm, text(size: 10pt)[ナギのFP])
  #at(27mm, 8mm, text(size: 20pt, weight: "bold", fill: blue)[3 → 5])
  #at(101mm, 11mm, text(size: 10pt)[敵のFP])
  #at(125mm, 8mm, text(size: 20pt, weight: "bold", fill: red)[0 → 2])
  #at(1mm, 23mm, rect(width: 170mm, fill: rgb("f1f4f6"), stroke: none, radius: 3pt, inset: 3mm)[
    #text(size: 9pt)[*終了時*　ナギ：HP 110 / MP 9 / FP 5　　敵：HP 21 / MP 6 / FP 2]
  ])
])
