"""R1の本番比較一覧・Q10の全小文字・容量内訳を残す。"""
import json
from pathlib import Path
import runpy

from PIL import Image, ImageDraw, ImageFont

VIDEO = Path(__file__).resolve().parents[1]
OUT = VIDEO / "_local/r1-resolve/out"


def treatment(row):
    cls = row["className"]
    if cls == "character-name":
        return "動画だけ大きくする（27px以上を提案）"
    if cls in ["result-winner", "result-damage"]:
        return "動画だけ大きくする（結果帯の余白を使う）"
    if cls == "skill-field":
        return "寄って映す（約1.85倍で24px、1文だけを映す）"
    if cls == "power-range":
        return "威力の説明で寄る／読ませないなら出さない"
    return "出さない（操作・識別情報、または札との重複）"


def main():
    report = json.loads((OUT / "browser-report.json").read_text(encoding="utf-8"))
    quality = json.loads((OUT / "quality.json").read_text(encoding="utf-8"))
    sizes = runpy.run_path(str(VIDEO / "scripts/summarize-r0-upgrade.py"))["html_sizes"](OUT / "r1-resolve-latest.html")
    max_delta = max(row["diff"]["max"] for row in report["checks"])
    max_strong = max(row["diff"]["strong"] for row in report["checks"])
    font = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 18)
    pairs = []
    for k in [1, 2, 3, 4]:
        row = next(r for r in report["records"] if r["k"] == k and (abs(r["t"] - .5) < .001 if k == 4 else r["t"] > 1))
        pairs.append((f'{row["stage"]} / 動画段階{k} t={row["t"]:.3f}s / 本番時計 {row["time"]:.6f}s',
                      f'{row["name"]}-app.png', f'{row["name"]}-video.png'))
    row = next(r for r in report["records"] if r["k"] == 4 and r["t"] > 3)
    pairs.append(("勝敗の末尾で停止", f'{row["name"]}-app.png', f'{row["name"]}-video.png'))
    for t in [.1, 2.199]:
        pairs.append((f"既存の演出一覧の経路 / 命中後 {t}s", f"gallery-{t}-app.png", f"gallery-{t}-video.png"))
    sheet = Image.new("RGB", (1280, 36 + (len(pairs) + 1) * 390), "#eeeeee")
    draw = ImageDraw.Draw(sheet)
    draw.text((8, 6), "R1: 左 本番ソース・演出一覧 ／ 右 egatari試作（同じ作例・同じ本番時計）", font=font, fill="black")
    draw.text((8, 38), "盤面：宣言後 → 帰還後（HP30→21、味方FP0→1）", font=font, fill="black")
    for col, name in enumerate(["board-before.png", "board-after.png"]):
        with Image.open(OUT / "frames" / name) as image:
            sheet.paste(image.resize((640, 360)), (col * 640, 64))
    for index, (label, left, right) in enumerate(pairs, 1):
        y = 36 + index * 390
        draw.text((8, y), label, font=font, fill="black")
        for col, name in enumerate([left, right]):
            with Image.open(OUT / "frames" / name) as image:
                sheet.paste(image.resize((640, 360)), (col * 640, y + 28))
    sheet.save(OUT / "r1-resolve-comparison.png")
    grouped = {}
    for row in report["smallText"]:
        key = (row["text"], row["className"], row["cssPx"], row["screenPx"])
        grouped.setdefault(key, {**row, "stages": []})["stages"].append(row["stage"])
    md = ["# R1 解決パネル試作の確認（2026-11-04）", "",
          "音声なし、1280×720。名前0.5秒・威力1.2秒・攻撃0.7秒・勝敗2.2秒を等倍で描き、各段階に1秒の静止時間を足す。盤面2秒→4段階→帰還3秒、全体13.6秒。R2・v3本編には入っていない。", "",
          "## 写し方と時刻", "",
          "`prepare-r1-resolve.mjs` がesbuildの依存グラフを調べ、23ファイルを `_local/r1-resolve/vendor/repo/` へ元の相対位置・同じ内容で写してからbundleする。15個の本番JSモジュールを含む。ResolveFlowPanel・resolve_stage・resolve_stage_layout・resolve_stage_motion・resolve_stage_timing・resolve_stacks・resolve_flow_fx/result_fxと依存先、fx_core/effectsを使う。CSSは演出一覧のextractResolvePanelCssで取り出す。アプリ側の変更は不要だった。", "",
          "本番のinitialize・fx_playerは使わない。Socket/SE/通知/自動進行の入口を止め、本番の_renderStepへ同期的な時計と作例stateを渡して戻す。Fx.play要求を採取してmount/render(t)へ渡し、powerの本番rateも保持する。攻撃の余韻は勝敗へつなぎ、各段階末尾は次段階の1µs手前で停止する。盤面は本編の宣言後HTMLを読み取りで取り込み、帰還時だけ試作内のHP/FPと行動済みを変える。", "",
          "画像はR0.5の共有CSS変数とWebPを使い、HTMLへ3枚を各1回だけ入れる。本番のimgは内容欄のDOMへ入る直前に共有参照へ変換する（先に挿入すると元PNGへの読み込みが走る）。名前の描画層を固定し、盤面も独立した描画層のopacityで切り替える。visibility切替では通常GPUが立ち絵を再縮小して差分を生じたため、既存の画素を保つ切り替えへ直した。", "",
          "## 検証", "",
          f"- 巻き戻し・途中・末尾・境界：{report['frames']}時刻。本番を直接bundleする参照と各段階を比較。演出一覧のcreateRealStage/collectSceneEventsでも同じ作例の命中後3時刻を比較。スキル辞書を明示し、一覧で固定される進行率だけ同じ本番時計に合わせた。",
          "- ブラウザは通常GPUのEdge。Egatari自身のpixelStats/LEGACY_TOL（RGB差の和48を超える画素40以下）で判定し、小さい差もログへ残す。63時刻中62時刻は画素が完全一致し、勝敗0.25秒だけ29画素に1階調の差が残った。本番参照51時刻と演出一覧3時刻は全画素一致。PNGの厳密な一致は未達だが、動き・配置の差は検出されていない。",
          f"- 今回の往復の最大差は{max_delta}階調、はっきり違う画素は最大{max_strong}。末尾の威力ロールは完了へそろえ、停止中に9・6が空白にならないことも検査した。",
          f"- 品質：エラー{quality['counts']['error']}・警告{quality['counts']['warn']}。音声なし6段階のnarrMissing 6件、fontNotEmbedded 1件（Cinzel / Yu Gothic UI / Zen Antique）。音声生成0。部品エラー0。アプリのstage/tick/motion/auto時計は全時刻でnull。",
          "- 単体テスト3件：作例、本番時間と停止、必須依存を含むbundleとfx_playerの不在。static/・app.py・本編01_1ラウンドの流れ/の差分なし。", "",
          "## Q10：24px未満の全表示文字", "",
          "画面上のpxは本番の縮小率0.92727倍を反映。元のCSS値と両方を示す。同じ文字の左右・時刻の重複はまとめた。空の状態欄に状態数字はなく、その仮例は加えていない。札のスキル名は約25.04px、主威力は約53.78pxで下の一覧には入らない。", "",
          "品質チェックは小文字を指摘していないが、実測では下記が24px未満。品質検査だけに頼らず、この文字一覧も更新時の確認対象にする。", "",
          "| 何の文字か | 種類 | CSS px | 画面px | 段階 | 扱いの提案 |",
          "| --- | --- | ---: | ---: | --- | --- |"]
    labels = {"names": "名前", "power": "威力", "attack": "攻撃", "outcome": "勝敗"}
    for row in grouped.values():
        text = row["text"].replace("|", "／")
        md.append(f"| {text} | `{row['className'] or '文章欄の見出し'}` | {row['cssPx']:g} | {row['screenPx']:.2f} | {'・'.join(labels[s] for s in row['stages'])} | {treatment(row)} |")
    md += ["", "## Q11：変更への気づき方", "",
           "既に、コピーのSHA-256照合・必須6モジュールの存在・fx_playerの不在・本番と同じ作例/時刻・画像の事前読込・無時計・結果HP/FPを検査している。依存の移動/削除はbundleテスト、非公開メソッドやDOM/CSSの変更はブラウザ比較と文字一覧で検出できる。", "",
           "包みは非公開の_ensurePanel/_panelContent/_renderStep/_stepStartedAtとstore._stateに依存するため、アプリ変更時のprepare＋verifyを必須にする。ここへ依存を集め、アプリ側へ動画専用APIは追加していない。", "",
           "CIへ足すなら、まず `node --test typst_manual/動画/scripts/test-r1-resolve.mjs`、ブラウザを用意したジョブでprepare→verify→品質チェックを行う。コピーmanifestは版固定ではなく毎回生成し、取り込み漏れと古い写しを検出する。画像・見本・試作は本番ソースの変更に合わせて作り直す。今回CI設定は変更していない。", "",
           "## HTMLの大きさ", "", "| 内訳（byte、埋込表現を含む） | 試作 |", "| --- | ---: |"]
    for key, label in [("audio", "音声"), ("image", "画像"), ("font", "フォント"), ("components", "部品・取り込んだ本番JS"), ("player", "egatari等JS"), ("other", "本文・CSS・JSON等"), ("total", "合計")]:
        md.append(f"| {label} | {sizes[key]:,} |")
    md += ["", "## R2の前に決めること", "",
           "1. 進行操作・スキルID・管理用の帯/重複見出しを動画で隠してよいか。",
           "2. 効果文/威力幅は寄って映し、名前/勝敗の結果帯は動画だけ大きくする方針で進めるか。全画面のまま全て24pxへ上げると、本番の並びを保てない。",
           "3. 配布時のフォントを既存の埋込可能なBIZ系へ揃えるか。試作は本番の指定とWindowsの代替字体を保持しており、端末を替えると見え方が変わり得る。", "",
           "Q8の台本3点はR2の絵コンテ/変更案で扱う。今回の試作では台本を変更していない。", ""]
    (VIDEO / "r1-resolve-review.md").write_text("\n".join(md), encoding="utf-8", newline="\n")
    print(json.dumps({"sizes": sizes, "smallTextRows": len(grouped), "quality": quality["counts"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
