# 全編で使う効果音

KenneyのInterface Sounds 1.0・Impact Sounds 1.0、アプリと同じSpringin’ Sound Stockのダイス音、自作音を使います。最新の追加と音量は末尾の2026-11-06節です。以下の初版の配置・回数は当時の記録です。

- [Interface Sounds](https://kenney.nl/assets/interface-sounds)：click_001、confirmation_002、pluck_001。
- [Impact Sounds](https://kenney.nl/assets/impact-sounds)：impactMetal_light_000。
- Kenneyの素材は[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)。同梱のLICENSE-*.txtも参照。
- [Springin’ Sound Stock サイコロ・ダイス](https://www.springin.org/sound-stock/subcategory/dice/)：「モノラル大きいダブルダイス3」。アプリの `static/audio/dice-roll.mp3` と同じ約1秒の音源です。

## アプリと同じダイス音

2026-10-26確認。`sound_fx.js`の既定音源とMP3のタイトル情報から出典を調べ、公式配布ファイルとバイト一致を確認しました。
SHA-256：`949e72e5b6b932af983ae9996853c270ca3ff8b9f19718e90eb904347ff8c064`。

[公式利用規約・FAQ](https://www.springin.org/sound-stock/guideline/)で動画の効果音利用と加工が可能と確認しました。
素材の単体再配布・素材集としての配布・Content ID登録には使いません。クレジットは任意ですが、共通の最終スライドへ `Springin’ Sound Stock` を追加します。

`prepare-round-v2.mjs`はアプリの元ファイルを読み取り、デッキ内の `sfx/imported/dice-roll.mp3` へコピーします。コピーはGit管理外です。
配布はナレーション等と合成したHTML・MP4。元MP3や単体SEの試聴ファイルを配布物へ追加しません。アプリ本体は変更しません。

## 音量と配置

| 場面 | 音 | ＋6dB適用後の素材ピーク |
| --- | --- | --- |
| 流れ・スロット・宣言 | click_001 | -18dBFS |
| マッチ成立 | confirmation_002 | -13dBFS |
| 速度値・最終威力の確定 | アプリのdice-roll.mp3 | -16dBFS |
| HP減少 | impactMetal_light_000 | -12dBFS |
| 勝利FP・終了時FP | pluck_001 | -17dBFS |

`cues.json`のsourcesに素材と基準ピーク、`voice/events.json`に音声markまたは段階先頭からの秒数を指定します。
`prepare-round-v2.mjs`から共通の `prepare-voice.mjs` を使い、声を-20 LUFS目標に調整してSE＋6dBを重ねます。
冒頭改訂版のSEは12回（タイトル1回、ダイス4回を含む）。速度値・最終威力が確定した時に、味方・敵それぞれ1回のダイス音を鳴らします。途中のロール音と確定tickは重ねません。ダイス周りの音を8回から4回へ減らしています。
勝利FPと終了時FPは別の段階です。全波形を検査し、クリップを起こす場合は生成を止めます。
BGMと常時の切替音は加えません。配布用HTML・MP4の最後にKenney（CC0）とSpringin’ Sound Stockを表示します。

## タイトル用チャイム（2026-10-27）

common/opening.mjsで523.251・659.255・783.991Hzの3音をPCM合成した自作音。外部音源は使わない。24kHzモノラル、開始0.08秒、音の余韻は1.2秒以内、カード全体は2.6秒。基準ピーク−22dBFSに共通の＋6dBを適用して−16dBFSとする。音声の欠損を埋める無音ではなく、題名を読むSEのみの段階。共通クレジットの効果音表記に「自作」を加えた。

## 2026-11-06：気づく間と動きの開始に合わせたSE

今回の追加はKenneyの既存CC0素材と自作だけを使う。効果音ラボは使用しない。声と間の基本規則は変えず、各動きの予定の開始時刻へ音を置く。囲みの印には音を付けない。

| 場面 | 素材・出どころ | 基準→＋6dB後のピーク |
| --- | --- | --- |
| C02・C15のスロット | soft-pop.wav（自作） | −29→−23dBFS |
| GMの吹き出し | 同じsoft-pop.wav（自作）。スロットと同時なら重ねず1回 | −35→−29dBFS |
| C04の矢印1本ごと | soft-swish.wav（自作） | −31→−25dBFS |
| 盤面⇔パネル | 同じsoft-swish.wav（自作）、軽め | −34→−28dBFS |
| C04の技名の札 | click_001.ogg（Kenney Interface Sounds 1.0、CC0） | −32→−26dBFS |
| C13の拡大窓 | paper-turn.wav（自作） | −32→−26dBFS |
| 段階表の現在位置が移る | click_001.ogg（Kenney Interface Sounds 1.0、CC0）、ごく小さく | −40→−34dBFS |

自作3音は `scripts/prepare-video-sfx.mjs` の固定乱数による24kHzモノラルPCM合成で再生成する。ポンッは短い下降音、シュッは帯域を絞った雑音、紙は細かな強弱を付けた雑音。自作音はCC0 1.0（LICENSE-self.txt）。Kenneyは既存のLICENSE-interface.txtを添付済み。新しい外部ファイルは取得しない。題・マッチ・FP・ダイスの既存素材は維持する。

段の終了計算には効果音の終端も含め、合成後の全波形の最大値が1未満であることを検査してから保存する。各段のSE一覧と最大ピークは `_local/round-v3/voice-report.json` に記録する。
