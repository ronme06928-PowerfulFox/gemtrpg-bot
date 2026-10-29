"""既存アイコンを表示用サイズへ縮小し、途中ファイルなしで埋め込む。"""
import base64
import io
import json
import sys
from pathlib import Path

from PIL import Image


def main():
    root = Path(__file__).resolve().parents[2]
    assets = {}
    for name in ["bleed", "rupture", "fissure", "thorns", "fear", "chikuryoku", "gyoma"]:
        path = f"/static/images/{name}.png"
        with Image.open(root / path.lstrip("/")) as image:
            image = image.convert("RGBA")
            image.thumbnail((96, 96), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, format="PNG", optimize=True)
        assets[path] = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    sys.stdout.write(json.dumps(assets, ensure_ascii=True))


if __name__ == "__main__":
    main()
