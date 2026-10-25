# 全編で使う効果音

KenneyのInterface Sounds 1.0とImpact Sounds 1.0の5種に、アプリで使っているSpringin’ Sound Stockのダイス音を加えています。

- [Interface Sounds](https://kenney.nl/assets/interface-sounds)：click_001、confirmation_002、tick_002、pluck_001。
- [Impact Sounds](https://kenney.nl/assets/impact-sounds)：impactMetal_light_000。
- Kenneyの素材は[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)。同梱のLICENSE-*.txtも参照。
- [Springin’ Sound Stock サイコロ・ダイス](https://www.springin.org/sound-stock/subcategory/dice/)：「モノラル大きいダブルダイス3」。アプリの `static/audio/dice-roll.mp3` と同じ約1秒の音源です。

## アプリと同じダイス音

2026-10-26確認。`sound_fx.js`の既定音源とMP3のタイトル情報から出典を調べ、公式配布ファイルとバイト一致を確認しました。
SHA-256：`949e72e5b6b932af983ae9996853c270ca3ff8b9f19718e90eb904347ff8c064`。

[公式利用規約・FAQ](https://www.springin.org/sound-stock/guideline/)で動画の効果音利用と加工が可能と確認しました。
素材の単体再配布・素材集としての配布・Content ID登録には使いません。クレジットは任意ですが、共通の最終スライドへ `Springin’ Sound Stock` を追加します。

`prepare-r2.mjs`はアプリの元ファイルを読み取り、デッキ内の `sfx/imported/dice-roll.mp3` へコピーします。コピーはGit管理外です。
配布はナレーション等と合成したHTML・MP4。元MP3や単体SEの試聴ファイルを配布物へ追加しません。アプリ本体は変更しません。

## 音量と配置

| 場面 | 音 | ＋6dB適用後の素材ピーク |
| --- | --- | --- |
| 流れ・スロット・宣言 | click_001 | -18dBFS |
| マッチ成立 | confirmation_002 | -13dBFS |
| ダイス結果・威力確定 | tick_002 | -16dBFS |
| 速度・威力のダイスを振る | アプリのdice-roll.mp3 | -16dBFS |
| HP減少 | impactMetal_light_000 | -12dBFS |
| 勝利FP・終了時FP | pluck_001 | -17dBFS |

`cues.json`のsourcesに素材と基準ピーク、`voice/events.json`に音声markまたは段階先頭からの秒数を指定します。
`prepare-r2.mjs`から共通の `prepare-voice.mjs` を使い、声を-20 LUFS目標に調整してSE＋6dBを重ねます。
SEは17回。ダイス音は速度と威力の計算で各2回、それぞれの出目確定より前に鳴らし、確定時のtickと役割を分けます。
勝利FPと終了時FPは別の段階です。全波形を検査し、クリップを起こす場合は生成を止めます。
BGMと常時の切替音は加えません。配布用HTML・MP4の最後にKenney（CC0）とSpringin’ Sound Stockを表示します。
