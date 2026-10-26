---
name: m-phase
series: gemuria-video
summary: 開始・選択・解決・終了の4段階を光らせる。
steps: 4
props: []
---

# 段階表示

子の `[data-phase]` を4個、この順に置く。各段階0.8秒。k=0は開始を示す。

使い方の断片は [demo.html](demo.html)。CSS・必要素材・確認デッキの組立は [共通README](../../README.md) を参照。部品はデッキの components/phase/index.js へコピーする。すべての表示を(k,t)から復元し、t=Infinityは段階の最終状態。独自タイマー・乱数・CSSアニメーションは使わない。

## 注意

図の文字は24px以上、本文27px。部品の配置先を含む図領域に .plot を付ける。数値JSONは呼出側で検算し、本文のルールを参照する。拡大縮小で文字の再ラスタライズを誘発せず、現在段階の背景色で光を示す。
