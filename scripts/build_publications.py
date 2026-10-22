"""基本ルールブックとセッション操作ガイドを組版し、配布用の名前を付けたPDFも作る。

使い方（リポジトリ直下から）:
    python scripts/build_publications.py

- 各冊子の main.pdf（Git管理）を作り直す。
- output/release/ に「ジェムリアTRPG_<書名>_<版>.pdf」をコピーする。Discordにはこのファイルを置く。
  書名と版は typst_manual/publication_info.typ から読む。output/release/ はGit管理しない。
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYPST_ROOT = ROOT / "typst_manual"
FONT_DIR = TYPST_ROOT / "_local" / "fonts"
RELEASE_DIR = ROOT / "output" / "release"
BOOKS = {
    "book": TYPST_ROOT / "全体マニュアル",
    "guide": TYPST_ROOT / "操作ガイド",
}


def read_publications():
    """publication_info.typ から、冊子ごとの書名と版を読む。"""
    source = (TYPST_ROOT / "publication_info.typ").read_text(encoding="utf-8")
    info = {}
    for key in BOOKS:
        match = re.search(rf'{key}: \(\s*title: "([^"]+)",\s*edition: "([^"]+)"', source)
        if not match:
            raise SystemExit(f"publication_info.typ に {key} の書名・版が見つかりません")
        info[key] = {"title": match.group(1), "edition": match.group(2)}
    return info


def compile_book(folder):
    command = ["typst", "compile", "--root", str(TYPST_ROOT)]
    if FONT_DIR.is_dir():
        # README の組版環境と同じく、システムの代替フォントを使わない
        command += ["--ignore-system-fonts", "--font-path", str(FONT_DIR)]
    command += [str(folder / "main.typ"), str(folder / "main.pdf")]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0 or result.stderr.strip():
        sys.stderr.write(result.stderr)
        raise SystemExit(f"組版に失敗しました: {folder / 'main.typ'}")


def main():
    publications = read_publications()
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    for key, folder in BOOKS.items():
        compile_book(folder)
        info = publications[key]
        target = RELEASE_DIR / f"ジェムリアTRPG_{info['title']}_{info['edition']}.pdf"
        shutil.copyfile(folder / "main.pdf", target)
        print(target.relative_to(ROOT))


if __name__ == "__main__":
    main()
