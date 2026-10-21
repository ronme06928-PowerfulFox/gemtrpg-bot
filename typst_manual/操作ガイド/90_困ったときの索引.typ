#import "parts.typ": chapter, line-c

#let answer-page(target) = context link(target)[#counter(page).at(target).first()ページ]

#chapter[困ったときの索引] <help-index>

症状を探し、回答のあるページを開いてください。PDFではページ番号を押すと、その章の「困ったとき」へ移動します。

== 参加前の確認

#block(breakable: false)[
#table(
  columns: (73%, 27%), inset: (x: 6pt, y: 5pt), stroke: 0.6pt + line-c,
  table.header([*症状*], [*回答のあるページ*]),
  [ルーム一覧に参加したいルームがない], [#answer-page(<help-common>)],
  [参加コードが通らない], [#answer-page(<help-common>)],
  [間違えて「GM」を押した], [#answer-page(<help-common>)],
  [ログイン画面が表示される], [#answer-page(<help-common>)],
  [パスワードを忘れた], [#answer-page(<help-common>)],
)
]

== 作成と配置

#block(breakable: false)[
#table(
  columns: (73%, 27%), inset: (x: 6pt, y: 5pt), stroke: 0.6pt + line-c,
  table.header([*症状*], [*回答のあるページ*]),
  [持ちキャラが一覧に出ない], [#answer-page(<help-pl1>)],
  [追加したキャラクターが盤面にいない], [#answer-page(<help-pl1>)],
  [「このキャラクターを操作する権限がありません」と表示される], [#answer-page(<help-pl1>)],
)
]

== 画面と表示

#block(breakable: false)[
#table(
  columns: (73%, 27%), inset: (x: 6pt, y: 5pt), stroke: 0.6pt + line-c,
  table.header([*症状*], [*回答のあるページ*]),
  [キャラクター詳細が開かない], [#answer-page(<help-pl2>)],
  [駒が画面の外にある], [#answer-page(<help-pl2>)],
  [能力値が探索の技能に変わった], [#answer-page(<help-pl2>)],
  [効果の説明が見えない], [#answer-page(<help-pl2>)],
  [ログが見つからない], [#answer-page(<help-pl2>)],
  [表示が更新されない], [#answer-page(<help-pl2>)],
)
]

== 探索と戦闘の操作

#block(breakable: false)[
#table(
  columns: (73%, 27%), inset: (x: 6pt, y: 5pt), stroke: 0.6pt + line-c,
  table.header([*症状*], [*回答のあるページ*]),
  [スロットが表示されない], [#answer-page(<help-pl3>)],
  [宣言パネルが開かない], [#answer-page(<help-pl3>)],
  [スキルのカードが選べない], [#answer-page(<help-pl3>)],
  [宣言ボタンが押せない], [#answer-page(<help-pl3>)],
  [宣言を選び直した], [#answer-page(<help-pl3>)],
  [解決が進まない], [#answer-page(<help-pl3>)],
  [探索判定でキャラクターを選べない], [#answer-page(<help-pl3>)],
  [探索判定のダイス数が分からない], [#answer-page(<help-pl3>)],
  [探索判定に成否が出ない], [#answer-page(<help-pl3>)],
)
]

== 終了後の操作

#block(breakable: false)[
#table(
  columns: (73%, 27%), inset: (x: 6pt, y: 5pt), stroke: 0.6pt + line-c,
  table.header([*症状*], [*回答のあるページ*]),
  [「成果を反映」が見つからない], [#answer-page(<help-pl4>)],
  [成果反映で「この操作を行う権限がありません。」と表示される], [#answer-page(<help-pl4>)],
  [「反映済みです」と表示される], [#answer-page(<help-pl4>)],
  [成長を適用できない], [#answer-page(<help-pl4>)],
  [成長後もルーム内のスキルが変わらない], [#answer-page(<help-pl4>)],
  [「🏠」を押しても一覧に戻れない], [#answer-page(<help-pl4>)],
)
]

== 卓の準備

#block(breakable: false)[
#table(
  columns: (73%, 27%), inset: (x: 6pt, y: 5pt), stroke: 0.6pt + line-c,
  table.header([*症状*], [*回答のあるページ*]),
  [参加者からルームが見えない], [#answer-page(<help-gm1>)],
  [コードを失効したのに新規参加できる], [#answer-page(<help-gm1>)],
  [公開設定を変更できない], [#answer-page(<help-gm1>)],
  [GM専用画像が一覧にない], [#answer-page(<help-gm1>)],
)
]

== 当日の進行

#block(breakable: false)[
#table(
  columns: (73%, 27%), inset: (x: 6pt, y: 5pt), stroke: 0.6pt + line-c,
  table.header([*症状*], [*回答のあるページ*]),
  [R開始・R終了が表示されない], [#answer-page(<help-gm2>)],
  [⚔️の戦闘開始が押せない], [#answer-page(<help-gm2>)],
  [GMなのに次の表示へ進めない], [#answer-page(<help-gm2>)],
  [成果を代理反映したい], [#answer-page(<help-gm2>)],
)
]

== 介入と復旧

#block(breakable: false)[
#table(
  columns: (73%, 27%), inset: (x: 6pt, y: 5pt), stroke: 0.6pt + line-c,
  table.header([*症状*], [*回答のあるページ*]),
  [調整の送信後も値が変わらない], [#answer-page(<help-gm3>)],
  [アイテムを減らせない], [#answer-page(<help-gm3>)],
  [一部のキャラクターが回復しない], [#answer-page(<help-gm3>)],
  [再入室しても解決が進まない], [#answer-page(<help-gm3>)],
)
]

== 素材の制作

#block(breakable: false)[
#table(
  columns: (73%, 27%), inset: (x: 6pt, y: 5pt), stroke: 0.6pt + line-c,
  table.header([*症状*], [*回答のあるページ*]),
  [チャートの対象が選ばれない], [#answer-page(<help-gm4>)],
  [素材を配置できるが編集できない], [#answer-page(<help-gm4>)],
  [素材や編成を削除できない], [#answer-page(<help-gm4>)],
  [移送JSONを取り込めない], [#answer-page(<help-gm4>)],
)
]
