"""2冊の原稿から、常用漢字表にない漢字を含む言葉を挙げる（計画51のルビの候補探し）。

使い方（リポジトリ直下から）:
    python scripts/find_ruby_candidates.py

- 常用漢字の一覧は scripts/data/joyo_kanji.txt（2136字。出典：Wikipedia「常用漢字一覧」、
  文化庁「常用漢字表」平成22年内閣告示第2号に準拠。2026-10-23取得）。
- typst_manual/readings.typ に読みが登録済みの言葉は「登録済み」と表示する。
- 常用漢字だけでできていても読みにくい言葉（「重絡」など）は拾えないので、人の判断で足す。
"""
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = [
    *sorted((ROOT / "typst_manual" / "全体マニュアル").glob("[09]*.typ")),
    *sorted((ROOT / "typst_manual" / "操作ガイド").glob("[09]*.typ")),
]
KANJI_RUN = re.compile(r"[㐀-鿿豈-﫿々〆ヶ]+")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    joyo = set((ROOT / "scripts" / "data" / "joyo_kanji.txt").read_text(encoding="utf-8").strip())
    readings_file = ROOT / "typst_manual" / "readings.typ"
    registered = set(re.findall(r'"([^"]+)":', readings_file.read_text(encoding="utf-8"))) if readings_file.exists() else set()
    counts = Counter()
    for path in SOURCES:
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"//.*", "", text)  # コメントは本文に出ないので除く
        for run in KANJI_RUN.findall(text):
            if any(ch not in joyo for ch in run if ch not in "々〆ヶ"):
                counts[run] += 1
    for word, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        rare = "".join(ch for ch in word if ch not in joyo and ch not in "々〆ヶ")
        mark = "登録済み" if word in registered else ""
        print(f"{word}\t{n}\t常用外:{rare}\t{mark}")


if __name__ == "__main__":
    main()
