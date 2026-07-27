#!/usr/bin/env python3
"""公開リポジトリへ環境固有値やsecretファイルが混入していないか検査する。"""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
IGNORED_PARTS = {".git", "__pycache__", "bin", "obj"}
FORBIDDEN_TEXT = (
    "ame.ski",
    "gate-keeper",
    "Tevare Valley",
    "PSO2 V3",
)
SECRET_DIRECTORY = ROOT / "secrets"
ALLOWED_SECRET_FILES = {".gitkeep"}


def main() -> int:
    errors: list[str] = []

    if SECRET_DIRECTORY.exists():
        for path in SECRET_DIRECTORY.rglob("*"):
            if path.is_file() and path.name not in ALLOWED_SECRET_FILES:
                errors.append(f"secretファイルが公開ツリーにあります: {path.relative_to(ROOT)}")

    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in IGNORED_PARTS for part in path.parts):
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for forbidden in FORBIDDEN_TEXT:
            if forbidden.casefold() in text.casefold():
                errors.append(
                    f"環境固有値 {forbidden!r}: {path.relative_to(ROOT)}"
                )

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("公開ツリー検査: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
