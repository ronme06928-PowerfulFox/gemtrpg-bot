"""旧プリセットJSONを、画面から取り込める移送JSONへ変換する。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from manager.cache_paths import BATTLE_ONLY_PRESETS_CACHE_FILE  # noqa: E402
from manager.preset_transfer import legacy_store_package, package_json  # noqa: E402


def _parse_args():
    parser = argparse.ArgumentParser(
        description="旧battle_only_presets_cache.jsonを移送JSONへ変換します。",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(BATTLE_ONLY_PRESETS_CACHE_FILE),
        help="変換元JSON（省略時は従来のキャッシュファイル）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "preset_transfer_legacy.json",
        help="出力先（省略時はリポジトリ直下のpreset_transfer_legacy.json）",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    if not source.is_file():
        raise SystemExit(f"変換元が見つかりません: {source}")
    if output.exists():
        raise SystemExit(f"出力先が既に存在します。別のパスを指定してください: {output}")
    with source.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    package = legacy_store_package(raw)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(package_json(package) + "\n", encoding="utf-8", newline="\n")
    print(f"移送JSONを出力しました: {output}")
    print(f"対象件数: {len(package['resources'])}")


if __name__ == "__main__":
    main()
