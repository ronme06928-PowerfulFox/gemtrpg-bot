"""配布用Cinzel/Zen Antiqueを使用文字へ絞る。元フォントとOFLはcommon/fonts。"""
from pathlib import Path
import re
import shutil
from fontTools.ttLib import TTFont
from fontTools import subset
from fontTools.varLib.instancer import instantiateVariableFont

video = Path(__file__).resolve().parent.parent
deck = video / "01_1ラウンドの流れ"
source = video / "common/fonts"
texts = [deck / "narration-v3-dialogue.md", deck / "deck.html",
         video / "scripts/r1-resolve-sample.mjs",
         video.parent.parent / "static/js/battle/components/resolve_stage.js",
         video.parent.parent / "static/js/fx/fx_effects.js"]
text = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz＋−＝〜→×勝利総ダメージ基本の一太刀味方敵"
for file in texts:
    data = file.read_text(encoding="utf-8")
    data = re.sub(r"<script[\s\S]*?</script>", "", data)
    text += data
css = []
for family, filename, weight in [("Cinzel", "Cinzel-wght.ttf", 900),
                                  ("Zen Antique", "ZenAntique-Regular.ttf", 400)]:
    font = TTFont(source / filename)
    if "fvar" in font:
        font = instantiateVariableFont(font, {"wght": weight}, inplace=True)
    options = subset.Options()
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]
    options.layout_features = ["*"]
    sub = subset.Subsetter(options=options)
    sub.populate(text=text)
    sub.subset(font)
    font.flavor = "woff2"
    output = source / (filename.removesuffix(".ttf") + ".woff2")
    font.save(output)
    (deck / "fonts").mkdir(exist_ok=True)
    shutil.copyfile(output, deck / "fonts" / output.name)
    css.append(f"@font-face{{font-family:'{family}';font-style:normal;font-weight:{weight};font-display:block;src:url('fonts/{output.name}') format('woff2')}}")
    print(output.name, output.stat().st_size)
css.append("[data-gallery-resolve-panel] .power-number,.fx-power-roll{font-variant-numeric:lining-nums}")
css.append(".v3-win-fp{position:absolute;left:210px;top:380px;background:#fff9ef;color:#ad2840;padding:8px 16px;border:2px solid #ad2840;border-radius:8px;font:28px 'BIZ UDPGothic',sans-serif}")
(deck / "fonts.css").write_text("\n".join(css) + "\n", encoding="utf-8", newline="\n")
