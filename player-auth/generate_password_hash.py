#!/usr/bin/env python3
"""標準入力または対話入力からPBKDF2合い言葉ハッシュを生成する。"""

from __future__ import annotations

import getpass
import sys

from auth_gateway import generate_password_hash


def main() -> None:
    if sys.stdin.isatty():
        passphrase = getpass.getpass("合い言葉: ")
    else:
        passphrase = sys.stdin.read().rstrip("\r\n")

    if not passphrase:
        raise SystemExit("合い言葉を空にはできません")

    print(generate_password_hash(passphrase))


if __name__ == "__main__":
    main()
