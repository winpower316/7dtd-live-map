#!/usr/bin/env python3
"""公開設定のサンプル、Compose、実行時テンプレートの対応を検査する。"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_NAME_PATTERN = re.compile(r"^([A-Z][A-Z0-9_]*)=", re.MULTILINE)
PLACEHOLDER_PATTERN = re.compile(r"\$\{([A-Z][A-Z0-9_]*)")
COMPOSE_ENV_PATTERN = re.compile(r"^\s+- ([A-Z][A-Z0-9_]*)=", re.MULTILINE)
ENTRYPOINT_DEFAULT_PATTERN = re.compile(
    r'^export ([A-Z][A-Z0-9_]*)="\$\{\1:-',
    re.MULTILINE,
)
CONFIG_KEY_PATTERN = re.compile(r"^\s{2}([a-z][A-Za-z0-9]*):", re.MULTILINE)


def names(path: str, pattern: re.Pattern[str]) -> set[str]:
    return set(pattern.findall((ROOT / path).read_text(encoding="utf-8")))


def main() -> int:
    errors: list[str] = []
    env_names = names(".env.example", ENV_NAME_PATTERN)
    compose_placeholders = names("docker-compose.yml", PLACEHOLDER_PATTERN)
    compose_environment = names("docker-compose.yml", COMPOSE_ENV_PATTERN)
    template_placeholders = set()
    for template in ("nginx.conf", "config/frontend-config.js.template"):
        template_placeholders.update(names(template, PLACEHOLDER_PATTERN))
    entrypoint_defaults = names(
        "docker-entrypoint.sh",
        ENTRYPOINT_DEFAULT_PATTERN,
    )

    missing_env_examples = compose_placeholders - env_names
    if missing_env_examples:
        errors.append(
            ".env.exampleにないCompose変数: "
            + ", ".join(sorted(missing_env_examples))
        )

    missing_compose_environment = template_placeholders - compose_environment
    if missing_compose_environment:
        errors.append(
            "コンテナへ渡されないテンプレート変数: "
            + ", ".join(sorted(missing_compose_environment))
        )

    required_without_defaults = (
        template_placeholders
        - entrypoint_defaults
        - {"SEVEN_DAYS_HOST"}
    )
    if required_without_defaults:
        errors.append(
            "entrypoint既定値がないテンプレート変数: "
            + ", ".join(sorted(required_without_defaults))
        )

    static_config_keys = names("site/config.js", CONFIG_KEY_PATTERN)
    template_config_keys = names(
        "config/frontend-config.js.template",
        CONFIG_KEY_PATTERN,
    )
    if static_config_keys != template_config_keys:
        errors.append(
            "site/config.jsと実行時テンプレートのキーが一致しません"
        )

    if errors:
        print("\n".join(errors))
        return 1
    print("設定サーフェス検査: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
