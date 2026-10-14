// Build: typst compile typst_manual/試作/46_戦闘図解.typ output/pdf/46_battle_visual_walkthrough.pdf
#set page(paper: "a4", margin: (x: 14mm, y: 13mm), fill: rgb("faf9f5"), footer: context align(right, text(size: 8pt, fill: rgb("667085"))[ジェムリアTRPG / 戦闘入門・図解試作　#counter(page).display() / 2]))
#set text(font: "Noto Sans JP", size: 10pt, fill: rgb("253345"), lang: "ja")
#set par(leading: 0.55em, spacing: 1.4em)
#set block(above: 0pt, below: 0pt)
#let blue = rgb("246589")
#let red = rgb("a9493e")
#let gold = rgb("99651e")
#let muted = rgb("647080")
#let light = rgb("e5e9ec")
#let ink = rgb("253345")
#let tag(body, color: blue) = box(fill: color.lighten(90%), radius: 3pt, inset: (x: 6pt, y: 3pt), text(fill: color, size: 9pt, weight: "bold", body))
#let at(x, y, body) = place(top + left, dx: x, dy: y, body)
#let arrow(w: 38mm, color: blue, reverse: false) = box(width: w, height: 6mm)[
  #place(left + horizon, line(length: w - 2mm, stroke: 1.5pt + color))
  #place(if reverse {left + horizon} else {right + horizon}, text(fill: color, size: 15pt)[#if reverse [◀] else [▶]])
]
#let token(name, color, hp, mp, fp) = box(width: 48mm)[
  #set par(spacing: 0pt)
  #align(center)[
    #circle(radius: 7mm, inset: 0pt, fill: color.lighten(91%), stroke: 1.4pt + color)[#align(center + horizon, text(size: 13pt, fill: color, weight: "bold", name))]
    #v(1mm)
    #text(size: 9pt)[HP #hp　MP #mp]
    #v(1mm)
    #tag([FP #fp], color: gold)
  ]
]
#let slot(name, speed, color, done: false) = rect(width: 55mm, height: 13mm, radius: 3pt, fill: if done {rgb("f0f1f2")} else {color.lighten(94%)}, stroke: 0.8pt + color, inset: 3mm)[
  #text(size: 10pt, weight: "bold", fill: color)[#name　#h(1fr)#if done [解決済] else [速度 #speed]]
]
#let panel(n, title, body, caption) = block(width: 100%, height: 68mm, fill: white, stroke: 0.6pt + light, radius: 5pt, inset: 4mm)[
  #set par(spacing: 0pt)
  #text(size: 12pt, weight: "bold")[#text(fill: blue)[#n]　#title]
  #v(2mm)
  #box(width: 100%, height: 41mm, body)
  #v(1mm)
  #text(size: 9pt, caption)
]
#let heading(kicker, title, desc) = [
  #text(fill: blue, size: 9pt, weight: "bold", tracking: 1pt, kicker)
  #v(2mm)
  #text(size: 24pt, weight: "bold", title)
  #v(2mm)
  #text(size: 9.5pt, desc)
  #v(4mm)
]

#heading([BATTLE TUTORIAL　/　01], [戦闘の流れ], [作成したキャラクターを使って、戦闘の開始から1ラウンドが終わるまでを見ていきます。])
#panel("01", [戦闘開始時の状態を確認する], [
  #at(9mm, 0mm, token("ナギ", blue, "110/129", "9/12", "1"))
  #at(115mm, 0mm, token("敵", red, "30/30", "6/6", "0"))
  #at(64mm, 3mm, box(width: 42mm)[#align(center)[#tag([ROUND 1])#v(3mm)#text(size: 10pt)[今回は1人1行動]#v(1mm)#text(size: 8pt, fill: muted)[追加効果・状態異常なし]]])
  #at(17mm, 35mm, text(size: 8pt, fill: muted)[HP・MPは 現在値 / 最大値])
  #at(65mm, 31mm, text(size: 8.5pt)[ナギは前の場面でHPとMPを消費しています。])
], [HP・MP・FPは前の場面から引き継ぎます。ただし、シナリオに指定があれば回復などを行います。])
#v(3mm)
#panel("02", [ラウンド開始時に行動速度を決める], [
  #at(1mm, 0mm, text(size: 9pt)[ナギ　出目4 ＋ 速度補正2])
  #at(99mm, 0mm, text(size: 9pt)[敵　出目3 ＋ 速度補正1])
  #at(1mm, 7mm, slot("ナギのスロット", "6", blue))
  #at(99mm, 7mm, slot("敵のスロット", "4", red))
  #at(61mm, 10mm, arrow(w: 30mm))
  #at(64mm, 17mm, text(size: 8pt, fill: muted)[速い順に処理])
  #at(1mm, 27mm, tag([出身ボーナス　ナギのFP 1 → 2], color: gold))
  #at(103mm, 27mm, text(size: 8.5pt)[ラティウム：50%でFP＋1\ 今回はFPを1得たものとします。])
], [１つのラウンドにおけるキャラの行動回数は「スロット」の数で決まります。
それぞれ1d6に速度補正を加えて、行動速度を決めます。])
#v(3mm)
#panel("03", [スキルと対象を選ぶ], [
  #at(1mm, 2mm, slot("ナギのスロット", "6", blue))
  #at(115mm, 2mm, slot("敵のスロット", "4", red))
  #at(59mm, 3mm, arrow(w: 51mm, color: blue))
  #at(59mm, 10mm, arrow(w: 51mm, color: red, reverse: true))
  #at(1mm, 20mm, tag([基本の一太刀 / 消費なし]))
  #at(115mm, 20mm, tag([基本の一太刀 / 消費なし], color: red))
  #at(64mm, 21mm, text(size: 13pt, weight: "bold")[マッチ])
  #at(30mm, 33mm, text(size: 9pt)[今回は互いに「基本の一太刀」で攻撃します。])
], [互いのスロットをマッチにすると、スキルの威力を比べて勝敗を決めます。
全員の宣言が確定したら、解決フェーズに移行します。])
#v(3mm)
#text(size: 8pt, fill: muted)[図の読み方：青＋名前＝ナギ ／ 赤＋名前＝敵 ／ 四角＝スロット ／ 矢印＝対象\ 教材用の敵・出目を使った模式図です。実画面のボタン配置は操作ガイドで扱います。]

#pagebreak()
#heading([BATTLE TUTORIAL　/　02], [マッチとラウンド終了の処理], [味方と敵の宣言を確定すると、解決フェーズでスキルの処理を行います。])
#panel("04", [スキルの威力を比べる], [
  #at(1mm, 0mm, tag([ナギ / 基本の一太刀]))
  #at(109mm, 0mm, tag([敵 / 基本の一太刀], color: red))
  #at(1mm, 10mm, text(size: 10pt)[4 ＋ 1d2 ＋ 1d3])
  #at(109mm, 10mm, text(size: 10pt)[4 ＋ 1d2 ＋ 1d2])
  #at(1mm, 18mm, text(size: 12pt)[4 ＋ #box(stroke: blue, inset: 4pt, radius: 3pt)[2] ＋ #box(stroke: blue, inset: 4pt, radius: 3pt)[3]])
  #at(109mm, 18mm, text(size: 12pt)[4 ＋ #box(stroke: red, inset: 4pt, radius: 3pt)[1] ＋ #box(stroke: red, inset: 4pt, radius: 3pt)[1]])
  #at(65mm, 12mm, text(size: 27pt, weight: "bold")[#text(fill: blue)[9] > #text(fill: red)[6]])
  #at(68mm, 27mm, tag([ナギの勝利]))
], [□内がダイスの出目です。ナギは物理補正が3なので1d3を振ります。今回は威力9でナギが勝ちました。])
#v(3mm)
#panel("05", [ダメージと勝利時のFPを反映する], [
  #at(1mm, 0mm, token("ナギ", blue, "110/129", "9/12", "2 → 3"))
  #at(121mm, 0mm, token("敵", red, "21/30", "6/6", "0"))
  #at(58mm, 2mm, text(size: 17pt, weight: "bold", fill: red)[9ダメージ])
  #at(56mm, 11mm, arrow(w: 60mm, color: red))
  #at(64mm, 20mm, text(size: 14pt, weight: "bold")[HP 30 → 21])
  #at(1mm, 32mm, text(size: 8.5pt)[攻撃同士の勝利でFP＋1])
  #at(110mm, 32mm, text(size: 8.5pt)[このマッチで両者の行動が終了])
], [攻撃同士のマッチでは、勝った側の威力がダメージになります。敵のHPが9減り、ナギはFPを1得ます。])
#v(3mm)
#panel("06", [ラウンド終了時の効果を処理する], [
  #at(1mm, 0mm, tag([基本の一太刀：終了時にFP＋2], color: gold))
  #at(1mm, 11mm, text(size: 10pt)[ナギのFP])
  #at(27mm, 8mm, text(size: 20pt, weight: "bold", fill: blue)[3 → 5])
  #at(101mm, 11mm, text(size: 10pt)[敵のFP])
  #at(125mm, 8mm, text(size: 20pt, weight: "bold", fill: red)[0 → 2])
  #at(1mm, 23mm, rect(width: 170mm, fill: rgb("f1f4f6"), stroke: none, radius: 3pt, inset: 3mm)[
    #text(size: 9pt)[*終了時*　ナギ：HP 110 / MP 9 / FP 5　　敵：HP 21 / MP 6 / FP 2]
  ])
], [「基本の一太刀」を使った2人は、それぞれFPを2得ます。マッチの勝敗にかかわらず発動する効果です。])
#v(3mm)
#text(size: 8pt, fill: muted)[ナギのFPは、開始時1＋出身ボーナス1＋勝利時1＋終了時2で5になります。\ 敵はまだ倒れていないので、戦闘を続ける場合は終了時のHP・MP・FPを次のラウンドへ引き継ぎます。]
