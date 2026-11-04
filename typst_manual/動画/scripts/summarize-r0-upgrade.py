"""R0の同時刻比較を一覧にし、埋め込み媒体の容量を排他的に集計する。"""
import json
import math
from pathlib import Path
import re
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFont


def html_sizes(file):
    source = file.read_text(encoding="utf-8")
    sizes = {"audio": 0, "image": 0, "font": 0, "components": 0, "player": 0}

    def media(match):
        mime = match[1]
        category = "audio" if mime.startswith("audio/") else "image" if mime.startswith("image/") else "font"
        sizes[category] += len(match[0].encode("utf-8"))
        return ""

    rest = re.sub(r"data:((?:audio|image|font|application/font)[^;,\s\"']*)[^,\s\"']*;base64,[A-Za-z0-9+/=]+", media, source)
    for match in re.finditer(r"<script\b([^>]*)>(.*?)</script>", rest, re.S):
        if re.search(r'type=["\']application/(?:json|ld\+json)', match[1]):
            continue
        category = "components" if "DECK.define(" in match[2] else "player"
        sizes[category] += len(match[0].encode("utf-8"))
    sizes["other"] = file.stat().st_size - sum(sizes.values())
    sizes["total"] = file.stat().st_size
    return sizes


def main():
    lightweight = "--r05" in sys.argv
    names = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    deck = Path("typst_manual/動画/01_1ラウンドの流れ/out")
    work = deck / ("r05-comparison" if lightweight else "r0-comparison")
    report = json.loads((work / "report.json").read_text(encoding="utf-8"))
    records = report["records"]
    chosen = [next(r for r in records if r["i"] == i and r["k"] == (1 if i == 0 else max(s["k"] for s in report["timeline"] if s["i"] == i)) and r["kind"] == "step") for i in range(12)]
    chosen += [next(r for r in records if r["kind"] == f"boundary-{i}-right" and r["t"] == 0) for i in range(1, 12)]
    chosen += [next(r for r in records if r["i"] == i and r["k"] == k and r["kind"] == "step") for i, k in [(0, 3), (1, 1), (2, 1), (5, 2)]]
    chosen += [next(r for r in records if r["kind"] == "ending" and r["t"] == t) for t in (0, 2.5, 4.99)]
    chosen += [r for r in records if r["kind"].startswith("mark-")]
    font = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 16)
    sheet = Image.new("RGB", (1280, math.ceil(len(chosen) / 2) * 208 + 36), "#f0f0f0")
    draw = ImageDraw.Draw(sheet)
    title = "R0.5: 左 軽量化前 ／ 右 軽量化後" if lightweight else "R0: 左 v0.4.5 ／ 右 v0.6.3（色調整後）"
    draw.text((12, 7), title + "   各組は同じ場面・段階・秒数", font=font, fill="black")
    for n, r in enumerate(chosen):
        x, y = n % 2 * 640, n // 2 * 208 + 36
        draw.text((x + 6, y), f'{r["key"]}  t={r["t"]:.2f}s  {r["kind"]}', font=font, fill="black")
        for v in range(2):
            with Image.open(work / r["states"][v]["file"]) as image:
                sheet.paste(image.resize((320, 180)), (x + v * 320, y + 25))
    if lightweight:
        with Image.open("typst_manual/動画/_local/r05-image-quality/quality-overview.png") as quality:
            quality = quality.resize((1280, round(quality.height * 1280 / quality.width)))
            combined = Image.new("RGB", (1280, sheet.height + quality.height), "#f0f0f0")
            combined.paste(sheet, (0, 0))
            combined.paste(quality, (0, sheet.height))
            sheet = combined
    sheet.save(deck / ("r05-comparison-overview.png" if lightweight else "r0-comparison-overview.png"))
    different = []
    for r in records:
        with Image.open(work / r["states"][0]["file"]) as a, Image.open(work / r["states"][1]["file"]) as b:
            diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
            channels = diff.split()
            maximum = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
            pixels = sum(maximum.histogram()[9:])
            if pixels:
                different.append({"key": r["key"], "t": r["t"], "kind": r["kind"], "pixelsOver8": pixels})
    labels = ["before", "after"] if lightweight else ["v0.4.5", "v0.6.3"]
    sizes = {label: html_sizes(deck / name) for label, name in zip(labels, names)}
    summary = {"pairs": len(records), "sizes": sizes, "wraps": report["wraps"], "pixelDifferences": different}
    (work / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
