#!/usr/bin/env python3
"""
Repository text encoding guard.

Checks:
1) Text files must be UTF-8 decodable.
2) Text files must not contain UTF-8 BOM.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


TEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".html",
    ".css",
    ".json",
    ".md",
    ".yml",
    ".yaml",
    ".txt",
    ".ini",
    ".cfg",
    ".toml",
    ".sh",
    ".bat",
    ".cmd",
    ".ps1",
    ".ts",
    ".tsx",
    ".jsx",
    ".csv",
    ".tsv",
    ".sql",
    ".url",
}

TEXT_FILENAMES = {
    "Dockerfile",
    "Procfile",
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
}

EXCLUDE_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
}


def _is_text_candidate(path: Path) -> bool:
    if path.name in TEXT_FILENAMES:
        return True
    return path.suffix.lower() in TEXT_EXTENSIONS


def iter_text_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        if not _is_text_candidate(path):
            continue
        yield path


def check_file(path: Path):
    rel = str(path).replace("\\", "/")
    data = path.read_bytes()
    errors = []
    if data.startswith(b"\xef\xbb\xbf"):
        errors.append(f"{rel}: UTF-8 BOM is not allowed")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        errors.append(
            f"{rel}: not UTF-8 decodable "
            f"(line={exc.start}, reason={exc.reason})"
        )
    return errors


def run(root: Path) -> int:
    errors = []
    for path in iter_text_files(root):
        errors.extend(check_file(path))

    if errors:
        print("[encoding-guard] FAILED", file=sys.stderr)
        for row in errors:
            print(f"  - {row}", file=sys.stderr)
        return 1

    print("[encoding-guard] OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check repository text encoding policy.")
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root path (default: current directory)",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()
    return run(root)


if __name__ == "__main__":
    raise SystemExit(main())

