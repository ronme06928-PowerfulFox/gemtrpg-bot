"""実MP4のC01/C03/C06を6フレームごとに抽出し、語りの区間と照合する。"""
import json
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageStat

DECK = Path(__file__).resolve().parents[1] / "01_1ラウンドの流れ"
OUT = DECK / "out/v2-sync"
FF = Path("C:/Users/yharu/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.1-full_build/bin/ffmpeg.exe")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def extract(movie, start, frames, directory):
    directory.mkdir(parents=True, exist_ok=True)
    expression = f"select=between(n\\,{start}\\,{start + frames - 1})*not(mod(n-{start}\\,6))"
    result = subprocess.run(
        [str(FF), "-v", "error", "-y", "-i", str(movie), "-vf", expression,
         "-frames:v", str((frames + 5) // 6),
         "-fps_mode", "passthrough", "-start_number", "0", "-compression_level", "1",
         str(directory / "%04d.png")], capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def hot(pixel):
    r, g, b = pixel[:3]
    return r > 120 and g < 125 and b < 160 and r > g * 1.45


def glow_fraction(image, rect):
    if rect["width"] <= 0:
        return 0
    cx = round(rect["x"] + rect["width"] / 2)
    top = math.floor(rect["y"]) - 6
    patch = image.crop((cx - 8, top - 1, cx + 8, top + 2))
    return sum(hot(p) for p in patch.getdata()) / (16 * 3)


def box_state(image, rect):
    x, y = round(rect["x"]), round(rect["y"])
    dark = sum(ImageStat.Stat(image.crop((x + 5, y + 5, x + 8, y + 8))).mean[:3]) / 3 < 90
    inner = image.crop((x + 12, y + 8, x + max(13, round(rect["width"]) - 8), y + max(9, round(rect["height"]) - 8)))
    letters = sum(min(p[:3]) > 170 for p in inner.getdata())
    return {"dark": dark, "letters": letters}


def digit_patch(image, rect):
    cx = round(rect["x"] + rect["width"] / 2)
    cy = round(rect["y"] + rect["height"] / 2)
    return image.crop((cx - 13, cy - 19, cx + 13, cy + 19))


def difference(a, b):
    pairs = [(x, y) for x, y in zip(a.getdata(), b.getdata()) if not hot(x) and not hot(y)]
    return sum(sum((x[c] - y[c]) ** 2 for c in range(3)) for x, y in pairs) / max(1, len(pairs) * 3)


def main():
    reference = load(OUT / "quarter-reference.json")
    render = load(OUT / "timeline.out.json")
    assert render["complete"]
    assert [(s["key"], s["frames"]) for s in render["segments"]] == [(s["key"], s["frames"]) for s in reference["timeline"]]
    failures, selected, checks = [], [], []
    seen = set()
    for cut in (0, 2, 5):
        samples = [r for r in reference["records"] if r["i"] == cut]
        segments = [s for s in reference["timeline"] if s["i"] == cut]
        directory = OUT / "quarter-frames" / f"C{cut + 1:02d}"
        extract(OUT / "full.mp4", segments[0]["frameStart"], sum(s["frames"] for s in segments), directory)
        assert len(list(directory.glob("*.png"))) == len(samples)
        for index, rec in enumerate(samples):
            file = directory / f"{index:04d}.png"
            with Image.open(file).convert("RGB") as image:
                for target in rec["glows"]:
                    fraction = glow_fraction(image, target["rect"])
                    actual = fraction >= .2
                    if actual != target["on"]:
                        failures.append({"file": str(file), "target": target["name"], "expected": target["on"], "redFraction": fraction})
                    checks.append({"cut": cut, "frame": rec["frame"], "name": target["name"], "on": target["on"], "fraction": fraction})
                    if target["on"] and (cut, target["name"]) not in seen:
                        selected.append((file, f"C{cut + 1:02d} {rec['frame'] / 24:.2f}s {target['name']}"))
                        seen.add((cut, target["name"]))
                if cut == 2:
                    box = box_state(image, rec["formula"]["rect"])
                    if rec["formula"]["visible"]:
                        assert box["dark"] and box["letters"] > 20, (file, box)
                    else:
                        assert not box["dark"], (file, "文字が出る前に箱が映る")
    baseline = load(DECK / "out/sync-before.json")
    old_segments = [s for s in baseline["render"]["segments"] if s["i"] == 2]
    old_start = round(old_segments[0]["clipStart"] * 24)
    old_count = sum(s["frames"] for s in old_segments)
    old_dir = OUT / "quarter-frames/C03-before"
    extract(DECK / "out/v2-opening/full.mp4", old_start, old_count, old_dir)
    old_empty = []
    for index, file in enumerate(sorted(old_dir.glob("*.png"))):
        with Image.open(file).convert("RGB") as image:
            box = box_state(image, reference["oldGeometry"]["formula"])
            if box["dark"] and box["letters"] <= 20:
                old_empty.append({"frame": old_start + index * 6, "seconds": (old_start + index * 6) / 24, "file": str(file)})
    assert old_empty, "修正前の空の箱も負例として検出する"
    selected.append((Path(old_empty[0]["file"]), f"BEFORE C03 {old_empty[0]['seconds']:.2f}s empty box"))
    measured = []
    new_samples = [r for r in reference["records"] if r["i"] == 2]
    for label, samples, directory, rects in [
        ("after", new_samples, OUT / "quarter-frames/C03", None),
        ("before", None, old_dir, reference["oldGeometry"]["dice"]),
    ]:
        if label == "after":
            template_index = next(i for i, r in enumerate(samples) if r["k"] == 3)
            geometry = samples[template_index]["dice"]
            rects = [d["rect"] for d in geometry]
            frames = [r["frame"] for r in samples]
        else:
            template_frame = round(next(s for s in old_segments if s["k"] == 3)["clipStart"] * 24) + 6
            template_index = math.ceil((template_frame - old_start) / 6)
            frames = list(range(old_start, old_start + old_count, 6))
        with Image.open(directory / f"{template_index:04d}.png").convert("RGB") as image:
            templates = [digit_patch(image, rect) for rect in rects]
        matches = [[], []]
        for index, frame in enumerate(frames):
            with Image.open(directory / f"{index:04d}.png").convert("RGB") as image:
                for side in (0, 1):
                    matches[side].append(difference(digit_patch(image, rects[side]), templates[side]) < 100)
        for side in (0, 1):
            first = next(i for i in range(len(frames) - 2) if all(matches[side][i:i + 3]))
            value_time = frames[first] / 24
            if label == "after":
                assert value_time < reference["comparison"][side]["after"]["spoken"]
                selected.append((directory / f"{first:04d}.png", f"AFTER C03 {value_time:.2f}s slot {6 if side == 0 else 4}"))
            measured.append({"version": label, "side": side, "firstStableValueFrame": frames[first], "seconds": value_time})
    report = {"interval": .25, "quarterFrames": len(reference["records"]), "glowChecks": len(checks), "failures": failures, "checks": checks, "beforeEmptyBoxFrames": old_empty, "measuredValues": measured, "comparison": reference["comparison"]}
    (OUT / "quarter-video-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert not failures, json.dumps(failures[:10], ensure_ascii=False)
    width, height = 426, 264
    sheet = Image.new("RGB", (width * 3, height * math.ceil(len(selected) / 3)), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (file, label) in enumerate(selected):
        x, y = i % 3 * width, i // 3 * height
        draw.text((x + 6, y + 4), label, fill="black")
        with Image.open(file) as image:
            sheet.paste(image.resize((426, 240)), (x, y + 24))
    sheet.save(OUT / "sync-comparison.png")
    print(f"Actual MP4: {len(reference['records'])} quarter-second frames, {len(checks)} glow checks passed; no empty box after fix")


if __name__ == "__main__":
    main()
