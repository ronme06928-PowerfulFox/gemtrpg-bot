---
name: m-gm-bubble
series: gemuria-video
summary: 画面の端にGMの仮アイコンと吹き出しを出す。
steps: 1
props: []
---

# GMの吹き出し

子に `[data-gm-panel]`。円・点・曲線で描いた仮の顔と案内を含む。0〜0.6秒で18px下から出す。盤面上部に置き、画面下の字幕用領域と分ける。人物や既存キャラクターの参照はない。

使い方の断片は [demo.html](demo.html)。CSS・必要素材・確認デッキの組立は [共通README](../../README.md) を参照。部品はデッキの components/gm-bubble/index.js へコピーする。すべての表示を(k,t)から復元し、t=Infinityは段階の最終状態。独自タイマー・乱数・CSSアニメーションは使わない。

## 注意

図の文字は24px以上、本文27px。部品の配置先を含む図領域に .plot を付ける。数値JSONは呼出側で検算し、本文のルールを参照する。確認デッキの配置は今回の2駒の作例に限定する。
