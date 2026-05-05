#!/usr/bin/env python3
"""
Repository mojibake guard.

This catches text that is still valid UTF-8 but visibly corrupted, for example
Japanese text decoded through the wrong console/code page. Manuals are excluded
by default because they are handled by a separate cleanup track.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
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
    "manuals",
}

# Stored as code points so this guard does not introduce literal mojibake into
# the source tree. Escaped strings such as "\u7e67" are intentionally allowed for
# legacy compatibility maps; only the actual corrupted characters are blocked.
MOJIBAKE_MARKER_CODEPOINTS = {
    0xFFFD: "replacement character",
    0x7E67: "common UTF-8/SJIS mojibake marker",
    0x7E3A: "common UTF-8/SJIS mojibake marker",
    0x8B41: "common UTF-8/SJIS mojibake marker",
    0x8B5B: "common UTF-8/SJIS mojibake marker",
    0x7E5D: "common UTF-8/SJIS mojibake marker",
    0x8373: "common UTF-8/SJIS mojibake marker",
    0x8737: "common UTF-8/SJIS mojibake marker",
    0x879F: "common UTF-8/SJIS mojibake marker",
    0x8C41: "common UTF-8/SJIS mojibake marker",
    0x8B28: "common UTF-8/SJIS mojibake marker",
    0x9695: "common UTF-8/SJIS mojibake marker",
    0x9B06: "common UTF-8/SJIS mojibake marker",
    0x9A65: "common UTF-8/SJIS mojibake marker",
    0x83A0: "common UTF-8/SJIS mojibake marker",
    0x8708: "common UTF-8/SJIS mojibake marker",
    0x8B5A: "common UTF-8/SJIS mojibake marker",
    0x90B1: "common UTF-8/SJIS mojibake marker",
    0x86F9: "common UTF-8/SJIS mojibake marker",
    0x87C6: "common UTF-8/SJIS mojibake marker",
    0x8C82: "common UTF-8/SJIS mojibake marker",
    0x9666: "common UTF-8/SJIS mojibake marker",
    0x8811: "common UTF-8/SJIS mojibake marker",
    0x965C: "common UTF-8/SJIS mojibake marker",
    0x9015: "common UTF-8/SJIS mojibake marker",
    0x9021: "common UTF-8/SJIS mojibake marker",
}

MOJIBAKE_MARKERS = {
    chr(codepoint): f"U+{codepoint:04X} {description}"
    for codepoint, description in MOJIBAKE_MARKER_CODEPOINTS.items()
}

QUESTION_PLACEHOLDER_PATTERNS = (
    re.compile(
        r"""
        (?P<context>
            ["']?
            (?:label|name|buff_name|state_name|source|damage_type|username|message|reason)
            ["']?
            \s*:\s*
            ["'][?]{2,}["']
        )
        """,
        re.VERBOSE,
    ),
    re.compile(
        r"""
        (?P<context>
            (?:==|===|!=|!==)
            \s*
            ["'][?]{2,}["']
        )
        """,
        re.VERBOSE,
    ),
)


def _is_text_candidate(path: Path) -> bool:
    if path.name in TEXT_FILENAMES:
        return True
    return path.suffix.lower() in TEXT_EXTENSIONS


def _is_excluded(path: Path, include_manuals: bool) -> bool:
    excluded = EXCLUDE_DIRS if not include_manuals else (EXCLUDE_DIRS - {"manuals"})
    return any(part in excluded for part in path.parts)


def iter_text_files(root: Path, include_manuals: bool = False):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if _is_excluded(path, include_manuals):
            continue
        if not _is_text_candidate(path):
            continue
        yield path


def _safe_line(line: str, max_len: int = 180) -> str:
    escaped = line.encode("unicode_escape").decode("ascii")
    if len(escaped) <= max_len:
        return escaped
    return escaped[: max_len - 3] + "..."


def check_file(path: Path):
    errors = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        rel = str(path).replace("\\", "/")
        return [
            f"{rel}: not UTF-8 decodable "
            f"(offset={exc.start}, reason={exc.reason})"
        ]

    rel = str(path).replace("\\", "/")
    for line_no, line in enumerate(text.splitlines(), 1):
        for marker, description in MOJIBAKE_MARKERS.items():
            if marker in line:
                errors.append(
                    f"{rel}:{line_no}: mojibake marker {description}: "
                    f"{_safe_line(line)}"
                )
        for pattern in QUESTION_PLACEHOLDER_PATTERNS:
            match = pattern.search(line)
            if match:
                errors.append(
                    f"{rel}:{line_no}: suspicious question-mark placeholder "
                    f"{match.group('context')!r}: {_safe_line(line)}"
                )
    return errors


def run(root: Path, include_manuals: bool = False) -> int:
    errors = []
    for path in iter_text_files(root, include_manuals=include_manuals):
        errors.extend(check_file(path))

    if errors:
        print("[mojibake-guard] FAILED", file=sys.stderr)
        for row in errors:
            print(f"  - {row}", file=sys.stderr)
        return 1

    print("[mojibake-guard] OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check repository mojibake markers.")
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root path (default: current directory)",
    )
    parser.add_argument(
        "--include-manuals",
        action="store_true",
        help="Also scan manuals/ (disabled by default)",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()
    return run(root, include_manuals=args.include_manuals)


if __name__ == "__main__":
    raise SystemExit(main())
