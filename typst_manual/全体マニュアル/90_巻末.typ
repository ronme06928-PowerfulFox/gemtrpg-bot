// 計画46・R09。照合・保留事項は出典・不足台帳§19.31。
#import "../manual_theme.typ": *
#let chapter-header = publication-header.with("A")
// 単独レビューでは文字だけを出し、参照先を収録した本では自動的にリンクにする。
// 索引の右の列（節の名前）にはルビを振らない。ルビは左の列（用語）だけに振る。
#let index-destination(target, body) = with-ruby-mode("off", context {
  section-ref(label(target), body, prefix: "第" + target.slice(2, 3) + "章")
})
#let appendix-table(..cells) = table(columns: (24%, 26%, 50%), stroke: 0.6pt + rgb("dce3e8"), ..cells.pos())

#book-chapter("A", "巻末", [巻末], [
  作成時の補正と戦闘中の恩恵を、出身ごとに確認します。作成時の計算は#section-ref(<r02-origin-adjustments>, [第2章「出身による補正」], prefix: "第2章")、成長の予算は#section-ref(<r07-budget>, [第7章「取得コストの上限」], prefix: "第7章")を参照してください。
], target: <rules-appendix>)

== 出身国ボーナスの表 <r09-origin>


他国の恩恵を選べる出身では、選んだ恩恵に従って計算します。

#appendix-table(
  chapter-header([*出身*], [*恩恵の名前*], [*効果*]),
  [ヨキューク・ツォー], [色とりどりの輝石], [他国の出身の恩恵を一つ選び、その恩恵に従って計算します。],
  [アーク・ジェムリア], [空を巡る叡智], [他国の出身の恩恵を一つ選び、その恩恵に従って計算します。],
  [ラティウム], [小麦色の風], [ラウンド開始時、50%の確率でFPを1得ます。],
  [アヌッサ・ホロウ], [大魔女の末裔], [最大MPに+1します。],
  [マホロバ], [神樹の恩寵], [ラウンド終了時、HPを3回復します。],
  [ラグラゼシス（都市部）], [厄災を探究せし理性], [魔法スキルの取得コスト合計のうち1点を追加で賄えます。情報収集技能4種（対話・尋問・諜報・窃取）の技能レベルに+1します。],
  [ラグラゼシス（非都市部）], [厄災と共に生きる知恵], [取得コスト上限が1点上がります。情報収集技能4種の技能レベルに−1します。],
  [ギァン・バルフ], [反撃の石], [防御スキルでマッチに勝つと、自分の威力が相手の威力を上回った分の反撃ダメージを与えます。],
  [ワダツミ], [誉れ高き刃], [斬撃スキルの基礎威力に+1します。],
  [シンシア], [爆縮], [攻撃時、追加で5のダメージを与えます。1回の戦闘で8回までです。],
  [オーセクト], [世界を見下ろす黒鳥], [他国の出身の恩恵を一つ選び、その恩恵に従って計算します。],
  [ヴァルヴァイレ], [畏怖の衣], [マッチの相手、または自分に一方攻撃をするキャラクターのスキルの最終威力に−1します（1未満にはなりません）。],
  [フローディアス], [活力の行き重なる落合], [対話・鑑定の技能レベルに+2、戦闘中の回避スキルのダイス威力に+1します。相手陣営に、盤面に配置されたヴァルヴァイレ出身のキャラクターがいるとき、回避のダイス威力にさらに+1します。対話・鑑定の技能レベルには追加しません。],
  [アルトマギア], [狭霧に息づく神秘], [ラウンド終了時、自分のMPを1回復します。],
  [グラン・リテラール・ブラン], [いずれ彩られる純白], [攻撃スキル的中時、対象に2ラウンド続く「色彩」を付与します。色彩は、付与した側と同陣営のキャラクターが、その相手陣営の対象へ攻撃スキルを使うとき、最終威力に+1する目印です。],
  [エムリダ], [盛夏と共鳴る高揚], [五感・本能・運動・回避の技能レベルに+1します。戦闘中、盤面に配置された、自分と同じ速度値の別のキャラクターがいれば、自分のスキルの基礎威力に+1します。],
  [アル・カルメイル], [砂海を流離う行人], [最大HPに+20、本能・隠密の技能レベルに+2します。],
)

#block(breakable: false)[
== 1ラウンドと判定の早見 <r09-quick>

以下は本文の要約です。詳しい条件は、各項目に示した章と節を確認してください。

#table(columns: (19%, 81%), stroke: 0.6pt + rgb("dce3e8"),
  chapter-header([*項目*], [*確認すること／詳しい章・節*]),
  [探索判定], [#formula[判定値＝GM指定の個数の6面ダイスの合計＋探索技能のレベル]。 \ #section-ref(<r03-dice>, [第3章「技能とダイスの個数」], prefix: "第3章")#section-ref(<r03-formula>, [「判定値の求め方」], prefix: "")],
  [成功], [判定値が目標値以上なら成功。 \ #section-ref(<r03-success>, [第3章「成功と失敗」], prefix: "第3章")],
  [1ラウンド], [開始（速度値）→選択→解決→終了。 \ #section-ref(<r04-round>, [第4章「ラウンドの流れ」], prefix: "第4章")],
  [速度値], [各スロットで#formula[6面ダイス1個＋速度補正]。加速・減速も適用。 \ #section-ref(<r04-speed>, [第4章「速度値を決める」], prefix: "第4章")],
  [解決順], [広域が先、次に単体を速度値の高い順で処理。 \ #section-ref(<r05-sequence>, [第5章「解決の順番」], prefix: "第5章")],
  [コスト・効果], [使用コスト→効果→ダメージ。指定の時機に従います。 \ #section-ref(<r05-timing>, [第5章「コスト・効果・ダメージの順」], prefix: "第5章")],
  [マッチ], [通常単体は相互指定で#term(target: <r05-match>)[マッチ]、一方向の指定で#term(target: <r05-one-sided>)[一方攻撃]。同陣営はマッチにしません。 \ #section-ref(<r05-match>, [第5章「マッチの成立」], prefix: "第5章")],
  [不発・コスト], [通常単体の実行前不発は未払いコストなし。広域は開始時先払い。*先払い後に不発でも返しません。* \ #section-ref(<r05-cost>, [第5章「不発と使用コスト」], prefix: "第5章")],
  [即時発動], [1キャラクターにつき1ラウンド1回。確定時に処理。 \ #section-ref(<r05-instant>, [第5章「即時発動」], prefix: "第5章")],
  [宝石の加護], [宝石の加護スキルは1回の戦闘で1回まで。 \ #section-ref(<r05-gem>, [第5章「宝石の加護スキル」], prefix: "第5章")],
)

組合せごとのダメージと勝利FPは、#section-ref(<r05-fp>, [第5章「ダメージと勝利FPの表」], prefix: "第5章")を参照してください。

効果の早見表は、#section-ref(<r06-quick>, [第6章「効果の早見表」], prefix: "第6章")を参照してください。

]

== 用語索引 <r09-index>

// 索引は調べるときに引く場所なので、ルビを毎回振る（計画51）。
#ruby-push("always")

用語を五十音順で並べ、本文で扱う章と節を示します。

#table(columns: (26%, 74%), stroke: 0.6pt + rgb("dce3e8"),
  chapter-header([*用語*], [*章番号・節の名前*]),
  [あがき], index-destination("r06-struggle", [第6章「あがき」]),
  [一方攻撃], index-destination("r05-one-sided", [第5章「マッチと一方攻撃」]),
  [HP], index-destination("r04-resources", [第4章「戦闘開始時の状態」]),
  [FP], index-destination("r04-damage-fp", [第4章「ダメージとFP」]),
  [MP], index-destination("r04-resources", [第4章「戦闘開始時の状態」]),
  [解決フェーズ], index-destination("r05-sequence", [第5章「解決の順番」]),
  [回避], index-destination("r05-evade", [第5章「回避」]),
  [加速], index-destination("r06-speed", [第6章「加速・減速」]),
  [輝化スキル], index-destination("r07-radiance", [第7章「輝化スキルと通過点」]),
  [技能レベル], index-destination("r02-exploration-skills", [第2章「探索技能」]),
  [強硬攻撃], index-destination("r05-hard", [第5章「強硬攻撃」]),
  [凝魔], index-destination("r06-stacks", [第6章「蓄力・凝魔」]),
  [亀裂], index-destination("r06-fissure", [第6章「亀裂」]),
  [亀裂崩壊], index-destination("r06-fissure-collapse", [第6章「亀裂崩壊」]),
  [荊棘], index-destination("r06-thorns", [第6章「荊棘」]),
  [荊棘重絡], index-destination("r06-entangle", [第6章「荊棘重絡」]),
  [経験], index-destination("r07-budget", [第7章「取得コストの上限」]),
  [減速], index-destination("r06-speed", [第6章「加速・減速」]),
  [広域-合算], index-destination("r05-mass-summation", [第5章「広域-合算」]),
  [広域-個別], index-destination("r05-mass-individual", [第5章「広域-個別」]),
  [再回避], index-destination("r05-followup", [第5章「再回避」]),
  [再使用], index-destination("r05-reuse", [第5章「再使用」]),
  [シナリオ経験], index-destination("r07-rewards", [第7章「報酬を受け取る」]),
  [出血], index-destination("r06-bleed", [第6章「出血」]),
  [出血遷延], index-destination("r06-bleed-maintenance", [第6章「出血遷延がある場合」]),
  [出血氾濫], index-destination("r06-bleed-overflow", [第6章「出血氾濫」]),
  [出身], index-destination("r02-origin", [第2章「人物像と出身」]),
  [取得コスト], index-destination("r02-combat-skills", [第2章「戦闘スキル」]),
  [召喚体], index-destination("r06-summon", [第6章「召喚体」]),
  [使用コスト], index-destination("r05-cost", [第5章「不発と使用コスト」]),
  [震盪], index-destination("r06-concussion", [第6章「震盪」]),
  [スロット], index-destination("r04-round", [第4章「ラウンドの流れ」]),
  [選択フェーズ], index-destination("r04-selection", [第4章「スキルと対象の選択」]),
  [戦闘終結], index-destination("r06-clear", [第6章「戦闘の区切りと解除」]),
  [戦闘突入], index-destination("r06-clear", [第6章「戦闘の区切りと解除」]),
  [戦闘不能], index-destination("r07-hp-zero", [第7章「HPが0になったとき」]),
  [戦慄], index-destination("r06-fear", [第6章「戦慄」]),
  [戦慄殺到], index-destination("r06-fear-surge", [第6章「戦慄殺到」]),
  [即時発動], index-destination("r05-instant", [第5章「即時発動」]),
  [速度値], index-destination("r04-speed", [第4章「速度値を決める」]),
  [速度補正], index-destination("r02-derived-stats", [第2章「最大HP・MPと補正」]),
  [探索判定], index-destination("r03-formula", [第3章#section-ref(<r03-formula>, [「判定値の求め方」], prefix: "")]),
  [蓄力], index-destination("r06-stacks", [第6章「蓄力・凝魔」]),
  [通過点], index-destination("r07-radiance", [第7章「輝化スキルと通過点」]),
  [同速], index-destination("r05-redirect", [第5章「引き寄せと同速」]),
  [破裂], index-destination("r06-rupture", [第6章「破裂・破裂爆発」]),
  [引き寄せ], index-destination("r05-redirect", [第5章「引き寄せと同速」]),
  [秘密判定], index-destination("r03-secret", [第3章「秘密判定」]),
  [封印], index-destination("r06-seal", [第6章「封印」]),
  [不発], index-destination("r05-cost", [第5章「不発と使用コスト」]),
  [付与スキル], index-destination("r06-granted", [第6章「付与スキル」]),
  [防御], index-destination("r05-defense", [第5章「防御」]),
  [宝石の加護スキル], index-destination("r05-gem", [第5章「宝石の加護スキル」]),
  [マッチ], index-destination("r05-match", [第5章「マッチの成立」]),
  [目標値], index-destination("r03-success", [第3章「成功と失敗」]),
  [ラウンド], index-destination("r04-round", [第4章「ラウンドの流れ」]),
)

#ruby-pop()
