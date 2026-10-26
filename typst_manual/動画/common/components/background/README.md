---
name: m-background
series: gemuria-video
summary: 格子から遺跡の背景へ切り替える。
steps: 1
props: []
---

# 背景

子の `[data-background-image]` は背景色のある全面コンテナとし、その中の `img` を `object-fit:contain` で表示する。0〜0.8秒で入る。画像ありでは格子を隠す。盤面と同じ段階で登場させ、以後の段階は最終状態を保持する。

使い方の断片は [demo.html](demo.html)。CSS・必要素材・確認デッキの組立は [共通README](../../README.md) を参照。部品はデッキの components/background/index.js へコピーする。すべての表示を(k,t)から復元し、t=Infinityは段階の最終状態。独自タイマー・乱数・CSSアニメーションは使わない。

## 注意

図の文字は24px以上、本文27px。部品の配置先を含む図領域に .plot を付ける。数値JSONは呼出側で検算し、本文のルールを参照する。背景を外した後に格子のCSS設定が残るアプリ側の挙動は共通READMEの比較記録を参照。部品はk=0で初期格子へ確実に戻す。
