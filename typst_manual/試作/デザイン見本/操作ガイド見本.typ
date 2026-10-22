// Build: typst compile --root typst_manual typst_manual/試作/デザイン見本/操作ガイド見本.typ output/pdf/46_design_sample_guide.pdf
// 計画46・操作ガイドのデザイン見本。表紙とPL 3の抜粋で、基本ルールブックとの違いを確かめる。
#import "guide_theme.typ": *
#import "../../操作ガイド/parts.typ": at, screen, button, tag, piece, blue, red

#set document(title: "ジェムリアTRPG セッション操作ガイド・デザイン見本")
#show: guide-conf

// ── 表紙 ──
#let logo(y, width) = {
  let s = width / 867
  place(top + center, dy: y - 107 * s, dx: (640 - 631.5) * s, image("../../assets/gemuria_logo.png", width: 1280 * s))
}
#page(header: none, footer: none, background: none, margin: 0pt)[
  #place(bottom + left, rect(width: 100%, height: 95mm, fill: night))
  #place(bottom + left, rect(width: 100%, height: 95mm, fill: grid-pattern(rgb("1f86a0").transparentize(75%))))
  #place(bottom + left, dy: -95mm, rect(width: 100%, height: 1.2mm, fill: gradient.linear(rgb("1f86a0"), rgb("4b4fb0"), rgb("a8457f"))))
  #logo(40mm, 150mm)
  #place(top + center, dy: 132mm, box(width: 150mm, align(center, stack(spacing: 6mm,
    text(font: mono, size: 10pt, tracking: 0.3em, fill: muted)[TRPG \/\/ SESSION OPERATION GUIDE],
    text(size: 34pt, weight: "bold", fill: ink)[セッション操作ガイド],
    text(size: 12pt, fill: muted)[共通編・PL編・GM編],
  ))))
  #place(bottom + left, dx: 30mm, dy: -45mm, stack(spacing: 4mm,
    ..(("common", "共通　始める前に"), ("pl", "PL 1〜4　キャラクターと操作"), ("gm", "GM 1〜4　卓の準備と進行")).map(((k, t)) => {
      let g = parts.at(k)
      grid(columns: (8mm, auto), column-gutter: 3mm, align: horizon,
        gem-shape(g.shape, 7mm, g.main.lighten(30%), wire: true),
        text(fill: white, size: 11pt)[#text(font: mono, fill: g.main.lighten(40%))[#g.code]　#t])
    })))
  #place(bottom + right, dx: -20mm, dy: -12mm, text(font: mono, size: 7.5pt, fill: rgb("8d9aab"))[DESIGN SAMPLE])
]

// ── PL 3（抜粋） ──
#chapter("pl", "03", "探索と戦闘を操作する", [
  探索で判定を行う操作と、戦闘でスキルを宣言して結果を見るまでを説明します。ここでは、自分のキャラクターを盤面に置いたところから始めます。
])

== 1ラウンドの流れ

通常ルームでは、次の順に戦闘が進みます。

#guide-table((27%, 73%), ([場面], [プレイヤーがすること]),
  [戦闘の準備], [GMが戦闘に突入し、ラウンドを開始するのを待ちます。],
  [選択フェーズ], [自分のキャラクターのスロットごとに、スキルと対象を選んで宣言します。],
  [解決フェーズ], [GMが解決を始めます。表示される結果を見て待ちます。],
  [ラウンドの終わり], [終了時の効果とログを確認し、GMが次のラウンドを始めるのを待ちます。],
)

#callout("gm")[戦闘への突入とラウンドの開始はGMが行います。手順はGM 2で説明します。]

GMが戦闘に突入すると状態表示が「戦闘中」になり、ラウンドを始めると駒の上に数字の付いたスロットが現れます。

#fig([駒の上の数字がスロットです。今回は自分が6、敵が4で、1人1回ずつ行動します。], box(width: 100%, height: 50mm)[
  #at(3mm, 0mm, screen(150mm, 48mm, [戦闘中の盤面], [
    #at(27mm, 22mm, piece([ナギ], blue))
    #at(29.5mm, 11mm, circle(radius: 3.5mm, fill: blue, stroke: none, align(center + horizon, text(size: 9pt, weight: "bold", fill: white)[6])))
    #at(78mm, 22mm, piece([敵], red))
    #at(80.5mm, 11mm, circle(radius: 3.5mm, fill: red, stroke: none, align(center + horizon, text(size: 9pt, weight: "bold", fill: white)[4])))
    #at(108mm, 7mm, tag([戦闘中]))
    #at(108mm, 20mm, button([戦闘記録]))
  ]))
])

== 攻撃を宣言する

選択フェーズで、次の順に操作します。

+ *使用者を選ぶ*：自分のキャラクターのスロット（今回は「6」）をクリックします。
+ *スキルを選ぶ*：今回は「基本の一太刀」のカードを押します。
+ *対象を選ぶ*：敵のスロット（今回は「4」）をクリックします。
+ 使用者・スキル・対象を確かめて*「宣言」*を押します。

#callout("check")[宣言後も、解決が始まる前なら内容を変えられます。ボタンは「宣言」または「再宣言」と表示されます。]
