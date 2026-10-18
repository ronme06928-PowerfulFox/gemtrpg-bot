// Build: typst compile typst_manual/試作/46_操作ガイド_最初のラウンド.typ output/pdf/46_operation_first_round.pdf
#set page(paper: "a4", margin: (x: 18mm, y: 16mm), footer: context align(right, text(size: 8pt, fill: rgb("647080"))[ジェムリアTRPG / セッション操作ガイド・試作　#counter(page).display()]))
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
#let muted = rgb("647080")
#let line-c = rgb("c9d2d9")

// 画面部品
#let button(body, active: false, color: blue) = box(
  fill: if active { color } else { white },
  stroke: 0.8pt + color, radius: 3pt, inset: (x: 5pt, y: 3pt),
  text(size: 9pt, weight: "bold", fill: if active { white } else { color }, body),
)
#let screen(w, h, title, body) = box(width: w, height: h, fill: white, stroke: 0.8pt + line-c, radius: 3pt)[
  #at(3mm, 2mm, text(size: 8.5pt, weight: "bold", fill: muted, title))
  #body
]
#let slot-badge(n, color) = box(width: 7mm, height: 7mm)[
  #circle(radius: 3.5mm, inset: 0pt, fill: color, stroke: none)[#align(center + horizon, text(size: 9pt, weight: "bold", fill: white, n))]
]
#let piece(name, color) = circle(radius: 6mm, inset: 0pt, fill: color.lighten(90%), stroke: 1.2pt + color)[#align(center + horizon, text(size: 10pt, weight: "bold", fill: color, name))]
#let card(id, name, cost, selected: false, disabled: false) = box(
  width: 34mm, height: 15mm, radius: 3pt, inset: 2mm,
  fill: if selected { blue } else { rgb("f6efe2") },
  stroke: 0.6pt + if selected { blue } else { rgb("d9c9a8") },
)[
  #set par(spacing: 0pt)
  #text(size: 7pt, fill: if selected { white } else { muted }, id)#h(1fr)#text(size: 7.5pt, fill: if selected { white } else { muted }, cost)\
  #v(1.5mm)
  #text(size: 9pt, weight: "bold", fill: if selected { white } else if disabled { muted } else { rgb("253345") }, name)
]
#let step(n, label, state) = box(
  fill: if state == "done" { blue.lighten(85%) } else if state == "active" { blue } else { rgb("eef1f3") },
  radius: 3pt, inset: (x: 5pt, y: 3pt),
  text(size: 8.5pt, weight: "bold", fill: if state == "active" { white } else if state == "done" { blue } else { muted })[#n #label#if state == "done" [ ✓]],
)

// 図1：キャラクターの追加
#let d1 = box(width: 174mm, height: 34mm)[
  #at(4mm, 3mm, screen(42mm, 28mm, [アクションドック], [
    #at(4mm, 9mm, button([＋], active: true))
    #at(14mm, 10mm, text(size: 8.5pt)[キャラクターを追加])
  ]))
  #at(48mm, 13mm, arrow(w: 10mm))
  #at(60mm, 3mm, screen(46mm, 28mm, [キャラクターを追加], [
    #at(4mm, 9mm, button([味方を追加], active: true))
    #at(4mm, 18mm, button([敵を追加]))
  ]))
  #at(108mm, 13mm, arrow(w: 10mm))
  #at(120mm, 3mm, screen(52mm, 28mm, [保存済みの持ちキャラから選ぶ], [
    #at(4mm, 10mm, box(width: 30mm, stroke: 0.6pt + line-c, radius: 2pt, inset: 3pt, text(size: 9pt)[ナギ　▼]))
    #at(37mm, 10mm, button([追加], active: true))
  ]))
]

// 図2：戦闘中の画面とスロット
#let d2 = box(width: 174mm, height: 66mm)[
  #at(4mm, 2mm, box(width: 166mm, height: 62mm, stroke: 0.8pt + line-c, radius: 3pt)[
    // アクションドック
    #at(0mm, 0mm, box(width: 12mm, height: 62mm, fill: rgb("eef1f3"))[
      #at(3mm, 4mm, text(size: 8pt, fill: muted)[ドック])
      #at(3.5mm, 12mm, button([＋]))
    ])
    // 盤面
    #at(16mm, 4mm, text(size: 8.5pt, weight: "bold", fill: muted)[盤面])
    #at(30mm, 26mm, piece("ナギ", blue))
    #at(32.5mm, 17mm, slot-badge("6", blue))
    #at(80mm, 26mm, piece("敵", red))
    #at(82.5mm, 17mm, slot-badge("4", red))
    #at(26mm, 44mm, text(size: 8pt)[駒の上の数字がスロット（速度値）])
    // 右列
    #at(112mm, 0mm, box(width: 54mm, height: 62mm, fill: rgb("f8f9fa"))[
      #at(3mm, 4mm, tag([戦闘中]))
      #at(3mm, 11mm, text(size: 7.5pt, fill: muted)[戦闘進行操作を利用できます。])
      #at(3mm, 17mm, button([戦闘記録]))
      #at(3mm, 27mm, box(width: 48mm, height: 32mm, fill: white, stroke: 0.6pt + line-c, radius: 2pt, inset: 3pt, text(size: 8pt, fill: muted)[チャット・ログ]))
    ])
  ])
]

// 図3：宣言パネル（スキル選択後は、カードの一覧がスキルの詳細に切り替わる）
#let d3 = box(width: 174mm, height: 62mm)[
  #at(4mm, 4mm, box(width: 62mm, height: 54mm, fill: white, stroke: 0.8pt + line-c, radius: 3pt)[
    #at(3mm, 3mm, text(size: 8.5pt, weight: "bold")[スキルを選ぶ前])
    #at(3mm, 10mm, step("1", "使用者", "done"))
    #at(27mm, 10mm, step("2", "スキル", "active"))
    #at(3mm, 18mm, card("Ps-00", "基本の一太刀", "コストなし"))
    #at(3mm, 35mm, card("D-02", "鉄壁の防御", "FP:2"))
    #at(39mm, 18mm, box(width: 20mm, text(size: 7.5pt, fill: muted)[スキルが\ カードで\ 並ぶ]))
  ])
  #at(70mm, 26mm, arrow(w: 10mm))
  #at(82mm, 4mm, box(width: 88mm, height: 54mm, fill: white, stroke: 0.8pt + line-c, radius: 3pt)[
    #at(3mm, 3mm, text(size: 8.5pt, weight: "bold")[スキルと対象を選んだ後])
    #at(3mm, 10mm, step("1", "使用者", "done"))
    #at(27mm, 10mm, step("2", "スキル", "done"))
    #at(51mm, 10mm, step("3", "対象", "done"))
    #at(3mm, 18mm, text(size: 8.5pt)[内容を確認して「宣言」を押してください。])
    #at(3mm, 25mm, text(size: 9pt, weight: "bold")[基本の一太刀　#button([↩])])
    #at(3mm, 33mm, text(size: 8.5pt)[威力レンジ: 6 \~ 9])
    #at(3mm, 39mm, text(size: 8.5pt)[コマンド: 4+1d2+1d3])
    #at(66mm, 44mm, button([宣言], active: true))
  ])
]

// 図4：解決パネル
#let d4 = box(width: 174mm, height: 44mm)[
  #at(30mm, 2mm, box(width: 114mm, height: 40mm, fill: white, stroke: 0.8pt + line-c, radius: 3pt)[
    #at(4mm, 3mm, tag([マッチ]))
    #at(8mm, 13mm, text(size: 10pt, weight: "bold", fill: blue)[ナギ / 基本の一太刀])
    #at(70mm, 13mm, text(size: 10pt, weight: "bold", fill: red)[敵 / 基本の一太刀])
    #at(16mm, 21mm, text(size: 18pt, weight: "bold", fill: blue)[9])
    #at(52mm, 21mm, text(size: 18pt, weight: "bold")[＞])
    #at(80mm, 21mm, text(size: 18pt, weight: "bold", fill: red)[6])
    #at(4mm, 33mm, text(size: 8.5pt)[ナギの勝利])
    #at(78mm, 31mm, button([次のマッチへ]))
    #at(78mm, 37.5mm, text(size: 7pt, fill: muted)[GMが操作します])
  ])
]

= 1ラウンドを操作する流れ

この章では、作成したキャラクターをルームに追加し、最初のラウンドで攻撃を宣言して、結果を確かめるまでの操作を説明します。例として、基本ルールブックで作成したナギを使います。

ルールの意味（速度値、マッチ、ダメージ、FP）は、基本ルールブックの「ナギの最初の1ラウンドを追ってみよう」で説明しています。\
この章では実際の操作手順を確かめていきましょう。

== 1. キャラクターをルームに追加する

ロビーでGMが用意したルームを選び、「入室」を押します。

入室したら、画面左端のアイコン列（アクションドック）にある「＋」（キャラクターを追加）を押し、「味方を追加」を選びます。\
次の画面の「保存済みの持ちキャラから選ぶ」で作成したキャラクターを選び、「追加」を押します。

#fig(1, [キャラクターの追加は「＋」→「味方を追加」→持ちキャラを選んで「追加」の順です。], d1)

ルームに追加したキャラクターは、アカウントに保存したキャラクターのコピーです。\
ルームの中でHPが減っても、保存したキャラクターは変わりません。セッションで得た経験値は、セッションの終わりに「成果を反映」で書き戻します。

追加した直後のキャラクターは、まだ盤面に置かれていません。ドックの「📦」（未配置キャラクター）を開き、自分のキャラクターの「配置」を押すと盤面に置けます。

#pagebreak()

== 2. 戦闘が始まるのを待つ

画面右側の列の一番上にある状態表示が「戦闘準備中」のあいだは、ラウンドは始まりません。

GMが「戦闘突入」を行い、続けてラウンドを開始すると、状態表示が「戦闘中」になります。\
盤面の駒の上には、丸い数字のバッジが付きます。これが「スロット（行動枠）」で、数字はこのラウンドの速度値です。

今回の例では、自分のキャラクターの駒に「6」、敵の駒に「4」のスロットが付いています。宣言は、このスロットから行います。

#fig(2, [駒の上の数字がスロットです。今回は1人1回ずつ行動します。], d2)

#pagebreak()

== 3. 攻撃を宣言する

宣言は、次の3つの手順で行います。開いた宣言パネルの上部に、今どの手順かが表示されます。

+ *使用者を選ぶ*：自分のキャラクターの駒のスロット（今回は「6」）をクリックします。宣言パネルが開き、そのキャラクターのスキルがカードで並びます。
+ *スキルを選ぶ*：使用するスキルのカードをクリックします。今回は「基本の一太刀」を選びます。
+ *対象を選ぶ*：対象にする敵の駒のスロット（今回は「4」）をクリックします。

スキルを選ぶと、カードの一覧がそのスキルの詳細に切り替わります。対象まで選ぶと、パネルに「内容を確認して『宣言』を押してください。」と表示され、「威力レンジ」に威力の幅が出ます。\
威力レンジは、まだダイスを振った結果ではありません。

内容を確認したら「宣言」を押します。これで自分のキャラクターの行動が決まりました。

#fig(3, [宣言パネルの上部に、使用者・スキル・対象の手順が表示されます。スキルを選ぶと、カードの一覧が詳細に切り替わります。], d3)

使用コストが足りないスキルのカードは薄く表示され、選べません。\
選んだスキルを変えたいときは、スキル名の横の「↩」を押すとカードの一覧に戻ります。\
宣言した後でも、解決が始まる前なら、もう一度スロットを選んで内容を変え、「再宣言」で確定し直せます。

#pagebreak()

== 4. 解決を見る

全員の宣言がそろうと、GMが解決を始めます。\
画面に解決パネルが開き、マッチの結果が順に表示されます。今回は自分のキャラクターと敵が互いのスロットを対象にしているので、マッチになります。

#fig(4, [解決パネルには、マッチの組み合わせと威力の比較が表示されます。], d4)

今回の結果は9対6で、自分のキャラクターの勝利です。敵へのダメージやFPの増減は、チャット欄のログにも残ります。\
解決パネルを次へ進めるのはGMです。プレイヤーは表示を見て待ちます。

== 5. ラウンドが終わったら

すべての行動が解決すると、ラウンドの終了処理が自動で行われます。\
今回の「基本の一太刀」のように、ラウンド終了時に効果のあるスキルは、ここで処理されます。

次のラウンドはGMが開始します。新しいスロットが付いたら、もう一度「3. 攻撃を宣言する」と同じ手順で宣言します。

GMが戦闘を終えるときは「戦闘終結」を行い、画面に「VICTORY」などの結果が表示されます。\
画面右側の列の一番上にある「戦闘記録」を開くと、その戦闘で与えたダメージと受けたダメージをキャラクターごとに確かめられます。

== 困ったとき

#table(columns: (58mm, 1fr), inset: 5pt, stroke: 0.5pt + rgb("dce3e8"),
[症状], [確かめること],
[スロットが表示されない], [状態表示が「戦闘中」で、ラウンドが始まっているか。キャラクターが盤面に置かれているか],
[スロットを押しても宣言パネルが開かない], [自分のキャラクターのスロットか。解決が始まった後ではないか],
[スキルのカードが選べない], [使用コストが足りているか（足りないカードは薄く表示されます）],
[宣言ボタンが押せない], [対象のスロットを選んだか。対象が要らないスキルでは不要です])
