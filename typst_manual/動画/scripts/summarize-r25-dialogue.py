"""R2.5の字幕比較一覧と、再開に必要な結果の記録を作る。"""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

VIDEO = Path(__file__).resolve().parents[1]
WORK = VIDEO / '_local/r25-dialogue'
voice = json.loads((WORK / 'logs/voice-report.json').read_text(encoding='utf-8'))
first = json.loads((WORK / 'logs/voice-first-generation.json').read_text(encoding='utf-8'))
browser = json.loads((WORK / 'logs/browser-report.json').read_text(encoding='utf-8'))
quality = json.loads((WORK / 'logs/quality.json').read_text(encoding='utf-8'))
font = ImageFont.truetype('C:/Windows/Fonts/meiryo.ttc', 21)
sheet = Image.new('RGB', (1920, 80 + 4 * 578), '#eeeae5')
draw = ImageDraw.Draw(sheet)
draw.text((12, 7), '計画54 R2.5：掛け合いの試作／左 字幕A（共通位置・推奨）／右 字幕B（左右へ）', font=font, fill='#282725')
draw.text((12, 40), '本文29px・話者名27px。音声と話者名を1発言ごとに同時切替。下段は場面とクレジットの見本。', font=font, fill='#514c46')
items = [('a-3', 'A 説明役：共通位置'), ('b-3', 'B 説明役：左へ'),
         ('a-2', 'A 聞き手：同じ位置に名前札と色'), ('b-2', 'B 聞き手：右へ'),
         ('a-5', '敵の幅と式／切れた札の文字は非表示'), ('a-11', '勝者・総ダメージ27px以上／9を保持'),
         ('credits', '最後の5秒：両方の声をクレジット')]
for i, (name, label) in enumerate(items):
    x = i % 2 * 960
    y = 80 + i // 2 * 578
    draw.text((x + 10, y + 5), label, font=font, fill='#282725')
    with Image.open(WORK / 'frames' / f'{name}.png') as im:
        sheet.paste(im.convert('RGB').resize((960, 540), Image.Resampling.LANCZOS), (x, y + 38))
draw.text((990, 1850), f"場面のみ：掛け合い {voice['sceneSeconds']:.2f}秒", font=font, fill='#282725')
draw.text((990, 1890), f"一人語り {voice['soloSceneSeconds']:.2f}秒／差 +{browser['delta']:.2f}秒", font=font, fill='#282725')
draw.text((990, 1930), '共通クレジット5秒を加えると37.01秒／31.09秒', font=font, fill='#282725')
draw.text((990, 1990), '説明役：冥鳴ひまり／ノーマル／速さ1.10／抑揚1.03', font=font, fill='#282725')
draw.text((990, 2030), '聞き手：春日部つむぎ／ノーマル／速さ1.08／抑揚1.00', font=font, fill='#282725')
draw.text((990, 2090), '声の相性・口調は、この短い試作で確認してから全編へ。', font=font, fill='#282725')
sheet.save(WORK / 'out/r25-subtitle-comparison.png')
script = (VIDEO / 'r25-dialogue/narration.md').read_text(encoding='utf-8')
turns = [line for line in script.splitlines() if line.startswith(('Expert:', 'Novice:'))]
warn = {}
for row in quality['results']:
    if row['sev'] == 'warn':
        warn[row['code']] = warn.get(row['code'], 0) + 1
size = (WORK / 'out/r25-dialogue-latest.html').stat().st_size
report = f"""# R2.5 掛け合い試作の結果（2026-11-05）

音声入り単一HTMLは `../_local/r25-dialogue/out/r25-dialogue-latest.html`。字幕は初期ON、既定は動画モード。Aキーで再生／一時停止、左右キーで段階を移動する。字幕Bは同じHTMLを `?subtitle=b` で開く。MP4は作っていない。

## 台本の全文

```text
{chr(10).join(turns)}
```

最初に本番の威力ロール1.2秒、その末尾で最初の質問。説明と質問の間は威力段階末尾で止める。攻撃の規則を話した後、攻撃0.7秒・勝敗2.2秒を等倍で流し、勝敗の末尾を止めて最後の2発言。話者交代で演出を再ロールしない。通常強度。基礎威力・ダイス威力・物理補正の語と式を対応させ、個々の出目は読まない。

## 尺の比較

| 条件 | 場面部分 | 共通クレジット込み |
| --- | ---: | ---: |
| 掛け合い | {voice['sceneSeconds']:.2f}秒 | {voice['dialogueSeconds']:.2f}秒 |
| 一人語り（同じExpertの6発言） | {voice['soloSceneSeconds']:.2f}秒 | {voice['soloSeconds']:.2f}秒 |
| 増加 | +{browser['delta']:.2f}秒 | +{browser['delta']:.2f}秒 |

比較版はNoviceの2問だけを省き、Expertの原音6本・話し方・本番演出・SE・クレジットを同一にして実際に組んだ。現行v2そのものとの比較ではない。発言間は約0.1秒の余白、演出のみの段階は本番の長さ、クレジットのみ5秒。目標尺へ合わせる静止は足していない。

## 声の設定

| 役 | 声／スタイルID | 速さ | 高さ | 抑揚 |
| --- | --- | ---: | ---: | ---: |
| Expert | 冥鳴ひまり／ノーマル14 | 1.10 | 0 | 1.03 |
| Novice | 春日部つむぎ／ノーマル8 | 1.08 | 0 | 1.00 |

VOICEVOX ENGINE 0.26.0。共通でprePhonemeLength=0.08、postPhonemeLength=0.10、24kHz・モノラル。各発言をI=-20 LUFS／TP=-3dBの設定で音量調整し、クリップしないことを確認。初期設定の速さ1.0・抑揚1.0と採用設定の短い候補を各声で生成し、原音をvoice/cacheへ保存した。スタイルはこの固定版の両者ともノーマルのみ。

採用値は短い試作の設定案であり、聴感での自然さ・2人の声の相性の合否はユーザー確認待ち。自動検査は音量・尺・割当て・再生を確かめ、音色の好みを判定したものではない。既存の本編の声設定は変えていない。

原音の新規生成は{first['made']}本（台詞8本と初期設定の比較2本）。以後の組み直しは全てキャッシュで、最後は{voice['cached']}参照・再生成{voice['made']}。威力開始時には本番と同じ既存ダイス音を1回、基準-22dBFSへ+6dBを加えた-16dBFSで置いた。Springin’ Sound Stockも試作のクレジットへ記載する。

## 字幕の2案

- A：同じ下中央の箱に、説明役ひまり／聞き手つむぎの名前札。青系／橙系を添える。**Aを推奨**。視線を戻す場所が一定で、本物のパネルと字幕を行き来しやすい。色が分からなくても名前で識別できる。
- B：同じ名前札・色に加え、説明役を左、聞き手を右へ寄せる。話者交代は目立つが、目線が左右へ移り、本文の横幅も減る。

本文29px、名前札27px。各発言をegatariの1段階にし、Expert:/Novice:の役と音声・字幕の境界を一致させる。無言の本番演出とクレジットへ前の字幕は持ち越さない。比較一覧は `../_local/r25-dialogue/out/r25-subtitle-comparison.png`。

## 検証・品質

- 品質エラー{quality['counts']['error']}・警告{quality['counts']['warn']}・情報{quality['counts']['info']}。警告内訳：{json.dumps(warn, ensure_ascii=False)}。narrMissingは入場0秒・ロール・攻撃・勝敗の無言段階とクレジット。fontNotEmbeddedはR1由来のCinzel／Zen Antiqueで、字体は配置確認用の代替を含む。
- 0.25秒刻み等の{len(browser['checks'])}時刻で字幕本文・役・サイズ・範囲・演出時刻、管理表示の非表示を照合。12状態のPNG往復はegatari基準で通過。動画モードでも字幕初期ON。
- 通信遮断で声8本＋SE1本を全デコードし、実時間の通し再生で8発言の字幕切替と最後の5秒へ到達。部品エラー0。声の設定・本文・役を入力にした原音キャッシュを使い、別人の声を流用しない。
- 拡大した名前の小さな文字切れを行高で解消。寄りでは切れた札・名前・VSを隠し、幅と数値を残す。説明式の見出しはなし。勝者・総ダメージはCSS30px（画面上約27.82px）。
- HTMLは{size:,} byte。static/・app.py・本編01_1ラウンドの流れ/の差分なし。本編とR1のHTMLはR2時点のSHA-256とも一致。単体テストはR2.5の2件とR1の3件。

## 次に決めること

1. この声の組合せと話し方、Expertの柔らかさ／Noviceのくだけ具合を全編に使うか。
2. 字幕Aで進めるか。Bを採る場合も本文27px以上と名前札を保つ。
3. 掛け合いはつまずきのある所へ絞り、全編の尺を測ってから質問の数を決める方針でよいか。各カットに必ず質問を挟む形にはしない。

まだ全編の台本を書き直していない。上の確認後に全編の変更案を作り、承認してからR3へ進む。配布用のCinzel／Zen Antiqueの埋め込みと許諾確認は本制作時に行う。
"""
(VIDEO / 'r25-dialogue/review.md').write_text(report, encoding='utf-8', newline='\n')
print(json.dumps({'quality': quality['counts'], 'size': size, 'scene': voice['sceneSeconds'], 'delta': browser['delta']}, ensure_ascii=False))
