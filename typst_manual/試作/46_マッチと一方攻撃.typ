#set page(paper: "a4", margin: (x: 18mm, y: 16mm), footer: context align(right, text(size: 8pt, fill: rgb("647080"))[ジェムリアTRPG / マッチと一方攻撃・試作　#counter(page).display()]))
#set text(font: "Noto Sans JP", size: 11pt, lang: "ja", fill: rgb("253345"))
#set par(leading: 0.65em, spacing: 1.4em)
#set heading(numbering: none)
#show heading.where(level: 1): set text(size: 23pt)
#show heading.where(level: 2): set text(size: 14pt, fill: rgb("246589"))
#let fig(n, caption, body) = block(breakable: false, above: 4mm, below: 4mm)[
  #rect(fill: rgb("f7f9fa"), stroke: 0.5pt + rgb("dce3e8"), radius: 4pt, inset: (x: 0pt, y: 4mm), body)
  #v(1mm)
  #text(size: 9pt, fill: rgb("647080"))[図#n　#caption]
]

#import "46_戦闘図解.typ": at, slot, arrow, tag, blue, red
#let d1 = box(width: 174mm, height: 57mm)[
  #at(3mm, 1mm, slot("味方のスロット", "7", blue))
  #at(116mm, 1mm, slot("敵のスロット", "4", red))
  #at(62mm, 2mm, arrow(w: 48mm))
  #at(62mm, 9mm, arrow(w: 48mm, color: red, reverse: true))
  #at(71mm, 18mm, text(size: 9pt)[互いに対象指定])
  #at(3mm, 36mm, slot("ナギのスロット", "3", blue))
  #at(60mm, 39mm, line(start: (0mm, 0mm), end: (58mm, -23mm), stroke: 1.5pt + blue))
  #at(113.5mm, 15.6mm, polygon((4.5mm, 0.4mm), (1.5mm, 3.7mm), (0mm, 0mm), fill: blue, stroke: none))
  #at(78mm, 36mm, text(size: 9pt)[ナギも敵を指定])
  #at(3mm, 52mm, text(size: 8pt)[全員「基本の一太刀」を使用])
]
#let die(value, color) = box(stroke: 0.8pt + color, inset: 3pt, radius: 3pt, str(value))
#let d2 = box(width: 174mm, height: 43mm)[
  #at(4mm, 1mm, tag([味方 / 基本の一太刀]))
  #at(116mm, 1mm, tag([敵 / 基本の一太刀], color: red))
  #at(4mm, 10mm, text(size: 10pt)[4＋1d2＋1d3])
  #at(4mm, 19mm, text(size: 12pt)[4＋#die(1, blue)＋#die(3, blue)])
  #at(116mm, 10mm, text(size: 10pt)[4＋1d2＋1d2])
  #at(116mm, 19mm, text(size: 12pt)[4＋#die(1, red)＋#die(1, red)])
  #at(72mm, 8mm, text(size: 23pt, weight: "bold")[8 > 6])
  #at(69mm, 23mm, tag([味方の勝利]))
  #at(39mm, 34mm, text(size: 12pt)[敵に8ダメージ　HP 30 → 22])
]
#let d3 = box(width: 174mm, height: 37mm)[
  #at(4mm, 1mm, tag([ナギ / 基本の一太刀]))
  #at(118mm, 1mm, tag([敵 / 行動済み], color: red))
  #at(4mm, 10mm, text(size: 10pt)[4＋1d2＋1d3])
  #at(4mm, 21mm, text(size: 12pt)[4＋#die(2, blue)＋#die(3, blue)＝9])
  #at(64mm, 13mm, arrow(w: 45mm))
  #at(73mm, 5mm, text(size: 9pt)[一方攻撃])
  #at(119mm, 12mm, text(size: 12pt)[9ダメージ])
  #at(116mm, 24mm, text(size: 13pt, weight: "bold")[HP 22 → 13])
]

= マッチと一方攻撃

== 同じ敵を複数人で攻撃する場合

先ほどは、ナギと敵が互いのスロットを対象にスキルを使用し、マッチが発生する例を見ました。\
次は味方を1人加えて、同じ敵を2人で攻撃する場合を見ていきます。

今回は説明のために別の場面を用意します。全員が1つずつスロットを持ち、味方の行動速度は7、敵は4、ナギは3になったものとします。使用するスキルは、全員「基本の一太刀」です。状態異常や追加効果はありません。

== 1. それぞれのスロットの対象を確認する

味方と敵は互いのスロットを対象にしています。ナギも敵のスロットを対象にしますが、敵の対象は味方のスロットのままです。

#fig(1, [宣言が確定した時点の対象。矢印はスキルの対象を表しています。], d1)

この場合、味方と敵の間ではマッチが発生します。ナギに対しては敵からの指定がないため、ナギの攻撃は「一方攻撃」として処理します。今回はナギのほうが敵より遅いため、ナギの指定によって敵の対象が変わることはありません。

全員の宣言が確定したら、解決フェーズに移行します。

#pagebreak()

== 2. 味方と敵のマッチを処理する

最も速い味方のスロットから処理します。敵のスロットとマッチしているため、2人のスキルの威力を求めます。

#fig(2, [味方と敵のマッチ。この処理で、両者のスロットが処理済みになります。], d2)

今回は味方の威力が8、敵が6になったものとします。味方が勝ち、敵に8ダメージを与えます。\
また、攻撃同士のマッチに勝った味方はFPを1得ます。

敵のスロットもこのマッチで処理済みになるので、敵の速度4の順番で同じ攻撃を再び行うことはありません。

== 3. ナギの一方攻撃を処理する

続いてナギのスロットを処理します。対象にしていた敵はまだ盤面に残っているため、ナギはその敵に攻撃します。

#fig(3, [ナギの一方攻撃。敵のスキルとの威力比較は行いません。], d3)

ナギの威力は9になったものとします。\
今回は一方攻撃なので、その威力で敵に9ダメージを与えます。\
対象の敵スロットは行動済みなのでマッチは発生しません

一方攻撃にはマッチの勝敗がないため、ナギはマッチ勝利によるFPを得ません。\
ただし、「基本の一太刀」を使用しているので、ラウンド終了時にFPを2得る効果は発動します。

== この例での処理順

#table(columns: (12mm, 1fr, 27mm), inset: 6pt, stroke: 0.5pt + rgb("dce3e8"), [順番], [処理], [敵のHP], [1], [味方と敵のマッチ。味方が勝ち、8ダメージ], [30 → 22], [2], [ナギの一方攻撃。9ダメージ], [22 → 13])

敵のスロットに2人から攻撃が向いていても、両方とマッチするわけではありません。この例では、敵が対象にしている味方とマッチし、ナギの攻撃は一方攻撃になります。\

