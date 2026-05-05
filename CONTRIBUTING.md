# Contributing

## Encoding Policy (Mojibake Prevention)

To prevent repeated mojibake issues, this repository uses the following fixed rules:

1. All text files must be `UTF-8` (without BOM).
2. Text files must follow repository line-ending rules from `.gitattributes` / `.editorconfig`.
3. When writing files in Python, always specify `encoding="utf-8"`.
4. When writing files in PowerShell, always use `-Encoding utf8`.
5. Do not re-save unknown external command output directly into source files without encoding confirmation.

## Local Check

Run before commit:

```bash
python scripts/check_text_encoding.py
```

## Pre-commit Hook (Recommended)

```bash
pip install pre-commit
pre-commit install
```

The repository includes `.pre-commit-config.yaml` and will run the encoding guard automatically.

## CI

GitHub Actions also runs the same encoding guard, so violations fail in CI.
