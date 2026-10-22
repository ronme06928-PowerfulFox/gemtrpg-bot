// Build: typst compile --root typst_manual typst_manual/試作/デザイン見本/見本.typ output/pdf/46_design_sample.pdf
// 計画46・デザイン見本。表紙・目次・章扉と本文（第4章・第6章の抜粋）・巻末の表で、紙面の案を確かめる。
// 目次の節名は短くした見出しの案、ページ番号は統合版（59bc233）のもの。
#import "book_theme.typ": *

#set document(title: "ジェムリアTRPG 基本ルールブック・デザイン見本")
#show: book-conf

// ── 表紙 ──
// ジェムリアのロゴ（ジェムリアプロジェクトの素材）は手を加えずに置き、下にTRPGの標章を添える。
// 元画像は1280×720pxの白地で、絵柄は(198,107)〜(1065,587)。表紙も白地なので切り取らずに全体を置き、
// 絵柄の上端が y の位置に来るようにずらす。width は絵柄の幅。
#let logo(y, width) = {
  let s = width / 867
  place(top + center, dy: y - 107 * s, dx: (640 - 631.5) * s,
    image("../../assets/gemuria_logo.png", width: 1280 * s))
}
#let serif = ("Noto Serif JP",)
#let logo-blue = rgb("4a90d9")
#let trpg-mark = align(center, stack(spacing: 3mm,
  grid(columns: (1fr, auto, 1fr), column-gutter: 4mm, align: horizon,
    line(length: 100%, stroke: 0.8pt + ink),
    gem(9mm, logo-blue, outline: ink),
    line(length: 100%, stroke: 0.8pt + ink)),
  text(font: serif, size: 30pt, weight: "black", tracking: 0.35em, fill: ink)[TRPG],
  text(font: serif, size: 8pt, tracking: 0.3em, fill: muted)[TABLETOP ROLE-PLAYING GAME],
))

#page(header: none, footer: none, background: none, margin: 0pt)[
  #let keys = ("0", "1", "2", "3", "4", "5", "6", "7", "A")
  #place(top + left, rect(width: 100%, height: 5mm, fill: gradient.linear(..keys.map(k => gems.at(k).main))))
  #logo(40mm, 150mm)
  #place(top + center, dy: 137mm, box(width: 110mm, trpg-mark))
  #place(top + center, dy: 180mm, box(width: 150mm, align(center, stack(spacing: 7mm,
    text(font: serif, size: 14pt, style: "italic", fill: muted)[The Ray, from Perfect Gemstone],
    text(size: 34pt, weight: "bold", fill: ink)[基本ルールブック],
  ))))
  #place(bottom + center, dy: -22mm, box(width: 160mm, grid(columns: keys.len(), column-gutter: 4mm,
    ..keys.map(k => align(center + bottom, gem-shape(gems.at(k).shape, 13mm, gems.at(k).main))))))
  #place(bottom + left, rect(width: 100%, height: 5mm, fill: gradient.linear(..keys.map(k => gems.at(k).main))))
  #place(bottom + center, dy: -10mm,
    text(size: 8pt, fill: muted)[デザイン見本。本文は作業版から抜粋しています。])
]

// ── 目次 ──
#let toc = (
  ("0", "この本の使い方", 4, (("用意するもの", 4), ("2冊の役割", 4), ("読み始める場所", 4), ("章の選び方", 5))),
  ("1", "ジェムリアで遊ぶ", 6, (("PLとGMの役割", 6), ("セッションの流れ", 6), ("基本用語", 6), ("物語の舞台", 7), ("会話の例", 7))),
  ("2", "キャラクターを作る", 8, (("人物像と出身", 8), ("出身による補正", 8), ("能力値を決める", 9), ("探索技能", 9), ("戦闘スキル", 10), ("戦い方とスキル", 10), ("輝化スキルと所持品", 10), ("最大HP・MPと補正", 11), ("完成の確認", 11))),
  ("3", "探索と判定", 12, (("行動の宣言", 12), ("技能とダイスの個数", 12), ("判定値の求め方", 12), ("成功と失敗", 13), ("会話の例", 13), ("秘密判定", 13))),
  ("4", "戦闘の基本", 14, (("ラウンドの流れ", 14), ("戦闘開始時の状態", 14), ("速度値を決める", 15), ("スキルと対象の選択", 15), ("威力の比較", 15), ("ダメージとFP", 16), ("ラウンド終了時", 16), ("次のラウンドへ", 16))),
  ("5", "戦闘の裁定", 17, (("マッチの成立", 17), ("引き寄せと同速", 18), ("解決の順番", 18), ("マッチと一方攻撃", 19), ("防御", 21), ("回避", 22), ("再回避と強硬攻撃", 23), ("ダメージと勝利FPの表", 23), ("威力とダメージ", 23), ("不発と使用コスト", 24), ("広域-個別", 25), ("広域-合算", 26), ("コスト・効果・ダメージの順", 27), ("即時発動", 27), ("再使用", 28))),
  ("6", "状態異常と特殊効果", 29, (("数値と発動の時機", 29), ("効果ごとの条件", 29), ("出血", 30), ("出血氾濫", 31), ("破裂・破裂爆発", 31), ("亀裂", 32), ("亀裂崩壊", 33), ("戦慄", 33), ("戦慄殺到", 34), ("荊棘", 34), ("荊棘重絡", 35), ("震盪", 35), ("蓄力・凝魔", 36), ("加速・減速", 37), ("ダメージの増減", 37), ("封印", 37), ("召喚体", 38), ("付与スキル", 38), ("あがき", 39), ("再使用・再回避", 39), ("戦闘の区切りと解除", 40), ("効果の早見表", 41))),
  ("7", "セッションの終わりと成長", 45, (("報酬を受け取る", 45), ("取得コストの上限", 45), ("スキルの取得", 46), ("輝化スキルと通過点", 46), ("継続して遊ぶ", 47), ("HPが0になったとき", 47), ("ルールとアプリの記録", 48))),
  ("A", "巻末", 49, (("出身国ボーナスの表", 49), ("1ラウンドと判定の早見", 51), ("用語索引", 52))),
)

#page(header: none, background: none)[
  #text(size: 26pt, weight: "bold")[目次]
  #v(6mm)
  #for (key, title, page, sections) in toc {
    let g = gems.at(key)
    let label = if key == "A" { "巻" } else { key }
    block(breakable: false, below: 5mm, { set block(spacing: 2.2mm)
      grid(columns: (9mm, 1fr, auto), column-gutter: 3mm, align: horizon,
        box(width: 9mm, height: 9mm, fill: g.main, radius: 1.5mm,
          align(center + horizon, text(size: 12pt, weight: "bold", fill: white, label))),
        text(size: 13pt, weight: "bold", fill: g.main, title),
        text(size: 11pt, weight: "bold", fill: g.main, str(page)))
      let half = calc.ceil(sections.len() / 2)
      let row((name, p)) = box(width: 100%, inset: (y: 0.9mm),
        [#text(size: 9.5pt, name)#box(width: 1fr, inset: (x: 1.5mm), repeat(text(size: 7pt, fill: rgb("c3cbd3"))[・]))#text(size: 9pt, fill: muted, str(p))])
      pad(left: 12mm, grid(columns: (1fr, 1fr), column-gutter: 9mm,
        stack(..sections.slice(0, half).map(row)),
        stack(..sections.slice(half).map(row))))
    })
  }
]

// ── 第4章（抜粋） ──
#chapter("4", "4", "戦闘の基本", [
  戦闘は、ラウンドごとに行動を決めて解決します。この章では、第2章で作成したナギと敵1人が戦う例を使い、1ラウンドの開始から終了までを見ていきます。
])

#[
== ラウンドの流れ

戦闘は、次の4つの段階をくり返して進みます。

#book-table((27%, 73%), ([段階], [行うこと]),
  [ラウンド開始], [行動回数からスロットを作り、それぞれの速度値を決めます。],
  [選択フェーズ], [行動できるスロットごとに、使うスキルと対象を選んで確定します。],
  [解決フェーズ], [必要な宣言がそろったら、確定したスキルを処理します。],
  [ラウンド終了], [終了時の効果を処理し、戦闘を続ける場合は次のラウンドへ進みます。],
)

#callout("point")[*スロットは1回分の行動枠*です。行動回数が複数なら、その数だけスロットを使います。]

== 戦闘開始時の状態

戦闘に入る前に、現在のHP・MP・FPを確認します。作成したキャラクターの最大HPは129、最大MPは12ですが、前の場面で消費しており、今回は*HP110・MP9・FP1*で始めるものとします。

#fig([HP・MPは「現在値／最大値」で示します。], pair(
  card([ナギ], ally, [#hp[110／129] #mp[9／12] #fp[1] \ 速度補正2　物理補正3]),
  card([敵], enemy, [#hp[30／30] #mp[6／6] #fp[0] \ 速度補正1　物理補正2]),
))

#callout("gm")[HP・MP・FPは前の場面から引き継ぎます。シナリオに指定があれば、回復などを行います。]

== 速度値を決める

各スロットで6面ダイスを1個振り、速度補正を加えます。加速・減速などの効果がある場合は、その補正も適用します。

#fig([各スロットの速度値を求めます。], pair(
  card([ナギのスロット], ally, [#die(4) ＋ 速度補正2 ＝ *速度値6* \ ラティウムの恩恵で、今回は#fp[1] → #fp[2]]),
  card([敵のスロット], enemy, [#die(3) ＋ 速度補正1 ＝ *速度値4* \ 出身の恩恵なし、#fp[0]のまま]),
))

ラティウムの恩恵は、ラウンド開始時に50%の確率でFPを1得るものです。今回はFPを得たものとし、自分のキャラクターのFPは1から2になります。
]

// ── 第6章（抜粋） ──
#chapter("6", "6", "状態異常と特殊効果", [
  状態異常と特殊効果が何を変え、いつ働き、どのように減ったり解除されたりするかを説明します。
])

#[
== 出血

出血は、ラウンド終了時に現在の出血値に等しいHPダメージを与えます。その後、出血値を半分にし、端数を切り捨てます。

#fig([ダメージを受けてから、出血値を半分にします。], pair(
  card([処理の前], ally, [#hp[40] ／ 出血5]),
  card([処理の後], enemy, [#hp[40－5＝35] \ 出血5 → 2]),
))

#callout("example")[出血1は、次の処理で1ダメージを与えてから0になります。出血0では出血によるダメージは発生しません。]

== 出血氾濫

出血氾濫は、その場で出血のダメージ処理を行います。（見本のため本文は省略）
]

// ── 巻末（抜粋） ──
#chapter("A", "巻末", "巻末", [
  出身国ボーナスの表、1ラウンドと判定の早見、用語索引を収録します。
])

#[
== 出身国ボーナスの表

#book-table((24%, 26%, 50%), ([出身], [恩恵の名前], [効果]),
  [ラティウム], [小麦色の風], [ラウンド開始時、50%の確率でFPを1得ます。],
  [アヌッサ・ホロウ], [大魔女の末裔], [最大MPに+1します。],
  [マホロバ], [神樹の恩寵], [ラウンド終了時、HPを3回復します。],
  [ワダツミ], [誉れ高き刃], [斬撃スキルの基礎威力に+1します。],
  [シンシア], [爆縮], [攻撃時、追加で5のダメージを与えます。1回の戦闘で8回までです。],
  [アルトマギア], [狭霧に息づく神秘], [ラウンド終了時、自分のMPを1回復します。],
)
]
