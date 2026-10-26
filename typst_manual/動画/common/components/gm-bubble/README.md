---
name: m-gm-bubble
series: gemuria-video
summary: オパール色のGMの札と吹き出しを出す。
steps: 1
props: []
---

# GMの吹き出し

子に `[data-gm-panel]`。「GM」の文字の札と案内を含む。札は操作ガイドGM編と同じオパール色 `#a8457f`。吹き出しの「GM：」は付けない。0〜0.6秒で18px下から出す。S1確認では盤面上部、S2絵コンテでは駒の下・字幕の上へ置く。どちらも字幕用領域と分ける。仮の顔アイコンは削除した。

使い方の断片は [demo.html](demo.html)。CSS・必要素材・確認デッキの組立は [共通README](../../README.md) を参照。部品はデッキの components/gm-bubble/index.js へコピーする。すべての表示を(k,t)から復元し、t=Infinityは段階の最終状態。独自タイマー・乱数・CSSアニメーションは使わない。

## 注意

図の文字は24px以上、本文27px。部品の配置先を含む図領域に .plot を付ける。数値JSONは呼出側で検算し、本文のルールを参照する。確認デッキの配置は今回の2駒の作例に限定する。
