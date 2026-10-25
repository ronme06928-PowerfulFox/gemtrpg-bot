# 全編で使う効果音

KenneyのInterface Sounds 1.0とImpact Sounds 1.0、すべてCC0です。R1で採用した5種を使います。
元OGGは未加工で保持し、生成時にピークをそろえます。

- [Interface Sounds](https://kenney.nl/assets/interface-sounds)：click_001、confirmation_002、tick_002、pluck_001。
- [Impact Sounds](https://kenney.nl/assets/impact-sounds)：impactMetal_light_000。
- [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)。同梱のLICENSE-*.txtも参照。

| 場面 | 音 | ＋6dB適用後の素材ピーク |
| --- | --- | --- |
| 流れ・スロット・宣言 | click_001 | -18dBFS |
| マッチ成立 | confirmation_002 | -13dBFS |
| ダイス結果・威力確定 | tick_002 | -16dBFS |
| HP減少 | impactMetal_light_000 | -12dBFS |
| 勝利FP・終了時FP | pluck_001 | -17dBFS |

`cues.json`のsourcesに素材と基準ピーク、`voice/events.json`に音声markまたは段階先頭からの秒数を指定します。
`prepare-r2.mjs`から共通の `prepare-voice.mjs` を使い、声を-20 LUFS目標に調整してSE＋6dBを重ねます。
SEは13回。勝利FPと終了時FPは別の段階です。全波形を検査し、クリップを起こす場合は生成を止めます。
BGMと常時の切替音は加えません。配布用HTML・MP4の最後にKenney（CC0）を表示します。
