---
name: m-effect-frame
series: gemuria-video
summary: タイミングを赤枠で囲み、効果全体へ広げる。
steps: 2
props: []
---

# 効果文の枠

子に `[data-effect-text]`、その中の `[data-effect-timing]` と `[data-effect-frame]`。段階1の3.5秒から0.6秒でタイミング枠を出し、段階2の0〜0.7秒で全文へ広げる。r3-v2と同じく文字の実幅を測り、上下左右8pxの余白を取る。

使い方の断片は [demo.html](demo.html)。CSS・必要素材・確認デッキの組立は [共通README](../../README.md) を参照。部品はデッキの components/effect-frame/index.js へコピーする。すべての表示を(k,t)から復元し、t=Infinityは段階の最終状態。独自タイマー・乱数・CSSアニメーションは使わない。

## 注意

図の文字は24px以上、本文27px。部品の配置先を含む図領域に .plot を付ける。数値JSONは呼出側で検算し、本文のルールを参照する。拡張する枠の中に別の文字枠を重ねず、タイミングと全文を同じ行で測る。
