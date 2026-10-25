# R1で比較する効果音

KenneyのInterface Sounds 1.0とImpact Sounds 1.0、いずれもCC0です。
基準版から5種の未加工OGGとライセンスをコピーしました。

- [Interface Sounds](https://kenney.nl/assets/interface-sounds)：click_001（宣言）、confirmation_002（マッチ成立）、tick_002（威力確定）、pluck_001（FP）。
- [Impact Sounds](https://kenney.nl/assets/impact-sounds)：impactMetal_light_000（被弾）。
- [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)。同梱のLICENSE-*.txtも参照。

`cues.json`のsourcesは従来の素材ピーク、`voice/events.json`は発話のmarkまたは段階先頭からの秒数を指定します。
prepare-r1.mjsは従来音量（--baseline）と＋6dB（既定）を生成します。
声の原音・話速・抑揚・間は同じにし、SEのゲインだけを比較します。
ナレーションは-20 LUFSを目標に調整し、合成した各段階がクリップしないことを検査します。
判定対象は発話とSEが重なった波形です。無音の多い全編の平均音量では判断しません。

使用箇所：宣言、マッチ成立、味方と敵の威力確定、被弾、FP獲得の計6回。
BGMは入れていません。SEの好みと声とのバランスはR1の試聴で決めます。
