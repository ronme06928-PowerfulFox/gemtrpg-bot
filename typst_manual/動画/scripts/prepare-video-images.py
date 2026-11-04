"""元PNGから動画用WebPを生成する。--compareは画質候補と拡大比較を作る。"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

VIDEO = Path(__file__).resolve().parents[1]
DECK = VIDEO / "01_1ラウンドの流れ"
SOURCES = {
    "ruins": VIDEO / "common/assets/ruins-battle.png",
    "ally": DECK / "images/ally-adventurer.png",
    "enemy": DECK / "images/wolf-shularker.png",
}


def write_webp(source, target, quality=None):
    with Image.open(source) as image:
        image.save(target, "WEBP", lossless=quality is None, quality=100 if quality is None else quality, method=6, exact=True)


def compare():
    out = VIDEO / "_local/r05-image-quality"
    out.mkdir(parents=True, exist_ok=True)
    original = Image.open(SOURCES["ruins"]).convert("RGB")
    variants = [("PNG", SOURCES["ruins"])]
    for quality in [None, 95, 90, 85]:
        label = "lossless" if quality is None else f"q{quality}"
        target = out / f"ruins-{label}.webp"
        write_webp(SOURCES["ruins"], target, quality)
        variants.append((label, target))
    font = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 18)
    sheet = Image.new("RGB", (1500, len(variants) * 260), "#eeeeee")
    draw = ImageDraw.Draw(sheet)
    crops = [(500, 40, 800, 240), (610, 350, 910, 550), (650, 680, 950, 880)]
    for row, (label, file) in enumerate(variants):
        image = Image.open(file).convert("RGB")
        draw.text((8, row * 260), f"{label}: {file.stat().st_size:,} bytes  全体 / 空 / 階段 / 石畳", font=font, fill="black")
        sheet.paste(image.resize((480, 240)), (0, row * 260 + 25))
        for col, crop in enumerate(crops):
            sheet.paste(image.crop(crop), (500 + col * 330, row * 260 + 35))
        print(label, file.stat().st_size, ImageChops.difference(original, image).getextrema())
    sheet.save(out / "quality-overview.png")
    for key in ["ally", "enemy"]:
        target = out / f"{key}-lossless.webp"
        write_webp(SOURCES[key], target)
        a = Image.open(SOURCES[key]).convert("RGBA")
        b = Image.open(target).convert("RGBA")
        assert a.tobytes() == b.tobytes(), "立ち絵のRGBA画素が完全一致"
        print(key, SOURCES[key].stat().st_size, target.stat().st_size, "RGBA identical")


def prepare():
    out = VIDEO / "common/assets/video"
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"backgroundQuality": 95, "method": 6, "sources": {}, "outputs": {}}
    for key, source in SOURCES.items():
        target = out / f"{key}.webp"
        write_webp(source, target, 95 if key == "ruins" else None)
        if key != "ruins":
            assert Image.open(source).convert("RGBA").tobytes() == Image.open(target).convert("RGBA").tobytes()
        manifest["sources"][key] = hashlib.sha256(source.read_bytes()).hexdigest()
        manifest["outputs"][key] = hashlib.sha256(target.read_bytes()).hexdigest()
        print(key, source.stat().st_size, target.stat().st_size, flush=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--compare", action="store_true")
    args = parser.parse_args()
    if args.compare:
        compare()
    else:
        prepare()
