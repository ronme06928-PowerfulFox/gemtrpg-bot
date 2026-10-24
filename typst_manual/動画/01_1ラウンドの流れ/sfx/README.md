# 試用する効果音

2026-10-25選定。すべてKenney作、CC0です。元OGGを未加工で同梱し、生成時に音量を揃えます。

- [Interface Sounds 1.0](https://kenney.nl/assets/interface-sounds)：click_001、confirmation_002、tick_002、pluck_001。
- [Impact Sounds 1.0](https://kenney.nl/assets/impact-sounds)：impactWood_light_000、impactMetal_light_000。
- ライセンス：[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)。元パックのLicenseは同フォルダのLICENSE-*.txtです。

| 場面 | 音 | 選定理由 | ピーク |
| --- | --- | --- | --- |
| ダイス結果 | impactWood_light_000 | 短い木の接触音。出目を見せるときに2回 | -22dBFS |
| スロット配置・宣言 | click_001 | 小さなクリック。操作の区切りを示す | -24dBFS |
| マッチ成立 | confirmation_002 | 組合せが確定したと分かる音 | -19dBFS |
| 威力確定 | tick_002 | 数字の出現に短い区切りを付ける | -22dBFS |
| HP減少 | impactMetal_light_000 | 装甲のある敵への軽い打撃 | -18dBFS |
| FP獲得 | pluck_001 | 打撃音と違う、短い音程のある音 | -23dBFS |

使用しない候補：足音・重い打撃・ベルは、移動や大きなダメージを連想させるため外しました。常時BGMやスライド切替音も加えません。
試聴用の`out/sfx-samples.wav`は表の順に2秒ごとです。最終的な音の好み・聴きやすさは動画と合わせて調整します。

`cues.json`は各段階の先頭からの秒数です。画面のアニメーションに合わせて配置しています。
FPの音は整数が増える時刻、マッチは矢印が金色になる時刻、被弾はHPが減り始める時刻に合わせます。
`prepare-media.mjs`がピーク正規化、短い末尾フェード、無音の追加を行い、標準の`audio/manifest.json`を生成します。
10段階・13音。字幕の説明中は基本的に無音です。読み上げとBGMは含みません。
