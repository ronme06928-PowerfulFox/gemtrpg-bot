// 計画46・R01。世界観の各文の出典とユーザー了承範囲は出典・不足台帳§19.29。
#import "../manual_theme.typ": *
#let chapter-header = publication-header.with("1")
#book-chapter("1", "1", [ジェムリアで遊ぶ], [
  正式名は*The Ray, from Perfect Gemstone*、略称は*ジェムリアTRPG*です。探索と戦闘を行き来しながら、キャラクターの選択と行動で物語を進めるテーブルトーク・ロールプレイングゲームです。
], target: <rules-introduction>)

== PLとGMの役割

#term[PL]は、物語の中で行動するキャラクターを作り、何をするかを宣言します。#term[GM]は、場所や出来事、相手の様子を示し、宣言された行動を裁定します。その結果を受けて、参加者は次の行動を考えます。

== セッションの流れ

#block(breakable: false)[
依頼や事件を知り、準備や情報収集をして、目的地へ向かいます。道中で出来事に対応し、ときには戦闘を行い、結末を迎えて報酬を確認します。*どの場面があり、何が起きるかはシナリオによって変わります。* 次の図は流れの一例です。

#book-fig([場面の進め方は#section-ref(<rules-exploration>, [第3章], prefix: "", named: false)、戦闘は#section-ref(<rules-battle-basics>, [第4章], prefix: "", named: false)、報酬は#section-ref(<rules-growth>, [第7章], prefix: "", named: false)で説明します。], [
  #let stages = (
    ([導入], [依頼や事件、置かれた状況を知る（#section-ref(<rules-exploration>, [第3章], prefix: "", named: false)）]),
    ([準備・情報収集], [必要な物や手掛かりをそろえる（#section-ref(<rules-exploration>, [第3章], prefix: "", named: false)）]),
    ([道中], [目的地へ向かい、出来事に対応する（#section-ref(<rules-exploration>, [第3章], prefix: "", named: false)）]),
    ([戦闘], [行動を宣言し、相手との戦いを解決する（#section-ref(<rules-battle-basics>, [第4章], prefix: "", named: false)）]),
    ([エンディングと報酬], [結末を確かめ、報酬と成長を確認する（#section-ref(<rules-growth>, [第7章], prefix: "", named: false)）]),
  )
  #stack(spacing: 1mm, ..stages.enumerate().map(((i, stage)) => {
    let (title, detail) = stage
    let row = rect(width: 100%, inset: (x: 3.5mm, y: 2mm), radius: 2mm,
      fill: white, stroke: 0.8pt + muted,
      grid(columns: (40mm, 1fr), column-gutter: 3mm, align: horizon,
        text(size: 11pt, weight: "bold", fill: muted, title), text(size: 10pt, detail)))
    if i < stages.len() - 1 { stack(spacing: 1mm, row, align(center)[↓]) } else { row }
  }))
])
]

== 基本用語

この本で使う基本用語を、次の表にまとめます。

#block(breakable: true)[#table(
  columns: (25%, 75%), stroke: 0.6pt + rgb("dce3e8"),
  chapter-header([*用語*], [*意味*]),
  [PL], [プレイヤー。自分のキャラクターの行動を考え、宣言する参加者です。],
  [GM], [ゲームマスター。状況を示し、進行と裁定を担当する参加者です。],
  [PC], [プレイヤーキャラクター。PLが操作する、物語の中の人物です。],
  [セッション], [導入から結末までを遊ぶ、一まとまりのプレイです。],
  [シナリオ], [セッションで扱う目的・事件・相手・舞台などをまとめたものです。],
)]

== 物語の舞台

ジェムリア大陸は、天災で一度滅びた世界に、新たな文明が築かれている舞台です。北部の寒冷な森林、東部の雨林や大河、西部の産業が発展した地域、南部の温暖で湿潤な土地など、地域ごとに異なる環境があります。

この大陸で暮らすキャラクターは、日常の小さなトラブルや、謎を秘めた事件、大きな冒険に関わっていきます。

人々は、生まれながらに一種の宝石の力を身に宿す「#term[宝石の加護]」を持ち、生活や戦闘でその力を使います。加護は、人が持つ個性の一つとして扱われています。

また、哺乳類に由来する身体的特徴や感覚・身体能力の傾向を持つ「#term[獣性]」があり、耳や尾などへの現れ方には個人差があります。人間の五感を備えたうえで、動物的な特徴や特技が加わります。

#term[シュラーカー]は、魔力濃度の高い場所で鉱石を核に発生する魔法生物の総称です。周囲の魔力を吸収して成長し、人間を含む生物にも襲いかかるため、人々の脅威となっています。

詳しい世界観は、今後の資料で扱います。この本では、キャラクターの行動と、その結果を決めるルールを説明します。

== 会話の例

#book-callout("example", body-size: 11pt, breakable: true)[
今回は、街の倉庫で荷物がなくなり、その調査を頼まれたものとします。行動を伝え、返ってきた状況に応じて動く、短い会話の例です。

#talk(
  "GM", [街で、倉庫の荷物を調べてほしいと頼まれました。],
  "PL", [ナギは、荷物が置かれていた棚を見に行きます。],
  "GM", [棚の奥から、何かを引きずる音がします。],
  "PL", [音がする方を確かめたいです。],
  "GM", [五感で判定してください。ダイスは2個、目標値は8です。],
  "PL", [判定値は9です。],
  "GM", [成功です。音は奥の扉の向こうからです。開けると、シュラーカーが荷物に噛みついています。],
  "PL", [剣を抜きます。みんなにも危険を知らせます。],
  "GM", [こちらに気づいて襲いかかってきます。戦闘に入ります。],
)
]

#related([判定の説明は#section-ref(<rules-exploration>, [第3章「探索と判定」], prefix: "第3章")、戦闘の進め方は#section-ref(<rules-battle-basics>, [第4章「戦闘の基本」], prefix: "第4章")で扱います。])
