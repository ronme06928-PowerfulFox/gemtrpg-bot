---
name: m-fp
series: gemuria-video
summary: 勝利と効果の理由札を添え、光ってFPが増える。
steps: 2
props: []
---

# FPの丸

JSONは `initial` と `gains:[{amount,reason}]`（1〜2件）。子に `[data-fp-value]` と `[data-fp-reason]`。段階ごとに0〜1.1秒で値を増やす。1件だけ使う敵は `steps="1"` を付ける。k=0は初期値、札は非表示。

使い方の断片は [demo.html](demo.html)。CSS・必要素材・確認デッキの組立は [共通README](../../README.md) を参照。部品はデッキの components/fp/index.js へコピーする。すべての表示を(k,t)から復元し、t=Infinityは段階の最終状態。独自タイマー・乱数・CSSアニメーションは使わない。

## 注意

図の文字は24px以上、本文27px。部品の配置先を含む図領域に .plot を付ける。数値JSONは呼出側で検算し、本文のルールを参照する。教材の1.7倍寸法は、FPの円だけ54px・白枠5pxへ丸める。端数のある円はChromiumの再描画で境界の画素に差が出るため。
