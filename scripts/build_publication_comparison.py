"""Build Plan 46 layout candidates without changing the approved prototypes.

Run from any directory: python scripts/build_publication_comparison.py
Requires Typst 0.15 with Noto Sans JP. Generated sources stay in _local.
"""

from pathlib import Path
import argparse
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPES = ROOT / "typst_manual" / "試作"
WORK = ROOT / "typst_manual" / "_local" / "work" / "46_layout"
OUTPUT = ROOT / "output" / "pdf"
CANDIDATES = {"A": (10.5, False), "B": (11, False),
              "C": (11, True), "R": (12, False)}


def adapt_diagrams(source, ratio):
    """Move horizontal geometry only; retain font sizes and vertical dimensions."""
    def scaled(match):
        return f"{match[1]}{float(match[2]) * ratio:.3f}mm"

    for pattern in (
        r"(#at\()([\d.]+)mm", r"(width: )([\d.]+)mm",
        r"(screen\()([\d.]+)mm", r"((?<!\w)w: )([\d.]+)mm",
        r"(end: \()([\d.]+)mm",
    ):
        source = re.sub(pattern, scaled, source)
    return source


def configuration(title, candidate, font_size, bound):
    if candidate == "C":
        return f'''#import "/typst_manual/manual_theme.typ": publication-conf, publication-figure
#show: publication-conf.with(
  header-label: [{title} / C・11pt　紙面比較・内容未確定],
  footer-label: [計画46 / C],
)
'''
    margin = ("(inside: 24mm, outside: 20mm, top: 23mm, bottom: 23mm)"
              if bound else "(x: 18mm, y: 16mm)")
    return f'''#set page(paper: "a4", binding: left, margin: {margin},
  header: context text(size: 8pt, fill: rgb("647080"))[{title} / {candidate}・{font_size}pt　紙面比較・内容未確定],
  footer: context align(right, text(size: 8pt, fill: rgb("647080"))[計画46 / {candidate}　#counter(page).display()]))
#set text(font: "Noto Sans JP", size: {font_size}pt, lang: "ja", fill: rgb("253345"))
#set par(leading: 0.65em, spacing: 1.4em)
#set heading(numbering: none)
#show heading.where(level: 1): set text(size: 23pt)
#show heading.where(level: 2): set text(size: 14pt, fill: rgb("246589"))
#show heading.where(level: 2): set block(above: 3.5mm, below: 1.5mm)
'''


def chapter(filename, title, candidate, font_size, bound):
    original = (PROTOTYPES / filename).read_text(encoding="utf-8")
    # Keep the full existing body; only isolate setup, diagram definitions and body.
    setup, body = original.split("\n= ", 1)
    setup = re.sub(r"^#(?:set|show) .*\n", "", setup, flags=re.MULTILINE)
    setup = re.sub(r"^//.*\n", "", setup, flags=re.MULTILINE)
    setup = re.sub(r'^#import "46_戦闘図解.typ":.*\n', "", setup,
                   flags=re.MULTILINE)
    setup = setup.replace("above: 4mm, below: 4mm", "above: 3mm, below: 3mm")
    setup = setup.replace("inset: (x: 0pt, y: 4mm)", "inset: (x: 0pt, y: 3mm)")
    if candidate == "C":
        setup, count = re.subn(r"^#let fig\(.*?^\]\n", "#let fig = publication-figure\n",
                               setup, count=1, flags=re.MULTILINE | re.DOTALL)
        if count != 1:
            raise ValueError("Prototype figure changed; review shared component")
    setup = adapt_diagrams(setup, 166 / 174 if bound else 1)
    if filename == "46_マッチと一方攻撃.typ":
        # Present the existing order table before the detailed resolution.
        # This frees the dense second page without reducing type or omitting text.
        pattern = r"\n== この例での処理順\n\n#table\([^\n]+\)\n"
        tables = re.findall(pattern, body)
        if len(tables) != 1 or body.count("#pagebreak()") != 1:
            raise ValueError("Prototype structure changed; review pagination")
        body = body.replace(tables[0], "\n")
        body = body.replace("#pagebreak()", tables[0] + "\n#pagebreak()")
    return configuration(title, candidate, font_size, bound) + f'''
#import "parts.typ": at, slot, arrow, tag, blue, red
{setup}
= {body}'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", choices=CANDIDATES,
                        help="Build one candidate; omitted builds all four")
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    helper = (PROTOTYPES / "46_戦闘図解.typ").read_text(encoding="utf-8")
    # Import definitions only; do not import the old page setup or demonstration.
    helper = helper.split("#let blue =", 1)[1].split("#let panel(", 1)[0]
    for candidate, (font_size, bound) in CANDIDATES.items():
        if args.candidate and candidate != args.candidate:
            continue
        folder = WORK / candidate
        folder.mkdir(exist_ok=True)
        parts = adapt_diagrams("#let blue =" + helper, 166 / 174 if bound else 1)
        (folder / "parts.typ").write_text(parts, encoding="utf-8", newline="\n")
        for filename, title, output in (
            ("46_マッチと一方攻撃.typ", "基本ルールブック / マッチと一方攻撃", "clash.typ"),
            ("46_操作ガイド_最初のラウンド.typ", "セッション操作ガイド / 最初のラウンド", "operation.typ"),
        ):
            source = chapter(filename, title, candidate, font_size, bound)
            (folder / output).write_text(source, encoding="utf-8", newline="\n")
        extra = (PROTOTYPES / "46_紙面比較_補足.typ").read_text(encoding="utf-8")
        extra = configuration("基本ルールブック / 探索判定・出血早見", candidate,
                              font_size, bound) + extra
        (folder / "extra.typ").write_text(extra, encoding="utf-8", newline="\n")
        entry = '''#include "clash.typ"
#pagebreak()
#include "operation.typ"
#pagebreak()
#include "extra.typ"
'''
        (folder / "main.typ").write_text(entry, encoding="utf-8", newline="\n")
        subprocess.run(["typst", "compile", "--root", str(ROOT),
                        str(folder / "main.typ"),
                        str(OUTPUT / f"46_layout_{candidate.lower()}.pdf")],
                       check=True, cwd=ROOT)


if __name__ == "__main__":
    main()
