---
name: m-dice
series: gemuria-video
summary: 本のSVGが駒から転がり出て止まり、確定値が行き先へ移る。
steps: 1
props: []
---

# ダイス

JSONは `face`（1〜6）、`value`（補正を含む確定値）、`from/stop/to`（盤面内の中心座標）。子に `[data-die]`、6つの `[data-face="1".."6"]`、`[data-dice-number]`、`[data-dice-target]` を置く。`data-face` は本の `die-1`〜`die-6` SVGを含む。0〜1.1秒で転がり、1.1〜1.5秒は確定面、1.5〜2.4秒は値を行き先へ動かす。

使い方の断片は [demo.html](demo.html)。CSS・必要素材・確認デッキの組立は [共通README](../../README.md) を参照。部品はデッキの components/dice/index.js へコピーする。すべての表示を(k,t)から復元し、t=Infinityは段階の最終状態。独自タイマー・乱数・CSSアニメーションは使わない。

## 注意

図の文字は24px以上、本文27px。部品の配置先を含む図領域に .plot を付ける。数値JSONは呼出側で検算し、本文のルールを参照する。確認デッキの配置は今回の2駒の作例に限定する。
