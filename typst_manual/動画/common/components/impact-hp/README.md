---
name: m-impact-hp
series: gemuria-video
summary: 説明用の一撃の到着からHPの減少へつなげる。
steps: 1
props: []
---

# 一撃とHP

JSONは `hp/max/damage`。子に `[data-hit]`、`[data-hp-value]`、`[data-hp-fill]`、`[data-damage]`。0〜0.8秒で味方から敵へ走り、0.8〜1.9秒でHPを減らし、0.8〜2.4秒でダメージ数字を浮かべて消す。駒間640pxの配置は今回の作例専用。アプリに実装された演出として扱わない。

使い方の断片は [demo.html](demo.html)。CSS・必要素材・確認デッキの組立は [共通README](../../README.md) を参照。部品はデッキの components/impact-hp/index.js へコピーする。すべての表示を(k,t)から復元し、t=Infinityは段階の最終状態。独自タイマー・乱数・CSSアニメーションは使わない。

## 注意

図の文字は24px以上、本文27px。部品の配置先を含む図領域に .plot を付ける。数値JSONは呼出側で検算し、本文のルールを参照する。確認デッキの配置は今回の2駒の作例に限定する。
