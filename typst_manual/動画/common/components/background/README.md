---
name: m-background
series: gemuria-video
summary: 採用した遺跡を全面に敷き、初期表示から格子を隠す。
steps: 1
props: []
---

# 背景

子の `[data-background-image]` は背景色のある全面コンテナとし、その中の `img` を `object-fit:cover` で表示する。初期表示から画像を見せ、0〜0.8秒で画像の不透明度を85%から100%へ整える。段階0や巻き戻しを含め、格子を出さない。盤面と同じ段階に割り当て、以後は最終状態を保持する。

切り取りの既定値は `object-position:center 65%`。カット側のCSS変数 `--battle-background-position` で位置を指定できる。空・奥の階段・駒の足元が残る位置を選び、余白を作るcontain表示は使わない。

使い方の断片は [demo.html](demo.html)。CSS・必要素材・確認デッキの組立は [共通README](../../README.md) を参照。部品はデッキの components/background/index.js へコピーする。すべての表示を(k,t)から復元し、t=Infinityは段階の最終状態。独自タイマー・乱数・CSSアニメーションは使わない。

## 注意

図の文字は24px以上、本文27px。部品の配置先を含む図領域に .plot を付ける。アプリのcontain表示は変更しない。動画側の切り取りとアプリの盤面設定を混同しない。
