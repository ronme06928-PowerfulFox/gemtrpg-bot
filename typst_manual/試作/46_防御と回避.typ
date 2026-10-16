#set page(paper: "a4", margin: (x: 18mm, y: 16mm), footer: context align(right, text(size: 8pt, fill: rgb("647080"))[ジェムリアTRPG / 防御・回避・試作　#counter(page).display()]))
#set text(font: "Noto Sans JP", size: 10.5pt, lang: "ja", fill: rgb("253345"))
#set par(leading: 0.65em, spacing: 1.4em)
#set heading(numbering: none)
#show heading.where(level: 1): set text(size: 23pt)
#show heading.where(level: 2): set text(size: 14pt, fill: rgb("246589"))
#let fig(n, caption, body) = block(breakable: false, above: 4mm, below: 4mm)[
  #rect(fill: rgb("f7f9fa"), stroke: 0.5pt + rgb("dce3e8"), radius: 4pt, inset: (x: 0pt, y: 4mm), body)
  #v(1mm)
  #text(size: 9pt, fill: rgb("647080"))[図#n　#caption]
]

#import "46_戦闘図解.typ": at, arrow, tag, blue, red
#let die(n, color) = box(stroke: 0.8pt + color, inset: 3pt, radius: 3pt, str(n))
#let duel(skill, formula, rolls, comparison, result) = box(width: 174mm, height: 37mm)[
  #at(3mm, 0mm, tag([ナギ / #skill]))
  #at(116mm, 0mm, tag([敵 / 基本の一太刀], color: red))
  #at(3mm, 8mm, text(size: 10pt, formula))
  #at(116mm, 8mm, text(size: 10pt)[4＋1d2＋1d6])
  #at(3mm, 16mm, text(size: 12pt, rolls))
  #at(116mm, 16mm, text(size: 12pt)[4＋#die(2, red)＋#die(6, red)])
  #at(70mm, 10mm, text(size: 21pt, weight: "bold", comparison))
  #at(3mm, 29mm, text(size: 9pt, result))
]
#let d1 = box(width: 174mm, height: 36mm)[
  #at(3mm, 2mm, tag([ナギのスロット]))
  #at(116mm, 2mm, tag([敵のスロット], color: red))
  #at(58mm, 5mm, arrow(w: 50mm))
  #at(58mm, 13mm, arrow(w: 50mm, color: red, reverse: true))
  #at(3mm, 23mm, text(size: 10pt)[鉄壁の防御 または 基本の回避])
  #at(116mm, 23mm, text(size: 10pt)[基本の一太刀])
]
#let d2 = duel([鉄壁の防御], [8＋1d4＋1d3], [8＋#die(3, blue)＋#die(2, blue)], [13 > 12], [ダメージ0 / HP 110 → 110 / FP 3 → 4（マッチ勝利で＋1）])
#let d3 = duel([鉄壁の防御], [8＋1d4＋1d3], [8＋#die(1, blue)＋#die(1, blue)], [10 < 12], [ダメージ12－10＝2 / HP 110 → 108 / FP 3 → 4（敗北時効果で＋1）])
#let d4 = duel([基本の回避], [4＋1d9], [4＋#die(9, blue)], [13 > 12], [ダメージ0 / HP 110 → 110 / FP 5 → 6（マッチ勝利で＋1）])
#let d5 = duel([基本の回避], [4＋1d9], [4＋#die(3, blue)], [7 < 12], [ダメージ12 / HP 110 → 98 / FP 5のまま])

= 防御・回避を使う場合

これまでは攻撃スキルを使ったマッチを見てきました。\
次は、守備スキルを使用した場合の戦闘の流れを学びましょう。

守備スキルには現在「防御スキル」と「回避スキル」の二種類があり、それぞれマッチにおける効果が異なります。

ナギが取得した「鉄壁の防御」と「基本の回避」を使う場合を例に、それぞれの効果を確かめてみましょう。

今回は敵の攻撃の威力が12になったものとして、防御と回避でそれぞれ勝った場合・負けた場合を比べます。

\
== 1. 敵の攻撃に防御・回避を合わせる

敵はナギのスロットを対象に「基本の一太刀」を使用します。\
ナギも敵のスロットを対象に、防御か回避のスキルを選びます。

#fig(1, [ナギと敵が互いのスロットを対象にしています。], d1)

防御・回避も、攻撃と同じようにスキルの威力を求めてマッチの勝敗を決めます。\
全員の宣言が確定したら、解決フェーズに移行します。

#pagebreak()

== 2. 「鉄壁の防御」で防ぐ

「鉄壁の防御」の使用コストはFP2です。ナギのFPは5から3になります。\
威力は8＋1d4＋1d〈物理補正〉です。ナギの物理補正は3なので、8＋1d4＋1d3で計算します。

=== 防御が勝った場合

#fig(2, [枠内の数字がダイスの出目です。], d2)

ナギの威力が敵より高いため、防御に成功し、ダメージを受けません。\
攻撃に対して防御でマッチに勝ったので、ナギはFPを1得ます。\
この例では、敵にダメージを与える効果はありません。

=== 防御が負けた場合

#fig(3, [防御で負けた場合は、敵の威力から防御の威力を引いてダメージを求めます。], d3)

敵の威力12に対してナギの威力は10なので、ナギは2ダメージを受けます。\
また、「鉄壁の防御」にはマッチ敗北時にFPを1得る効果があります。

#pagebreak()

== 3. 「基本の回避」で避ける

「基本の回避」には使用コストがありません。\
威力は4＋1d9で求めます。

=== 回避が勝った場合

#fig(4, [回避の威力が敵の攻撃を上回り、ナギはダメージを受けません。], d4)

攻撃に対して回避でマッチに勝ったので、ナギはFPを1得ます。\
この例では、敵にダメージを与える効果はありません。

回避に成功すると、条件を満たす後続の攻撃に対して「再回避」ができる状態にもなります。\
今回はこのマッチまでを扱い、再回避の条件と処理は別の例で説明します。

=== 回避が負けた場合

#fig(5, [回避で負けた場合は、敵の威力ぶんのダメージを受けます。], d5)

ナギは12ダメージを受けます。\
防御のように、敵の威力から自分の威力を引くことはできません。

== スキルの種類とマッチの勝敗

#table(columns: (40mm, 50mm, 1fr), inset: 5pt, stroke: 0.5pt + rgb("dce3e8"),
[使用スキル], [マッチの結果], [受けるダメージ],
[鉄壁の防御], [勝利（13対12）], [0],
[鉄壁の防御], [敗北（10対12）], [2],
[基本の回避], [勝利（13対12）], [0],
[基本の回避], [敗北（7対12）], [12])

防御は負けた場合も、防御の威力ぶんだけダメージを減らせます。\
回避は勝てばダメージを受けませんが、負けた場合は敵の威力ぶんのダメージを受けます。

防御・回避のスキルにも、スキルごとにさまざまな効果があります。\
使うときは、スキルの効果も確かめてみてください。\

