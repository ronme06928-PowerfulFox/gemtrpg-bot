"""2冊のルビが、上・左右の罫線・枠・ほかの文字に重なっていないかを全ページで測る（計画51）。

使い方（リポジトリ直下から）:
    python scripts/check_ruby_clearance.py

- 原稿を一時フォルダへ写し、ルビありの版とルビを隠した版を組んで画像にする。
  2枚の差分がルビの位置になる。ルビを隠した版で、その周りにインクがあるかを測る。
- 上・左右の空きが MIN_PT 未満のルビを一覧にし、1件でもあれば終了コード1を返す。
- 必要なもの：typst、pdftoppm、numpy、scipy、Pillow。
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
TYPST_ROOT = ROOT / "typst_manual"
FONT_DIR = TYPST_ROOT / "_local" / "fonts"
BOOKS = {"rulebook": "全体マニュアル/main.typ", "guide": "操作ガイド/main.typ"}
RUBY_TEXT = re.compile(r'text\(size: if compact \{ [0-9.]+em \} else \{ [0-9.]+em \}, weight: "regular", reading\)')
DPI = 300
PX_PER_PT = DPI / 72
MIN_PT = 1.0


def compile_pages(src, out, variant):
    pages = {}
    for name, main in BOOKS.items():
        pdf = out / f"{name}_{variant}.pdf"
        command = ["typst", "compile", "--root", str(src)]
        if FONT_DIR.exists():
            command += ["--ignore-system-fonts", "--font-path", str(FONT_DIR)]
        subprocess.run(command + [str(src / main), str(pdf)], check=True)
        folder = out / f"{name}_{variant}"
        folder.mkdir()
        subprocess.run(["pdftoppm", "-r", str(DPI), "-gray", str(pdf), str(folder / "p")], check=True)
        pages[name] = sorted(folder.glob("p-*.pgm"))
    return pages


def has_ink(region):
    return region.size > 0 and int(region.max()) - int(region.min()) > 18


def clearance(off, y0, y1, x0, x1):
    """ルビの箱から上・左右へ1pxずつ広げ、最初にインクに当たった距離（pt）。当たらなければNone。"""
    top = side = None
    for k in range(1, 16):
        if has_ink(off[max(y0 - k, 0):y0 - k + 1, max(x0 - 2, 0):x1 + 3]):
            top = (k - 1) / PX_PER_PT
            break
    for k in range(1, 10):
        if has_ink(off[y0:y1 + 1, max(x0 - k, 0):x1 + k + 1]):
            side = (k - 1) / PX_PER_PT
            break
    return top, side


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / "src"
        shutil.copytree(TYPST_ROOT, src, ignore=shutil.ignore_patterns("_local", "*.pdf"))
        theme = src / "manual_theme.typ"
        text = theme.read_text(encoding="utf-8")
        if len(RUBY_TEXT.findall(text)) != 1:
            sys.exit("manual_theme.typ のルビの文字指定が見つかりません。RUBY_TEXT を直してください。")
        on = compile_pages(src, tmp, "on")
        theme.write_text(RUBY_TEXT.sub(lambda m: f"hide({m.group(0)})", text), encoding="utf-8", newline="\n")
        off = compile_pages(src, tmp, "off")

        total, bad = 0, []
        for name in BOOKS:
            for page_on, page_off in zip(on[name], off[name]):
                a = np.asarray(Image.open(page_on), dtype=np.int16)
                b = np.asarray(Image.open(page_off), dtype=np.int16)
                diff = np.abs(a - b) > 40
                if not diff.any():
                    continue
                labels, _ = ndimage.label(ndimage.binary_dilation(diff, structure=np.ones((3, 15))))
                for ys, xs in ndimage.find_objects(labels):
                    yy, xx = np.nonzero(diff[ys, xs])
                    y0, y1 = ys.start + yy.min(), ys.start + yy.max()
                    x0, x1 = xs.start + xx.min(), xs.start + xx.max()
                    if y1 - y0 > 6 * PX_PER_PT:  # ルビより大きい差分は対象外
                        continue
                    total += 1
                    top, side = clearance(b, y0, y1, x0, x1)
                    near = min(v for v in (top, side, 99) if v is not None)
                    if near < MIN_PT:
                        page = int(re.search(r"p-(\d+)", page_on.name).group(1))
                        bad.append((name, page, round(near, 2)))
    print(f"ルビ {total} か所を検査しました。")
    for name, page, near in bad:
        print(f"  {name} {page}ページ：空き {near}pt")
    if bad:
        sys.exit(1)
    print(f"すべて上・左右に {MIN_PT}pt 以上空いています。")


if __name__ == "__main__":
    main()
